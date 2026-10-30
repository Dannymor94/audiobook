"""Reading pace per chapter: does one chapter run faster or slower than the rest?

    ./run.sh pace   → table + out/pace.tsv

Uses ms per character of rendered chunks (qc stores it), only chunks of at
least MIN_CHARS characters — short headings are dominated by edge silence.
Flags chapters whose median deviates from the book median by more than
FLAG_PCT. Read-only except the tsv.
"""
from __future__ import annotations

import statistics

from audiobook import paths

MIN_CHARS = 60
FLAG_PCT = 8.0


def section_rates(rows: list[dict]) -> list[float]:
    return [float(r["ms_per_char"]) for r in rows
            if r.get("status") == "done" and r.get("ms_per_char")
            and len(r.get("text", "")) >= MIN_CHARS]


def table(per_section: dict[str, list[float]]) -> tuple[float, list[dict]]:
    """(book median, [{section, n, median, dev_pct, flag}])."""
    every = [x for v in per_section.values() for x in v]
    book = statistics.median(every) if every else 0.0
    out = []
    for s, v in per_section.items():
        if not v:
            continue
        med = statistics.median(v)
        dev = (med / book - 1) * 100 if book else 0.0
        out.append({"section": s, "n": len(v), "median": round(med, 1),
                    "dev_pct": round(dev, 1), "flag": abs(dev) > FLAG_PCT})
    return book, out


def run(config: dict) -> int:
    from audiobook.synth import _read_manifest
    per = {}
    for m in sorted((paths.OUT / "sections").glob("*/manifest.jsonl")):
        per[m.parent.name] = section_rates(_read_manifest(m))
    book, rows = table(per)
    if not rows:
        print("нет отрендеренных чанков с ms_per_char (нужен qc)")
        return 1
    print(f"{'секция':<44} {'чанков':>6} {'мс/симв':>8} {'откл.':>7}")
    for r in rows:
        print(f"{r['section'][:44]:<44} {r['n']:>6} {r['median']:>8} {r['dev_pct']:>+6.1f}%"
              + ("  ← темп отличается" if r["flag"] else ""))
    print(f"\nмедиана книги: {book:.1f} мс/симв (~{1000 / book:.1f} симв/с)" if book else "")
    out = paths.OUT / "pace.tsv"
    tmp = out.with_name(out.name + ".part")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("section\tn\tmedian_ms_per_char\tdev_pct\tflag\n")
        for r in rows:
            f.write(f"{r['section']}\t{r['n']}\t{r['median']}\t{r['dev_pct']}\t{int(r['flag'])}\n")
    tmp.replace(out)
    print(f"→ {out}")
    return 0
