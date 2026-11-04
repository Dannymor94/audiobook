"""Deliverable book: export finished chapters as a store-ready set.

    ./run.sh export [--format mp3|m4b] [--allow-missing]
        mp3 → out/export/mp3/NN_<ascii title>.mp3 + playlist.m3u8, out/export/contents.tsv
        m4b → out/export/<ascii book title>.m4b (AAC, chapters, tags, cover)
    ./run.sh export-sample --section S [--start SEC] [--length SEC]
        → out/export/sample.mp3 (≤ 5 min store excerpt, re-encoded, faded)
    ./run.sh credits
        → out/credits/{opening,closing}.mp3 from config ``credits`` (heavy: model)

Sources are the mastered chapter files out/sections/<S>/section.mp3 of every
book section in order (status.book_sections() minus render.skip_sections),
plus the credits tracks first/last when their text is set. Nothing here edits
a chapter: mp3 export copies the files byte-for-byte (tags untouched), m4b
decodes and re-encodes into one container.

A previous export (or credits audio whose text changed) is never deleted: it
is moved aside to out/export/_old/<stamp>/ (out/credits/_old_<hash12>/).
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from audiobook import paths

TRACK_LIMIT_MIN = 120       # store limit for one file of a multi-file audiobook
SAMPLE_MAX_S = 300          # store limit for a retail sample
SAMPLE_FADE_IN_S = 0.5
SAMPLE_FADE_OUT_S = 1.5
CREDITS_PAUSE_MS = 350
CREDITS_MUSIC_FADE_S = 3.0
CREDIT_NAMES = ("opening", "closing")
CREDIT_TITLES = {"opening": "Вступление", "closing": "Концовка"}
NAME_MAX = 60


# ── tool lookup ───────────────────────────────────────────────────────────────

def ffprobe() -> Path | None:
    """ffprobe next to the ffmpeg paths.ffmpeg() picks (bin/ first), else PATH."""
    exe = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
    ff = paths.ffmpeg()
    if ff is not None and (ff.parent / exe).exists():
        return ff.parent / exe
    local = paths.BIN / exe
    if local.exists():
        return local
    found = shutil.which(exe)
    return Path(found) if found else None


def _ff() -> str:
    ff = paths.ffmpeg()
    if ff is None:
        raise SystemExit("ffmpeg не найден (bin/ или PATH)")
    return str(ff)


def _fp() -> str:
    fp = ffprobe()
    if fp is None:
        raise SystemExit("ffprobe не найден (рядом с ffmpeg, bin/ или PATH)")
    return str(fp)


def parse_float(stdout: str, what: str) -> float:
    for ln in stdout.splitlines():
        ln = ln.strip()
        if ln and ln != "N/A":
            return float(ln)
    raise SystemExit(f"ffprobe не вернул {what}")


def probe_duration(path: Path) -> float:
    """Container duration in seconds (mp3 with a Xing/LAME header: exact)."""
    p = subprocess.run([_fp(), "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                       capture_output=True, text=True, check=True)
    return parse_float(p.stdout, f"длительность {path.name}")


def probe_channels(path: Path) -> int:
    p = subprocess.run([_fp(), "-v", "error", "-select_streams", "a:0",
                        "-show_entries", "stream=channels",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                       capture_output=True, text=True, check=True)
    return int(parse_float(p.stdout, f"число каналов {path.name}"))


# ── naming ────────────────────────────────────────────────────────────────────

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def translit(text: str) -> str:
    """Cyrillic → Latin (simplified passport style). Case kept on the first
    letter of a multi-letter result ("Щ" → "Shch")."""
    out = []
    for ch in text:
        low = ch.lower()
        if low in _TRANSLIT:
            t = _TRANSLIT[low]
            out.append(t.capitalize() if ch != low else t)
        else:
            out.append(ch)
    return "".join(out)


def ascii_name(title: str, fallback: str = "track", max_len: int = NAME_MAX) -> str:
    """File-system-safe ASCII stem: translit, strip accents, every run of other
    characters → "_", trimmed to max_len."""
    t = unicodedata.normalize("NFKD", translit(title))
    t = t.encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_")
    t = t[:max_len].rstrip("_")
    return t or fallback


def track_file_names(titles: list[str]) -> list[str]:
    """NN_<ascii title>.mp3, two-digit numbering (three past 99 tracks)."""
    width = max(2, len(str(len(titles))))
    return [f"{i:0{width}d}_{ascii_name(t)}.mp3" for i, t in enumerate(titles, 1)]


def hms(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"


# ── track plan ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Track:
    src: Path
    title: str
    kind: str       # "section" | "credits"
    name: str       # section name or credit name


def book_order(config: dict) -> list[str]:
    from audiobook.status import book_sections
    skip = set((config.get("render") or {}).get("skip_sections") or [])
    return [s for s in book_sections() if s not in skip]


def section_heading(section: str) -> str:
    jf = paths.TEXT / "blocks" / f"{section}.blocks.json"
    if not jf.exists():
        return section
    with open(jf, encoding="utf-8") as f:
        return json.load(f).get("heading") or section


def section_problem(sec_dir: Path) -> str | None:
    """Why this chapter's section.mp3 can't ship, or None if it is current."""
    mp3 = sec_dir / "section.mp3"
    manifest = sec_dir / "manifest.jsonl"
    if not manifest.exists():
        return "не нарезано (нет manifest.jsonl)"
    if not mp3.exists():
        return "нет section.mp3 (assemble + master)"
    if mp3.stat().st_mtime < manifest.stat().st_mtime:
        return "section.mp3 старше manifest.jsonl (пересобрать assemble + master)"
    return None


def collect_tracks(config: dict) -> tuple[list[Track], list[str]]:
    """(tracks in play order, problems). A problem track is left out of the list."""
    tracks: list[Track] = []
    problems: list[str] = []
    credit = {}
    for name in CREDIT_NAMES:
        state, mp3 = credit_state(config, name)
        if state == "empty":
            continue
        if state == "ok":
            credit[name] = Track(mp3, CREDIT_TITLES[name], "credits", name)
        else:
            why = "нет mp3" if state == "missing" else "текст/голос/музыка изменились"
            problems.append(f"{CREDIT_TITLES[name].lower()} (credits.{name}): {why} — ./run.sh credits")
    if "opening" in credit:
        tracks.append(credit["opening"])
    for s in book_order(config):
        sec = paths.OUT / "sections" / s
        why = section_problem(sec)
        if why:
            problems.append(f"{s}: {why}")
        else:
            tracks.append(Track(sec / "section.mp3", section_heading(s), "section", s))
    if "closing" in credit:
        tracks.append(credit["closing"])
    return tracks, problems


def preflight(config: dict, allow_missing: bool) -> list[Track]:
    tracks, problems = collect_tracks(config)
    if problems and not allow_missing:
        raise SystemExit("export: книга не готова, ничего не собрано:\n  "
                         + "\n  ".join(problems)
                         + "\nисправь или запусти с --allow-missing (книга будет неполной)")
    if problems:
        bar = "!" * 70
        print(f"{bar}\nВНИМАНИЕ: --allow-missing, книга НЕПОЛНАЯ, пропущено {len(problems)}:\n  "
              + "\n  ".join(problems) + f"\n{bar}")
    if not any(t.kind == "section" for t in tracks):
        raise SystemExit("export: нет ни одной готовой главы")
    return tracks


def long_tracks(tracks: list[Track], durations: list[float],
                limit_min: float = TRACK_LIMIT_MIN) -> list[str]:
    return [f"{t.src.parent.name if t.kind == 'section' else t.name}: {hms(d)}"
            for t, d in zip(tracks, durations) if d > limit_min * 60]


# ── retire, never delete ──────────────────────────────────────────────────────

def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def retire(p: Path, old_dir: Path) -> Path | None:
    """Move ``p`` (file or folder) into ``old_dir`` keeping its name. Audio is
    never deleted; the user cleans _old/ by hand."""
    if not p.exists():
        return None
    old_dir.mkdir(parents=True, exist_ok=True)
    dst = old_dir / p.name
    n = 1
    while dst.exists():
        dst = old_dir / f"{p.stem}.{n}{p.suffix}"
        n += 1
    shutil.move(str(p), str(dst))
    return dst


def _write_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    tmp.replace(path)


# ── text builders (pure) ──────────────────────────────────────────────────────

def m3u8_text(files: list[str], titles: list[str], durations: list[float],
              artist: str = "") -> str:
    lines = ["#EXTM3U"]
    for fn, t, d in zip(files, titles, durations):
        label = f"{artist} - {t}" if artist else t
        lines += [f"#EXTINF:{int(round(d))},{label}", fn]
    return "\n".join(lines) + "\n"


def contents_tsv(files: list[str], titles: list[str], durations: list[float]) -> str:
    lines = ["track\tfile\ttitle\tduration"]
    for i, (fn, t, d) in enumerate(zip(files, titles, durations), 1):
        lines.append(f"{i}\t{fn}\t{t.replace(chr(9), ' ')}\t{hms(d)}")
    return "\n".join(lines) + "\n"


def ffmeta_escape(s: str) -> str:
    """FFMETADATA1: '=', ';', '#', '\\' and newline are escaped with a backslash."""
    out = []
    for ch in str(s):
        out.append("\\" + ch if ch in "=;#\\\n" else ch)
    return "".join(out)


def chapter_times(durations_s: list[float]) -> list[tuple[int, int]]:
    """(start_ms, end_ms) per chapter, rounded on the running sum so rounding
    never accumulates drift over a long book."""
    out = []
    cum = 0.0
    for d in durations_s:
        start = int(round(cum * 1000))
        cum += d
        out.append((start, int(round(cum * 1000))))
    return out


def ffmetadata_text(tags: dict[str, str], chapters: list[tuple[str, int, int]]) -> str:
    lines = [";FFMETADATA1"]
    lines += [f"{ffmeta_escape(k)}={ffmeta_escape(v)}" for k, v in tags.items() if v]
    for title, start, end in chapters:
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={start}", f"END={end}",
                  f"title={ffmeta_escape(title)}"]
    return "\n".join(lines) + "\n"


def concat_list_text(files: list[Path]) -> str:
    """ffconcat list; single quotes inside a path are closed, escaped, reopened."""
    lines = ["ffconcat version 1.0"]
    for p in files:
        q = p.resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{q}'")
    return "\n".join(lines) + "\n"


def global_tags(config: dict) -> dict[str, str]:
    b = config.get("book") or {}
    tags = {
        "title": str(b.get("title") or ""),
        "album": str(b.get("title") or ""),
        "artist": str(b.get("author") or ""),
        "album_artist": str(b.get("author") or ""),
        "genre": "Audiobook",
        "comment": f"Читает: {b['narrator']}" if b.get("narrator") else "",
    }
    return {k: v for k, v in tags.items() if v}


def aac_bitrate(channels: int) -> str:
    return "64k" if channels <= 1 else "96k"


def m4b_args(ff: str, concat_list: Path, meta: Path, out: Path, bitrate: str,
             channels: int, sr: int = 44100, cover: Path | None = None) -> list[str]:
    cmd = [ff, "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
           "-i", str(meta)]
    if cover:
        cmd += ["-i", str(cover)]
    cmd += ["-map", "0:a"]
    if cover:
        cmd += ["-map", "2:v", "-c:v", "copy", "-disposition:v:0", "attached_pic"]
    cmd += ["-map_metadata", "1", "-map_chapters", "1",
            "-c:a", "aac", "-b:a", bitrate, "-ac", str(channels), "-ar", str(sr),
            "-movflags", "+faststart", "-f", "mp4", str(out)]
    return cmd


def fade_filter(length_s: float, fade_in: float = SAMPLE_FADE_IN_S,
                fade_out: float = SAMPLE_FADE_OUT_S) -> str:
    st = max(0.0, length_s - fade_out)
    return f"afade=t=in:st=0:d={fade_in:g},afade=t=out:st={st:g}:d={fade_out:g}"


def sample_args(ff: str, src: Path, out: Path, start_s: float, length_s: float, sr: int,
                tags: dict[str, str], cover: Path | None = None) -> list[str]:
    cmd = [ff, "-hide_banner", "-y", "-ss", f"{start_s:g}", "-t", f"{length_s:g}",
           "-i", str(src)]
    if cover:
        cmd += ["-i", str(cover), "-map", "0:a", "-map", "1:v", "-c:v", "copy",
                "-metadata:s:v", "title=Album cover", "-metadata:s:v", "comment=Cover (front)"]
    else:
        cmd += ["-map", "0:a"]
    cmd += ["-map_metadata", "-1", "-af", fade_filter(length_s), "-ar", str(sr),
            "-c:a", "libmp3lame", "-b:a", "192k", "-id3v2_version", "3"]
    for k, v in tags.items():
        cmd += ["-metadata", f"{k}={v}"]
    return cmd + ["-f", "mp3", str(out)]


def music_bed_args(ff: str, voice: Path, music: Path, out: Path, music_db: float,
                   voice_dur_s: float, sr: int = 24000,
                   fade_s: float = CREDITS_MUSIC_FADE_S) -> list[str]:
    """Voice + looped/trimmed music at ``music_db`` under it, music faded out at
    the end; length = the voice. amix scales both inputs alike, so the ratio
    holds (loudnorm in master sets the final level); ``apad`` keeps the music
    input alive to the voice's last sample, otherwise amix drops it a few ms
    early and the voice jumps +6 dB at the very end. FLOAT wav out."""
    fade = min(fade_s, voice_dur_s / 2)
    st = max(0.0, voice_dur_s - fade)
    fc = (f"[1:a]aresample={sr},aformat=channel_layouts=mono,volume={music_db:g}dB,"
          f"atrim=0:{voice_dur_s:.3f},afade=t=out:st={st:.3f}:d={fade:.3f},apad[m];"
          f"[0:a]aresample={sr},aformat=channel_layouts=mono[v];"
          f"[v][m]amix=inputs=2:duration=first:dropout_transition=0[out]")
    return [ff, "-hide_banner", "-y", "-i", str(voice), "-stream_loop", "-1", "-i", str(music),
            "-filter_complex", fc, "-map", "[out]", "-c:a", "pcm_f32le", "-f", "wav", str(out)]


# ── export ────────────────────────────────────────────────────────────────────

def export(config: dict, fmt: str = "mp3", out_dir: Path | None = None,
           allow_missing: bool = False,
           duration_fn: Callable[[Path], float] | None = None) -> Path:
    if fmt not in ("mp3", "m4b"):
        raise SystemExit(f"export: формат {fmt!r} не поддерживается (mp3 | m4b)")
    out_dir = out_dir or paths.OUT / "export"
    tracks = preflight(config, allow_missing)
    dur = duration_fn or probe_duration
    durations = [dur(t.src) for t in tracks]
    for line in long_tracks(tracks, durations):
        print(f"ВНИМАНИЕ: файл длиннее {TRACK_LIMIT_MIN} мин (лимит магазинов): {line}")
    out_dir.mkdir(parents=True, exist_ok=True)
    if fmt == "mp3":
        return _export_mp3(config, tracks, durations, out_dir)
    return _export_m4b(config, tracks, durations, out_dir)


def _export_mp3(config: dict, tracks: list[Track], durations: list[float],
                out_dir: Path) -> Path:
    titles = [t.title for t in tracks]
    files = track_file_names(titles)
    final = out_dir / "mp3"
    part = out_dir / "mp3.part"
    old = out_dir / "_old" / _stamp()
    retire(part, old)               # leftover of an interrupted export
    part.mkdir()
    for t, fn in zip(tracks, files):
        shutil.copy2(t.src, part / fn)     # copy, never move: section.mp3 stays
    artist = str((config.get("book") or {}).get("author") or "")
    with open(part / "playlist.m3u8", "w", encoding="utf-8", newline="\n") as f:
        f.write(m3u8_text(files, titles, durations, artist))
    moved = retire(final, old)
    part.replace(final)
    _write_text(out_dir / "contents.tsv", contents_tsv(files, titles, durations))
    print(f"export mp3: {len(files)} файлов, {hms(sum(durations))} → {final}")
    if moved:
        print(f"  прошлый экспорт перенесён: {moved}")
    return final


def _export_m4b(config: dict, tracks: list[Track], durations: list[float],
                out_dir: Path, bitrate: str | None = None) -> Path:
    from audiobook.master import cover_path
    ff = _ff()
    titles = [t.title for t in tracks]
    chapters = [(ti, s, e) for ti, (s, e) in zip(titles, chapter_times(durations))]
    book = str((config.get("book") or {}).get("title") or "")
    out = out_dir / f"{ascii_name(book, 'audiobook')}.m4b"
    lst = out_dir / "m4b.concat.part.txt"
    meta = out_dir / "m4b.ffmeta.part.txt"
    _write_text(lst, concat_list_text([t.src for t in tracks]))
    _write_text(meta, ffmetadata_text(global_tags(config), chapters))
    channels = probe_channels(tracks[0].src)
    sr = int((config.get("master") or {}).get("sample_rate") or 44100)
    tmp = out.with_name(out.name + ".part")
    cmd = m4b_args(ff, lst, meta, tmp, bitrate or aac_bitrate(channels), channels, sr,
                   cover_path(config))
    print(f"export m4b: {len(tracks)} глав, {hms(sum(durations))}, AAC "
          f"{bitrate or aac_bitrate(channels)} {'моно' if channels == 1 else f'{channels} кан.'} …")
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"export m4b: ffmpeg упал:\n{p.stderr[-1500:]}")
    moved = retire(out, out_dir / "_old" / _stamp())
    tmp.replace(out)
    lst.unlink()            # text lists, not audio
    meta.unlink()
    _write_text(out_dir / "contents.tsv", contents_tsv([out.name] * len(tracks), titles, durations))
    print(f"  → {out}")
    if moved:
        print(f"  прошлый m4b перенесён: {moved}")
    return out


# ── sample ────────────────────────────────────────────────────────────────────

def sample_window(start_s: float, length_s: float, total_s: float) -> tuple[float, float]:
    """Validated (start, length) clipped to the chapter; refuses > store limit."""
    if length_s > SAMPLE_MAX_S:
        raise SystemExit(f"export-sample: длина {length_s:g} с больше лимита {SAMPLE_MAX_S} с")
    if length_s <= SAMPLE_FADE_IN_S + SAMPLE_FADE_OUT_S or start_s < 0:
        raise SystemExit("export-sample: нужны --start ≥ 0 и --length > 2 с")
    if start_s >= total_s:
        raise SystemExit(f"export-sample: --start {start_s:g} с за концом главы ({hms(total_s)})")
    length = min(length_s, total_s - start_s)
    if length <= SAMPLE_FADE_IN_S + SAMPLE_FADE_OUT_S:
        raise SystemExit("export-sample: от --start до конца главы меньше 2 с")
    return start_s, length


def sample_tags(config: dict, section: str) -> dict[str, str]:
    from audiobook.master import book_tags
    tags = {k: v for k, v in book_tags(config, section).items() if k != "track"}
    book = str((config.get("book") or {}).get("title") or "")
    tags["title"] = f"{book} — отрывок" if book else "отрывок"
    return tags


def sample(config: dict, section: str, start_s: float = 0, length_s: float = SAMPLE_MAX_S,
           out_dir: Path | None = None) -> Path:
    from audiobook.master import cover_path
    if length_s > SAMPLE_MAX_S:     # refuse before touching any file
        raise SystemExit(f"export-sample: длина {length_s:g} с больше лимита {SAMPLE_MAX_S} с")
    src = paths.OUT / "sections" / section / "section.mp3"
    if not src.exists():
        raise SystemExit(f"export-sample: нет {src}")
    start, length = sample_window(start_s, length_s, probe_duration(src))
    out_dir = out_dir or paths.OUT / "export"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "sample.mp3"
    tmp = out.with_name(out.name + ".part")
    sr = int((config.get("master") or {}).get("sample_rate") or 44100)
    subprocess.run(sample_args(_ff(), src, tmp, start, length, sr,
                               sample_tags(config, section), cover_path(config)),
                   capture_output=True, text=True, check=True)
    moved = retire(out, out_dir / "_old" / _stamp())
    tmp.replace(out)
    print(f"отрывок: {section} с {hms(start)}, {length:.1f} с → {out}")
    if moved:
        print(f"  прошлый отрывок перенесён: {moved}")
    return out


# ── credits ───────────────────────────────────────────────────────────────────

def credits_cfg(config: dict) -> dict:
    return config.get("credits") or {}


def credit_text(config: dict, name: str) -> str:
    return str(credits_cfg(config).get(name) or "").strip()


def credit_chunks(text: str, config: dict) -> list[str]:
    """Each non-empty line is a paragraph, chunked by the book's own rules."""
    from audiobook.chunker import chunk_prose, limits
    lim = limits(config)
    out: list[str] = []
    for line in text.splitlines():
        line = " ".join(line.split())
        if line:
            out.extend(chunk_prose(line, lim))
    return out


