---
id: T15-7-WP4-YO-ADR-ESCALATION
title: Decide immutable human stress truth under changing yo restoration
status: todo
owner: claude-chat-architect
agent: architect
branch: task/T15
order: 15
depends_on: [T15-7-WP4]
estimate_active_h: 1-3
estimate_qa_h: 1-2
actual_active_h: unknown
actual_elapsed_h: unknown
---

# T15-7 WP-4 F1 — Narrow Architecture Decision Required

**Decision maker:** Claude Chat — Architect. **Owner:** approves any changed semantics for human gold.  
**Coordinator:** ChatGPT. **Implementation:** Claude Code Sonnet 4.6 only AFTER approved ADR decision.  
**Branch:** `task/T15`; accepted source snapshot unchanged.  
**Code SHA:** `f4a8dea2026fb35b104e81d396672bd96d9b0c59` (WP-4 combined implementation); current final report/doc SHA `f07d88e41d6ab6b5a97b864eb8d063cf41bb2430`.  
**Verdict:** independently reproduced **CHANGES_REQUIRED**, exact finding in `tasks/T15-7-WP4.md` section **Sol F1**.  
**Status:** WP-4 BLOCKED; WP-5, T16/T17 and full render HOLD. 320 local real todo entries remain unlabeled; real scorer **INCOMPLETE rc 2**.  
**Inputs:** `tasks/T15-7-FINAL-ADR.md` §5 five-part human-gold identity, §10 `gold_vowel=yo` + `yo_correct` grammar / C3 version ledger; `src/audiobook/stress_eval.py` functions `validate_gold`, `inspect_ledger`, `_accepted_vowels`, `score`.

## Architectural inconsistency (confirmed by independent Sol)

Normative §5: gold remains CURRENT when the following five fields match present normalized source/context:

1. `source_key`
2. `form_source`
3. `unit_text_sha256`
4. `unit_kind`
5. `context_sha256`

No analysis fingerprint is part of that identity. An analysis/RUAccent/config/yo-restoration-only change is not supposed to invalidate stable human truth under this rule.

Normative §10: `gold_vowel=yo` is accepted when the source has one `ё` **OR** the current `form_synth` has one `ё` for `yo_changed`; accepted(g) resolves it as index of `ё`. `yo_correct=y|n` is separately required when `yo_changed`; it judges a specific orthographic restoration and **does not encode stress placement**.

The authoritative TSV has **only ten fields**:

```
source_key  form_source  unit_text_sha256  unit_kind  context_sha256  context  gold_vowel  yo_correct  labeler  date
```

It stores neither the historical restored `ё` vowel index nor the specific restored form/analysis generation to which `yo_correct` refers. Code may derive both from **current** `occ.form_synth`:

- `validate_gold` re-evaluates `gold_vowel=yo` against current `form_synth` and enforces `yo_correct=y/n` based on current `yo_changed`.
- `inspect_ledger` therefore may reclassify unchanged gold on analysis-only edits, despite a matching source identity.
- `_accepted_vowels` locates `ё` in the **current** `form_synth` and thereby can silently reinterpret old human truth.

Independent Sol synthetic counterexamples (no corpus excerpts):

1. Removing an earlier restored `ё` makes the formerly valid `gold_vowel=yo` row fail as `GOLD_INVALID` despite stable five-part identity.
2. Introducing a new restored `ё` makes an earlier numeric gold with `yo_correct=na` fail as `GOLD_INVALID` despite stable identity.
3. Moving restored `ё` between two source `е` vowel positions makes the **same ten-field label** remain valid but changes its accepted stressed-vowel index silently.

**STOP condition:** No automatic conversion, no choice of a replacement `ё` location, no silent invalidation of human truth, no global drop of old labels, no unsupported extra TSV columns/sidecars and no modification to current gold data without an explicit approved design.

## Decision the architect must provide

Select one authoritative, complete correction for **both** gold stress truth and separate `yo_correct` orthographic evidence:

**Option A — Persist sufficient historical restoration evidence (preserve source-only validity of the stress label).** Store an immutable, explicitly referenced observation at labeling time: accepted stress vowel index (if `yo`), and the exact restoration target/context on which `yo_correct` was judged. Specify whether the canonical ledger schema changes or a new ignored per-entry evidence file is needed; specify atomicity, version matching, identity, stale criteria, migration of existing `yo` records without evidence, and conflict/rollback behavior. A correct `yo`-derived human stress judgment can then survive later analysis changes; comparison of a prior orthographic judgment to a new restoration must be evidence-driven.

