"""Loudness report over the mastered sections — measurement only, no audio is
written or changed.

For every out/sections/<S>/section.mp3 (or the sections given) ffmpeg's
ebur128 meter (peak=true) gives integrated loudness (LUFS), true peak (dBTP)
and loudness range (LRA, LU). Audio files in extra directories (the author's
live recordings, say) are measured as a reference only: listed, never flagged.

Flags, against config.master (lufs / true_peak):
  громкость    |I - lufs| > 1.0 LU
  пик          true peak above true_peak
  LRA мин/макс the extremes when the LRA spread across chapters exceeds 3 LU

Output: a Russian table on stdout and out/loudness/report.tsv (atomic write).
Parsing the ffmpeg text is a pure function (parse_ebur128) with unit tests;
the measurement itself needs ffmpeg and is not run in tests.
"""
from __future__ import annotations

import re
import subprocess
import uuid
from pathlib import Path
from typing import Callable

from audiobook import paths

LUFS_TOL = 1.0
LRA_SPREAD_MAX = 3.0
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".aac"}

FLAG_LOUD = "громкость"
FLAG_PEAK = "пик"
FLAG_LRA_MIN = "LRA мин"
FLAG_LRA_MAX = "LRA макс"

_NUM = r"(-?inf|[-+]?\d+(?:\.\d+)?)"
_I = re.compile(r"^\s*I:\s*" + _NUM + r"\s*LUFS", re.M)
_LRA = re.compile(r"^\s*LRA:\s*" + _NUM + r"\s*LU\b", re.M)
_PEAK = re.compile(r"^\s*Peak:\s*" + _NUM + r"\s*dBFS", re.M)


def _num(s: str) -> float:
    return float(s)  # float() accepts "-inf" / "inf" as ffmpeg prints them


def parse_ebur128(stderr: str) -> dict[str, float]:
    """{'lufs', 'true_peak', 'lra'} from the ``Summary:`` block that ffmpeg's
    ebur128 filter prints at the end. Per-frame progress lines before it are
    ignored (only the last Summary counts). Raises ValueError if there is no
    summary or a value is missing; a silent file gives -inf/-70 values as
    ffmpeg prints them."""
    pos = stderr.rfind("Summary:")
    if pos == -1:
        raise ValueError("в выводе ffmpeg нет Summary ebur128")
    tail = stderr[pos:]
    out = {}
    for name, rx in (("lufs", _I), ("lra", _LRA), ("true_peak", _PEAK)):
        m = rx.search(tail)
        if not m:
            raise ValueError(f"в Summary ebur128 нет значения {name}")
        out[name] = _num(m.group(1))
    return out


