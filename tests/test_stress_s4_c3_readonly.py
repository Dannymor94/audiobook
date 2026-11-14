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
