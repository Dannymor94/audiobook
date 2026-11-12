---
id: T15-7-WP2-WP3-TRANSITION
title: Record completed Sol WP-2 acceptance and verify RUAccent offline gate B1
status: todo
owner:
agent: codex
branch: task/T15
order: 12
depends_on: []
---

# T15-7 — Independent transition evidence: WP-2 acceptance + B1

**Executor:** Codex Sol — independent read-only QA  
**Code SHA:** `d3f51854a283b90b94e141ace35f5a62d952b00a`  
**Branch:** `task/T15`  
**Coordinator status:** WP-2 corrective code delivered. Agent handoff states that a single targeted Sol review already **PASSED**, but no separately attributable final independent Sol verdict is attached to `tasks/T15-7-WP2-FIX.md` at the audited HEAD. Record the existing review evidence instead of duplicating completed work.  
**Goal:** finish two prerequisites for WP-3 with a single read-only handoff, **not** another architecture audit.

Read directly from GitHub: `tasks/T15-7-FINAL-ADR.md` §§2, 7, 11–14, `tasks/T15-7-WP2-FIX.md`, `tasks/T15-7-WP2-REVIEW.md`, `tasks/T15-7-EXECUTION-PLAN.md`, `CLAUDE.md`, `AGENTS.md`.

## Gate A — Evidence of independent WP-2-FIX acceptance

1. **If Codex Sol already performed the targeted review:** Provide its actual independently authored verdict, target SHA, test commands/results, original R1–R7 reproduction/closure verdicts and protected snapshot aggregate counts. Do not rerun the full review just to restate a prior PASS.
2. If the alleged Sol PASS is only a developer or nested agent self-report, **do not endorse it as independent evidence**. Independently validate R1–R7 from code and reproducible synthetic probes at the pinned SHA, then provide a single PASS / CHANGES_REQUIRED / BLOCKED verdict. This should remain targeted, not repeat the 6C11/ADR review.
3. Cross-check actual file diff against the approved correction scope, 56 sections, 76,036 occurrences (76,033 aligned; 3 known prep_token_mismatch), 5,127 SU baseline digest `0346b71f7b3f3c2078a144b56a8374a8998bf6b722d25af1fe0ce2a07ec1a5d6`, and full suite **1,479 passed, 5 skipped**, only to the extent required to authenticate the earlier independent evidence. If those read-only checks have already been independently performed, cite their existing outputs.
4. Do not publish real text, per-occurrence hashes, or private files. Report Gate A separately from Gate B.

## Gate B — T15-7.0c / B1: RUAccent runtime interface (independent)

B1 currently remains **OPEN** per the authoritative ADR; it gates T15-7.1b, T15-7.5 and WP-3 implementation. Confirm the pinned local offline RUAccent weights/config identity and repeatability of the three previously reported synthetic tests:

- `process_all()` returns stress notation using `+` markers.
- At least one of the known synthetic probes exercises the reported `е → ё` change, without propagating returned spelling to the synthesis pipeline.
- The three local synthetic probes preserve input token order/count under the ADR fold(lower, ё→е) matching contract and are repeatable under the same pinned local model/config.

Re-use already completed independent evidence if available; otherwise run **only these three synthetic probes** using existing local weights in full offline mode, with network disabled and temporary scratch outside the repository. No model downloads, no original manuscript, no audio/voice, no full text or private source outputs. Treat the test as **interface validation only**, not a claim of correct stress or speech quality.

If the local model/config, original synthetic test cases, or reproducibility evidence is missing, report **B1 BLOCKED** with exact missing prerequisites; do not invent outputs or substitute cloud inference. Gate A can still independently PASS when Gate B is BLOCKED.

## Requirements

- READ-ONLY repository, manifests, source, S2 baseline, audio and cache; temporary scratch only outside the repository. No commits/pushes, data re-publishing, synthesis or WP-3 changes.
- No extra Sol review cycle if the independent WP-2 verdict already exists; the task's purpose then is to record it and verify the separate B1 prerequisite.
- No change to approved ADR, accepted 6C11, current v4 publisher, frozen snapshot or render settings.
- STOP if any privacy or protected-state invariant fails. Return only aggregate evidence.

## Mandatory English report

```text
TASK: T15-7-WP2-WP3-TRANSITION
REFERENCE_SHA: d3f51854a283b90b94e141ace35f5a62d952b00a
ACTUAL_LOCAL_SHA:
GATE_A_WP2: PASS | CHANGES_REQUIRED | BLOCKED
GATE_A_INDEPENDENT_REVIEW_SOURCE: [actual Sol report/evidence or new targeted tests]
GATE_A_R1_R7_CLOSURE:
GATE_A_CORPUS_AND_BASELINE:
GATE_A_FULL_TEST_RESULT:
GATE_A_PRIVACY:
GATE_B_RUACCENT_B1: PASS | BLOCKED | FAIL
GATE_B_LOCAL_MODEL_CONFIG_IDENTITY:
GATE_B_3_SYNTHETIC_PROBES:
GATE_B_REPRODUCIBILITY_AND_NO_NETWORK:
REPOSITORY_FILES_CHANGED: NONE
SOURCE_CONTENT_DISCLOSED: NO
BLOCKING_FINDINGS:
COORDINATOR_NEXT_ACTION: [WP2 may be closed? WP3 may be authorized?]
```

STOP after reporting. **Do not start WP-3**; final release of its implementation remains a coordinator decision.