def measure(path: Path, ff: str) -> dict[str, float]:
    """Run the ebur128 meter on one file (needs ffmpeg; not unit-tested)."""
    p = subprocess.run(
        [ff, "-hide_banner", "-nostats", "-i", str(path),
         "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise ValueError(f"ffmpeg код {p.returncode}: {p.stderr.strip()[-300:]}")
    return parse_ebur128(p.stderr)


# ------------------------------------------------------------------ pure logic

def evaluate(rows: list[dict], lufs: float, true_peak: float) -> float | None:
    """Add ``flags`` to every row in place; return the LRA spread across the
    chapter rows (None with fewer than two measured). Reference rows
    (kind == "ref") and rows with an error get no flags."""
    chapters = [r for r in rows if r["kind"] == "section" and not r.get("error")]
    for r in rows:
        r["flags"] = []
    for r in chapters:
        if abs(r["lufs"] - lufs) > LUFS_TOL:
            r["flags"].append(FLAG_LOUD)
        if r["true_peak"] > true_peak:
            r["flags"].append(FLAG_PEAK)
    lras = [r["lra"] for r in chapters]
    if len(lras) < 2:
        return None
    spread = max(lras) - min(lras)
    if spread > LRA_SPREAD_MAX:
        lo, hi = min(lras), max(lras)
        for r in chapters:
            if r["lra"] == lo:
                r["flags"].append(FLAG_LRA_MIN)
            if r["lra"] == hi:
                r["flags"].append(FLAG_LRA_MAX)
    return spread


def _fmt(v: float) -> str:
    return f"{v:.1f}"


def format_report(rows: list[dict], spread: float | None, lufs: float,
                  true_peak: float) -> str:
    lines = [f"цель: {_fmt(lufs)} LUFS ±{LUFS_TOL:.0f} LU, true peak ≤ {_fmt(true_peak)} dBTP, "
             f"разброс LRA по главам ≤ {LRA_SPREAD_MAX:.0f} LU",
             f"{'файл':<34} {'LUFS':>7} {'TP dBTP':>8} {'LRA LU':>7}  флаги"]
    last_kind = None
    for r in rows:
        if r["kind"] != last_kind:
            lines.append("— главы —" if r["kind"] == "section" else "— эталон (не оценивается) —")
            last_kind = r["kind"]
        name = r["name"][:34]
        if r.get("error"):
            lines.append(f"{name:<34} {'—':>7} {'—':>8} {'—':>7}  ошибка: {r['error']}")
            continue
        flags = ", ".join(r["flags"])
        lines.append(f"{name:<34} {_fmt(r['lufs']):>7} {_fmt(r['true_peak']):>8} "
                     f"{_fmt(r['lra']):>7}  {flags}")
    lines.append("")
    if spread is not None:
        mark = "  ПРЕВЫШЕН" if spread > LRA_SPREAD_MAX else ""
        lines.append(f"разброс LRA по главам: {_fmt(spread)} LU{mark}")
    flagged = [r for r in rows if r["flags"]]
    errors = [r for r in rows if r.get("error")]
    lines.append(f"глав: {sum(r['kind'] == 'section' for r in rows)}, с флагами: {len(flagged)}"
                 + (f", ошибок измерения: {len(errors)}" if errors else ""))
    return "\n".join(lines)


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(paths.ROOT).as_posix()
    except ValueError:
        return p.name


def write_tsv(rows: list[dict], path: Path) -> None:
    """Atomic: temp file next to the target, then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:6]}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write("kind\tname\tfile\tlufs\ttrue_peak\tlra\tflags\terror\n")
        for r in rows:
            vals = ["", "", ""] if r.get("error") else [
                _fmt(r["lufs"]), _fmt(r["true_peak"]), _fmt(r["lra"])]
            f.write("\t".join([r["kind"], r["name"], r["file"], *vals,
                               "; ".join(r["flags"]),
                               (r.get("error") or "").replace("\t", " ").replace("\n", " ")])
                    + "\n")
    tmp.replace(path)


# ------------------------------------------------------------------ collection

def collect(sections: list[str] | None, extra_dirs) -> list[tuple[str, str, Path]]:
    """[(kind, name, path)] — chapters first (by name), then reference files."""
    sec_root = paths.OUT / "sections"
    items: list[tuple[str, str, Path]] = []
    if sections:
        names = list(sections)
    else:
        names = sorted(d.name for d in sec_root.glob("*") if (d / "section.mp3").exists())
    for s in names:
        items.append(("section", s, sec_root / s / "section.mp3"))
    for d in extra_dirs or ():
        d = Path(d)
        files = [d] if d.is_file() else sorted(
            f for f in d.glob("*") if f.is_file() and f.suffix.lower() in AUDIO_EXT)
        for f in files:
            items.append(("ref", f.name, f))
    return items


def report(config: dict, sections: list[str] | None = None, extra_dirs=(),
           measure_fn: Callable[[Path], dict] | None = None) -> int:
    m = config["master"]
    lufs, true_peak = float(m["lufs"]), float(m["true_peak"])
    for d in extra_dirs or ():
        if not Path(d).exists():
            print(f"нет такого пути: {d}")
            return 2
    items = collect(sections, extra_dirs)
    if not items:
        print("нечего измерять: нет out/sections/*/section.mp3 (сначала master)")
        return 1
    if measure_fn is None:
        ff = paths.ffmpeg()
        if ff is None:
            raise SystemExit("ffmpeg не найден (bin/ или PATH)")
        measure_fn = lambda p: measure(p, str(ff))  # noqa: E731
    rows = []
    for kind, name, p in items:
        row = {"kind": kind, "name": name, "file": _rel(p), "error": None}
        if not p.exists():
            row["error"] = f"нет {p.name}"
        else:
            try:
                row.update(measure_fn(p))
            except ValueError as e:
                row["error"] = str(e)
        rows.append(row)
    spread = evaluate(rows, lufs, true_peak)
    print(format_report(rows, spread, lufs, true_peak))
    out = paths.OUT / "loudness" / "report.tsv"
    write_tsv(rows, out)
    print(f"таблица: {out}")
    return 0
