"""Synthetic review tests: no manuscript, no reference, no TTS."""
import hashlib
import json
import subprocess

import numpy as np
import pytest
import soundfile as sf

from audiobook import paths, smart_listen as sl


def fixture(n=40):
    rows = []
    index = {}
    for i in range(n):
        cid = f"{i+1:04d}"
        rows.append({"id": cid, "hash": "a" * 40, "seed": i, "status": "done",
                     "cer": 0.0, "min_p": 0.9, "ms_per_char": 60, "peak": 0.5,
                     "flag_words": [], "locked": False})
        index[cid] = {"start_ms": i*10000, "dur_ms": 8000, "lead_ms": 0}
    return rows, index


def test_selection_budget_mandatory_occurrence_and_random_controls():
    rows, index = fixture()
    rows[1]["flag_words"] = [["fixture", 1.0, 0.1, "conf"]]
    rows[2]["flag_words"] = [["fixture", 1.0, 0.1, "conf"]]
    rows[3]["locked"] = True
    mandatory = [sl.Window(0, 2000, ("known",)), sl.Window(1000, 4000, ("seam",))]
    chosen, summary = sl.select(rows, index, mandatory, 80000, 4)
    assert chosen == sl.select(rows, index, mandatory, 80000, 4)[0]
    assert sl.cost(chosen) <= 80000
    assert chosen[0] == sl.Window(0, 4000, ("known", "seam"))
    assert summary["random_controls"] == 4
    assert summary["risk_rows"] == 2
    assert any(w.start == 10000 for w in chosen)
    assert any(w.start == 20000 for w in chosen)
    assert not any(w.start <= 30000 < w.end for w in chosen)
    assert summary["acoustic_stress_checked"] == 0
    assert all(a.end < b.start for a, b in zip(chosen, chosen[1:]))


def test_mandatory_over_budget_never_dropped():
    rows, index = fixture()
    with pytest.raises(ValueError, match="MANDATORY_EXCEEDS_BUDGET"):
        sl.select(rows, index, [sl.Window(0, 20000, ("known",))], 10000)


def test_missing_metrics_are_not_clean_controls():
    rows, index = fixture(3)
    del rows[0]["cer"]
    rows[1]["locked"] = True
    chosen, summary = sl.select(rows, index, [], 240000)
    assert summary["missing_metric_rows"] == 1 and summary["random_controls"] == 1
    assert any("missing_metrics" in w.reasons for w in chosen)


def test_actual_mp3_pack_is_private_bounded_and_source_unchanged(tmp_path):
    ff = paths.ffmpeg()
    if ff is None:
        pytest.skip("ffmpeg unavailable")
    sec = tmp_path / "source"
    sec.mkdir()
    rows, index = fixture(3)
    manifest = sec / "manifest.jsonl"
    manifest.write_text("".join(json.dumps(r)+"\n" for r in rows), encoding="utf-8")
    idx = sec / "section.index.tsv"
    idx.write_text("id\tstart_ms\tlead_ms\thash16\tseed\tdur_ms\n" +
                   "".join(f"{r['id']}\t{i*10000}\t0\t{r['hash'][:16]}\t{r['seed'] or ''}\t8000\n"
                           for i, r in enumerate(rows)), encoding="utf-8")
    raw = sec / "original.wav"
    t = np.arange(30*24000)/24000
    sf.write(raw, (0.1*np.sin(2*np.pi*220*t)).astype(np.float32), 24000)
    source = sec / "section.mp3"
    subprocess.run([str(ff), "-v", "error", "-i", str(raw), "-c:a", "libmp3lame", str(source)],
                   check=True)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (manifest, idx, source)}
    dest = tmp_path / "pack"
    with pytest.raises(ValueError, match="SOURCE_DIGEST_MISMATCH"):
        sl.run(sec, source, "0"*64, dest, 0, 20000, [1000], [])
    assert not dest.exists()
    result = sl.run(sec, source, before[source], dest, 0, 20000, [1000], [])
    assert result["decoded_duration_ms"] <= 20100
    assert result["source_sha256"] == before[source]
    assert (dest/"READY.json").exists()
    assert (dest/"review.html").exists()
    assert (dest/"review.mp3").exists()
    assert all(sl.digest(p) == h for p,h in before.items())
    with pytest.raises(FileExistsError):
        sl.run(sec, source, before[source], dest, 0, 20000, [1000], [])
