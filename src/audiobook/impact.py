"""What would a settings change cost? Rebuild every chunked section's manifest
in memory with the CURRENT config/pronounce.yaml/text and count the rendered
chunks whose audio would no longer match (their hash disappears).

    ./run.sh impact                                  # after editing a setting
    AUDIOBOOK_CONFIG=out/cfg_try.yaml ./run.sh impact   # trial copy, main untouched

Read-only: manifests, cache and audio are not touched. Accepted (locked)
chunks that would lose their match are listed — their human choice would
have to be redone.
"""
from __future__ import annotations

from collections import Counter

from audiobook import paths

RENDERED = ("done", "manual")


def diff_rows(old: list[dict], new: list[dict]) -> dict:
    """Rendered old rows whose hash is not in the new manifest (multiset-aware)."""
    pool = Counter(r["hash"] for r in new)
    lost = []
    for r in old:
        if pool[r["hash"]] > 0:
            pool[r["hash"]] -= 1
        elif r.get("status") in RENDERED:
            lost.append(r)
    return {"lost": lost, "chars": sum(len(r.get("text", "")) for r in lost),
            "locked": [r["id"] for r in lost if r.get("locked")],
            "rendered": sum(1 for r in old if r.get("status") in RENDERED)}


def section_impact(config: dict, section: str) -> dict | None:
    from audiobook.chunker import build_manifest, load_units
    from audiobook.synth import _read_manifest
    manifest = paths.OUT / "sections" / section / "manifest.jsonl"
    if not manifest.exists():
        return None
    nn, slug = section.split("_", 1)
    return diff_rows(_read_manifest(manifest), build_manifest(load_units(nn, slug), config))


def run(config: dict, section: str | None = None, verbose: bool = False) -> int:
    from audiobook.status import DEFAULT_CPS, DEFAULT_RTF, _hm, eta_hours
    secs = [section] if section else sorted(
        p.parent.name for p in (paths.OUT / "sections").glob("*/manifest.jsonl"))
    rtf = float((config.get("render") or {}).get("eta_rtf") or DEFAULT_RTF)
    tot_lost = tot_chars = tot_rendered = 0
    locked_all: list[str] = []
    for s in secs:
        d = section_impact(config, s)
        if d is None:
            print(f"{s}: нет манифеста")
            continue
        tot_lost += len(d["lost"])
        tot_chars += d["chars"]
        tot_rendered += d["rendered"]
        if d["lost"] or verbose:
            print(f"{s[:44]:<44} перерендер {len(d['lost']):>4} из {d['rendered']:<4} отрендеренных"
                  + (f"  ЗАБЛОКИРОВАННЫЕ: {', '.join(d['locked'])}" if d["locked"] else ""))
            if verbose:
                for r in d["lost"][:5]:
                    print(f"    {r['id']}: {r.get('text', '')[:60]!r}")
        locked_all += [f"{s}/{i}" for i in d["locked"]]
    print(f"\nитого: перерендер {tot_lost} чанков из {tot_rendered} отрендеренных, "
          f"~{tot_chars / DEFAULT_CPS / 60:.0f} мин звука, "
          f"~{_hm(eta_hours(tot_chars, DEFAULT_CPS, rtf))} машины")
    if locked_all:
        print("потеряют ручной выбор (accept): " + ", ".join(locked_all))
    if not tot_lost:
        print("правка не задевает отрендеренный звук")
    return 0