def credit_rows(text: str, config: dict, table: dict, lat_hash: str) -> list[dict]:
    """Manifest-like rows hashed exactly as chunker.build_manifest does, so the
    per-chunk seed (synth.seed_for_chunk) and model input match a book chunk."""
    from audiobook import leadin, voicecfg
    from audiobook.chunker import chunk_hash
    from audiobook.pronounce import respell
    m = config["model"]
    model = voicecfg.model_id(config)
    rows = []
    for n, c in enumerate(credit_chunks(text, config), 1):
        # Credit lines are standalone — no cross-line sentence continuations.
        prepared = voicecfg.prepare_text(c, config, open_end=False)
        rows.append({"id": f"{n:04d}", "n": n, "text": c, "seed_override": None,
                     "open_end": False,
                     "hash": chunk_hash(c, model, m["seed"], m["temperature"], m["language"],
                                        lat_hash, respell(prepared, table),
                                        leadin.fires(prepared, config))})
    return rows


def credit_key(text: str, rows: list[dict]) -> str:
    """Voice key: the text plus every chunk hash (model id, seed, temperature,
    language, latents hash, pronounce/lead-in input are all inside those)."""
    payload = text + "\x00" + "\x00".join(r["hash"] for r in rows)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _file_sha1(p: Path | None) -> str:
    if p is None or not p.exists():
        return ""
    return hashlib.sha1(p.read_bytes()).hexdigest()


