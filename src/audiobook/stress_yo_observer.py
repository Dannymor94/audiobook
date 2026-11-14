"""Pre-respell YO-restoration observer for WP4-G1.

Observation contract version: yo-observation/1.
Observer uses only production voicecfg/synth/leadin/pronounce paths; it does
not modify synthesis, source text, manifests, models, cache or audio.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from audiobook.wordprov import WordOcc

OBSERVER_VERSION = "yo-observation/1"

_VOWELS = frozenset("аеёиоуыэюя")
_WORD = re.compile(r"[А-Яа-яЁё]+")


def _h(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


# ---------------------------------------------------------------------------
# Observation result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NONE_obs:
    """Verified absence of forward restoration in the pre-respell path."""


@dataclass(frozen=True)
class RESTORED_obs:
    """Confirmed е→ё forward restoration before respell."""
    form: str               # Pre-respell form (restored)
    indices: tuple[int, ...]  # Sorted source-vowel indices changed
    fp: str                 # restoration_fp


@dataclass(frozen=True)
class UNSUPPORTED_obs:
    """Cannot safely determine restoration status."""
    reason: str


ObsResult = NONE_obs | RESTORED_obs | UNSUPPORTED_obs


# ---------------------------------------------------------------------------
# Digest helpers
# ---------------------------------------------------------------------------

def compute_yo_map_digest(yo_map: dict) -> str:
    """SHA-256 of canonical JSON of the YO map (bytes content, not mtime)."""
    return _h(yo_map)


def compute_prep_config_digest(config: dict) -> str:
    """SHA-256 of canonical JSON of the text_prep config section."""
    return _h(config.get("text_prep") or {})


def compute_norm_digest(text_dir: Path) -> str:
    """SHA-256 of sorted-concatenated content of all .norm.txt files."""
    files = sorted(text_dir.glob("*.norm.txt"))
    combined = b"".join(p.read_bytes() for p in files)
    return hashlib.sha256(combined).hexdigest()


# ---------------------------------------------------------------------------
# restoration_fp
# ---------------------------------------------------------------------------

def restoration_fp(
    source_identity: dict,
    candidate: str,
    indices: list[int],
    *,
    contract_version: str = OBSERVER_VERSION,
) -> str:
    """Canonical fingerprint for one restoration candidate (ADR §4.6)."""
    return _h({
        "algo": "yo-evidence/1",
        "observation_contract_version": contract_version,
        "source_identity": {k: source_identity[k] for k in (
            "source_key", "form_source", "unit_text_sha256",
            "unit_kind", "context_sha256",
        )},
        "restored_form_pre_respell": candidate,
        "restored_vowel_indices": sorted(indices),
    })


# ---------------------------------------------------------------------------
# L3 parity check
# ---------------------------------------------------------------------------

class L3Mismatch(Exception):
    pass


def l3_check(
    raw_text: str,
    config: dict,
    table: dict,
    sentinel: str,
    phrase,
    open_end: bool,
) -> None:
    """Verify observer's independent L3 composition matches prepare_synth_text.

    Raises L3Mismatch if the final UTF-8 bytes or phrase type/value differ.
    One-byte or phrase-type divergence is a hard error; no fuzzy fallback.
    """
    from audiobook import leadin
    from audiobook.voicecfg import prepare_text
    from audiobook.pronounce import respell
    from audiobook.synth import apply_sentinel, prepare_synth_text

    pre_resp = prepare_text(raw_text, config, open_end)
    p = leadin.fires(pre_resp, config) if phrase is leadin.AUTO else phrase
    base = leadin.pad(pre_resp, p) if p else pre_resp
    obs_final = apply_sentinel(respell(base, table), sentinel)
    obs_phrase = p

    prod_final, prod_phrase = prepare_synth_text(
        raw_text, config, table, sentinel, phrase, open_end
    )

    if obs_final.encode("utf-8") != prod_final.encode("utf-8"):
        raise L3Mismatch("COMPOSED_FINAL_MISMATCH")
    if obs_phrase != prod_phrase:
        raise L3Mismatch("COMPOSED_PHRASE_MISMATCH")


# ---------------------------------------------------------------------------
# Token-level helpers
# ---------------------------------------------------------------------------

def _apply_map_to_word(word: str, yo_map: dict) -> str:
    """Apply the YO map to one word (mirrors yo.restore for a single word)."""
    lower = word.lower()  # Map keys are folded (ё→е), so ё-words don't match.
    mapped = yo_map.get(lower)
    if mapped is None:
        return word
    if word.isupper() and len(word) > 1:
        return mapped.upper()
    return mapped[0].upper() + mapped[1:] if word[0].isupper() else mapped


def _find_forward_ye_yo(source: str, restored: str) -> list[int] | None:
    """Return source-vowel indices of forward е→ё changes, or None on invalid edit.

    Returns an empty list when texts are equal (no restoration).
    Returns None when any non-forward or non-е→ё character difference is found.
    Length mismatch also returns None.
    """
    s, r = source.lower(), restored.lower()
    if len(s) != len(r):
        return None
    changes: list[int] = []
    vowel_idx = 0
    for sc, rc in zip(s, r):
        is_vowel = sc in _VOWELS
        if is_vowel:
            if sc == "е" and rc == "ё":
                changes.append(vowel_idx)
            elif sc != rc:
                return None  # Non-forward change.
            vowel_idx += 1
        elif sc != rc:
            return None  # Non-vowel difference.
    return changes


# ---------------------------------------------------------------------------
# Single-SU observation
# ---------------------------------------------------------------------------

def observe_su(
    *,
    source_token: str,
    raw_text: str,
    token_idx: int,
    config: dict,
    yo_map: dict,
    table: dict,
    sentinel: str,
    phrase,
    open_end: bool,
    source_identity: dict,
) -> ObsResult:
    """Observe one source token's pre-respell restoration status.

    Performs a full L3 parity check for every call, including NONE cases.
    token_idx: 0-based Cyrillic-word index within prepare_text(raw_text) output,
               after leadin pad stripped (matches su_token_index in WordOcc).
    source_identity: dict with five source-identity fields (for restoration_fp).
    """
    from audiobook.voicecfg import prepare_text

    try:
        l3_check(raw_text, config, table, sentinel, phrase, open_end)
    except L3Mismatch as exc:
        return UNSUPPORTED_obs(str(exc))

    yo_restore_enabled = bool((config.get("text_prep") or {}).get("yo_restore"))

    pre_resp = prepare_text(raw_text, config, open_end)
    words = list(_WORD.finditer(pre_resp))
    if token_idx < 0 or token_idx >= len(words):
        return UNSUPPORTED_obs("TOKEN_INDEX_OUT_OF_RANGE")

    pre_resp_word = words[token_idx].group()
    source_nfc = unicodedata.normalize("NFC", source_token)
    pre_resp_nfc = unicodedata.normalize("NFC", pre_resp_word)

    if yo_restore_enabled:
        # Direct restoration branch: prepare_text applied yo.restore to raw_text.
        # Directly compare source token with prepared word to detect е→ё changes.
        changes = _find_forward_ye_yo(source_nfc, pre_resp_nfc)
        if changes is None:
            return UNSUPPORTED_obs("INVALID_EDIT_PATTERN")
        if not changes:
            return NONE_obs()  # Source-native ё or no entry in the map.
        return RESTORED_obs(
            form=pre_resp_nfc,
            indices=tuple(sorted(changes)),
            fp=restoration_fp(source_identity, pre_resp_nfc, changes),
        )
    else:
        # Disabled branch: prepare_text did NOT call yo.restore.
        # Verify the prepared word equals the unchanged source token.
        if source_nfc != pre_resp_nfc:
            return UNSUPPORTED_obs("PREPARED_WORD_MISMATCH_DISABLED")
        return NONE_obs()


# ---------------------------------------------------------------------------
# F1 exclusion counters
# ---------------------------------------------------------------------------

@dataclass
class F1Counters:
    """Track F1-excluded RESTORED occurrences and YO_EVALUABLE count."""
    by_rule: int = 0
    by_flag: int = 0
    by_both: int = 0
    union: int = 0
    yo_evaluable: int = 0

    def add(self, occ: "WordOcc", obs_result: ObsResult) -> None:
        """Update counters for one occurrence."""
        if not isinstance(obs_result, RESTORED_obs):
            return
        has_rule = occ.f1_rule is not None
        has_flag = occ.f1_flag != "none"
        if has_rule:
            self.by_rule += 1
        if has_flag:
            self.by_flag += 1
        if has_rule and has_flag:
            self.by_both += 1
        if has_rule or has_flag:
            self.union += 1
        else:
            self.yo_evaluable += 1
