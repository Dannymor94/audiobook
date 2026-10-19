"""Compare voice references on the same text: each candidate renders the first N
chunks of one section with the configured model, through the same
prepare → seed → retry → trim path as `synth`, then is assembled and mastered
like a section. Output only — never touches the section manifest or chunk cache.

Candidates live in ref/candidates/ (gitignored with the rest of ref/):
  <name>.wav  — 15-25 s, mono, 24 kHz, one speaker, whole phrases
  <name>.txt  — verbatim transcript, confirmed by ear (full-clone/ICL mode needs it)
`--transcribe` writes <name>.draft.txt from whisper for the human to check and
rename to <name>.txt — a draft is never used for latents.

Latents are computed once per candidate and model variant
(<name>.latents_<variant>.pt) in a short-lived spawn child, so the model is never
held twice in RAM. Seeds come from each chunk's hash, identical across
candidates, so the reference is the only thing that differs.

Out: out/ref_compare/<section>/<name>_<tag>.mp3 (+ chunk wavs in <name>_<tag>/ for
resume); <tag> hashes the clip + confirmed text, so a corrected transcript gets
fresh latents and a fresh render instead of the stale ones.
"""
from __future__ import annotations

import logging
from pathlib import Path

import soundfile as sf

from audiobook import paths, voicecfg

log = logging.getLogger(__name__)

CANDIDATES_DIR_NAME = "candidates"


def candidates_dir() -> Path:
    return paths.ROOT / "ref" / CANDIDATES_DIR_NAME


def find_candidates(cdir: Path) -> list[tuple[str, Path, Path | None]]:
    """[(name, wav, txt-or-None)] sorted by name."""
    out = []
    for wav in sorted(cdir.glob("*.wav")):
        txt = wav.with_suffix(".txt")
        out.append((wav.stem, wav, txt if txt.exists() else None))
    return out


def candidate_tag(wav: Path, txt: Path) -> str:
    """Short content hash of the reference audio + its confirmed text. Editing
    the transcript (or replacing the clip) yields a new tag, so latents and
    renders made from the old text are never silently reused."""
    import hashlib
    h = hashlib.sha1(wav.read_bytes())
    h.update(b"\x00" + txt.read_text(encoding="utf-8").strip().encode("utf-8"))
    return h.hexdigest()[:8]


def latents_file(wav: Path, variant: str, tag: str) -> Path:
    return wav.with_name(f"{wav.stem}.latents_{variant.lower()}_{tag}.pt")


def _latents_job(variant: str, wav: str, ref_text: str, out: str) -> None:
    """Spawn child: load model, compute ICL latents, save atomically, exit."""
    from audiobook.synth import compute_latents, load_model, save_latents
    model = load_model("cpu", variant)
    lat = compute_latents(model, Path(wav), ref_text)
    tmp = Path(out).with_name(Path(out).name + ".part")
    save_latents(lat, tmp)
    tmp.replace(out)


def ensure_latents(wav: Path, txt: Path, variant: str) -> Path:
    out = latents_file(wav, variant, candidate_tag(wav, txt))
    if out.exists():
        return out
    import multiprocessing as mp
    ref_text = txt.read_text(encoding="utf-8").strip()
    if not ref_text:
        raise SystemExit(f"пустой текст референса: {txt}")
    p = mp.get_context("spawn").Process(
        target=_latents_job, args=(variant, str(wav), ref_text, str(out)))
    p.start()
    p.join()
    if p.exitcode != 0 or not out.exists():
        raise SystemExit(f"латенты не посчитались для {wav.name} (exit {p.exitcode})")
    return out


def transcribe_drafts(cdir: Path) -> int:
    """whisper draft for every candidate wav without a .txt."""
    from audiobook.qc import _release, load_whisper, transcribe
    todo = [(n, w) for n, w, t in find_candidates(cdir) if t is None]
    if not todo:
        print("все кандидаты уже с .txt")
        return 0
    wm = load_whisper()
    try:
        for name, wav in todo:
            draft = wav.with_suffix(".draft.txt")
            draft.write_text(transcribe(wm, wav) + "\n", encoding="utf-8")
            print(f"черновик: {draft}  → проверь на слух и переименуй в {name}.txt")
    finally:
        _release(wm)
    return 0


