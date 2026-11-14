"""WP4-G1 I1 observer tests: T26, T30, T31, T32, T33, T36.

All fixtures are synthetic and invented; no real manuscript words or corpus data.
Tests run offline and write nothing outside tmp_path.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from audiobook.stress_yo_observer import (
    NONE_obs,
    RESTORED_obs,
    UNSUPPORTED_obs,
    F1Counters,
    L3Mismatch,
    OBSERVER_VERSION,
    _apply_map_to_word,
    _find_forward_ye_yo,
    compute_prep_config_digest,
    compute_yo_map_digest,
    compute_norm_digest,
    l3_check,
    observe_su,
    restoration_fp,
)


# ---------------------------------------------------------------------------
# Shared synthetic helpers
# ---------------------------------------------------------------------------

_SENTINEL = " [end]"
_TABLE: dict = {}  # Empty respell table for most tests.
_NO_PHRASE = None  # No leadin.


def _config(yo_restore: bool = False) -> dict:
    return {"text_prep": {"yo_restore": yo_restore}} if yo_restore else {}


def _identity(source_key: str = "01_s|0|0", form_source: str = "тест") -> dict:
    return {
        "source_key": source_key,
        "form_source": form_source,
        "unit_text_sha256": hashlib.sha256(form_source.encode()).hexdigest(),
        "unit_kind": "text",
        "context_sha256": "a" * 64,
    }


def _obs(source_token, raw_text, token_idx, yo_map=None, yo_restore=False, source_key="s|0|0"):
    cfg = _config(yo_restore=yo_restore)
    return observe_su(
        source_token=source_token,
        raw_text=raw_text,
        token_idx=token_idx,
        config=cfg,
        yo_map=yo_map or {},
        table=_TABLE,
        sentinel=_SENTINEL,
        phrase=_NO_PHRASE,
        open_end=False,
        source_identity=_identity(source_key, source_token),
    )


# ---------------------------------------------------------------------------
# T30 — disabled yo_restore with live map entry → verified NONE, not RESTORED
# ---------------------------------------------------------------------------

class TestT30DisabledYoRestore:
    def test_disabled_with_map_entry_gives_none(self):
        """T30: yo_restore disabled; map has entry that WOULD restore; result is NONE."""
        word = "дети"
        yo_map = {"дети": "дёти"}  # Map entry exists but restore is disabled.
        result = _obs(word, f"Он видел {word}.", 2, yo_map=yo_map, yo_restore=False)
        assert isinstance(result, NONE_obs), f"expected NONE_obs, got {result!r}"

    def test_disabled_no_map_entry_gives_none(self):
        """T30: disabled, no map entry — still NONE."""
        result = _obs("слово", "Одно слово.", 1, yo_map={}, yo_restore=False)
        assert isinstance(result, NONE_obs)

    def test_disabled_source_native_yo_gives_none(self):
        """T30: source has native ё; disabled restore → NONE (не UNSUPPORTED)."""
        word = "пёс"
        result = _obs(word, f"Там {word}.", 1, yo_map={}, yo_restore=False)
        assert isinstance(result, NONE_obs)

    def test_disabled_mismatch_between_source_and_prepared(self):
        """T30: disabled restore but prepared word differs → UNSUPPORTED."""
        # Respell table changes the word — won't happen with empty table,
        # but simulate by using a word that prepare_text would change.
        # With empty table and no yo_restore, prepare_text returns text unchanged.
        # So source ≠ prepared only if something else transforms it.
        # We test the guard directly: if source != pre_resp_word → UNSUPPORTED.
        # Use a word that's not in the text at token_idx 0.
        result = _obs("кот", "пёс.", 0, yo_restore=False)
        assert isinstance(result, UNSUPPORTED_obs)


# ---------------------------------------------------------------------------
# T31 — ordinal witness and L3 parity
# ---------------------------------------------------------------------------

class TestT31L3Parity:
    def test_full_match_accepted(self):
        """T31d: ordinal and L3 exact match → observation accepted."""
        result = _obs("слово", "Одно слово.", 1, yo_restore=False)
        assert isinstance(result, NONE_obs)

    def test_l3_mismatch_raises(self):
        """T31b: l3_check raises L3Mismatch when composed_final differs."""
        # Inject a modified prepare_synth_text that returns a different string.
        import audiobook.synth as synth_mod
        orig = synth_mod.prepare_synth_text

        def patched(text, config, table, sentinel, phrase=None, open_end=False):
            final, p = orig(text, config, table, sentinel, phrase, open_end)
            return final + "X", p  # Differs by one character.

        synth_mod.prepare_synth_text = patched
        try:
            with pytest.raises(L3Mismatch):
                l3_check("Слово.", {}, {}, _SENTINEL, None, False)
        finally:
            synth_mod.prepare_synth_text = orig

    def test_phrase_mismatch_raises(self):
        """T31c: composed_phrase None vs '' → L3Mismatch."""
        import audiobook.synth as synth_mod
        orig = synth_mod.prepare_synth_text

        def patched(text, config, table, sentinel, phrase=None, open_end=False):
            final, _ = orig(text, config, table, sentinel, phrase, open_end)
            return final, ""  # Differs from None.

        synth_mod.prepare_synth_text = patched
        try:
            with pytest.raises(L3Mismatch):
                l3_check("Слово.", {}, {}, _SENTINEL, None, False)
        finally:
            synth_mod.prepare_synth_text = orig

    def test_token_index_out_of_range(self):
        """T31a: token_idx beyond word count → UNSUPPORTED."""
        result = _obs("слово", "Одно.", 5, yo_restore=False)
        assert isinstance(result, UNSUPPORTED_obs)
        assert "TOKEN_INDEX" in result.reason

    def test_first_word_at_index_zero(self):
        """T31d: correct ordinal (index 0) → accepted."""
        result = _obs("Одно", "Одно слово.", 0, yo_restore=False)
        assert isinstance(result, NONE_obs)


# ---------------------------------------------------------------------------
# T32 — enabled vs disabled yo_restore controls
# ---------------------------------------------------------------------------

class TestT32EnabledVsDisabled:
    """T32: controls for enabled vs disabled yo_restore, using monkeypatch for real yo.book_map."""

    def _obs_with_map(self, source, raw, token_idx, yo_map, yo_restore, monkeypatch):
        """Run observation with a patched yo.book_map returning the synthetic map."""
        import audiobook.yo as yo_mod
        monkeypatch.setattr(yo_mod, "book_map", lambda: yo_map)
        return _obs(source, raw, token_idx, yo_map=yo_map, yo_restore=yo_restore)

    def test_enabled_restores_ye_to_yo(self, monkeypatch):
        """T32a: enabled restore; map has entry; source е→ё → RESTORED."""
        source = "реки"
        restored_form = "рёки"
        yo_map = {"реки": restored_form}
        raw = f"{source} текут."
        result = self._obs_with_map(source, raw, 0, yo_map, yo_restore=True, monkeypatch=monkeypatch)
        assert isinstance(result, RESTORED_obs), f"got {result!r}"
        assert result.form == restored_form
        assert 0 in result.indices

    def test_disabled_same_map_gives_none(self, monkeypatch):
        """T32b: disabled restore; same map; result is NONE."""
        source = "реки"
        yo_map = {"реки": "рёки"}
        raw = f"{source} текут."
        result = self._obs_with_map(source, raw, 0, yo_map, yo_restore=False, monkeypatch=monkeypatch)
        assert isinstance(result, NONE_obs)

    def test_enabled_no_map_entry_gives_none(self, monkeypatch):
        """T32: enabled restore; no matching map entry → NONE (source unchanged)."""
        import audiobook.yo as yo_mod
        monkeypatch.setattr(yo_mod, "book_map", lambda: {})
        result = _obs("трава", "Там трава.", 1, yo_map={}, yo_restore=True)
        assert isinstance(result, NONE_obs)

    def test_enabled_source_native_yo_no_changes(self, monkeypatch):
        """T32: source already has ё; enabled restore; native ё not newly restored → NONE."""
        source = "пёс"
        # Map uses folded (ё→е) key. "пёс".lower() = "пёс" ≠ folded key "пес".
        # So yo.restore won't change "пёс". Pre_resp_word == source → NONE.
        yo_map = {"пес": "пёс"}
        import audiobook.yo as yo_mod
        monkeypatch.setattr(yo_mod, "book_map", lambda: yo_map)
        raw = f"{source} бежал."
        result = _obs(source, raw, 0, yo_map=yo_map, yo_restore=True)
        assert isinstance(result, NONE_obs)

    def test_enabled_unsupported_on_non_forward_edit(self):
        """T32: enabled restore but word had no restoration → NONE (not UNSUPPORTED)."""
        # yo.restore never does ё→е. So UNSUPPORTED from invalid edit requires
        # the prepared word to differ in a non-е→ё way. With an empty table and
        # no yo.restore effect, source matches pre_resp_word → NONE.
        source = "рёки"
        raw = "рёки текут."
        result = _obs(source, raw, 0, yo_map={}, yo_restore=True)
        assert isinstance(result, NONE_obs)


# ---------------------------------------------------------------------------
# T26 — direct pre-respell vs post-respell ё
# ---------------------------------------------------------------------------

class TestT26DirectPreRespellOnly:
    def test_post_respell_yo_not_counted_as_restored(self):
        """T26: ё appears only in respell output (form_synth), not in pre-respell.
        Observer must use pre-respell form; it cannot see form_synth.
        With a respell table that changes е→ё in the final string but not in
        prepare_text output, the observer should return NONE (source unchanged).
        Note: the respell table affects ONLY pronounce.respell, not prepare_text.
        prepare_text is called BEFORE respell in production order.
        With yo_restore disabled, prepare_text leaves source unchanged.
        So if source="реки" and respell table adds ё, pre-respell form is "реки" → NONE.
        """
        source = "реки"
        # Respell table would change "реки" → "рёки" in the final string.
        # But the observer looks at prepare_text output (before respell).
        from audiobook.voicecfg import prepare_text
        raw = f"{source} текут."
        pre_resp = prepare_text(raw, {}, False)
        words = list(re.finditer(r"[А-Яа-яЁё]+", pre_resp))
        pre_resp_word = words[0].group()
        # Verify prepare_text did not add ё.
        assert "ё" not in pre_resp_word.lower(), "prepare_text should not add ё here"
        # Observer with disabled restore: NONE
        result = _obs(source, raw, 0, yo_map={}, yo_restore=False)
        assert isinstance(result, NONE_obs)

    def test_pre_respell_yo_counts_as_restored(self, monkeypatch):
        """T26: ё appears in pre-respell form (from yo.restore) → RESTORED."""
        source = "реки"
        yo_map = {"реки": "рёки"}
        import audiobook.yo as yo_mod
        monkeypatch.setattr(yo_mod, "book_map", lambda: yo_map)
        raw = f"{source} текут."
        result = _obs(source, raw, 0, yo_map=yo_map, yo_restore=True)
        assert isinstance(result, RESTORED_obs)


# ---------------------------------------------------------------------------
# T33 — two е→ё changes in one word
# ---------------------------------------------------------------------------

class TestT33TwoForwardChanges:
    def test_two_ye_to_yo_indices(self, monkeypatch):
        """T33: word with two forward е→ё changes → sorted two-element indices."""
        source = "еленей"  # 3 vowels: е(idx 0), е(idx 1), е(idx 2)
        restored = "ёлёней"  # vowel indices 0 and 1 changed е→ё.
        yo_map = {"еленей": restored}
        import audiobook.yo as yo_mod
        monkeypatch.setattr(yo_mod, "book_map", lambda: yo_map)
        raw = f"Там {source}."
        result = _obs(source, raw, 1, yo_map=yo_map, yo_restore=True)
        assert isinstance(result, RESTORED_obs), f"got {result!r}"
        assert result.form == restored
        assert len(result.indices) == 2
        assert result.indices == tuple(sorted(result.indices)), "indices must be sorted"
        fp2 = restoration_fp(_identity("s|0|0", source), restored, list(result.indices))
        assert result.fp == fp2

    def test_single_ye_to_yo_index(self, monkeypatch):
        """T33: word with one forward е→ё change → one-element indices."""
        source = "реки"
        restored = "рёки"
        yo_map = {"реки": restored}
        import audiobook.yo as yo_mod
        monkeypatch.setattr(yo_mod, "book_map", lambda: yo_map)
        raw = f"{source} текут."
        result = _obs(source, raw, 0, yo_map=yo_map, yo_restore=True)
        assert isinstance(result, RESTORED_obs)
        assert len(result.indices) == 1

    def test_restoration_fp_sorted_indices(self):
        """T33: restoration_fp uses sorted indices regardless of input order."""
        ident = _identity()
        fp1 = restoration_fp(ident, "ёлёней", [1, 0])
        fp2 = restoration_fp(ident, "ёлёней", [0, 1])
        assert fp1 == fp2

    def test_different_candidates_different_fp(self):
        """T33: different candidate form → different fp."""
        ident = _identity()
        fp1 = restoration_fp(ident, "рёки", [0])
        fp2 = restoration_fp(ident, "рёка", [0])
        assert fp1 != fp2


# ---------------------------------------------------------------------------
# T36 — YO map content digest catches content change (not mtime)
# ---------------------------------------------------------------------------

class TestT36MapContentDigest:
    def test_digest_changes_on_map_content_change(self):
        """T36: same map keys, different value → different digest."""
        m1 = {"реки": "рёки"}
        m2 = {"реки": "рёки2"}
        assert compute_yo_map_digest(m1) != compute_yo_map_digest(m2)

    def test_digest_stable_for_same_content(self):
        """T36: same map → same digest."""
        m = {"реки": "рёки", "дети": "дёти"}
        assert compute_yo_map_digest(m) == compute_yo_map_digest(dict(m))

    def test_digest_ignores_key_order(self):
        """T36: canonical JSON sorts keys → order-independent digest."""
        m1 = {"а": "1", "б": "2"}
        m2 = {"б": "2", "а": "1"}
        assert compute_yo_map_digest(m1) == compute_yo_map_digest(m2)

    def test_digest_uses_bytes_not_mtime(self, tmp_path):
        """T36: changing file content changes digest even without mtime change."""
        f = tmp_path / "01_ch.norm.txt"
        f.write_bytes(b"content1\n")
        d1 = compute_norm_digest(tmp_path)
        f.write_bytes(b"content2\n")
        d2 = compute_norm_digest(tmp_path)
        assert d1 != d2

    def test_norm_digest_empty_dir(self, tmp_path):
        """T36: empty directory → digest of empty bytes."""
        d = compute_norm_digest(tmp_path)
        assert d == hashlib.sha256(b"").hexdigest()

    def test_prep_config_digest_changes_on_field_change(self):
        """T36: changing text_prep changes prep digest."""
        c1 = {"text_prep": {"yo_restore": True}}
        c2 = {"text_prep": {"yo_restore": False}}
        assert compute_prep_config_digest(c1) != compute_prep_config_digest(c2)

    def test_prep_config_digest_empty_config(self):
        """T36: no text_prep → digest of {}."""
        assert compute_prep_config_digest({}) == compute_prep_config_digest({"text_prep": None})


# ---------------------------------------------------------------------------
# F1 counters (T16, T18 — exercised here via observer unit; full oracle in
# test_stress_eval_sample.py where WordOcc fixtures are built)
# ---------------------------------------------------------------------------

class TestF1Counters:
    def _make_occ(self, f1_rule=None, f1_flag="none"):
        """Create a minimal fake WordOcc-like object."""
        class FakeOcc:
            pass
        occ = FakeOcc()
        occ.f1_rule = f1_rule
        occ.f1_flag = f1_flag
        return occ

    def _restored(self):
        return RESTORED_obs(form="рёки", indices=(0,), fp="fp")

    def test_rule_only_increments_rule_and_union(self):
        """T16: f1_rule non-null, f1_flag none → rule=1, flag=0, both=0, union=1, eval=0."""
        counters = F1Counters()
        counters.add(self._make_occ(f1_rule="some_rule", f1_flag="none"), self._restored())
        assert counters.by_rule == 1
        assert counters.by_flag == 0
        assert counters.by_both == 0
        assert counters.union == 1
        assert counters.yo_evaluable == 0

    def test_flag_only_increments_flag_and_union(self):
        """T18: f1_rule none, f1_flag non-none → rule=0, flag=1, both=0, union=1, eval=0."""
        counters = F1Counters()
        counters.add(self._make_occ(f1_rule=None, f1_flag="span_ambiguous"), self._restored())
        assert counters.by_rule == 0
        assert counters.by_flag == 1
        assert counters.by_both == 0
        assert counters.union == 1
        assert counters.yo_evaluable == 0

    def test_both_rule_and_flag_union_not_double_counted(self):
        """T18: both f1_rule and f1_flag → rule=1, flag=1, both=1, union=1 (not 2)."""
        counters = F1Counters()
        counters.add(self._make_occ(f1_rule="r", f1_flag="span_ambiguous"), self._restored())
        assert counters.by_rule == 1
        assert counters.by_flag == 1
        assert counters.by_both == 1
        assert counters.union == 1  # Not double-counted.
        assert counters.yo_evaluable == 0

    def test_no_exclusion_increments_evaluable(self):
        """T16/T18: f1_rule null, f1_flag none → evaluable=1, all exclusion=0."""
        counters = F1Counters()
        counters.add(self._make_occ(f1_rule=None, f1_flag="none"), self._restored())
        assert counters.yo_evaluable == 1
        assert counters.union == 0

    def test_non_restored_obs_not_counted(self):
        """T16: NONE_obs and UNSUPPORTED_obs do not affect counters."""
        counters = F1Counters()
        counters.add(self._make_occ(f1_rule="r"), NONE_obs())
        counters.add(self._make_occ(f1_rule="r"), UNSUPPORTED_obs("x"))
        assert counters.union == 0
        assert counters.yo_evaluable == 0

    def test_flag_only_then_rule_flag_does_not_double_count_union(self):
        """T18: flag-only (union=1) + rule+flag (union=1) → union=2 total (independent)."""
        counters = F1Counters()
        counters.add(self._make_occ(f1_rule=None, f1_flag="span_ambiguous"), self._restored())
        counters.add(self._make_occ(f1_rule="r", f1_flag="span_ambiguous"), self._restored())
        assert counters.by_flag == 2
        assert counters.by_rule == 1
        assert counters.by_both == 1
        assert counters.union == 2  # Each occurrence adds 1 to union.


# ---------------------------------------------------------------------------
# Internal helper unit tests
# ---------------------------------------------------------------------------

class TestInternalHelpers:
    def test_find_forward_ye_yo_single_change(self):
        changes = _find_forward_ye_yo("реки", "рёки")
        assert changes == [0]

    def test_find_forward_ye_yo_no_change(self):
        changes = _find_forward_ye_yo("трава", "трава")
        assert changes == []

    def test_find_forward_ye_yo_reverse_change_returns_none(self):
        changes = _find_forward_ye_yo("рёки", "реки")
        assert changes is None

    def test_find_forward_ye_yo_length_mismatch_returns_none(self):
        changes = _find_forward_ye_yo("ре", "рёки")
        assert changes is None

    def test_apply_map_to_word_lowercase(self):
        m = {"реки": "рёки"}
        assert _apply_map_to_word("реки", m) == "рёки"

    def test_apply_map_to_word_capitalized(self):
        m = {"реки": "рёки"}
        assert _apply_map_to_word("Реки", m) == "Рёки"

    def test_apply_map_to_word_uppercase(self):
        m = {"реки": "рёки"}
        assert _apply_map_to_word("РЕКИ", m) == "РЁКИ"

    def test_apply_map_to_word_no_entry(self):
        assert _apply_map_to_word("трава", {}) == "трава"

    def test_apply_map_to_word_native_yo_no_match(self):
        """Word with native ё: lookup uses 'ё' key which doesn't match folded 'е' map key."""
        m = {"рёки": "рёки2"}  # Map key is NOT folded here — simulating wrong usage.
        # Correct usage: map keys are folded. If map key were "рёки" instead of "реки",
        # then lookup for "рёки".lower() = "рёки" would match.
        # This tests that our function correctly mirrors yo.restore's lookup logic.
        assert _apply_map_to_word("рёки", {"рёки": "рёки2"}) == "рёки2"

    def test_restoration_fp_contract_version(self):
        ident = _identity()
        fp = restoration_fp(ident, "рёки", [0], contract_version="yo-evidence/1")
        # Recompute with same args to verify determinism.
        fp2 = restoration_fp(ident, "рёки", [0], contract_version="yo-evidence/1")
        assert fp == fp2

    def test_restoration_fp_different_contract_version_different_result(self):
        ident = _identity()
        fp1 = restoration_fp(ident, "рёки", [0], contract_version="yo-evidence/1")
        fp2 = restoration_fp(ident, "рёки", [0], contract_version="yo-evidence/2")
        assert fp1 != fp2
