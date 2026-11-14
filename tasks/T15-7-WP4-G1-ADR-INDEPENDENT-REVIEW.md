---
id: T15-7-WP4-G1-ADR-INDEPENDENT-REVIEW
title: "One independent Sol review of proposed unified G1 normative ADR retaining C3"
status: REQUESTED_NOT_COMPLETED
owner: owner
reviewer: codex-sol
branch: task/T15-7-wp4-g1-normative-adr
---

# T15-7 WP-4 G1 — one independent architectural consistency review

**STATUS: PENDING INDEPENDENT SOL.** The coordinator authored the proposal; the coordinator's static checks are not an independent review and cannot mark this PASS.

## Pin and sources

1. Compare exact pinned proposed ADR at tasks/T15-7-WP4-G1-NORMATIVE-ADR.md from this branch. Record the exact SHA.
2. Compare the unchanged current authority tasks/T15-7-FINAL-ADR.md rev.2 §§5/10 (C3)/11/12, plus tasks/T15-7-WP4-YO-ADR-ESCALATION.md with the three Sol F1 reproductions.
3. Read tasks/T15-7-WP4-YO-G1-OWNER-DECISION.md on task/T15 for the final owner declaration: G1.1–G1.5 approved in principle; keep current C3 version-ledger; reject authoritative archive/one-active-physical-row model; absolutely no S4 migration, no production GO.
4. Read owner-local S4 census aggregate report tasks/T15-7-WP4-G1-S4-READONLY-AUDIT.md in draft PR #3 (prior census at SHA 355507df): stress gold 0, archive 0, todo 320 blank, selected RESTORED=40, YO_EVALUABLE=40, F1 excluded=0. No private S4 copies, per-row text or hashes.
5. Read tasks/T15-7-WP4-YO-G1-DECISION-PACKET.md and tasks/T15-7-WP4-YO-ARCHITECTURE-AUDIT.md from draft PR #3, but their unapproved old B/B′ proposals do not supersede the owner's final C3 decision.

## Independent review obligations — no edits to production

- **Authority/C3:** confirm one authoritative stress_gold.tsv with all source-history rows; derived archive never input/authority; no archive-first M1–M5 transaction; source A→B→A reactivation and conflicting human labels fail closed; legacy synth-only yo preserved but not scored; valid current numeric replacement may become sole ACTIVE without removing legacy.
- **Identity/ambiguity:** source-only vowel coordinates, five-part identity and canonical equal-vowel sets; legitimate ambiguous/unknown_name completion versus unusable denominators; numeric-vs-numeric and usable-vs-unusable conflicts STOP rather than latest-date selection; source stale and history retained.
- **Sample/2:** exact identity commitments with selected key-to-stratum assignments, deterministic six strata and seed; no post-respell-only yo signal; current 320 blank H04 todo protected despite policy change; no automatic S4 writes.
- **YO observer:** source-key/chunk/fragment ordinal, fresh byte-hash yo map, independent direct+prepared **pre-respell** evidence, no WordOcc.form_synth provenance; NONE/RESTORED/UNSUPPORTED, explicit F1 exclusion truth table.
- **YO evidence:** 16-field local sidecar, candidate-level y/n and all forward changed source-vowel indices, same-fp contradiction ERROR, A→B→A reuse only for exact verified target, global map/config provenance distinct from human candidate identity.
- **Dual ledger:** separate single-file atomic writes, no fictitious two-file atomicity, pin both S4 byte hashes and generation, recheck before S3 score publish and on persisted COMPLETE read; absent required current y/n ⇒ INCOMPLETE rc2.
- **Metrics:** zero denominator null/inconclusive; coverage and accuracy denominators separated; Wilson 40/40,92/100,91/100,73/73; no auto-synthesis changes from G-hint or YO_WARN.
- **Privacy:** no novel source/gold/voice exposure in ADR/test proposal; P1/P4 source-local boundaries; no protected S4/source/manifests/cache/model/audio or production changes.
- **T01–T42:** audit all 42 numbered proposed tests for exact stimulus/oracle sufficiency and correct inclusion of T06, T27, T28. **Provenance caveat:** the original full architect-authored T01–T42 table was NOT present in owner handoff or inspected tracked repo. This 42-row registry was reconstructed and MUST NOT be represented as verbatim original. If exact reconciliation requires the original, mark that specific issue BLOCKED and request its source; do not guess silent equivalence.
- **Scope and adoption:** proposed ADR is a candidate, does NOT replace accepted rev.2 or authorize code/merge/H04/S4 migration/WP5/T16/T17/render until a later owner decision. A successful review is not itself code GO.

## Historical numbering reconciliation

Prior architect handoff fragments described T06 as requiring owner adjudication on conflicting current judgments, T27 as stale-history archive behavior, and T28 as source-context return. The proposed ADR now redefines **T06** as fail-closed OWNER_ADJUDICATION_REQUIRED, **T27** as M4-derived SOURCE_STALE archive export *while retaining history in gold*, and **T28** as A→B→A reactivation from gold without trusting archive. These are deliberate adaptations because the owner rejected the archive-authoritative model. Legacy synth-only yo replacement is now explicitly covered by **T10**; F1-exclusion predicate by **T16/T18/T29**. The original complete table remains unavailable and must not be claimed as source-identical without comparison.

## Output required

Respond with exact SHA and one of PASS / CHANGES_REQUIRED / BLOCKED. State only independently inspected evidence and aggregate facts; identify any line/section blockers and exact corrective wording. Include explicit checks:
  C3_RETAINED;
  C3_ARCHIVE_NON_AUTHORITATIVE;
  LEGACY_YO_REPLACEMENT_T10;
  HUMAN_CONFLICT_OWNER_ADJUDICATION_REQUIRED_T06;
  SOURCE_CONTEXT_REVERSIONS;
  HUMAN_CONFLICT_STOP;
  M1_TO_M5_ATOMICITY;
  SAMPLE_2_TODO_PRESERVATION;
  PRE_RESPELL_YO_EVIDENCE;
  F1_EXCLUSION_T16_T18;
  DERIVED_ARCHIVE_T27;
  SOURCE_CONTEXT_RETURN_T28;
  DUAL_LEDGER_SCORE_FRESHNESS;
  COMPLETE_INCOMPLETE_ERROR;
  T01_T42_NORMATIVE_ORACLES_AND_PROVENANCE;
  PRIVACY_NO_CODE_CHANGE;
  NO_MIGRATION_NO_IMPL_GO.

**STOP after review.** Do not modify the production code, existing accepted ADR, owner S4, text, inventory, sample/todo, any model/audio artifact or PR #3. The review of this text does not grant WP4 PASS.
