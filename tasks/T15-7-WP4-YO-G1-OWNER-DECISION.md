---
id: T15-7-WP4-YO-G1-OWNER-DECISION
title: G1 Option B-prime proposed owner decision register
status: owner_normative_g1_approved_at_pinned_sha_code_go_pending
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

## Owner final implementation PLAN approval — CODE GO not granted (2026-11-14)

**Owner decision received explicitly:** `APPROVE IMPLEMENTATION PLAN` at **plan commit SHA `0afd382a276832816bb7e84a020a5b58ae8d5f58`**, relative path `tasks/T15-7-WP4-G1-IMPLEMENTATION-PLAN.md` (verified at that exact ref; the current `task/T15` version matches). The normative G1 ADR remains approved separately at **`a012c84240eb246b8072a735989f598b6ca566e2`**. This owner approval accepts the plan's C1–C6 corrections, exact T01–T42 assignment and STOP gates. **It is NOT production code authorization, a command to Sonnet, local corpus-run permission, or approval of any S3/S4 data writes.**

**Approved I1/I2/I3 breakdown:** I1 = 13 T oracles, infrastructure and two-part memory-only *future* owner-local checkpoint; I2 = 22 T oracles plus original 3 Sol F1 regressions, C3/source-only stress/YO evidence; I3 = 7 T oracles and full exit suite with five previously S2-dependent tests actually executed and PASS. One separate commit per stage, full pytest at every stage, coordinator gates I1 and I2, final independent Sol CODE review. I1-A reads the original 320-row sample/1 todo; I1-B computes sample/2 only in memory, must **not** assume its selected YO totals equal old 40/40/0; full eligible RESTORED=223 expected only at same pinned G0 identity. Any fingerprint mismatch or protected file change => STOP.

**Approved design constraints, still subject to a future separate CODE GO:** fixed code base `201f0cd4e946f7f5405e47fe27153df9aeac17ef`, implementation branch `task/T15-7-wp4-g1-implementation` only if later authorized; file allowlist §5.1, read-only imports permitted, no change outside that scope; no PR #3 cherry-pick or PR #3/#4 merge. S4/H04, existing 320-row todo, migration, WP5, T16/T17, full render HOLD. Coordinator is authorized now **only to prepare a separate owner-facing limited CODE GO proposal** and present it for approval. No Sonnet execution before an explicit owner `APPROVE LIMITED CODE GO`.

## Final independent architecture review PASS — pinned owner-approved SHA (2026-11-14)

**Verdict reported by user:** independent Sol **PASS** for **DOCUMENT ARCHITECTURE ONLY** at `a012c84240eb246b8072a735989f598b6ca566e2`. The architect's external `ACCEPT_RECONSTRUCTED_T01_T42_AT_PINNED_SHA` resolves the former provenance blocker. Older `PENDING`/`NOT SIGNED` wording inside the pinned PR #4 review-request docs records prior status, not the current owner decision; do not change these files on the owner-approved SHA. No claim that the PASS was posted as a GitHub review.

**R1–R8 independently inspected according to the delivered Sol report:** T42(a) all-nonpositional COMPLETE rc0, accuracy null, G_hint INCONCLUSIVE; T10 legacy row retained alongside numeric ACTIVE, idempotent merge; T24/T25 differing todo bytes protected even if blank; T31/§4.8 every-SU ordinal + exact L3 final bytes and phrase None/empty distinction; T21(a) replacing O17 sample/1 with sample/2 assignment-fingerprint oracle; T19/M4 deterministic non-authoritative ten-column SOURCE_STALE archive; T41/§5.5 preserved existing score bytes on ERROR; §0/§3.6 versioned YO todo and §5.5 both assignment digests. Retained C3 T06 conflict STOP, T27 stale history retained in authoritative gold, T28 A→B→A reactivation from gold; original disabled-yo, restoration_fp and old-C3 semantics problems closed. O01–O42 map: **42/42**, 40 MAPPED, O17 REPLACED, O38 VOID/REPLACED. Source comparison PR base→pinned SHA reportedly **4 task Markdown files only**, no production or accepted rev.2 changes.

**Evidence limits:** This PASS certifies the consistency of reviewed document contracts only. The independent report expressly states **pytest not run**, no private S4 execution and no future T01–T42 implementation proof. Do not convert architecture PASS into code WP4 PASS, a rendered audio approval or S4 compatibility attestations.