def render_candidate(engine, rows: list[dict], config: dict, out_dir: Path) -> int:
    """Synth each row into out_dir/<id>.wav (skip existing — resumable). Returns
    the number of failed chunks; a failed chunk gets no wav (never silence)."""
    from audiobook.pronounce import load_table
    from audiobook.synth import _SAMPLE_RATE, _synth_one_chunk
    out_dir.mkdir(parents=True, exist_ok=True)
    table = load_table()
    sentinel = config["model"].get("sentinel", "")
    retries = config.get("render", {}).get("timeout_retries", 2)
    failed = 0
    for row in rows:
        wav_path = out_dir / f"{row['id']}.wav"
        if wav_path.exists():
            continue
        wav, _seed = _synth_one_chunk(row, config, table, sentinel, engine, retries)
        if wav is None:
            log.warning("chunk %s failed", row["id"])
            failed += 1
            continue
        tmp = wav_path.with_name(wav_path.name + ".part")
        sf.write(str(tmp), wav, _SAMPLE_RATE, subtype="PCM_16", format="WAV")
        tmp.replace(wav_path)
    return failed


def run(config: dict, section: str | None, first: int | None,
        transcribe: bool = False) -> int:
    cdir = candidates_dir()
    if not cdir.is_dir():
        raise SystemExit(f"нет папки кандидатов: {cdir}")
    if transcribe:
        return transcribe_drafts(cdir)
    if not section or not first:
        raise SystemExit("ref-compare: нужны --section и --first")

    from audiobook.assemble import join_chunks
    from audiobook.master import master_wav
    from audiobook.synth import _SAMPLE_RATE, _read_manifest, worker_config
    from audiobook.worker import TimeoutSynth

    manifest = paths.OUT / "sections" / section / "manifest.jsonl"
    if not manifest.exists():
        raise SystemExit(f"нет манифеста {manifest} — сначала chunk --section {section}")
    rows = _read_manifest(manifest)[:first]

    cands = find_candidates(cdir)
    missing = [n for n, _w, t in cands if t is None]
    if missing:
        raise SystemExit(f"нет подтверждённого текста (.txt) у: {missing} — "
                         "сначала ref-compare --transcribe, проверить на слух, переименовать")
    if not cands:
        raise SystemExit(f"нет *.wav в {cdir}")

    variant = voicecfg.variant(config)
    base = worker_config(config, 1)  # validates variant/workers; latents swapped below
    timeout_s = config.get("render", {}).get("chunk_timeout_s", 600)
    out_root = paths.OUT / "ref_compare" / section
    for base_name, wav, txt in cands:
        name = f"{base_name}_{candidate_tag(wav, txt)}"  # new text → new render
        mp3 = out_root / f"{name}.mp3"
        if mp3.exists():
            print(f"{name}: уже есть {mp3}")
            continue
        lat = ensure_latents(wav, txt, variant)
        wcfg = dict(base, latents_path=str(lat))
        chunk_dir = out_root / name
        with TimeoutSynth(wcfg, timeout_s) as engine:
            failed = render_candidate(engine, rows, config, chunk_dir)
        if failed:
            print(f"{name}: {failed} чанк(ов) не синтезировались — mp3 не собран, "
                  "перезапуск догенерирует недостающие")
            continue
        audio, _stats = join_chunks(rows, chunk_dir, config)
        raw = out_root / f"{name}.wav"
        sf.write(str(raw), audio, _SAMPLE_RATE, subtype="PCM_16")
        meas = master_wav(raw, mp3, config)
        raw.unlink()  # intermediate of this command only; chunk wavs are kept
        print(f"{name}: {mp3}  ({len(audio) / _SAMPLE_RATE:.1f} s, вход {meas['input_i']} LUFS)")
    return 0