def music_path(config: dict) -> Path | None:
    m = str(credits_cfg(config).get("music") or "").strip()
    if not m:
        return None
    p = paths.ROOT / m
    if not p.exists():
        raise SystemExit(f"credits.music: файл не найден: {m}")
    return p


def credit_tags(config: dict, name: str) -> dict[str, str]:
    from audiobook.master import book_tags
    tags = {k: v for k, v in book_tags(config, name).items() if k != "track"}
    tags["title"] = CREDIT_TITLES[name]
    return tags


def mix_key(voice_key: str, config: dict, tags: dict[str, str], cover: Path | None,
            music: Path | None) -> str:
    """Key of the mastered mp3: voice + music bed + master settings + tags/cover.
    A change here re-masters without re-synthesising."""
    payload = json.dumps({
        "voice": voice_key,
        "music": music.name if music else "", "music_sha1": _file_sha1(music),
        "music_db": float(credits_cfg(config).get("music_db", -24)) if music else 0.0,
        "master": config.get("master") or {}, "tags": tags,
        "cover_sha1": _file_sha1(cover),
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def read_state(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_state(p: Path, state: dict) -> None:
    _write_text(p, json.dumps(state, ensure_ascii=False, indent=1))


@dataclass(frozen=True)
class CreditPlan:
    synth: bool            # render the voice wav
    master: bool           # (re)build the mp3
    retire_voice: str      # "" or _old_ suffix: move old wav/mp3/json aside first
    retire_mp3: str        # "" or _old_ suffix: move only the old mp3 aside


def plan_credit(state: dict, key: str, mkey: str, wav_exists: bool,
                mp3_exists: bool) -> CreditPlan:
    """Pure caching decision for one credits track."""
    if state.get("key") != key:
        had = wav_exists or mp3_exists
        old = (state.get("key") or "unknown")[:12]
        return CreditPlan(True, True, old if had else "", "")
    synth = not wav_exists
    if not synth and mp3_exists and state.get("mix_key") == mkey:
        return CreditPlan(False, False, "", "")
    old = (state.get("mix_key") or "unknown")[:12]
    return CreditPlan(synth, True, "", old if mp3_exists else "")


def credits_dir() -> Path:
    return paths.OUT / "credits"


def _credit_keys(config: dict, name: str, text: str) -> tuple[list[dict], str, str]:
    from audiobook.chunker import latents_hash
    from audiobook.master import cover_path
    from audiobook.pronounce import load_table
    rows = credit_rows(text, config, load_table(), latents_hash(config))
    key = credit_key(text, rows)
    mkey = mix_key(key, config, credit_tags(config, name), cover_path(config), music_path(config))
    return rows, key, mkey


def credit_state(config: dict, name: str) -> tuple[str, Path]:
    """("empty" | "missing" | "stale" | "ok", mp3 path) for export's pre-flight."""
    d = credits_dir()
    mp3 = d / f"{name}.mp3"
    text = credit_text(config, name)
    if not text:
        return "empty", mp3
    if not mp3.exists():
        return "missing", mp3
    _rows, key, mkey = _credit_keys(config, name, text)
    st = read_state(d / f"{name}.json")
    return ("ok" if st.get("key") == key and st.get("mix_key") == mkey else "stale"), mp3


def join_with_pauses(wavs: list, sr: int, pause_ms: int = CREDITS_PAUSE_MS):
    import numpy as np
    gap = np.zeros(int(sr * pause_ms / 1000), dtype=np.float32)
    parts = []
    for i, w in enumerate(wavs):
        if i:
            parts.append(gap)
        parts.append(np.asarray(w, dtype=np.float32))
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


def _default_engine(config: dict):
    from audiobook.synth import worker_config
    from audiobook.worker import TimeoutSynth
    timeout_s = (config.get("render") or {}).get("chunk_timeout_s", 600)
    return TimeoutSynth(worker_config(config, 1), timeout_s)


def render_credits(config: dict, engine_factory: Callable | None = None,
                   master_fn: Callable | None = None,
                   mix_fn: Callable | None = None) -> list[Path]:
    """Render/refresh out/credits/<name>.mp3 for every non-empty credits text.

    Unchanged text (same voice key) never re-synthesises; a changed master/music
    setting only re-masters. ``engine_factory(config)`` returns a context-managed
    engine with ``synth(text, seed, leadin=)`` (default TimeoutSynth — loads the
    model, opened lazily only when something needs synthesis); ``master_fn`` /
    ``mix_fn`` default to master.master_wav / the ffmpeg music bed.
    """
    import soundfile as sf
    from audiobook.master import cover_path
    from audiobook.master import master_wav as _master_wav
    from audiobook.pronounce import load_table
    from audiobook.synth import _SAMPLE_RATE, _synth_one_chunk

    engine_factory = engine_factory or _default_engine
    master_fn = master_fn or _master_wav
    mix_fn = mix_fn or _mix_music
    d = credits_dir()
    table = load_table()
    sentinel = config["model"].get("sentinel", "")
    retries = (config.get("render") or {}).get("timeout_retries", 2)
    cover = cover_path(config)
    music = music_path(config)

    jobs = []
    for name in CREDIT_NAMES:
        text = credit_text(config, name)
        if not text:
            print(f"credits.{name}: пусто — не рендерится")
            continue
        rows, key, mkey = _credit_keys(config, name, text)
        wav, mp3, js = d / f"{name}.wav", d / f"{name}.mp3", d / f"{name}.json"
        plan = plan_credit(read_state(js), key, mkey, wav.exists(), mp3.exists())
        jobs.append((name, rows, key, mkey, wav, mp3, js, plan))

    out: list[Path] = []
    engine = None
    try:
        for name, rows, key, mkey, wav, mp3, js, plan in jobs:
            d.mkdir(parents=True, exist_ok=True)
            if plan.retire_voice:
                old = d / f"_old_{plan.retire_voice}"
                for p in (wav, mp3, d / f"{name}.mix.wav", js):
                    retire(p, old)
                print(f"credits.{name}: текст/голос изменились, старое → {old}")
            if plan.synth:
                if engine is None:
                    engine = engine_factory(config).__enter__()
                parts = []
                for r in rows:
                    w, _seed = _synth_one_chunk(r, config, table, sentinel, engine, retries)
                    if w is None:   # never cache silence: nothing is written
                        raise SystemExit(f"credits.{name}: чанк {r['id']} не синтезировался "
                                         f"после {retries + 1} попыток — ничего не записано")
                    parts.append(w)
                tmp = wav.with_name(wav.name + ".part")
                sf.write(str(tmp), join_with_pauses(parts, _SAMPLE_RATE), _SAMPLE_RATE,
                         subtype="FLOAT", format="WAV")
                tmp.replace(wav)
                write_state(js, {"key": key, "chunks": len(rows)})
                print(f"credits.{name}: синтез {len(rows)} чанков → {wav.name}")
            if plan.master:
                if plan.retire_mp3:
                    for p in (mp3, d / f"{name}.mix.wav"):
                        retire(p, d / f"_old_{plan.retire_mp3}")
                src = wav
                if music is not None:
                    src = d / f"{name}.mix.wav"
                    mix_fn(wav, music, src, config)
                master_fn(src, mp3, config, pad=True, tags=credit_tags(config, name), cover=cover)
                write_state(js, dict(read_state(js), key=key, mix_key=mkey))
                print(f"credits.{name}: мастер → {mp3}")
            elif not plan.synth:
                print(f"credits.{name}: без изменений")
            out.append(mp3)
    finally:
        if engine is not None:
            engine.__exit__(None, None, None)
    return out


def _mix_music(voice: Path, music: Path, out: Path, config: dict) -> None:
    import soundfile as sf
    info = sf.info(str(voice))
    db = float(credits_cfg(config).get("music_db", -24))
    tmp = out.with_name(out.name + ".part")
    p = subprocess.run(music_bed_args(_ff(), voice, music, tmp, db, info.duration,
                                      info.samplerate),
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"credits: музыкальная подложка не собралась:\n{p.stderr[-1000:]}")
    tmp.replace(out)


# ── CLI entry points ──────────────────────────────────────────────────────────

def run_export(config: dict, fmt: str = "mp3", allow_missing: bool = False) -> int:
    export(config, fmt, allow_missing=allow_missing)
    return 0


def run_sample(config: dict, section: str, start_s: float = 0,
               length_s: float = SAMPLE_MAX_S) -> int:
    sample(config, section, start_s, length_s)
    return 0


def run_credits(config: dict) -> int:
    render_credits(config)
    return 0
