"""List the places in an assembled section worth a human listen.

QC stores per chunk ``flag_words`` (whisper-unsure words and stress-trap
words, with time inside the chunk); assemble writes ``<stem>.index.tsv``
(where each chunk starts in the section and how much leading silence it lost).
This joins them into section timestamps:

    ./run.sh suspects --section S [--first N]
    → out/sections/S/<stem>.suspects.tsv  and a printed list "m:ss  word  why"

The index must belong to the current manifest: it is refused when it is older
than manifest.jsonl (synth/qc/redo/accept rewrote the manifest after assemble)
or when its chunk ids differ from the manifest's (re-chunked) — the times would
point at the wrong audio. Fix: assemble again.

Whisper hears words, not stress: "conf" catches garbled words (тебья, дышьи,
каша), "watch" points at known traps whose stress only an ear can confirm.
"""
from __future__ import annotations

from pathlib import Path

from audiobook import paths


def mmss(ms: float) -> str:
    s = max(0, int(ms // 1000))
    return f"{s // 60}:{s % 60:02d}"


def read_index(path: Path) -> dict[str, tuple[int, int]]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        cid, start, lead = line.split("\t")
        out[cid] = (int(start), int(lead))
    return out


def check_index(index_ids: list[str], rows: list[dict], first: int | None,
                idx_mtime: float, manifest_mtime: float) -> str | None:
    """Reason (Russian) why the index does not match the manifest, or None."""
    if idx_mtime < manifest_mtime:
        return ("index.tsv старше manifest.jsonl — манифест менялся после assemble "
                "(synth/qc/redo/accept)")
    want = [str(r["id"]) for r in (rows[:first] if first else rows)]
    if index_ids != want:
        extra = [i for i in index_ids if i not in set(want)]
        lost = [i for i in want if i not in set(index_ids)]
        detail = []
        if extra:
            detail.append(f"нет в манифесте: {', '.join(extra[:5])}")
        if lost:
            detail.append(f"нет в index.tsv: {', '.join(lost[:5])}")
        if not detail:
            detail.append("другой порядок чанков")
        return "чанки index.tsv не совпадают с манифестом (" + "; ".join(detail) + ")"
    return None


def read_index_ids(path: Path) -> list[str]:
    return [ln.split("\t", 1)[0] for ln in path.read_text(encoding="utf-8").splitlines()[1:]
            if ln.strip()]


def collect(rows: list[dict], index: dict[str, tuple[int, int]]) -> list[dict]:
    """[{t_ms, id, word, p, why}] sorted by section time."""
    out = []
    for r in rows:
        if r["id"] not in index:
            continue
        start, lead = index[r["id"]]
        for word, s, p, why in r.get("flag_words") or []:
            out.append({"t_ms": start - lead + s * 1000, "id": r["id"],
                        "word": word, "p": p, "why": why})
    return sorted(out, key=lambda x: x["t_ms"])


def run(config: dict, section: str | None, first: int | None = None) -> int:
    if not section:
        raise SystemExit("suspects: --section обязателен")
    from audiobook.assemble import preview_name
    from audiobook.synth import _read_manifest
    sec_dir = paths.OUT / "sections" / section
    stem = preview_name(first)
    idx_path = sec_dir / f"{stem}.index.tsv"
    if not idx_path.exists():
        raise SystemExit(f"нет {idx_path.name} — сначала assemble"
                         + (f" --first {first}" if first else ""))
    manifest = sec_dir / "manifest.jsonl"
    rows = _read_manifest(manifest)
    why = check_index(read_index_ids(idx_path), rows, first,
                      idx_path.stat().st_mtime, manifest.stat().st_mtime)
    if why:
        raise SystemExit(f"suspects: {idx_path.name} не от текущего манифеста: {why}. "
                         "Сначала assemble --section " + section
                         + (f" --first {first}" if first else ""))
    if not any("flag_words" in r for r in rows):
        raise SystemExit("в манифесте нет flag_words — сначала qc (новой версии)")
    items = collect(rows, read_index(idx_path))
    why_ru = {"conf": "неуверенно", "watch": "ловушка"}
    out = sec_dir / f"{stem}.suspects.tsv"
    with open(out, "w", encoding="utf-8") as f:
        f.write("time\tchunk\tword\tprob\twhy\n")
        for it in items:
            f.write(f"{mmss(it['t_ms'])}\t{it['id']}\t{it['word']}\t{it['p']}\t{it['why']}\n")
    print(f"{section}: подозрительных мест {len(items)} "
          f"(неуверенно {sum(i['why'] == 'conf' for i in items)}, "
          f"ловушек {sum(i['why'] == 'watch' for i in items)})")
    for it in items:
        print(f"  {mmss(it['t_ms']):>6}  {it['word']:<16} {why_ru[it['why']]}"
              f"  p={it['p']}  (чанк {it['id']})")
    print(f"→ {out}")
    return 0
