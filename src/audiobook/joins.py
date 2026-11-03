"""Measure F0, tempo, and RMS continuity at within-paragraph chunk joins.

Usage:  ./run.sh joins --section NN_slug [--first N]
Output: out/sections/S/section.joins.tsv  and top-20 printed to console.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from audiobook import paths

_SR = 24_000        # synth output sample rate
_WINDOW_S = 0.5     # tail/head analysis window (seconds)
_FRAME = 1024       # yin / rms frame length
_HOP = 256
_FMIN = 65
_FMAX = 320
_TOP_N = 20         # rows printed to console


# ── audio helpers ─────────────────────────────────────────────────────────────

def _load_wav(path: Path) -> np.ndarray:
    import soundfile as sf
    y, sr = sf.read(str(path), dtype="float32")
    if y.ndim > 1:
        y = y[:, 0]
    if sr != _SR:
        import librosa
        y = librosa.resample(y, orig_sr=sr, target_sr=_SR)
    return y


def _f0_rms(y: np.ndarray):
    """F0 array (NaN on silence/unvoiced) and RMS array — same shape."""
    import librosa
    f0 = librosa.yin(y, fmin=_FMIN, fmax=_FMAX, sr=_SR, frame_length=_FRAME)
    rms = librosa.feature.rms(y=y, frame_length=_FRAME, hop_length=_HOP)[0]
    n = min(len(f0), len(rms))
    f0, rms = f0[:n], rms[:n]
    pos = rms[rms > 0]
    if pos.size:
        f0[rms < 0.3 * np.median(pos)] = np.nan
    return f0, rms


def _to_semitones(f0: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(np.isnan(f0) | (f0 <= 0), np.nan,
                        12.0 * np.log2(f0 / 27.5))


def _f0_median_st(y: np.ndarray) -> float:
    f0, _ = _f0_rms(y)
    st = _to_semitones(f0)
    v = st[~np.isnan(st)]
    return float(np.median(v)) if v.size else float("nan")


def _f0_slope_st_per_s(y: np.ndarray) -> float:
    """Linear slope of F0 in semitones/s over the window."""
    f0, _ = _f0_rms(y)
    st = _to_semitones(f0)
    idx = np.where(~np.isnan(st))[0]
    if idx.size < 4:
        return float("nan")
    t = idx * (_HOP / _SR)
    return float(np.polyfit(t, st[idx], 1)[0])


def _rms_db(y: np.ndarray) -> float:
    return 20.0 * np.log10(float(np.sqrt(np.mean(y ** 2))) + 1e-9)


def _voiced_dur_s(y: np.ndarray) -> float:
    """Duration of voiced (non-silent) frames in seconds."""
    import librosa
    rms = librosa.feature.rms(y=y, frame_length=_FRAME, hop_length=_HOP)[0]
    pos = rms[rms > 0]
    if not pos.size:
        return 0.0
    return float(np.sum(rms >= 0.3 * np.median(pos)) * _HOP / _SR)


def _window(y: np.ndarray, from_end: bool) -> np.ndarray:
    n = int(_WINDOW_S * _SR)
    return y[-n:] if from_end else y[:n]


# ── metrics for one join ───────────────────────────────────────────────────────

def _join_row(y_i: np.ndarray, y_j: np.ndarray,
              text_i: str, text_j: str) -> dict:
    tail = _window(y_i, from_end=True)
    head = _window(y_j, from_end=False)

    f0_tail = _f0_median_st(tail)
    f0_head = _f0_median_st(head)

    vd_i = _voiced_dur_s(y_i)
    vd_j = _voiced_dur_s(y_j)
    ci = len(text_i.strip())
    cj = len(text_j.strip())
    tempo_i = ci / vd_i if vd_i > 0 else float("nan")
    tempo_j = cj / vd_j if vd_j > 0 else float("nan")
    tempo_diff_pct = (
        (tempo_j - tempo_i) / tempo_i * 100.0
        if (not np.isnan(tempo_i) and tempo_i > 0) else float("nan")
    )

    return {
        "f0_tail_st": f0_tail,
        "f0_head_st": f0_head,
        "f0_diff_st": f0_head - f0_tail,
        "slope_tail_st_s": _f0_slope_st_per_s(tail),
        "rms_tail_db": _rms_db(tail),
        "rms_head_db": _rms_db(head),
        "rms_diff_db": _rms_db(head) - _rms_db(tail),
        "tempo_i": tempo_i,
        "tempo_j": tempo_j,
        "tempo_diff_pct": tempo_diff_pct,
    }


# ── paragraph-pair detection ───────────────────────────────────────────────────

def _within_para_pairs(units: list[dict], config: dict) -> list[tuple[int, int]]:
    """Return manifest index pairs (k, k+1) that are adjacent chunks of the
    same prose paragraph.  Uses chunker structure, not a raw ms threshold."""
    from audiobook.chunker import build_chunks, chunk_prose, limits, split_step_label

    chunks = build_chunks(units, config)
    pauses = (config or {}).get("pauses_ms") or {}
    p_par = int(pauses.get("paragraph", 900))
    p_step = pauses.get("step_label")
    lim = limits(config)

    unit_of: list[int] = []
    for ui, u in enumerate(units):
        t = u["type"]
        if t == "heading":
            # _heading_chunks may split one heading into several; we don't
            # care about heading pairs — just count them correctly.
            from audiobook.chunker import _heading_chunks
            n = len(_heading_chunks(u["text"], 0, pauses))
            unit_of.extend([ui] * n)
        elif t == "stack":
            unit_of.append(ui)
        else:  # paragraph, flow, chain, prose_with_arrow
            text = u["text"]
            extra = 0
            if p_step:
                label, text = split_step_label(text)
                if label:
                    unit_of.append(ui)
                    extra = 1  # noqa: F841 (helps readability)
            pieces = chunk_prose(text, lim)
            unit_of.extend([ui] * len(pieces))

    assert len(unit_of) == len(chunks), (
        f"unit tracking mismatch: {len(unit_of)} vs {len(chunks)}"
    )

    pairs = []
    for k in range(len(chunks) - 1):
        if (unit_of[k] == unit_of[k + 1]
                and chunks[k].get("kind") == "text"
                and chunks[k + 1].get("kind") == "text"
                # redundant with unit equality, but defensive
                and chunks[k]["pause_after_ms"] < p_par):
            pairs.append((k, k + 1))
    return pairs


# ── flags ─────────────────────────────────────────────────────────────────────

def _flags(row: dict, thresholds: dict) -> str:
    flags = []
    if abs(row["f0_diff_st"]) >= thresholds.get("f0_jump_st", 4.0):
        flags.append("F0_JUMP")
    if row["slope_tail_st_s"] <= -thresholds.get("slope_fall_st_s", 8.0):
        flags.append("FALL_END")
    if abs(row["rms_diff_db"]) >= thresholds.get("rms_jump_db", 6.0):
        flags.append("RMS_JUMP")
    if (not np.isnan(row["tempo_diff_pct"])
            and abs(row["tempo_diff_pct"]) >= thresholds.get("tempo_diff_pct", 25.0)):
        flags.append("TEMPO_DIFF")
    return ",".join(flags)


# ── main ──────────────────────────────────────────────────────────────────────

def run(config: dict, section: str, first: int | None = None) -> int:
    from audiobook.chunker import load_units, section_config, _read_manifest
    from audiobook.assemble import preview_name

    sec_dir = paths.OUT / "sections" / section
    manifest_path = sec_dir / "manifest.jsonl"
    if not manifest_path.exists():
        raise SystemExit(f"joins: манифест не найден: {manifest_path}")

    manifest = _read_manifest(manifest_path)
    if first is not None:
        manifest = manifest[:first]

    done_rows = [r for r in manifest if r.get("status") == "done"]
    if not done_rows:
        raise SystemExit("joins: нет чанков со status=done — сначала synth+qc")

    nn, slug = section.split("_", 1)
    units = load_units(nn, slug)
    sec_cfg = section_config(config, section)

    pairs = _within_para_pairs(units, sec_cfg)

    thresholds = (config.get("qc") or {}).get("joins") or {}

    # Accumulate timestamps from duration_ms
    timestamps_ms: list[float] = []
    acc = 0.0
    for r in manifest:
        acc += r.get("duration_ms") or 0.0
        timestamps_ms.append(acc)

    chunks_dir = sec_dir / "chunks"
    results = []
    skipped = 0
    for k, m in pairs:
        if k >= len(manifest) or m >= len(manifest):
            continue
        ri, rj = manifest[k], manifest[m]
        wav_i = chunks_dir / f"{ri['id']}.wav"
        wav_j = chunks_dir / f"{rj['id']}.wav"
        if not wav_i.exists() or not wav_j.exists():
            skipped += 1
            continue

        y_i = _load_wav(wav_i)
        y_j = _load_wav(wav_j)
        row = _join_row(y_i, y_j, ri["text"], rj["text"])
        row["id_i"] = ri["id"]
        row["id_j"] = rj["id"]
        ts_ms = timestamps_ms[k]
        row["time"] = f"{int(ts_ms // 60000)}:{int(ts_ms // 1000 % 60):02d}"
        row["flags"] = _flags(row, thresholds)
        results.append(row)

    if skipped:
        print(f"joins: пропущено {skipped} пар (нет wav)")

    stem = preview_name(first)
    out_path = sec_dir / f"{stem}.joins.tsv"
    _write_tsv(results, out_path)
    print(f"joins: {len(results)} пар → {out_path}")
    _print_top(results, thresholds)
    return 0


_COLS = [
    "time", "id_i", "id_j",
    "f0_tail_st", "f0_head_st", "f0_diff_st", "slope_tail_st_s",
    "rms_tail_db", "rms_head_db", "rms_diff_db",
    "tempo_i", "tempo_j", "tempo_diff_pct",
    "flags",
]


def _fmt(v) -> str:
    if isinstance(v, float):
        return "nan" if np.isnan(v) else f"{v:.2f}"
    return str(v)


def _write_tsv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\t".join(_COLS) + "\n")
        for r in rows:
            f.write("\t".join(_fmt(r.get(c, "")) for c in _COLS) + "\n")


def _sort_key(r: dict) -> float:
    """Score for sorting: weight flagged joins first, then by F0 jump magnitude."""
    flag_score = len(r["flags"].split(",")) if r["flags"] else 0
    f0 = abs(r.get("f0_diff_st", 0) or 0)
    return -(flag_score * 100 + f0)


def _print_top(rows: list[dict], thresholds: dict) -> None:
    if not rows:
        print("joins: нет пар для вывода")
        return
    flagged = [r for r in rows if r["flags"]]
    top = sorted(rows, key=_sort_key)[:_TOP_N]
    print(f"\nТоп-{min(_TOP_N, len(top))} стыков  "
          f"(всего с флагами: {len(flagged)}/{len(rows)}):")
    print(f"{'время':<8} {'id_i':>4} {'id_j':>4}  "
          f"{'ΔF0,st':>7} {'наклон':>7} {'ΔRMS,dB':>8} {'Δтемп,%':>8}  флаги")
    print("-" * 70)
    for r in top:
        print(
            f"{r['time']:<8} {r['id_i']:>4} {r['id_j']:>4}  "
            f"{_fmt(r['f0_diff_st']):>7} {_fmt(r['slope_tail_st_s']):>7} "
            f"{_fmt(r['rms_diff_db']):>8} {_fmt(r['tempo_diff_pct']):>8}  "
            f"{r['flags']}"
        )
