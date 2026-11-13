---
id: T15-7-WP4-YO-OWNER-APPROVAL
title: Owner approval gate for proposed immutable stress gold and restoration evidence
status: blocked
owner:
agent: coordinator
branch: task/T15
order: 16
depends_on: [T15-7-WP4-YO-ADR-ESCALATION]
estimate_active_h: 0.25-0.75
estimate_qa_h: 0
actual_active_h: unknown
actual_elapsed_h: unknown
---

# WP-4 F1 — Architect's Option B Proposal, Pending Explicit Owner Approval

**Received:** 2026-11-13 as owner-supplied full architect response, headed `TASK: T15-7-WP4-YO-ADR`, **STATUS: BLOCKED — OWNER APPROVAL REQUIRED**.  
**Code:** `f4a8dea2026fb35b104e81d396672bd96d9b0c59`; blocked report `tasks/T15-7-WP4.md`.  
**Gate:** This file is a **proposal/decision register**, NOT acceptance, not a final ADR addendum, and NOT permission to change production semantics or owner gold files.  
**Owner approval:** **NOT APPROVED**. On 2026-11-13 the owner explicitly declined to approve Option B pending deeper architectural risk analysis. This file remains an unapproved proposal, not a GO. Review findings will be prepared separately; no production/gold/ADR semantics may be changed.

## Three explicit owner-approved semantic decisions required together

1. **Stress truth from original source only:** numeric source-vowel positions or source-native single `ё` are authoritative; new synth-only `gold_vowel=yo` forbidden. Historic synth-only `yo` stays preserved in the ten-field C3 ledger but is marked `LEGACY_YO_UNRESOLVED` and requires human numeric relabel; no guessing/migration.
2. **Restoration truth is separate:** `yo_correct=y/n` means one exact `е→ё` restoration, not a timeless attribute of the source word. For new stress rows the existing ten-field `yo_correct` column is `na`; historical y/n is preserved but never used as unbound current evidence.
3. **One additional private authoritative S4 evidence ledger:** `text/stress_gold.yo_evidence.tsv` (12 columns `schema_version,source_key,form_source,unit_text_sha256,unit_kind,context_sha256,form_synth,restored_vowel_indices,restoration_fp,yo_correct,labeler,date`), plus `text/stress_gold.yo.todo.tsv` and `stress-eval merge-yo`. Each ledger has its own one-file atomic transaction, no cross-ledger transaction; missing current evidence means INCOMPLETE rc2, conflicting evidence ERROR.

Keep original ten-field gold TSV, five-field source identity, C3 history, separate orthography states, exact source/restore fingerprint validation and zero automatic backfill. On A→B→A restore, reuse A evidence only for exact identical fingerprint; never rebind to B or to a different source/context identity.

**Owner approval request:** confirm all three as one bounded decision. A file upload that merely contains the architect's `OWNER_APPROVAL_REQUIRED` proposal is NOT, by itself, approval.

## Implementation preflight that the coordinator independently identified

Actual `WordOcc.form_synth` in current `src/audiobook/wordprov.py` is copied from `SUTrace.prep_text` token alignment (`orig_tw`). It therefore represents the prepared synthesis token, not a proven separate **pre-respell restoration observation**. The proposed evidence contract explicitly requires an exact `е→ё` restoration target **before respell()**.

**Do not silently equate post-preparation `form_synth` with pre-respell evidence.** Repository inspection identifies a plausible **read-only candidate**: `voicecfg.prepare_text(text, config, open_end)` is executed before `pronounce.respell(...)`; `sutrace.py` records only the later `prep_text`, while `synth.py` documents the exact order `text_prep → pad → respell → sentinel`. A correctly matched pre-respell token may therefore be reconstructed through the existing voicecfg interface, **but this is not yet proven safe for all chunks/fragments, quotes, lead-in carriers, punctuation, phrase respell and selected word offsets**. Sonnet must prove a deterministic, local, source-compatible pre-respell target read path with synthetic tests, no changes to protected synthesis, manifest, 6C11, cache, production inputs or original observations. If unavailable, raise a *narrow* architect question before implementing `merge-yo`. Never infer an **old** target from current preparation or annotation dates. The evidence contract's `form_synth` column must be interpreted as the validated specific pre-respell restoration spelling, not arbitrary SUTrace text.

Second check: new stress rows must allow `yo_correct=na` even when `yo_changed`, whereas current `validate_gold` rejects it. Legacy historical values stay readable without being treated as live restoration proof. Effective YO scoring comes exclusively from currently matching evidence; incomplete orthography does not block source-stress validity, but it blocks a complete overall score when restoration judgment is required.

Third check: existing `.gitignore` pattern `/text/stress_gold*.tsv` already covers the proposed S4 evidence/todo paths. P1/P4 still must run before every actual write, and no S4 data can be committed.

## Coordinator execution policy after explicit approval

- Commit one narrowly scoped **approved ADR addendum** in §5, §10, §11 and §12 before implementing production changes; resolve any remaining pre-respell trace ambiguity with the architect.
- Sonnet or a separately isolated coordinator PR may implement approved non-conflicting synthetic helper/test work; Sonnet integrates `stress_eval.py` behavior and `merge-yo` CLI only after approval.
- Extend `tasks/T15-7-WP4-YO-ADR-ESCALATION.md` original Sol three cases with source-native yo, numeric stress on yo toggle, missing/conflicting evidence, A→B→A, crash, P1/P4, hash seeds 1/2/3.
- Prebuilt test-only draft PR: `https://github.com/Dannymor94/audiobook/pull/2` contains strict-XFAIL synthetic F1 reproducers; they are **not yet acceptance PASS**, must be activated and adapted when ADR is approved.
- Preserve 320 local unlabeled todo entries and all old gold/archive bytes; no merge, owner gold rewrite or regeneration is authorized merely by approving a code plan.
- End with **one targeted independent Sol re-review** at the final corrected WP-4 SHA. No WP5, T16/T17 or render while blocked.

## Decision state

```text
OWNER_APPROVES_SOURCE_ONLY_STRESS_TRUTH: NOT_APPROVED_PENDING_REVIEW
OWNER_APPROVES_SEPARATE_RESTORATION_TRUTH: NOT_APPROVED_PENDING_REVIEW
OWNER_APPROVES_PRIVATE_S4_YO_EVIDENCE_AND_MERGE_YO: NOT_APPROVED_PENDING_REVIEW
PRE_RESPELL_EVIDENCE_PROVEN_ACCESSIBLE: UNVERIFIED
WP4_CODE_FIX_AUTHORIZED: NO
WP4_STATUS: BLOCKED
```
