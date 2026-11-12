"""Stress facts F1-F5, F6=not_run, resolve_expected and §9 status/reason matrix.

Public API:
  StressFacts           — dataclass, fields 22-35 of ADR §6 schema
  FACTS_FIELDS          — ordered list of TSV header names (fields 22-35)
  _classify_f1          — (trace, su_token_index) → (rule, phrase, flag)
  _classify_f2          — (f1_rule) → (approval, vowel)
  _classify_f3          — (form, verified_set) → bool
  compute_facts         — build StressFacts for one WordOcc
  apply_facts           — apply facts to a WordOcc, return new WordOcc
  resolve_expected      — ADR §9 T1/T2/T3 expected source resolution
  classify_status       — ADR §9 status/reason precedence matrix
  classify_status_reason — alias for classify_status
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from audiobook.sutrace import SUTrace

_WORD = re.compile(r"[а-яёА-ЯЁ]+")

FACTS_FIELDS = [
    "f1_rule", "f1_phrase", "f1_flag",
    "f2_approval", "f2_vowel",
    "f3_verified",
    "f5_vowel", "f5_status",
    "f6_vowel", "f6_status",
    "expected_source", "expected_vowel",
    "status", "reason",
]


@dataclass(frozen=True)
class StressFacts:
    """Fields 22-35 of ADR §6 occurrences schema."""
    f1_rule: str | None    # 22
    f1_phrase: bool        # 23
    f1_flag: str           # 24: "none" | "span_ambiguous"
    f2_approval: str       # 25: "approved" | "unknown" | "none"
    f2_vowel: int | None   # 26: null always today
    f3_verified: bool      # 27
    f5_vowel: int | None   # 28: null (dormant)
    f5_status: str         # 29: "none"
    f6_vowel: int | None   # 30: null
    f6_status: str         # 31: "not_run"
    expected_source: str   # 32: "decision"|"source_mark"|"conflict"|"ruaccent"|"none"
    expected_vowel: int | None  # 33
    status: str            # 34: "ok"|"covered_by_override"|"unresolved"
    reason: str            # 35: ""| reason code | ";" separated informational


# ---------------------------------------------------------------------------
# F3: safe read-only verified-forms loader (never creates missing files)
# ---------------------------------------------------------------------------

def _load_verified_safe(p: Path) -> set[str]:
    if not p.exists():
        return set()
    import yaml
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return set(str(w).lower() for w in (data.get("verified") or []))


# ---------------------------------------------------------------------------
# F1: classify via SUTrace matches (ADR U4)
# ---------------------------------------------------------------------------

def _classify_f1(
    trace: SUTrace | None,
    su_token_index: int,
) -> tuple[str | None, bool, str]:
    """Return (f1_rule, f1_phrase, f1_flag) for one word.

    f1_flag is "span_ambiguous" when any match partially overlaps the target
    token or fully covers it while also partially overlapping another token.
    Returns (None, False, "none") when trace is None or no match found.
    """
    if trace is None:
        return None, False, "none"

    if not trace.matches:
        return None, False, "none"

    post_pad = trace.prep_text[trace.pad_len:]
    words = list(_WORD.finditer(post_pad))
    if su_token_index >= len(words):
        return None, False, "none"

    target = words[su_token_index]
    # Absolute coordinates in prep_text
    abs_t_start = trace.pad_len + target.start()
    abs_t_end = trace.pad_len + target.end()

    best_rule: str | None = None
    is_phrase = False

    for match in trace.matches:
        ms, me = match["start"], match["end"]

        # No overlap with target
        if me <= abs_t_start or ms >= abs_t_end:
            continue

        # Partial overlap with target itself → span_ambiguous
        if ms > abs_t_start or me < abs_t_end:
            return None, False, "span_ambiguous"

        # Match fully covers target [abs_t_start, abs_t_end) ⊆ [ms, me)
        # Check if any OTHER token is partially covered by this match (ADR U4)
        partially_covered_other = False
        fully_covered_count = 0
        for i, w in enumerate(words):
            abs_w_start = trace.pad_len + w.start()
            abs_w_end = trace.pad_len + w.end()
            if me <= abs_w_start or ms >= abs_w_end:
                continue  # no overlap with this token
            if ms <= abs_w_start and me >= abs_w_end:
                # Fully covered
                fully_covered_count += 1
            else:
                # Partial overlap with another token → span_ambiguous
                if i != su_token_index:
                    partially_covered_other = True
                    break
                # Partial overlap with target already handled above

        if partially_covered_other:
            return None, False, "span_ambiguous"

        best_rule = match["key"]
        is_phrase = fully_covered_count > 1

    return best_rule, is_phrase, "none"


# ---------------------------------------------------------------------------
# F2: approval (R7 — no approval journal yet)
# ---------------------------------------------------------------------------

def _classify_f2(f1_rule: str | None) -> tuple[str, int | None]:
    """Return (f2_approval, f2_vowel).

    R7: no approval journal; f2_vowel always null.
    """
    approval = "unknown" if f1_rule is not None else "none"
    return approval, None


# ---------------------------------------------------------------------------
# F3: verified forms
# ---------------------------------------------------------------------------

def _classify_f3(form_analysis: str, verified_forms: set[str] | None) -> bool:
    """Return True when form_analysis (case-insensitive) is in verified_forms."""
    if not verified_forms:
        return False
    return form_analysis.lower() in verified_forms


# ---------------------------------------------------------------------------
# resolve_expected (ADR §9 T1/T2/T3)
# ---------------------------------------------------------------------------

def resolve_expected(
    f2_approval: str,
    f2_vowel: int | None,
    f5_status: str,
    f5_vowel: int | None,
    f6_status: str,
    f6_vowel: int | None,
) -> tuple[str, int | None]:
    """Return (expected_source, expected_vowel) per ADR §9 T1/T2/T3."""
    has_f5 = f5_status == "ok" and f5_vowel is not None
    has_f2 = f2_approval == "approved" and f2_vowel is not None
    if has_f5 or has_f2:
        if has_f5 and has_f2:
            if f5_vowel == f2_vowel:
                return "source_mark", f5_vowel
            else:
                return "conflict", None
        if has_f5:
            return "source_mark", f5_vowel
        return "decision", f2_vowel
    if f6_status == "resolved" and f6_vowel is not None:
        return "ruaccent", f6_vowel
    return "none", None


# ---------------------------------------------------------------------------
# §9 status/reason precedence matrix
# ---------------------------------------------------------------------------

def classify_status(
    alignment_status: str,
    f1_flag: str,
    f1_rule: str | None,
    expected_source: str,
    f6_status: str,
    f6_vowel: int | None,
    expected_vowel: int | None,
    f3_verified: bool,
) -> tuple[str, str]:
    """Return (status, reason) per ADR §9 precedence matrix."""
    # 1. Alignment error
    if alignment_status != "aligned":
        return "unresolved", alignment_status

    # 2. Span ambiguous
    if f1_flag == "span_ambiguous":
        return "unresolved", "override_span_ambiguous"

    # 3. Complete validated F1
    if f1_rule is not None and f1_flag == "none":
        return "covered_by_override", ""

    # 4. Expected conflict
    if expected_source == "conflict":
        return "unresolved", "conflict"

    # 5. F6 failure statuses
    if f6_status in ("no_stress", "multi_stress", "invalid_mark", "tokenization_mismatch"):
        return "unresolved", f6_status

    # 6. not_run → ruaccent_not_run
    if f6_status == "not_run":
        return "unresolved", "ruaccent_not_run"

    # 7. ok — collect informational reasons
    info: list[str] = []
    if expected_source in ("ruaccent", "decision", "source_mark") and expected_vowel is not None:
        if f6_vowel is not None and f6_vowel != expected_vowel:
            info.append("ruaccent_disagreement")
            if f3_verified:
                info.append("verified_disagreement")
    return "ok", ";".join(info)


# Alias used in direct test imports
classify_status_reason = classify_status


# ---------------------------------------------------------------------------
# compute_facts — build StressFacts for one word
# ---------------------------------------------------------------------------

def compute_facts(
    trace: SUTrace | None,
    su_token_index: int | None,
    alignment_status: str,
    form_analysis: str,
    verified_forms: set[str] | None = None,
) -> StressFacts:
    """Compute StressFacts for one WordOcc."""
    if verified_forms is None:
        verified_forms = set()

    f1_rule, f1_phrase, f1_flag = _classify_f1(
        trace if alignment_status == "aligned" else None,
        su_token_index or 0,
    )

    f2_approval, f2_vowel = _classify_f2(f1_rule)
    f3_verified = _classify_f3(form_analysis, verified_forms)

    f5_vowel: int | None = None
    f5_status = "none"

    f6_vowel: int | None = None
    f6_status = "not_run"

    expected_source, expected_vowel = resolve_expected(
        f2_approval, f2_vowel, f5_status, f5_vowel, f6_status, f6_vowel
    )

    status, reason = classify_status(
        alignment_status, f1_flag, f1_rule,
        expected_source, f6_status, f6_vowel, expected_vowel, f3_verified,
    )

    return StressFacts(
        f1_rule=f1_rule,
        f1_phrase=f1_phrase,
        f1_flag=f1_flag,
        f2_approval=f2_approval,
        f2_vowel=f2_vowel,
        f3_verified=f3_verified,
        f5_vowel=f5_vowel,
        f5_status=f5_status,
        f6_vowel=f6_vowel,
        f6_status=f6_status,
        expected_source=expected_source,
        expected_vowel=expected_vowel,
        status=status,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# apply_facts — populate fields 22-35 on a WordOcc
# ---------------------------------------------------------------------------

def apply_facts(
    occ: WordOcc,
    trace: SUTrace | None,
    verified_forms: set[str] | None = None,
) -> WordOcc:
    """Return a new WordOcc with stress-facts fields 22-35 populated."""
    facts = compute_facts(
        trace=trace,
        su_token_index=occ.su_token_index,
        alignment_status=occ.alignment_status,
        form_analysis=occ.form_analysis,
        verified_forms=verified_forms,
    )
    return dataclasses.replace(
        occ,
        f1_rule=facts.f1_rule,
        f1_phrase=facts.f1_phrase,
        f1_flag=facts.f1_flag,
        f2_approval=facts.f2_approval,
        f2_vowel=facts.f2_vowel,
        f3_verified=facts.f3_verified,
        f5_vowel=facts.f5_vowel,
        f5_status=facts.f5_status,
        f6_vowel=facts.f6_vowel,
        f6_status=facts.f6_status,
        expected_source=facts.expected_source,
        expected_vowel=facts.expected_vowel,
        status=facts.status,
        reason=facts.reason,
    )
