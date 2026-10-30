"""Render identical chunks once, reuse the audio everywhere (``render.reuse_identical``).

The book repeats some chunks verbatim: «Главное, что нужно помнить» ×34,
«Шаг один.» ×18 … Same hash = same text and settings, yet each copy was a
separate generation with its own stress luck. With reuse on:

  * synth, before rendering a section: a pending chunk whose hash is already
    rendered anywhere in the book (the *leader*) gets a COPY of the leader's
    wav and results; among pending duplicates inside the section only the first
    is rendered, the rest wait as status "dup" and are filled right after;
  * qc: best-of-N takes run only for leaders; afterwards every follower is
    re-synced to its leader's current wav (a better take, an accept) — so all
    copies stay identical.

Followers carry ``reused_from = "<section>/<id>"``. A follower accepted by ear
(locked) stops following. Files are copied, never linked (Windows) or moved;
nothing is deleted. The chunk hash is unchanged — no cache reset.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from audiobook import paths

# Results that belong to the audio; copied leader → follower.
AUDIO_FIELDS = ("seed", "duration_ms", "cer", "transcript", "flag_words", "ms_per_char",
                "suspect", "min_p", "mean_p", "peak", "takes", "take_base")
DONE = ("done",)


def enabled(config: dict) -> bool:
    return bool((config.get("render") or {}).get("reuse_identical", False))


def _read(manifest: Path) -> list[dict]:
    with open(manifest, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def leaders(out: Path, exclude: str | None = None) -> dict[str, tuple[str, dict]]:
    """hash → (section, row) of a rendered, non-follower chunk with its wav on
    disk, across every section (``exclude`` = section handled separately)."""
    found: dict[str, tuple[str, dict]] = {}
    for m in sorted((out / "sections").glob("*/manifest.jsonl")):
        sec = m.parent.name
        if sec == exclude:
            continue
        for r in _read(m):
            if (r.get("status") in DONE and not r.get("reused_from")
                    and (m.parent / "chunks" / f"{r['id']}.wav").exists()):
                found.setdefault(r["hash"], (sec, r))
    return found


def _copy_wav(src: Path, dst: Path) -> bool:
    """Copy if missing or different bytes. → True if written."""
    if dst.exists() and dst.stat().st_size == src.stat().st_size \
            and dst.read_bytes() == src.read_bytes():
        return False
    tmp = dst.with_name(dst.name + ".part")
    shutil.copyfile(src, tmp)
    tmp.replace(dst)
    return True


def follow(row: dict, leader: dict, leader_sec: str) -> None:
    for k in AUDIO_FIELDS:
        if k in leader:
            row[k] = leader[k]
    st = leader.get("status")
    row["status"] = st if st in ("done", "qc_fail", "manual") else "done"
    row["reused_from"] = f"{leader_sec}/{leader['id']}"


def _pending(row: dict, wav_exists: bool) -> bool:
    if row.get("locked"):
        return False
    return (not wav_exists) or row.get("status") in (None, "pending", "timeout", "dup")


def before_render(sec_dir: Path, rows: list[dict], out: Path | None = None,
                  first: int | None = None) -> tuple[int, int]:
    """Fill pending chunks from leaders elsewhere; park in-section duplicates as
    "dup". Mutates ``rows``. → (copied, parked)."""
    out = Path(out or paths.OUT)
    chunks = sec_dir / "chunks"
    chunks.mkdir(parents=True, exist_ok=True)
    lead = leaders(out, exclude=sec_dir.name)
    here = {r["hash"]: r for r in rows
            if r.get("status") in DONE and not r.get("reused_from")
            and (chunks / f"{r['id']}.wav").exists()}
    copied = parked = 0
    first_pending: set[str] = set()
    for r in rows[:first]:
        if not _pending(r, (chunks / f"{r['id']}.wav").exists()):
            continue
        h = r["hash"]
        if h in here and here[h] is not r:
            src = chunks / f"{here[h]['id']}.wav"
            _copy_wav(src, chunks / f"{r['id']}.wav")
            follow(r, here[h], sec_dir.name)
            copied += 1
        elif h in lead:
            ls, lr = lead[h]
            _copy_wav(out / "sections" / ls / "chunks" / f"{lr['id']}.wav", chunks / f"{r['id']}.wav")
            follow(r, lr, ls)
            copied += 1
        elif h in first_pending:
            r["status"] = "dup"
            parked += 1
        else:
            first_pending.add(h)
            if r.get("status") == "dup":
                r["status"] = "pending"
    return copied, parked


def after_render(sec_dir: Path, rows: list[dict]) -> int:
    """Fill "dup" rows from the now-rendered first copy in this section; a dup
    whose leader failed goes back to "pending". Mutates ``rows``. → filled."""
    chunks = sec_dir / "chunks"
    done = {r["hash"]: r for r in rows
            if r.get("status") in DONE and not r.get("reused_from")
            and (chunks / f"{r['id']}.wav").exists()}
    filled = 0
    for r in rows:
        if r.get("status") != "dup":
            continue
        lead = done.get(r["hash"])
        if lead is None:
            r["status"] = "pending"
            continue
        _copy_wav(chunks / f"{lead['id']}.wav", chunks / f"{r['id']}.wav")
        follow(r, lead, sec_dir.name)
        filled += 1
    return filled


def resync(sec_dir: Path, rows: list[dict], out: Path | None = None) -> int:
    """Make every follower in this section identical to its leader's CURRENT
    wav and results (after takes/accept on the leader). Mutates ``rows``."""
    out = Path(out or paths.OUT)
    chunks = sec_dir / "chunks"
    cache: dict[str, dict[str, dict]] = {}
    changed = 0
    for r in rows:
        src_ref = r.get("reused_from")
        if not src_ref or r.get("locked"):
            continue
        ls, _, lid = src_ref.partition("/")
        if ls == sec_dir.name:
            by_id = {x["id"]: x for x in rows}
        else:
            if ls not in cache:
                m = out / "sections" / ls / "manifest.jsonl"
                cache[ls] = {x["id"]: x for x in _read(m)} if m.exists() else {}
            by_id = cache[ls]
        lead = by_id.get(lid)
        src = out / "sections" / ls / "chunks" / f"{lid}.wav"
        if lead is None or lead.get("hash") != r["hash"] or not src.exists():
            r.pop("reused_from", None)          # leader gone/changed: stand alone
            continue
        wrote = _copy_wav(src, chunks / f"{r['id']}.wav")
        before = {k: r.get(k) for k in AUDIO_FIELDS}
        follow(r, lead, ls)
        if wrote or before != {k: r.get(k) for k in AUDIO_FIELDS}:
            changed += 1
    return changed
