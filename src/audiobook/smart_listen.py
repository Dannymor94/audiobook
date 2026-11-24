"""Bounded offline review of an existing mastered chapter. No model or TTS."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import random
import re
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path

GAP_MS = 800
SEED = 20261124


@dataclass(frozen=True)
class Window:
    start: int
    end: int
    reasons: tuple[str, ...]


def merge(windows: list[Window]) -> list[Window]:
    out: list[Window] = []
    for w in sorted(windows, key=lambda x: (x.start, x.end, x.reasons)):
        if out and w.start <= out[-1].end:
            prev = out.pop()
            out.append(Window(prev.start, max(prev.end, w.end),
                              tuple(sorted(set(prev.reasons + w.reasons)))))
        else:
            out.append(w)
    return out


def cost(windows: list[Window]) -> int:
    return sum(w.end - w.start for w in windows) + GAP_MS * max(0, len(windows) - 1)


def select(rows: list[dict], index: dict[str, dict], mandatory: list[Window],
           budget_ms: int = 240000, random_count: int = 6) -> tuple[list[Window], dict]:
    """Mandatory windows, stratified unflagged controls, then ranked risks.
    Index uses mastered MP3 milliseconds. Selection is by occurrence, never text hash.
    """
    if not 0 < budget_ms <= 360000 or random_count < 0:
        raise ValueError("INVALID_BUDGET")
    if any(w.start < 0 or w.end <= w.start for w in mandatory):
        raise ValueError("INVALID_MANDATORY_WINDOW")
    chosen = merge(mandatory)
    if cost(chosen) > budget_ms:
        raise ValueError("MANDATORY_EXCEEDS_BUDGET")
    rates = [x["ms_per_char"] for x in rows if isinstance(x.get("ms_per_char"), (int, float))
             and math.isfinite(x["ms_per_char"]) and x["ms_per_char"] > 0]
    median = statistics.median(rates) if rates else None
    risks, clean = [], []
    missing = 0
    locked = 0
    for row in rows:
        cid = row["id"]
        ix = index[cid]
        start, end = ix["start_ms"], ix["start_ms"] + ix["dur_ms"]
        if row.get("locked"):
            locked += 1
            continue
        if not all(row.get(k) is not None for k in ("cer", "min_p", "ms_per_char", "peak", "flag_words")):
            missing += 1
        score, reasons = 0, []
        flags = row.get("flag_words") or []
        positions = []
        for f in flags:
            if len(f) >= 4 and f[3] in ("conf", "watch", "ending", "word"):
                why = f[3]
                score += {"word": 5, "ending": 3, "conf": 4, "watch": 2}[why]
                reasons.append(why)
                if isinstance(f[1], (int, float)) and math.isfinite(f[1]):
                    positions.append(({"word": 5, "ending": 3, "conf": 4, "watch": 2}[why],
                                      start - ix["lead_ms"] + round(f[1] * 1000)))
        if (row.get("cer") or 0) > 0.05:
            score += 6
            reasons.append("CER")
        if (row.get("min_p") if row.get("min_p") is not None else 1) < 0.35:
            score += 4
            reasons.append("low_confidence")
        rate = row.get("ms_per_char")
        if row.get("suspect") or (median and rate and (rate > 1.8 * median or rate < 0.5 * median)):
            score += 4
            reasons.append("pace")
        if (row.get("peak") or 0) >= 0.999:
            score += 6
            reasons.append("peak")
        if not all(row.get(k) is not None for k in ("cer", "min_p", "ms_per_char", "peak", "flag_words")):
            score += 2
            reasons.append("missing_metrics")
        # Keep whole short chunks; long chunks are centered at strongest flag.
        if end - start > 15000:
            center = max(positions)[1] if positions else (start + end) // 2
            a = min(max(start, center - 7500), end - 15000)
            b = a + 15000
        else:
            a, b = start, end
        if b <= a:
            raise ValueError("INVALID_INDEX_DURATION")
        if score:
            risks.append((score, cid, Window(a, b, tuple(sorted(set(reasons))))))
        else:
            clean.append(Window(a, b, ("random_control",)))
    def add(w: Window) -> bool:
        nonlocal chosen
        if any(w.start >= x.start and w.end <= x.end for x in chosen):
            return False
        proposal = merge(chosen + [w])
        if cost(proposal) <= budget_ms:
            chosen = proposal
            return True
        return False
    rng = random.Random(SEED)
    controls = 0
    for i in range(min(random_count, len(clean))):
        n = min(random_count, len(clean))
        group = clean[i * len(clean) // n:(i + 1) * len(clean) // n]
        eligible = [w for w in group if not any(w.start < x.end and w.end > x.start for x in chosen)]
        rng.shuffle(eligible)
        for w in eligible:
            if add(w):
                controls += 1
                break
    for _, _, w in sorted(risks, key=lambda x: (-x[0], x[1])):
        add(w)
    touched = sum(any(ix["start_ms"] < w.end and ix["start_ms"] + ix["dur_ms"] > w.start
                      for w in chosen) for ix in index.values())
    return chosen, {"rows": len(rows), "risk_rows": len(risks), "missing_metric_rows": missing,
                    "locked_rows": locked, "random_controls": controls,
                    "rows_touched": touched, "rows_not_touched": len(rows) - touched,
                    "duration_ms": cost(chosen), "windows": len(chosen),
                    "acoustic_stress_checked": 0}


def digest(p: Path) -> str:
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def time_label(ms: int) -> str:
    s = ms // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


def run(section_dir: Path, source: Path, expected_sha256: str, out: Path,
        head_ms: int, budget_ms: int, points: list[int], seams: list[str]) -> dict:
    import numpy as np
    import soundfile as sf
    from audiobook import paths
    from audiobook.listen import _decode
    from audiobook.master import encode_args
    from audiobook.suspects import read_index_identity, check_identity
    from audiobook.sync import read_index_full

    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or digest(source) != expected_sha256:
        raise ValueError("SOURCE_DIGEST_MISMATCH")
    manifest = section_dir / "manifest.jsonl"
    idx = section_dir / "section.index.tsv"
    initial = (digest(manifest), digest(idx))
    rows = [json.loads(x) for x in manifest.read_text(encoding="utf-8").splitlines() if x.strip()]
    ident = read_index_identity(idx)
    if not rows or any(r.get("status") != "done" for r in rows) or ident is None or check_identity(ident, rows, None):
        raise ValueError("INDEX_OR_MANIFEST_NOT_READY")
    index = read_index_full(idx)
    if head_ms < 0 or len(index) != len(rows) or list(index) != [r["id"] for r in rows]:
        raise ValueError("INVALID_INDEX")
    sr = 44100
    audio = _decode(source, sr)
    duration = len(audio) * 1000 // sr
    if not np.isfinite(audio).all() or not len(audio):
        raise ValueError("INVALID_AUDIO")
    last = 0
    for ix in index.values():
        ix["start_ms"] += head_ms
        if ix["dur_ms"] <= 0 or ix["start_ms"] < last:
            raise ValueError("INVALID_INDEX_INTERVAL")
        last = ix["start_ms"] + ix["dur_ms"]
        if last > duration:
            raise ValueError("INDEX_OUTSIDE_AUDIO")
    mandatory = []
    for t in points:
        if not 0 <= t < duration:
            raise ValueError("POINT_OUTSIDE_AUDIO")
        mandatory.append(Window(max(0, t - 5000), min(duration, t + 7000), ("owner_time",)))
    ids = list(index)
    for cid in seams:
        if cid not in index:
            raise ValueError("UNKNOWN_SEAM")
        ix = index[cid]
        mandatory.append(Window(max(0, ix["start_ms"] - 3500),
                                min(duration, ix["start_ms"] + ix["dur_ms"] + 3500),
                                ("repair_seam",)))
    windows, summary = select(rows, index, mandatory, budget_ms)
    if not windows:
        raise ValueError("EMPTY_SELECTION")
    if initial != (digest(manifest), digest(idx)) or digest(source) != expected_sha256:
        raise ValueError("SOURCE_CHANGED")
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    gap = np.zeros(GAP_MS * sr // 1000, dtype=np.float32)
    segments, entries = [], []
    pos = 0
    for n, w in enumerate(windows, 1):
        seg = audio[w.start * sr // 1000:w.end * sr // 1000]
        if n > 1:
            segments.append(gap)
            pos += len(gap)
        entries.append({"n": n, "pack_ms": pos * 1000 // sr, "source_start_ms": w.start,
                        "source_end_ms": w.end, "chunk_ids": ",".join(cid for cid, ix in index.items()
                        if ix["start_ms"] < w.end and ix["start_ms"] + ix["dur_ms"] > w.start),
                        "reason": ", ".join(w.reasons)})
        segments.append(seg)
        pos += len(seg)
    raw = out / "review.wav"
    sf.write(raw, np.concatenate(segments), sr, subtype="FLOAT")
    ff = paths.ffmpeg()
    if ff is None:
        raise ValueError("FFMPEG_UNAVAILABLE")
    mp3 = out / "review.mp3"
    subprocess.run(encode_args(str(ff), raw, mp3, "anull", sr), check=True, capture_output=True)
    decoded = _decode(mp3, sr)
    if len(decoded) > budget_ms * sr // 1000 + sr // 10:
        raise ValueError("PACK_EXCEEDS_BUDGET")
    raw.unlink()
    with (out / "index.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(entries[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(entries)
    body = []
    for e in entries:
        body.append(f'<tr><td>{e["n"]}</td><td><button data-ms="{e["pack_ms"]}">'
                    f'{time_label(e["pack_ms"])}</button></td><td>{time_label(e["source_start_ms"])}–'
                    f'{time_label(e["source_end_ms"])}</td><td>{html.escape(e["chunk_ids"])}</td>'
                    f'<td>{html.escape(e["reason"])}</td><td><select><option>—</option>'
                    '<option>OK</option><option>Ошибка</option></select></td>'
                    '<td><input placeholder="Слово / замечание"></td></tr>')
    page = """<!doctype html><html lang="ru"><meta charset="utf-8"><title>Проверка главы</title>