**Option B — Conservative contract revision to require relabeling on relevant analysis/restoration changes.** Keep the ten-field TSV if possible, but **prove how the ledger can detect the historical relevant analysis identity for each label**. Without persisted history, simply inspecting current `form_synth` is not detection. One possible minimal strategy is to prohibit `gold_vowel=yo` when `ё` exists only in current `form_synth` (use explicit source vowel index instead), and version/bind the `yo_correct` judgment to an immutable restoration identity; specify how that binding is stored and which changes make **only the affected judgment** stale. No unchecked conversion of existing human labels to numeric indices.

**Option C — Another explicit mechanism**, if it preserves both source-derived stress truth and restoration-specific `yo_correct` without loss or reinterpretation. Include proof that it solves all three counterexamples and remains consistent with C3 append-only versioning.

No option is automatically approved by this task. In particular, a patch that changes code while retaining contradictory §5/§10 semantics is insufficient.

### Questions to answer exactly

- What is the immutable meaning of `gold_vowel=yo` when the **source itself lacks ё**? Does it remain allowed at all?
- Is source-only five-part identity still sufficient to treat a **stress label** as current? Which additional immutable identity is needed for a **`yo_correct` restoration judgment**?
- For a previously saved `yo` row with no historical restoration evidence, what happens: `STALE + relabel`, `ERROR + owner action`, or another safe state? Can the score remain `INCOMPLETE rc 2` rather than silently becoming COMPLETE?
- For numeric gold where the current `yo_changed` property toggles, how are prior stress truth and orthographic judgment kept distinct? Do not rewrite a human `yo_correct=na` or invent y/n.
- Does the ten-column TSV remain canonical? If a sidecar/new field is required, specify exact schema, binding, atomicity, migration and safe no-sidecar failure behavior. Check P1/P4 and C3 version ledger; no lost historical rows.
- In the three synthetic examples, what are the exact required outcomes for `inspect_ledger`, `merge`, `sample todo`, `_accepted_vowels`, `score` and `YO_WARN`?
- How do we ensure that reverting a restoration choice never revives contradictory active labels or silently uses old judgments?
- Does the owner need to re-label any of the currently **320 blank todo entries** once the contract is accepted? They have **no existing gold labels**, so avoid unnecessary migration claims.

## Bounded correction / validation after ADR

The architect must deliver **one final targeted ADR addendum** (not a redesign of WP-1–WP-3), revising only the necessary paragraphs in §5, §10/C3, task acceptance and any P1/P4 details. Require Sonnet to:

- Implement exact chosen behavior with **three reproduced original counterexamples and reversions**, empty historical evidence, conflicting active labels, migration/upgrade if needed, crash-between-write tests, strict ledger versioning and privacy tests.
- Preserve original 10-field ledger **unless** the approved amendment explicitly changes it; no speculative migration.
- Preserve all existing owner S4 files byte-identically until a separately authorized, safe migration is demonstrated; currently all 320 todo labels are blank.
- Ensure historical human truth can never be silently reassigned to a different stressed vowel.
- Re-run full regression (current 1798 passed, 6 skipped), `PYTHONHASHSEED=1,2,3`, P1/P4, accepted D `0346b71f7b3f3c2078a144b56a8374a8998bf6b722d25af1fe0ce2a07ec1a5d6`, historical v4 D_tsv `105711f20d92f337642b66924eba30317dba4e2f393676d07739e83d7ebc11c6`, v5 inventory archive and protected production file parity.
- Request **one targeted independent Sol re-review** of the WP-4 fix against the pinned final SHA; do not re-audit accepted WP-1–WP-3.

## Architect report format (English)

```text
TASK: T15-7-WP4-YO-ADR
STATUS: APPROVED_ADR | BLOCKED
SELECTED_SEMANTICS:
GOLD_VOWEL_YO_SOURCE_VS_SYNTH:
SOURCE_ONLY_IDENTITY_RULE:
RESTORATION_IDENTITY_AND_PERSISTENCE:
TEN_FIELD_LEDGER_COMPATIBILITY:
YO_CORRECT_STALENESS_AND_SCORING:
MISSING_HISTORICAL_EVIDENCE:
MIGRATION_OR_OWNER_RELABEL_POLICY:
THREE_SOL_COUNTEREXAMPLES_EXPECTED_OUTCOMES:
C3_MERGE_CRASH_CONFLICT_REQUIREMENTS:
ADR_SECTIONS_TO_AMEND:
EXACT_TEST_ORACLES:
IMPLEMENTATION_FILE_SCOPE:
PRIVACY_AND_BASELINE_GATES:
OWNER_DECISION_REQUIRED:
NEXT_SONNET_ACTION:
```

STOP after delivering the decision. **No production code or gold-data change from the architect.**
