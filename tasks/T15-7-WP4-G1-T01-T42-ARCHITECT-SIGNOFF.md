---
id: T15-7-WP4-G1-T01-T42-ARCHITECT-SIGNOFF
status: REQUESTED_NOT_SIGNED
owner: owner
reviewer: claude-chat-architect
branch: task/T15-7-wp4-g1-normative-adr
---

# G1 architect sign-off — provenance of reconstructed T01–T42

**Status: NOT SIGNED.** This record is a review request, not a signature or an approved normative ADR. The coordinator must never sign for the architect.

## Scope

Review the **entire, exact numbered T01–T42 table** in `tasks/T15-7-WP4-G1-NORMATIVE-ADR.md` from the latest exact PR #4 SHA, plus §1–§8, §10–§11. Compare with the owner's final model:
- `text/stress_gold.tsv`: sole authoritative historical stress version-ledger.
- `text/stress_gold.archive.tsv`: derived, non-authoritative stale export.
- No one-active-physical-row archive-first design, no S4 migration.
- Source-only human stress; legacy synth-only YO requires human numeric relabel.
- sample/2, frozen pre-respell observer (including disabled yo_restore), 16-column exact YO evidence, two-ledger score freshness.

**Provenance reconciliation now available:** The architect supplied an explicit historical-concept inventory O01–O42 and requested three specific corrections C1–C3. The revised proposed T01–T42 is a **new reconstruction for the retained C3 version-ledger**, not a verbatim transcript of the rejected authoritative-archive model. The exact 42-row mapping, including O38 VOID/REPLACED, is in `tasks/T15-7-WP4-G1-ORACLE-COVERAGE-MAP.md`. C1 isolates stress merge from sample/analysis/restoration; C2 adds exact L3 byte equivalence; C3 fixes full eligible/selected sample/2 digests and versioned paths. These text changes DO NOT constitute architect signature or owner adoption.

## Required architect decision

After independently reading both the revised normative ADR and the O01–O42 coverage map at one exact pinned SHA, choose exactly ONE:
- **A — ACCEPT_RECONSTRUCTED_T01_T42_AT_PINNED_SHA:** independently inspect and approve each of the 42 current numbered requirements as the authoritative complete regression contract for the owner-approved retained-C3 architecture, including T06 (current human conflict STOP), T27 (derived archive only), T28 (A→B→A reactivation from stress gold). Record any necessary edits first and approve only an exact final SHA.
- **B — PROVIDE_ORIGINAL_AND_RECONCILE:** supply the original full 42-row authored table, identify differences from the current proposal, and explicitly accept a final reconciled 42-row table at one exact SHA.
- **C — CHANGES_REQUIRED / BLOCKED:** identify each exact inconsistent/missing item and the smallest necessary correction; do not approve it by implication.

## Exact reply format

```text
TASK: T15-7-WP4-G1-T01-T42-PROVENANCE
REVIEWED_PR4_SHA: <full 40-character SHA>
DECISION: ACCEPT_RECONSTRUCTED_T01_T42_AT_PINNED_SHA | PROVIDE_ORIGINAL_AND_RECONCILE | CHANGES_REQUIRED | BLOCKED
C3_MODEL: VERSION_LEDGER_AUTHORITY_ONLY
T06: ...
T27: ...
T28: ...
DISABLED_YO_RESTORE_T30_T32: ...
T38_RESTORATION_FP: ...
ORACLE_T01_T42_COVERAGE: 42/42 accepted | specific corrections
REMAINING_BLOCKERS: ...
ADOPTION_AUTHORIZED: NO
PRODUCTION_CODE_AUTHORIZED: NO
S4_MIGRATION_AUTHORIZED: NO
```

The coordinator provides the pinned SHA and document files; the architect must sign explicitly and must not assume the reconstructed register is verbatim. The architect only approves a **proposed contract** and cannot grant implementation/owner adoption. Any independent Sol verdict on the exact reviewed SHA is separate; only owner can later approve normative adoption. **STOP.**