**Current authorization remains:** owner-approved ADR and reconstructed T01–T42 only. Bounded WP4-I1/I2/I3 plan exists, but **OWNER_PLAN_APPROVAL PENDING and IMPLEMENTATION_CODE_GO NOT GRANTED**. No Sonnet coding, no real corpus probe without its own future explicit scope, no S3/S4 owner data write, no legacy 320-row todo modification, no H04, no PR #3/#4 merge, WP5/T16/T17/full render HOLD. Next owner decision: independently approve the bounded plan, then issue a separate limited CODE GO if desired.

## Owner/auditor alignment — authoritative status (2026-11-14)

**Final decision: ADR APPROVED / IMPLEMENTATION GO PENDING.** The owner explicitly approved normative G1 and reconstructed T01–T42 at PR #4 exact SHA `a012c84240eb246b8072a735989f598b6ca566e2`. The owner reports **architect ACCEPT_RECONSTRUCTED_T01_T42_AT_PINNED_SHA** and independent **Sol PASS** on that same SHA, and confirms coverage of O01–O42. This newer sign-off supersedes the earlier CHANGES_REQUIRED and review-pending *decision statuses* noted lower in this historical log, but not their documented findings. The archived GitHub PR review listing and old sign-off document may not display the external chats; treat ACCEPT/PASS as owner-relayed and do not attribute those records to a GitHub review that was never posted.

**Owner-approved only:** architecture and regression contract. **Not approved:** implementation or code, existing S4, 320-row todo, migration, H04, sample regeneration, PR #3/#4 merge, WP5/T16/T17 or full render. **Next:** present the limited WP4-I1/I2/I3 plan for **separate owner approval**; do not treat plan preparation or Sol architectural PASS as permission to dispatch Sonnet.

## Owner approval of normative G1 ADR and T01–T42 at pinned SHA — 2026-11-14

**DECISION: APPROVE NORMATIVE ADR** (owner, explicitly supplied in conversation). Approved **exact** PR #4 SHA `a012c84240eb246b8072a735989f598b6ca566e2`, for `tasks/T15-7-WP4-G1-NORMATIVE-ADR.md` and its reconstructed, newly adopted `T01–T42` regression register, with `tasks/T15-7-WP4-G1-ORACLE-COVERAGE-MAP.md` tracing O01–O42. Owner cites **architect sign-off ACCEPT** and **independent Sol architecture PASS** at that exact SHA; these are owner-relayed attestations. The files `tasks/T15-7-WP4-G1-T01-T42-ARCHITECT-SIGNOFF.md` and `tasks/T15-7-WP4-G1-ADR-INDEPENDENT-REVIEW.md` in pinned PR #4 still contain earlier unsynchronized `REQUESTED_NOT_SIGNED` / `CHANGES_REQUIRED` statuses, and GitHub PR #4 reviews list is empty. Do **not** misstate those stale tracked declarations as independently verified sign-offs, but do not override the owner's express adoption either.

**Normative scope effective by explicit owner decision:** G1.1–G1.5 source-only gold, completeness, sample/2, exact pre-respell YO evidence, independent ledgers/freshness; G1.6 retaining `stress_gold.tsv` as sole authoritative human-stress version-ledger with `stress_gold.archive.tsv` derived, non-authoritative; no archive-first migration; current-identity conflicts stop. Full T01–T42 is the **new approved reconstructed version**, not a claim of verbatim equality to a rejected earlier archive-authoritative table. The mapped O17 and O38 replacements are specifically acknowledged as part of this approved version.

**Approved contract is pinned, not merged:** PR #4 remains DRAFT and unmerged. G1 at pinned SHA has owner normative approval, but `task/T15` still contains rev.2 `tasks/T15-7-FINAL-ADR.md`; no unapproved PR merge may occur. Cite this decision and exact pinned G1 document; do not imply the physical rev.2 file has already been replaced.

**Separate implementation authorization:** `NOT_GRANTED`. Owner **only** authorizes coordinator to record decision and prepare a tightly limited WP4 implementation plan with acceptance criteria. No production or S4 changes, gold/todo/archive or YO sidecar writes, H04/real-score, sample regeneration, WP5/T16/T17/render or PR #3/#4 merge. S4 migration forbidden.

**Next permitted deliverable:** `tasks/T15-7-WP4-G1-IMPLEMENTATION-PLAN.md` (planning only), followed by distinct explicit owner code-GO decision. Any future owner S4/sample writes must also receive separate authorization. WP4 remains `BLOCKED_PENDING_CODE_AUTHORIZATION`; WP5/T16/T17/render HOLD.

**Owner reply format:** `G1.1–G1.5: УТВЕРЖДАЮ/НЕ УТВЕРЖДАЮ; G1.6 изменение C3: УТВЕРЖДАЮ/НЕ УТВЕРЖДАЮ`. The coordinator must update this register **only after** an actual owner response. Do not read approval into forwarding an architect handoff.
