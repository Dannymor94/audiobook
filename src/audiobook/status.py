"""Book status in one screen: per section what is rendered, what needs a human,
whether the assembled audio is current, and how long the rest will take.

    ./run.sh status

Read-only: never renders, never writes manifests. Sections not chunked yet are
estimated from their *.norm.txt length. Sections in ``render.skip_sections``
are shown as skipped and left out of the totals.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from audiobook import paths

DEFAULT_CPS = 13.0      # chars per second of speech, until measured on rendered chunks
DEFAULT_RTF = 6.5       # effective machine RTF (2 workers, 1.7B on gamebox)


@dataclass
class SectionStatus:
    name: str
    chars: int = 0
    rows: int = 0
    done: int = 0
    manual: int = 0
    locked: int = 0
    done_chars: int = 0
    done_ms: int = 0
    suspects: int | None = None
    audio: str = "—"          # "—" | "собрано" | "устарело"
    chunked: bool = False
    skipped: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def remaining_chars(self) -> int:
        return 0 if self.skipped else max(0, self.chars - self.done_chars)


def book_sections() -> list[str]:
    out = []
    for jf in sorted((paths.TEXT / "blocks").glob("*.blocks.json")):
        try:
            d = json.loads(jf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name = f"{d['nn']}_{d['slug']}"
        norm = paths.TEXT / f"{name}.norm.txt"
        if norm.exists() and norm.stat().st_size >= 50:
            out.append(name)
    return out


def _count_lines(p: Path) -> int:
    return max(0, len([ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]) - 1)


def section_status(name: str, skip: set[str]) -> SectionStatus:
    st = SectionStatus(name=name, skipped=name in skip)
    sec = paths.OUT / "sections" / name
    manifest = sec / "manifest.jsonl"
    norm = paths.TEXT / f"{name}.norm.txt"
    if not manifest.exists():
        st.chars = len(" ".join(norm.read_text(encoding="utf-8").split())) if norm.exists() else 0
        return st
    st.chunked = True
    with open(manifest, encoding="utf-8") as f:
        rows = [json.loads(ln) for ln in f if ln.strip()]
    st.rows = len(rows)
    for r in rows:
        n = len(r.get("text", ""))
        st.chars += n
        if r.get("status") == "done":
            st.done += 1
            st.done_chars += n
            st.done_ms += int(r.get("duration_ms") or 0)
        elif r.get("status") == "manual":
            st.manual += 1
        if r.get("locked"):
            st.locked += 1
    sus = sec / "section.suspects.tsv"
    if sus.exists():
        st.suspects = _count_lines(sus)
    mp3 = sec / "section.mp3"
    if mp3.exists():
        st.audio = "собрано" if mp3.stat().st_mtime >= manifest.stat().st_mtime else "устарело"
    return st


def measured_cps(stats: list[SectionStatus]) -> float:
    chars = sum(s.done_chars for s in stats)
    ms = sum(s.done_ms for s in stats)
    return chars / (ms / 1000) if chars >= 2000 and ms > 0 else DEFAULT_CPS


def eta_hours(remaining_chars: int, cps: float, rtf: float) -> float:
    return remaining_chars / cps * rtf / 3600


def _hm(hours: float) -> str:
    if hours >= 48:
        return f"{hours / 24:.1f} сут"
    return f"{int(hours)} ч {int(hours * 60) % 60:02d} мин"


def run(config: dict) -> int:
    rcfg = config.get("render") or {}
    skip = set(rcfg.get("skip_sections") or [])
    rtf = float(rcfg.get("eta_rtf") or DEFAULT_RTF)
    stats = [section_status(n, skip) for n in book_sections()]
    cps = measured_cps(stats)

    print(f"{'секция':<44} {'готово':>11} {'ручн':>5} {'подозр':>6}  звук")
    for s in stats:
        if s.skipped:
            print(f"{s.name[:44]:<44} {'пропуск':>11}")
            continue
        if not s.chunked:
            print(f"{s.name[:44]:<44} {'не начато':>11} {'':>5} {'':>6}  —   (~{s.chars / cps / 60:.0f} мин)")
            continue
        sus = "" if s.suspects is None else str(s.suspects)
        print(f"{s.name[:44]:<44} {s.done:>5}/{s.rows:<5} {s.manual or '':>5} {sus:>6}  {s.audio}")

    live = [s for s in stats if not s.skipped]
    total = sum(s.chars for s in live)
    done = sum(s.done_chars for s in live)
    remaining = sum(s.remaining_chars for s in live)
    print(f"\nвсего: {done / max(1, total):.0%} текста отрендерено "
          f"({done:,} из {total:,} симв.)".replace(",", " "))
    print(f"звук: готово ~{done / cps / 3600:.1f} ч, осталось ~{remaining / cps / 3600:.1f} ч "
          f"(темп речи {cps:.1f} симв/с{'' if cps != DEFAULT_CPS else ', оценка'})")
    print(f"осталось рендера: ~{_hm(eta_hours(remaining, cps, rtf))} при RTF {rtf} (render.eta_rtf)")
    manual = [(s.name, s.manual) for s in live if s.manual]
    if manual:
        print("ждут человека (manual): " + ", ".join(f"{n} ({k})" for n, k in manual))
    stale = [s.name for s in live if s.audio == "устарело"]
    if stale:
        print("звук устарел (нужны assemble+master): " + ", ".join(stale))
    try:
        from audiobook.jobqueue import list_jobs, queue_root
        if not queue_root().exists():      # list_jobs would create the folders
            return 0
        jobs = list_jobs()
        pend = sum(1 for j in jobs if j.get("status") == "pending")
        runn = [j for j in jobs if j.get("status") == "running"]
        print(f"очередь: {pend} ждут" + (f", идёт: {' '.join(runn[0].get('args', []))}" if runn else ""))
    except Exception:  # noqa: BLE001 — status must never fail on the queue
        pass
    return 0