<style>body{font:16px system-ui;max-width:1000px;margin:24px auto;padding:12px}table{border-collapse:collapse;width:100%}td,th{padding:9px;border-bottom:1px solid #ccc;text-align:left}audio{width:100%;position:sticky;top:0;background:white}input{width:100%;min-width:100px}button,select,input{font:inherit}button{cursor:pointer}</style>
<h1>Выборочная проверка главы</h1><p>Нажмите время, прослушайте фрагмент и отметьте результат. Сохраните замечания кнопкой ниже.</p>
<audio id="audio" controls src="review.mp3"></audio><table><thead><tr><th>№</th><th>Подборка</th><th>Глава</th><th>Чанк</th><th>Причина</th><th>Оценка</th><th>Комментарий</th></tr></thead><tbody>"""
    page += "".join(body) + """</tbody></table><p><button id="save">Сохранить замечания</button></p>
<script>const a=document.getElementById('audio');document.querySelectorAll('[data-ms]').forEach(b=>b.onclick=()=>{a.currentTime=Number(b.dataset.ms)/1000;a.play()});document.getElementById('save').onclick=()=>{const rows=[...document.querySelectorAll('tbody tr')].map(r=>({n:r.cells[0].textContent,source:r.cells[2].textContent,chunks:r.cells[3].textContent,decision:r.querySelector('select').value,note:r.querySelector('input').value}));const url=URL.createObjectURL(new Blob([JSON.stringify(rows,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='review-notes.json';link.click();URL.revokeObjectURL(url)};</script></html>"""
    (out / "review.html").write_text(page, encoding="utf-8")
    summary.update(source_sha256=expected_sha256, manifest_sha256=initial[0], index_sha256=initial[1],
                   pack_sha256=digest(mp3), decoded_duration_ms=len(decoded)*1000//sr,
                   stress_limitation="Metadata screening only; no acoustic stress detection claimed.")
    (out / "READY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--section-dir", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--sha256", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--head-ms", type=int, required=True)
    p.add_argument("--budget-ms", type=int, default=240000)
    p.add_argument("--point-ms", type=int, action="append", default=[])
    p.add_argument("--seam", action="append", default=[])
    a = p.parse_args()
    print(json.dumps(run(a.section_dir, a.source, a.sha256, a.out, a.head_ms,
                         a.budget_ms, a.point_ms, a.seam), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
