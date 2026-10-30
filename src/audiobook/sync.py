"""Text ↔ audio sync map of an assembled chapter, for the interactive reader
(highlight the phrase being read, click a phrase to jump there).

    ./run.sh sync --section S      → out/sections/S/section.sync.json
    ./run.sh sync --all            → every section that has section.index.tsv

Times are in section.mp3 (master's head silence included). Built from
assemble's index.tsv, refused if that index is not from the current manifest
(same id/hash/seed check as suspects). Read-only except the json it writes.
"""
from __future__ import annotations

import json
from pathlib import Path

from audiobook import paths


def read_index_full(path: Path) -> dict[str, dict]:
    """id → {start_ms, lead_ms, dur_ms} from an index.tsv with a dur_ms column."""
    lines = path.read_text(encoding="utf-8").splitlines()
    head = lines[0].split("\t") if lines else []
    if "dur_ms" not in head:
        raise SystemExit(f"{path.name}: нет колонки dur_ms — пересобери assemble")
    col = {name: i for i, name in enumerate(head)}
    out = {}
    for ln in lines[1:]:
        if not ln.strip():
            continue
        f = ln.split("\t")
        out[f[0]] = {"start_ms": int(f[col["start_ms"]]), "lead_ms": int(f[col["lead_ms"]]),
                     "dur_ms": int(f[col["dur_ms"]] or 0)}
    return out


def build(rows: list[dict], index: dict[str, dict], head_ms: int, para_ms: int) -> list[dict]:
    """One entry per chunk in reading order: book text (not the respelled model
    input), start/end in the mp3, and whether a paragraph ends after it."""
    out = []
    for r in rows:
        ix = index.get(str(r["id"]))
        if ix is None:
            continue
        start = ix["start_ms"] + head_ms
        out.append({"id": str(r["id"]), "start_ms": start, "end_ms": start + ix["dur_ms"],
                    "text": r["text"],
                    "para_end": int(r.get("pause_after_ms") or 0) >= para_ms})
    return out


def _heading(section: str) -> str:
    jf = paths.TEXT / "blocks" / f"{section}.blocks.json"
    if not jf.exists():
        return ""
    with open(jf, encoding="utf-8") as f:
        return json.load(f).get("heading") or ""


def write_section(config: dict, section: str) -> Path:
    from audiobook.suspects import check_identity, read_index_identity
    from audiobook.synth import _read_manifest
    sec = paths.OUT / "sections" / section
    idx = sec / "section.index.tsv"
    if not idx.exists():
        raise SystemExit(f"{section}: нет section.index.tsv — сначала assemble")
    rows = _read_manifest(sec / "manifest.jsonl")
    ident = read_index_identity(idx)
    why = check_identity(ident, rows, None) if ident is not None else "старый index.tsv"
    if why:
        raise SystemExit(f"{section}: index.tsv не от текущего манифеста ({why}) — "
                         "сначала assemble --section " + section)
    head = int((config.get("master") or {}).get("head_ms") or 0)
    para = int((config.get("pauses_ms") or {}).get("paragraph", 900))
    data = {"section": section, "title": _heading(section), "audio": "section.mp3",
            "head_ms": head, "chunks": build(rows, read_index_full(idx), head, para)}
    out = sec / "section.sync.json"
    tmp = out.with_name(out.name + ".part")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    tmp.replace(out)
    return out


def run(config: dict, section: str | None, all_sections: bool = False) -> int:
    if all_sections:
        secs = sorted(p.parent.name for p in (paths.OUT / "sections").glob("*/section.index.tsv"))
    elif section:
        secs = [section]
    else:
        raise SystemExit("sync: нужен --section S или --all")
    bad = 0
    for s in secs:
        try:
            out = write_section(config, s)
            n = len(json.loads(out.read_text(encoding="utf-8"))["chunks"])
            print(f"{s}: {n} фраз → {out}")
        except SystemExit as e:
            bad += 1
            print(f"  ПРОПУЩЕНО {e}")
    return 1 if bad else 0
