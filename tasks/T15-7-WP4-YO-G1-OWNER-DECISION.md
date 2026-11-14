---
id: T15-7-WP4-YO-G1-OWNER-DECISION
title: G1 Option B-prime proposed owner decision register
status: owner_c3_retained_adr_authoring_authorized
owner: owner
agent: coordinator
branch: task/T15
depends_on: [T15-7-WP4-YO-G1-DECISION-PACKET]
---

# T15-7 WP-4 — Option B′ G1 owner decision register

**Received:** 2026-11-13, owner-provided "COORDINATOR HANDOFF — T15-7-WP4-YO-G1".  
**Reported architect verdict:** `PROPOSED_FOR_OWNER — READY FOR OWNER DECISION`.  
**Owner decision 2026-11-14:** **A / G1.1–G1.5 APPROVED IN PRINCIPLE; B / G1.6 DEFERRED — NOT APPROVED.** This is **not** implementation authorization.  
**Normative ADR:** **UNCHANGED**, pending explicit owner approval followed by a complete, reconciled addendum.  
**WP4:** `BLOCKED`. **WP5/T16/T17/full render:** `HOLD`. **Owner's latest decision (2026-11-14):** keep existing authoritative C3 version-ledger; reject proposed archive-authority redesign; ADR drafting/independent review authorized only.

This record reproduces the six owner decision subjects **from the handoff** and preserves the distinction between an architect's reported review and independently verified evidence. It is not approval, not implementation authorization, and not the complete proposed ADR text. The source handoff says architect resolved G1.1–G1.6, P1/P2 and C3/M1–M5, but **does not include the full T01–T42 oracle table or the normative replacement paragraphs**. Before implementing, those exact contracts must be present and validated against the current authoritative `tasks/T15-7-FINAL-ADR.md`.

## A. Explicit owner approval group: G1.1–G1.5

1. **G1.1 Source-only gold:** human stress truth uses the original source-vowel coordinates; historic synth-only `yo` is not interpreted from current synthesis and must not be silently migrated.
2. **G1.2 Completeness:** `ambiguous` and `unknown_name` are completed human annotations, but excluded from applicable metric denominators; zero-denominator gates need an explicit conservative state.
3. **G1.3 Sample/2:** version sample policy and commit to exact key→stratum membership; preserve existing owner-local 320-row H04 todo byte-for-byte until a separately authorized action.
4. **G1.4 YO evidence:** separate append-only local history binds each human y/n to an exact independently verified **pre-respell** restoration observation, never to post-respell `WordOcc.form_synth`. Future map/config changes require reobservation and exact match before reuse.
5. **G1.5 Dual ledger:** independent atomic stress/YO operations, read consistency and freshness check when a stored score is consumed; no false cross-file atomicity or inference of missing human labels.

**Owner decision G1.1–G1.5:** `APPROVED_IN_PRINCIPLE` (2026-11-14). Exact normative ADR and tests remain to be approved before code.

## B. Separately approvable C3 contract change: G1.6

6. **G1.6 C3 model change:** proposed switch to **one active stress row per `source_key`** with an authoritative append-only archive, conflict resolution M1–M5 and **mandatory read-only compatibility gate before any migration**. This differs from the current C3 storage model and **requires its own explicit owner decision**. No implicit consent merely from approving G1.1–G1.5.

**Owner final decision G1.6 (2026-11-14):** `RETAIN_EXISTING_C3_VERSION_LEDGER_APPROVED`; `PROPOSED_AUTHORITATIVE_ARCHIVE_MODEL_REJECTED`; `S4_MIGRATION_NOT_AUTHORIZED`. The authorized read-only S4 census **PASS** at pinned SHA `355507df` supported this decision. `stress_gold.tsv` remains the *sole authoritative stress version ledger*, containing all historical versions. `stress_gold.archive.tsv` is *derived and non-authoritative*, recoverable from current ledger. Conflicting human label correction requires a separately approved explicit contract; no latest-date or silent revision.

**Even if G1.6 is approved:** any specific existing S4 migration or rewrite remains disallowed until a read-only compatibility report is reviewed and the owner separately authorizes that concrete operation. Preserving history is mandatory.

## Mandatory normative-adoption checks (NOT executed/approved yet)

