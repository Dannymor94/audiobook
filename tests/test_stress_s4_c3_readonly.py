"""T15-7 S4 census: source-free synthetic proof of read-only counts.

No manuscript, owner S4 or production files accessed by these helper tests.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from stress_s4_c3_readonly import (
    AuditBlocked, _ledger_numbers, _read_gold_table, _todo_numbers,
)

FIELDS = (
    "source_key", "form_source", "unit_text_sha256", "unit_kind",
    "context_sha256", "context", "gold_vowel", "yo_correct",
    "labeler", "date",
)


class FakeEval:
    GOLD_FIELDS = FIELDS
    IDENTITY_FIELDS = FIELDS[:5]
    LABEL_FIELDS = FIELDS[6:]

    @staticmethod
    def validate_gold(row, **_):
        if row["gold_vowel"] == "INVALID":
            raise ValueError("synthetic invalid gold")
        return row


def synthetic_row(key="k1", stress="0", identity="A"):
    result = {field: identity for field in FIELDS}
    result.update(
        source_key=key, gold_vowel=stress, yo_correct="na",
        labeler="synthetic", date="2026-01-01",
    )
    return result


class Source:
    def resolve(self, key):
        if key == "old":
            return None
        return {**{field: "A" for field in FIELDS[:5]}, "source_key": key}, None, None


class Context:
    sources = Source()


def test_absent_file_is_not_mistaken_for_a_present_empty_ledger(tmp_path):
    table, digest = _read_gold_table(tmp_path / "missing.tsv", FIELDS)
    assert table == {"exists": False, "rows": []}
    assert digest is None


def test_exact_tsv_header_and_read_bytes(tmp_path):
    file = tmp_path / "synthetic.tsv"
    row = synthetic_row()
    original = "\t".join(FIELDS) + "\n" + "\t".join(row[field] for field in FIELDS) + "\n"
    file.write_text(original, encoding="utf-8")
    table, digest = _read_gold_table(file, FIELDS)
    assert table["rows"] == [row]
    assert len(digest) == 32
    assert file.read_text(encoding="utf-8") == original


def test_repeated_keys_and_historical_identities_counted_separately():
    rows = [
        synthetic_row("k1"), synthetic_row("k1", identity="B"),
        synthetic_row("k1"), synthetic_row("k2"), synthetic_row("old"),
    ]
    counts = _ledger_numbers(rows, Context(), FakeEval)
    assert counts["rows"] == 5
    assert counts["unique_source_keys"] == 3
    assert counts["source_keys_repeated"] == 1
    assert counts["repeated_key_rows_extra"] == 2
    assert counts["keys_with_multiple_source_identities"] == 1
    assert counts["extra_historical_identities"] == 1
    assert counts["currently_stale_rows"] == 2
    assert counts["current_identity_rows"] == 3


def test_active_conflict_is_counted_not_auto_resolved():
    counts = _ledger_numbers(
        [synthetic_row("k1", "0"), synthetic_row("k1", "1")],
        Context(), FakeEval,
    )
    assert counts["active_conflicting_keys"] == 1


def test_human_filled_todo_not_merged_versus_blank():
    merged = synthetic_row("k1")
    pending = synthetic_row("k2")
    blank = synthetic_row("old")
    blank.update({field: "" for field in FIELDS[6:]})
    counts = _todo_numbers(
        [merged, pending, blank], [merged], FakeEval, {"k1", "k2", "old"},
    )
    assert counts["rows"] == 3
    assert counts["filled_rows"] == 2
    assert counts["filled_not_merged"] == 1
    assert counts["blank_rows"] == 1
    assert counts["partially_filled_rows"] == 0


def test_partial_todo_and_invalid_label_are_visible():
    partial = synthetic_row("k1")
    partial["date"] = ""
    invalid = synthetic_row("k2", "INVALID")
    counts = _todo_numbers([partial, invalid], [], FakeEval, {"k1", "k2"})
    assert counts["partially_filled_rows"] == 1
    assert counts["filled_invalid"] == 1
    assert counts["filled_not_merged"] == 1


@pytest.mark.parametrize("payload,code", [
    ("invalid\n", "S4_HEADER_INVALID"),
    ("\t".join(FIELDS) + "\nshort\trow\n", "S4_ROW_WIDTH_INVALID"),
    ("\t".join(FIELDS) + "\n", None),
])
def test_no_silent_header_or_width_repair(tmp_path, payload, code):
    path = tmp_path / "bookless.tsv"
    path.write_text(payload, encoding="utf-8")
    if code is None:
        table, _ = _read_gold_table(path, FIELDS)
        assert table["rows"] == []
    else:
        with pytest.raises(AuditBlocked, match=code):
            _read_gold_table(path, FIELDS)


def test_symlink_refused(tmp_path):
    target = tmp_path / "target.tsv"
    target.write_text("\t".join(FIELDS) + "\n", encoding="utf-8")
    link = tmp_path / "link.tsv"
    link.symlink_to(target)
    with pytest.raises(AuditBlocked, match="S4_SYMLINK_UNSUPPORTED"):
        _read_gold_table(link, FIELDS)



@pytest.mark.parametrize("rule,flag,excluded,by_rule,by_flag", [
    (None, "none", 0, 0, 0),
    ("synthetic_rule", "none", 1, 1, 0),
    (None, "span_ambiguous", 1, 0, 1),
    ("synthetic_rule", "span_ambiguous", 1, 1, 1),
])
def test_selected_restored_f1_exclusion_truth_table(
    tmp_path, monkeypatch, rule, flag, excluded, by_rule, by_flag,
):
    """Exact pre-respell ё only; never guess from post-respell WordOcc."""
    import dataclasses
    import json
    from audiobook import paths, stress_eval as evaluation, yo
    from stress_s4_c3_readonly import _selected_yo_exclusions
    from test_stress_eval_sample import context_for

    raw = "Елепа."
    context = context_for([{"type": "text", "text": raw}])
    occ = dataclasses.replace(context.rows[0], f1_rule=rule, f1_flag=flag)
    context = dataclasses.replace(context, rows=(occ,))
    selection = evaluation._selection(context)
    section = tmp_path / "sections" / "01_test"
    section.mkdir(parents=True)
    (section / "manifest.jsonl").write_text(
        json.dumps({"id": "0001", "text": raw}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "OUT", tmp_path)
    mapping = {"елепа": "ёлепа"}
    monkeypatch.setattr(yo, "book_map", lambda: mapping)
    result = _selected_yo_exclusions(
        {"text_prep": {"yo_restore": True}}, context, selection, mapping,
    )
    assert result["selected_checked"] == 1
    assert result["selected_restored"] == 1
    assert result["excluded_union"] == excluded
    assert result["excluded_f1_rule"] == by_rule
    assert result["excluded_f1_flag"] == by_flag
    assert result["excluded_both"] == int(by_rule and by_flag)
    assert result["yo_evaluable"] == 1 - excluded


def test_disabled_yo_restore_is_not_misclassified_as_restoration(tmp_path, monkeypatch):
    import json
    from audiobook import paths, stress_eval as evaluation
    from stress_s4_c3_readonly import _selected_yo_exclusions
    from test_stress_eval_sample import context_for

    raw = "Елепа."
    context = context_for([{"type": "text", "text": raw}])
    section = tmp_path / "sections" / "01_test"
    section.mkdir(parents=True)
    (section / "manifest.jsonl").write_text(
        json.dumps({"id": "0001", "text": raw}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "OUT", tmp_path)
    result = _selected_yo_exclusions(
        {"text_prep": {"yo_restore": False}}, context,
        evaluation._selection(context), {"елепа": "ёлепа"},
    )
    assert result["selected_checked"] == 1
    assert result["selected_restored"] == 0
    assert result["yo_evaluable"] == 0
    assert result["excluded_union"] == 0



def test_missing_owner_gold_mount_blocks_audit_before_any_inventory_read(tmp_path, monkeypatch):
    from audiobook import paths
    from stress_s4_c3_readonly import audit_local

    monkeypatch.setattr(paths, "TEXT", tmp_path)
    with pytest.raises(AuditBlocked, match="AUTHORITATIVE_GOLD_NOT_MOUNTED"):
        audit_local({})


def test_missing_owner_todo_mount_blocks_even_with_empty_gold_header(tmp_path, monkeypatch):
    from audiobook import paths
    from stress_s4_c3_readonly import audit_local

    monkeypatch.setattr(paths, "TEXT", tmp_path)
    (tmp_path / "stress_gold.tsv").write_text("\t".join(FIELDS) + "\n", encoding="utf-8")
    with pytest.raises(AuditBlocked, match="OWNER_TODO_NOT_MOUNTED"):
        audit_local({})
