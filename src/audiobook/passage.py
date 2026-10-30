"""A/B a continuous passage: render N consecutive chunks of a section with the
CURRENT (possibly trial) config, assemble them with the real pauses and master
— without touching the book's manifest, chunk cache or section audio.

    ./run.sh passage --section S --start 10 --count 15 --tag base
    AUDIOBOOK_CONFIG=out/cfg_ctx.yaml ./run.sh passage --section S --start 10 --count 15 --tag ctx

→ out/passage/<tag>/passage.mp3 (+ index.tsv, chunks/<hash16>.wav). For things
only audible across chunk joins (context lead-in, pauses), which golden's
isolated chunks cannot show. Chunk wavs are keyed by hash, so a rerun with the
same settings renders nothing new.
"""
from __future__ import annotations

import json
import re

from audiobook import paths

_TAG_RE = re.compile(r"[A-Za-z0-9._-]{1,40}")


def select(rows: list[dict], start: int, count: int) -> list[dict]:
    """Chunks n = start .. start+count-1 (1-based ``n`` as in the manifest)."""
    return [r for r in rows if start <= int(r["n"]) < start + count]


def run(config: dict, section: str, start: int = 1, count: int = 15, tag: str = "base") -> int:
    import soundfile as sf
    from audiobook.assemble import join_chunks
    from audiobook.chunker import build_manifest, load_units, section_config
    from audiobook.master import master_wav
    from audiobook.pronounce import load_table
    from audiobook.synth import _SAMPLE_RATE, _synth_one_chunk, worker_config
    from audiobook.worker import TimeoutSynth

    if not _TAG_RE.fullmatch(tag):
        raise SystemExit(f"недопустимый --tag {tag!r} (латиница, цифры, . _ -)")
    nn, _, slug = section.partition("_")
    cfg = section_config(config, section)
    rows = select(build_manifest(load_units(nn, slug), cfg), start, count)
    if not rows:
        raise SystemExit(f"в {section} нет чанков {start}…{start + count - 1}")
    out = paths.OUT / "passage" / tag
    wav_dir = out / "chunks"
    wav_dir.mkdir(parents=True, exist_ok=True)
    todo = [r for r in rows if not (wav_dir / f"{r['hash'][:16]}.wav").exists()]
    print(f"{section}: чанки {rows[0]['id']}…{rows[-1]['id']} ({len(rows)}), рендер {len(todo)}")
    if todo:
        table = load_table()
        sentinel = config["model"].get("sentinel", "")
        rcfg = config.get("render") or {}
        with TimeoutSynth(worker_config(config, 1), rcfg.get("chunk_timeout_s", 600)) as eng:
            for r in todo:
                wav, _seed = _synth_one_chunk(r, config, table, sentinel, eng,
                                              rcfg.get("timeout_retries", 2))
                if wav is None:
                    raise SystemExit(f"чанк {r['id']} не синтезировался (cap/timeout)")
                p = wav_dir / f"{r['hash'][:16]}.wav"
                tmp = p.with_name(p.name + ".part")
                sf.write(str(tmp), wav, _SAMPLE_RATE, subtype="FLOAT", format="WAV")
                tmp.replace(p)
    by_hash = [dict(r, id=r["hash"][:16]) for r in rows]          # join reads <id>.wav
    audio, stats = join_chunks(by_hash, wav_dir, cfg)
    raw = out / "passage.wav.part"
    sf.write(str(raw), audio, _SAMPLE_RATE, subtype="FLOAT", format="WAV")
    master_wav(raw, out / "passage.mp3", config)
    raw.unlink()   # intermediate; chunk wavs are kept
    with open(out / "index.tsv", "w", encoding="utf-8", newline="\n") as f:
        f.write("id\tstart_ms\tleadin\ttext\n")
        for r, st in zip(rows, stats):
            f.write(f"{r['id']}\t{st['start_ms']}\t{r.get('leadin') or ''}\t"
                    f"{' '.join(r['text'].split())}\n")
    with open(out / "settings.json", "w", encoding="utf-8") as f:
        json.dump({"section": section, "start": start, "count": count,
                   "leadin": (config.get("render") or {}).get("leadin"),
                   "temperature": config["model"].get("temperature")}, f,
                  ensure_ascii=False, indent=1)
    print(f"→ {out / 'passage.mp3'}  ({len(audio) / _SAMPLE_RATE:.0f} с)")
    return 0