- The scorer reads **only the active stress ledger and YO ledger**, not the archive.
- Include full T01–T42 regression expectations, explicitly T06/T27/T28.
- `YO_EVALUABLE = RESTORED ∧ f1_rule=null ∧ f1_flag=none`; measure **aggregate excluded counts for the current source snapshot before** any implementation, without emitting words/keys/text.
- Reconcile current §5 source identity, §10 sampling+completeness, §11 privacy/cache, C3 transaction/conflict/archiving, M1–M5 and both-ledger score freshness; no implicit assumptions about legacy labels.
- Attach the **actual final proposed ADR** (not just the coordinator handoff) or reconstruct and have the architect sign the full exact normative clauses and regression oracle table before changing the accepted contract.
- Preserve G0 evidence: isolated installed-.venv **52/52 focused PASS** at `650127b90199342dfe4d1e555784025e11056f2f`; full suite **1,845 PASS / 11 SKIP / 0 FAIL**. Earlier source-private mapping **51,629/51,629 eligible**, **320/320 selected**, unsupported=0; five S2-baseline-dependent skips still need final QA environment confirmation. These are agent-reported, not independent Sol acceptance.

## Authorization status / constraints

```text
ARCHITECT_PROPOSAL: READY_FOR_OWNER_DECISION (reported)
OWNER_G1_1_TO_G1_5: APPROVED_IN_PRINCIPLE
OWNER_G1_6_C3_CHANGE: RETAIN_EXISTING_C3_APPROVED_NEW_MODEL_REJECTED
NORMATIVE_ADR_CHANGE: PROPOSAL_DRAFT_AND_INDEPENDENT_REVIEW_ONLY
READ_ONLY_S4_COMPATIBILITY: COMPLETED_PASS
S4_MIGRATION_OR_WRITE: NOT_AUTHORIZED
PRODUCTION_IMPLEMENTATION: NOT_AUTHORIZED
PR_3_MERGE: NOT_AUTHORIZED
WP4: BLOCKED
WP5_T16_T17_FULL_RENDER: HOLD
```

**Owner audit scope (2026-11-14):** local-only aggregate counts of `stress_gold.tsv` rows, distinct/repeated source_key and historical identities, `stress_gold.archive.tsv` rows, completed gold labels and filled-but-unmerged todo, selected RESTORED candidates excluded by `f1_rule != null` or `f1_flag != none`, and conservative C3 alternative recommendation. No private rows, text, individual hashes, file content, S4 writes, H04, PR merge, production, WP5/T16/T17 or rendering. B stays deferred until the owner reviews the audit and separately authorizes it.

## Completed local S4 audit — evidence for G1.6 decision (2026-11-14)

User forwarded Sonnet's read-only owner-local output for pinned `355507df2789840adb2925f644818ccd899be8c6`. `tests/test_stress_s4_c3_readonly.py`: **17 PASS / 0 FAIL / 0 SKIP**. Scanner `PASS`, no reported data/code writes, migration not authorized. `stress_gold.tsv` present but **0 rows**: 0 unique/repeated keys, historical versions, current conflicts, stale records, or human labels. `stress_gold.archive.tsv` present **0 rows**. `stress_gold.todo.tsv` present **320 blank / 0 filled / 0 partially filled / 0 unmerged**. Selected `RESTORED=40`, F1 excluded **0**, `YO_EVALUABLE=40`. G0 verified eligible **51,629**. `text/` count 246 before/after, local MD5 gold/todo unchanged; these checks are **not** a fresh 416-file hash audit. The aggregate data were not independently rerun by coordinator because S4 remains local and Git-ignored.

**Assessment:** census PASS, C3 owner decision **PENDING**. Given zero historical annotations, the **simplest/least migration-risk path is to retain the existing authoritative C3 version-ledger** and derived non-authoritative archive; do **not** migrate empty gold or change the archive authority. A later correction procedure for same-source conflicting human labels remains a separate ADR issue; never silently prefer newest date.

Detailed report: `tasks/T15-7-WP4-G1-S4-READONLY-AUDIT.md` in draft PR #3. No B approval is inferred from forwarding this audit. The owner must explicitly decide **retain current C3** versus request an alternative before any new normative ADR or code GO.

## Final owner C3 decision (2026-11-14) — replaces prior B deferral

The owner explicitly approved preserving current **C3 version-ledger** and explicitly **rejected** the proposed new one-active-row + authoritative-archive model. `text/stress_gold.tsv` alone remains authoritative for human stress decisions, including historical versions. `text/stress_gold.archive.tsv` remains a reproducible, non-authoritative stale export. Independent YO evidence is permitted as the in-principle G1.4/G1.5 *architecture* only. No auto-correction of conflicting human judgments; later adjudication requires a separate history-preserving owner-approved rule. **No S4 migration**. The owner authorized **only creation and independent validation of a self-contained normative ADR proposal**, not production code, S4 edits, merging draft PR #3, H04, WP5/T16/T17 or full render.

