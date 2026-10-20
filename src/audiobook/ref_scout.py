"""Scout a long live recording for voice-reference candidates.

The clone copies the reference's delivery — tempo included (validated: a
faster reference gave faster, sloppier speech; ref_lively). So a good candidate
is a whole-phrase 15-25 s stretch whose speaking rate is close to the approved
calm reference, with as much melodic movement (pitch spread) as possible.

Steps: decode → whisper segments (phrase bounds + draft text) → windows of
consecutive segments → rate (chars/s, CER-normalized text) and pitch spread
(p10–p90 of F0 in semitones) → keep windows within the rate band, rank by
spread, pick K non-overlapping → cut to ref/candidates/scout_MMSS.wav with a
.draft.txt next to it. Drafts are NEVER used for latents: a human listens,
fixes the text and renames it to .txt (then `ref-compare`).

Also writes out/ref_scout/report.tsv (all windows) and listen_all.mp3
(the picks back to back, 1.5 s apart) for a quick audition.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from audiobook import paths

_SR = 16_000
MIN_S, MAX_S = 15.0, 25.0


@dataclass
class Seg:
    start: float
    end: float
    text: str


@dataclass
class Window:
    start: float
    end: float
    text: str
    rate: float = 0.0      # normalized chars per second of window
    spread: float = 0.0    # p10–p90 pitch, semitones
    prev_end: float = 0.0          # end of the segment before (cut may not go earlier)
    next_start: float = float("inf")  # start of the segment after

    @property
    def dur(self) -> float:
        return self.end - self.start


# ── pure logic (layer-1 tested) ───────────────────────────────────────────────

def char_rate(text: str, seconds: float) -> float:
    from audiobook.qc import normalize_for_cer
    n = len(normalize_for_cer(text).replace(" ", ""))
    return n / seconds if seconds > 0 else 0.0


def windows(segs: list[Seg], min_s: float = MIN_S, max_s: float = MAX_S) -> list[Window]:
    """Every run of consecutive segments lasting min_s..max_s. Boundaries sit on
    segment edges, so each window starts and ends on a whole phrase."""
    out: list[Window] = []
    for i in range(len(segs)):
        for j in range(i, len(segs)):
            dur = segs[j].end - segs[i].start
            if dur > max_s:
                break
            if dur >= min_s:
                text = " ".join(s.text.strip() for s in segs[i:j + 1]).strip()
                out.append(Window(
                    segs[i].start, segs[j].end, text,
                    prev_end=segs[i - 1].end if i > 0 else 0.0,
                    next_start=segs[j + 1].start if j + 1 < len(segs) else float("inf")))
    return out


def semitone_spread(f0: np.ndarray) -> float:
    """p10–p90 of voiced F0 in semitones around its median; 0 if too few frames."""
    f = f0[np.isfinite(f0) & (f0 > 0)]
    if len(f) < 20:
        return 0.0
    st = 12 * np.log2(f / np.median(f))
    return float(np.percentile(st, 90) - np.percentile(st, 10))


def pick(cands: list[Window], target_rate: float, tol: float, k: int) -> list[Window]:
    """Windows with rate within ±tol of target, highest spread first, no overlap."""
    ok = [w for w in cands if abs(w.rate - target_rate) <= tol * target_rate]
    ok.sort(key=lambda w: w.spread, reverse=True)
    chosen: list[Window] = []
    for w in ok:
        if all(w.end <= c.start or w.start >= c.end for c in chosen):
            chosen.append(w)
        if len(chosen) == k:
            break
    return sorted(chosen, key=lambda w: w.start)


def snap_to_silence(y: np.ndarray, sr: int, t: float, side: str,
                    reach: float = 0.8, inside: float = 0.15) -> tuple[float, float]:
    """Move a cut point to the quietest 20 ms spot nearby. Whisper segment edges
    are not silence-aligned (adjacent segments share an edge, gap 0.00 s) and
    clipped the onset of scout_2526's first word. For a start we search
    [t-reach, t+inside], for an end [t-inside, t+reach]: the quietest spot there
    is the pause between words, so the cut never splits a word.
    Returns (time, depth_db) — depth of that spot vs the median frame level;
    around -20 dB or lower is a real pause, near 0 dB means none was found."""
    lo, hi = (t - reach, t + inside) if side == "start" else (t - inside, t + reach)
    a, b = max(0, int(lo * sr)), min(len(y), int(hi * sr))
    frame, hop = int(0.02 * sr), int(0.005 * sr)
    seg = y[a:b]
    if len(seg) < frame:
        return t, 0.0
    n = 1 + (len(seg) - frame) // hop
    rms = np.array([np.sqrt(np.mean(seg[i * hop:i * hop + frame] ** 2)) for i in range(n)])
    i = int(np.argmin(rms))
    tc = (a + i * hop + frame // 2) / sr
    ref = np.median(rms[rms > 0]) if np.any(rms > 0) else 1.0
    depth = 20 * np.log10(max(rms[i], 1e-9) / ref)
    return tc, float(depth)


def mmss(t: float) -> str:
    m, s = divmod(int(t), 60)
    return f"{m:02d}{s:02d}"


# ── audio / models ────────────────────────────────────────────────────────────

def _ff() -> str:
    ff = paths.ffmpeg()
    if ff is None:
        raise SystemExit("ffmpeg не найден (bin/ или PATH)")
    return str(ff)


def _decode(src: Path, out: Path, sr: int) -> None:
    subprocess.run([_ff(), "-hide_banner", "-y", "-i", str(src), "-ac", "1",
                    "-ar", str(sr), str(out)], capture_output=True, check=True)


def _segments(wav: Path) -> list[Seg]:
    from audiobook.qc import load_whisper
    wm = load_whisper()
    segs, _info = wm.transcribe(str(wav), language="ru", beam_size=5, vad_filter=True)
    return [Seg(s.start, s.end, s.text) for s in segs]


def _f0(y: np.ndarray) -> np.ndarray:
    # librosa comes with qwen-tts (transitive, already in uv.lock) — no new dep.
    import librosa
    f0 = librosa.yin(y, fmin=65, fmax=320, sr=_SR, frame_length=1024)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=256)[0]
    n = min(len(f0), len(rms))
    f0, rms = f0[:n], rms[:n]
    f0[rms < 0.3 * np.median(rms[rms > 0])] = np.nan  # drop pauses/breaths
    return f0


def run(config: dict, src: str, k: int = 6, tol: float = 0.10) -> int:
    import soundfile as sf
    from audiobook.qc import normalize_for_cer  # noqa: F401  (fail early if broken)

    src_p = Path(src)
    if not src_p.is_absolute():
        src_p = paths.ROOT / src_p
    if not src_p.exists():
        raise SystemExit(f"нет записи: {src_p}")

    ref = paths.ROOT / config["reference"]["path"]
    ref_txt = paths.ROOT / config["reference"]["ref_text_path"]
    info = sf.info(str(ref))
    target = char_rate(ref_txt.read_text(encoding="utf-8"), info.duration)

    work = paths.OUT / "ref_scout"
    work.mkdir(parents=True, exist_ok=True)
    wav16 = work / "source_16k.wav"
    wav24 = work / "source_24k.wav"
    if not wav16.exists():
        _decode(src_p, wav16, _SR)
    if not wav24.exists():
        _decode(src_p, wav24, 24_000)

    segs = _segments(wav16)
    y, _ = sf.read(str(wav16), dtype="float32")
    cands = windows(segs)
    for w in cands:
        w.rate = char_rate(w.text, w.dur)
        a, b = int(w.start * _SR), int(w.end * _SR)
        w.spread = semitone_spread(_f0(y[a:b]))

    with open(work / "report.tsv", "w", encoding="utf-8") as f:
        f.write("start\tend\tdur\trate\tspread_st\ttext\n")
        for w in cands:
            f.write(f"{w.start:.2f}\t{w.end:.2f}\t{w.dur:.1f}\t{w.rate:.2f}\t"
                    f"{w.spread:.2f}\t{w.text}\n")

    chosen = pick(cands, target, tol, k)
    if not chosen:
        raise SystemExit(f"нет окон в полосе темпа {target:.1f}±{tol:.0%} симв/с — "
                         f"см. {work / 'report.tsv'}, можно расширить --tol")

    cdir = paths.ROOT / "ref" / "candidates"
    cdir.mkdir(parents=True, exist_ok=True)
    gap = np.zeros(int(1.5 * 24_000), dtype=np.float32)
    full, _ = sf.read(str(wav24), dtype="float32")
    listen: list[np.ndarray] = []
    print(f"цель темпа (текущий референс): {target:.2f} симв/с")
    for w in chosen:
        name = f"scout_{mmss(w.start)}"
        a, da = snap_to_silence(full, 24_000, w.start, "start")
        b, db = snap_to_silence(full, 24_000, w.end, "end")
        clip = full[int(a * 24_000):int(b * 24_000)]
        sf.write(str(cdir / f"{name}.wav"), clip, 24_000, subtype="PCM_16")
        (cdir / f"{name}.draft.txt").write_text(w.text + "\n", encoding="utf-8")
        listen += [clip, gap]
        print(f"{name}  {mmss(w.start)[:2]}:{mmss(w.start)[2:]}  {w.dur:4.1f} с  "
              f"темп {w.rate:.2f}  мелодика {w.spread:.1f} пт  "
              f"паузы на срезе {da:.0f}/{db:.0f} дБ")
    raw = work / "listen_all.wav"
    sf.write(str(raw), np.concatenate(listen), 24_000, subtype="PCM_16")
    subprocess.run([_ff(), "-hide_banner", "-y", "-i", str(raw), "-c:a", "libmp3lame",
                    "-b:a", "128k", str(work / "listen_all.mp3")],
                   capture_output=True, check=True)
    raw.unlink()
    print(f"прослушка: {work / 'listen_all.mp3'}  |  кандидаты: {cdir}")
    return 0
