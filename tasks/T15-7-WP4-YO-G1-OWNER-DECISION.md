---
id: T15-7-WP4-YO-G1-OWNER-DECISION
title: G1 Option B-prime proposed owner decision register
status: proposed_for_owner
owner: owner
agent: coordinator
branch: task/T15
depends_on: [T15-7-WP4-YO-G1-DECISION-PACKET]
---

# T15-7 WP-4 — Option B′ G1 owner decision register

**Received:** 2026-11-13, owner-provided "COORDINATOR HANDOFF — T15-7-WP4-YO-G1".  
**Reported architect verdict:** `PROPOSED_FOR_OWNER — READY FOR OWNER DECISION`.  
**Formal owner approval:** **NOT YET GRANTED**.  
**Normative ADR:** **UNCHANGED**, pending explicit owner approval followed by a complete, reconciled addendum.  
**WP4:** `BLOCKED`. **WP5/T16/T17/full render:** `HOLD`.

This record reproduces the six owner decision subjects **from the handoff** and preserves the distinction between an architect's reported review and independently verified evidence. It is not approval, not implementation authorization, and not the complete proposed ADR text. The source handoff says architect resolved G1.1–G1.6, P1/P2 and C3/M1–M5, but **does not include the full T01–T42 oracle table or the normative replacement paragraphs**. Before implementing, those exact contracts must be present and validated against the current authoritative `tasks/T15-7-FINAL-ADR.md`.

## A. Explicit owner approval group: G1.1–G1.5

1. **G1.1 Source-only gold:** human stress truth uses the original source-vowel coordinates; historic synth-only `yo` is not interpreted from current synthesis and must not be silently migrated.
2. **G1.2 Completeness:** `ambiguous` and `unknown_name` are completed human annotations, but excluded from applicable metric denominators; zero-denominator gates need an explicit conservative state.
3. **G1.3 Sample/2:** version sample policy and commit to exact key→stratum membership; preserve existing owner-local 320-row H04 todo byte-for-byte until a separately authorized action.
4. **G1.4 YO evidence:** separate append-only local history binds each human y/n to an exact independently verified **pre-respell** restoration observation, never to post-respell `WordOcc.form_synth`. Future map/config changes require reobservation and exact match before reuse.
5. **G1.5 Dual ledger:** independent atomic stress/YO operations, read consistency and freshness check when a stored score is consumed; no false cross-file atomicity or inference of missing human labels.

**Owner decision G1.1–G1.5:** `PENDING_EXPLICIT_OWNER_REPLY`.

## B. Separately approvable C3 contract change: G1.6

6. **G1.6 C3 model change:** proposed switch to **one active stress row per `source_key`** with an authoritative append-only archive, conflict resolution M1–M5 and **mandatory read-only compatibility gate before any migration**. This differs from the current C3 storage model and **requires its own explicit owner decision**. No implicit consent merely from approving G1.1–G1.5.

**Owner decision G1.6:** `PENDING_SEPARATE_EXPLICIT_OWNER_REPLY`.

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
OWNER_G1_1_TO_G1_5: PENDING
OWNER_G1_6_C3_CHANGE: PENDING_SEPARATE_APPROVAL
NORMATIVE_ADR_CHANGE: NOT_AUTHORIZED
READ_ONLY_S4_COMPATIBILITY: AFTER_OWNER_ARCHITECTURE_DECISION
S4_MIGRATION_OR_WRITE: NOT_AUTHORIZED
PRODUCTION_IMPLEMENTATION: NOT_AUTHORIZED
PR_3_MERGE: NOT_AUTHORIZED
WP4: BLOCKED
WP5_T16_T17_FULL_RENDER: HOLD
```

**Owner reply format:** `G1.1–G1.5: УТВЕРЖДАЮ/НЕ УТВЕРЖДАЮ; G1.6 изменение C3: УТВЕРЖДАЮ/НЕ УТВЕРЖДАЮ`. The coordinator must update this register **only after** an actual owner response. Do not read approval into forwarding an architect handoff.