This explicit decision supersedes the earlier `DEFERRED_NOT_APPROVED` status, but **does not by itself approve a completed ADR revision or grant any implementation permission**. The eventual self-contained ADR must retain C3 and amend M1–M5 accordingly, cover T01–T42 including T06/T27/T28, source-only/legacy YO/C3 conflicts, sample/2, YO sidecar and two-ledger freshness; one independent Sol review is required.

## Unified G1 normative ADR prepared for one independent review (2026-11-14)

A self-contained replacement **proposal** covering source-only gold, LEGACY_YO_UNRESOLVED/SOURCE_STALE/C3 ACTIVE semantics, source-context reversions, M1–M5 with derived archive, sample/2, YO evidence, dual-ledger score freshness and 42 regression oracles is published as **draft PR #4**: https://github.com/Dannymor94/audiobook/pull/4. Proposed file: `tasks/T15-7-WP4-G1-NORMATIVE-ADR.md`; independent review instructions: `tasks/T15-7-WP4-G1-ADR-INDEPENDENT-REVIEW.md`.

**Review status: REQUESTED / NOT COMPLETED.** Coordinator's structural self-check found 42 sequential test IDs and all required domain sections, but **this is NOT independent Sol signoff**. Original architect-authored T01–T42 table was not included in the owner handoff or located in inspected tracked sources; PR #4 contains a clearly labeled reconstructed 42-oracle register, and independent reviewer must flag any mismatch/provenance gap. Keep current `tasks/T15-7-FINAL-ADR.md` rev.2 untouched until reviewed ADR is separately adopted. No code, S4, H04, sample recreation, PR #3 merge, WP5/T16/T17 or render authorization.

## Independent Sol review #1 of PR #4: CHANGES_REQUIRED (2026-11-14)

The user relayed independent Sol's review of exact PR #4 SHA `c382723fae22d5cb903e46396628fd527eea1cf4`: **CHANGES_REQUIRED**, specifically §4.2/T30/T32 incorrectly applied direct yo.restore when disabled; T38 used undefined `observation_fp` instead of `restoration_fp`; and test-acceptance wording wrongly required retained-C3 T06/T27/T28 to fail against old safe code. The **original architect-authored complete T01–T42 table remains unavailable**, so provenance is **BLOCKED** pending exact architect signoff on reconstructed 42 rows or supply/reconciliation of the original.

Coordinator updated **only PR #4 proposal documents**, not production, S4 or the accepted rev.2 ADR:
- Disabled yo_restore explicitly compares unchanged source to verified pre-respell prepared word (NONE when equal even when map could change it); enabled restore applies direct map; T30/T32 explicit.
- T38 matches freshly verified current restoration_fp.
- T06/T27/T28 preserve existing C3 PASS and catch selection by latest date/authoritative archive/history deletion; the three original unsafe Sol F1 repros remain expected to fail pre-fix.
- Added explicit architect signature request in `tasks/T15-7-WP4-G1-T01-T42-ARCHITECT-SIGNOFF.md`, within draft PR #4.

**Revision status:** three textual findings `FIX_APPLIED_PENDING_INDEPENDENT_REVIEW`; T01–T42 provenance `BLOCKED_PENDING_ARCHITECT`. Sol reported prior-code full suite **1,793 passed / 11 skipped / 0 failed** at reviewed SHA. This is not a rerun of corrected ADR or the future 42 test implementations.

**No change in owner's authorizations:** C3 existing version-ledger approved, archive-authority model rejected, S4 migration prohibited; G1.1–G1.5 approved in principle; reviewed final normative ADR NOT adopted; production code / S4 / H04 / sample recreation / PR #3 or #4 merge / WP5/T16/T17 / render all HOLD. One **targeted independent re-review** of corrected exact SHA and one exact architect T01–T42 signoff are required before a new owner adoption request.

**Owner reply format:** `G1.1–G1.5: УТВЕРЖДАЮ/НЕ УТВЕРЖДАЮ; G1.6 изменение C3: УТВЕРЖДАЮ/НЕ УТВЕРЖДАЮ`. The coordinator must update this register **only after** an actual owner response. Do not read approval into forwarding an architect handoff.
