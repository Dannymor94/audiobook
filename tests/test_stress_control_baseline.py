from collections import defaultdict

import pytest

from audiobook.stress_control_baseline import ACUTE, CASES, snapshot_hashes, trial_plan


def test_paired_probe_changes_only_accent_mark():
    rows = trial_plan(42)
    assert len(rows) == 2 * len(CASES) == 16
    assert rows == trial_plan(42)
    assert len({r["id"] for r in rows}) == 16
    groups = defaultdict(dict)
    for row in rows:
        groups[row["case"]][row["condition"]] = row
    for pair in groups.values():
        a, b = pair["plain"], pair["acute"]
        assert b["text"].replace(ACUTE, "") == a["text"]
        assert a["seed"] == b["seed"]
        assert a["expected_index"] == b["expected_index"]
        pos = a["source_start"] + a["expected_index"]
        assert b["text"][pos + 1] == ACUTE
        assert a["text"][a["source_start"]:a["source_end"]] == a["expected_word"]
    assert groups["castle"]["plain"]["expected_index"] != groups["lock"]["plain"]["expected_index"]


def test_snapshot_requires_local_safetensors(tmp_path):
    (tmp_path / "config.json").write_text("{}")
    with pytest.raises(ValueError, match="EXPECTED_EXISTING"):
        snapshot_hashes(tmp_path)
    (tmp_path / "model.safetensors").write_bytes(b"fixture")
    hashes = snapshot_hashes(tmp_path)
    assert set(hashes) == {"config.json", "model.safetensors"}
    (tmp_path / "model.safetensors").write_bytes(b"changed")
    assert snapshot_hashes(tmp_path) != hashes
