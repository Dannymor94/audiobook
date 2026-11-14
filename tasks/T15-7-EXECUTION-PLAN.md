# T15-7 — Execution Plan: Capability-Sized Work Packages

**Status:** APPROVED OPERATIONAL PLAN — owner-authorized risk-based Sol review is now reflected in the Final ADR §§12–13.  
**Date:** 2026-11-12  
**Repository:** `Dannymor94/audiobook`  
**Branch:** `task/T15`  
**Authority for technical contracts:** `tasks/T15-7-FINAL-ADR.md`. This operational plan does not silently supersede normative acceptance, safety, dependencies, or privacy requirements.  
**Owner preference:** group Sonnet 4.6's implementable work and require independent Sol review at meaningful risk boundaries, not every tiny substep.

## Roles and workflow

- **Owner:** approves sound quality, snapshot authority, external compute, and any full-book render or merge.
- **ChatGPT Coordinator + direct contributor:** prioritizes and scopes work packages, but **self-executes every safely separable task within available tools before delegating** (source-free pure code, synthetic tests, minimal documentation, GitHub branches/PRs, reproducible static review and evidence). Delegates only work requiring local protected corpus/model/device, unavailable runtime, an architectural decision, owner human judgment, or independent Sol acceptance. For parallel code, use an exclusive branch/worktree and draft PR, avoid Sonnet-owned files, prove local tests when available, and explicitly separate tests personally run from agent reports. Do not merge into an active shared branch, touch protected data, bypass STOP gates, or self-approve independent QA.
- **Claude Chat Architect:** resolves actual contract contradictions; no architecture reopen without new evidence.
- **Claude Code Sonnet 4.6:** implements bounded work packages, runs local tests after each internal milestone, commits to assigned branch/worktree, and STOPs at gates.
- **Codex Sol:** scouts evidence and independently reviews only at specified high-risk integration gates or on reproducible failures.

## Self-execution-first rule (owner directive, 2026-11-13)

Before giving an implementation task to another agent, the coordinator checks: **Can I complete this safely and prove it directly with my available tools?** If yes, perform it now, commit to an isolated branch or authorized docs-only plan, run the applicable local tests and report the exact SHA; do not spend a Sonnet task slot on that work. If only part is independently implementable, do that part first and hand over a narrow integration contract and PR; keep one independent Sol review at the final risk boundary. If there is a hard blocker, work on non-invasive synthetic reproducers and verification scaffolding instead of bypassing it.

**Must delegate/escalate rather than self-implement:** changes to normative ADR without architect/owner decision; any synthesis, full render, human truth/labeling; code requiring private model/manuscript/audio access not available to the coordinator; independent acceptance of one's own work. Keep existing P1–P6, production 6C11, WP1/WP3 baselines, protected code/data and main branch untouched. No background action is implied; each execution occurs when requested and available.

**Active example:** WP-4 historical ё semantics remain BLOCKED until a signed architect ADR decision. Coordinator may independently prepare isolated synthetic regression tests and a failure-characterization PR, but may not decide semantic migration or rewrite gold labels. See `tasks/T15-7-WP4-YO-ADR-ESCALATION.md`.

## Current position

- **Production 6C11, TD-1–TD-4:** CLOSED. Do not re-audit.
- **Final T15-7 ADR:** approved after independent acceptance.
- **T15-7.0b (ignore local gold files):** independent Sol PASS on `7cb8688589f81992c8c4e50cb04e9996e7c2b533`; task metadata `done`.
- **T15-7.0d:** independent read-only scouting PASS (D1–D6); 56/56 mapped, 4,624 units, 5,127 chunks, 77,998/77,998 consumed atoms, 1293 passed and 5 skipped; no blockers. Sol report received 2026-11-12.
- **T15-7.0c / B1:** **CLOSED** after independent Sol PASS: 3 synthetic offline probes repeated byte-identically in 2 processes with pinned RUAccent runtime/content identity. Interface validation only, no stress-accuracy claim; evidence in `tasks/T15-7-WP2-ACCEPTANCE.md`.
- **T15-7.0e / B2:** snapshot discrepancy investigated; owner has not authorized a future rendering snapshot.
- **T15-7 WP-1 (7.1a + 7.2):** DONE after independent Sol PASS on corrective code `aee1150d4ba866e53db2a560ac5635b89a8873eb`; report `tasks/T15-7-WP1-ACCEPTANCE.md`. All 56 sections / 5127 SU inputs match baseline, 1316 passed / 5 skipped.
- **T15-7 WP-2 (7.3 + 7.4): DONE**; independent Sol PASS authenticated against original session evidence at code SHA `d3f51854a283b90b94e141ace35f5a62d952b00a`. All seven R1–R7 corrections closed, 1,479 passed / 5 skipped, 56 sections, 76,036 occurrences, WP-1 D unchanged. Acceptance recorded in `tasks/T15-7-WP2-ACCEPTANCE.md`.
- **T15-7 WP-3 (7.1b + 7.5 + 7.6): DONE** after owner-supplied final independent Sol PASS at `205485b9eade65ca55af141f246703b7aaa71f0e`; task status is `done`. v5 published locally, v3 archive preserved, 1,602 passed / 6 skipped, S2 D and v4 D_tsv unchanged. A separately archived original Sol verdict is still useful for audit but is not a technical re-review requirement.
- **CURRENT: WP-4 (7.7 + 7.8): BLOCKED / CHANGES_REQUIRED**. Combined scorer code delivered at `f4a8dea2026fb35b104e81d396672bd96d9b0c59`; final report SHA `f07d88e41d6ab6b5a97b864eb8d063cf41bb2430`. Independent Sol found F1: unchanged `gold_vowel=yo` can silently change stress index when `form_synth` ё-restoration moves; §5 five-field gold identity conflicts with §10 restored-yo/yo_correct rules. Full suite 1,798 passed / 6 skipped but those results do NOT close F1. Architect's **Option B proposal was reviewed and explicitly NOT APPROVED by owner on 2026-11-13**. Independent risk audit and revised B′/C alternatives: draft PR #3 (`tasks/T15-7-WP4-YO-ARCHITECTURE-AUDIT.md`, branch `task/T15-7-yo-risk-audit`). Owner decision register and pre-respell evidence preflight: `tasks/T15-7-WP4-YO-OWNER-APPROVAL.md`. No normative ADR/production-code change is authorized. Original escalation: `tasks/T15-7-WP4-YO-ADR-ESCALATION.md`. No revised production contract is authorized yet. Real sample: 320 todo, zero human labels, scorer INCOMPLETE rc 2. Pause label editing/merge dependent on yo semantics until the ADR correction. All S4 data and baselines unchanged. **No WP-5, T16/T17 or rendering authorization.**
- **G0 technical verification — PASS, architecture G1 still BLOCKED (2026-11-13):** PR #3 pinned SHA `650127b90199342dfe4d1e555784025e11056f2f` was tested in isolated offline audiobook .venv by Sonnet: four G0 modules **52/52 PASS, 0 FAIL, 0 SKIP**; full pytest **1,845 PASS, 0 FAIL, 11 SKIP**. Earlier read-only private-corpus mapping PASS: **51,629/51,629 eligible and 320/320 selected** exact source→fragment→pre-respell matches, unsupported=0, selected pre/post YO mismatches=0; 416 protected files unchanged. Latest worktree clean. Five more SKIPs vs previous baseline-equipped run are consistent with missing S2 fixture but latest `-rs` node IDs were not reported, so do not claim those five tested again at this SHA. **Draft PR #3 remains unmerged.** The `g0_closed=false` diagnostic flag is intentional and the broad WP4 BLOCKED status is unchanged: architect + owner have not signed a replacement for historical YO evidence, sample/1→sample/2, dual-ledger and C3 completeness/conflict rules. G1 decision-only packet: `tasks/T15-7-WP4-YO-G1-DECISION-PACKET.md` in draft PR #3. No B/B′/C implementation authorization, S4 gold edits, sample regeneration, WP5 or rendering.

## G1 owner decision — A approved in principle, B deferred (2026-11-14)

**Owner explicitly authorized only an aggregate, read-only S4 compatibility audit.** G1.1–G1.5 (source-only gold, completeness, sample/2, exact pre-respell YO evidence, independent ledgers/freshness) = **APPROVED_IN_PRINCIPLE**, **not** code/ADR implementation permission. G1.6 (one active stress row + authoritative append-only archive, replacing C3 version ledger) = **DEFERRED_NOT_APPROVED**, pending local S4 audit and a separate owner decision. Authoritative decision register: `tasks/T15-7-WP4-YO-G1-OWNER-DECISION.md`.

Read-only audit required: physical `text/stress_gold.tsv` rows, distinct/repeated source_key and historical identity versions, `text/stress_gold.archive.tsv` rows, existing human labels and non-merged filled `text/stress_gold.todo.tsv`, selected verified RESTORED observations excluded when `f1_rule != null` or `f1_flag != none`, with aggregated PASS/BLOCKED and conservative C3 recommendation only. No row values, individual hashes or corpus text may leave the machine. **Actual local owner S4 files are unavailable via GitHub and their counts must not be invented or inferred from 320 blank selected todo entries.**

G0 remains technical PASS: 52/52 targeted tests at `650127b9`; 51,629/51,629 eligible and 320/320 selected pre-respell mappings verified for that snapshot, unsupported=0. Full test report 1,845 PASS / 11 SKIP, with five extra S2-baseline-dependent skips still to be confirmed at final QA. Independent Sol not yet given WP4 PASS.

Do **not** change normative ADR, production, S4 gold/todo/archive, sample, local corpus, 6C11, audio, models or cache; do not run H04, merge PR #3, or start WP5/T16/T17/render. After S4 audit, obtain separate owner decision on B, then a complete T01–T42 normative ADR, independent review and new explicit code GO.

### S4 compatibility audit implementation — pending owner-local run (2026-11-14)

Coordinator independently authored **test-only** read-only `tests/stress_s4_c3_readonly.py`, synthetic `tests/test_stress_s4_c3_readonly.py` and runbook `tasks/T15-7-WP4-G1-S4-READONLY-AUDIT.md` in draft PR #3 (`task/T15-7-yo-risk-audit`). These files were not run with the owner's actual private S4. **No gold/archive/todo counts are yet established**; the S4 files are Git-ignored and inaccessible via the GitHub connector. Local pure helper synthetic harness: 5 PASS (not full project QA). The audit now refuses missing owner-local gold/todo or unverifiable saved sample instead of interpreting absent worktree files as zero history; validates pre-respell selected RESTORED and F1 exclusions, checks private snapshot freshness and emits safe aggregates only. Owner-local runner must verify 416-file protected parity and return only aggregate status/counts.

G1.1–G1.5 = APPROVED_IN_PRINCIPLE; G1.6 = DEFERRED_NOT_APPROVED. Read-only audit authorization does **not** include approval of format change, migration, PR merge, production code, H04 or render. After actual S4 counts and owner decision on B, request full exact T01–T42 ADR and separate GO.

## Workload and review strategy

Package work into approximately two adjacent implementation tasks (up to three if tightly connected) and one observable output. A package should have a coherent data flow, bounded file scope and one major invariant risk. Sonnet must run focused tests at each internal step and full pytest before submitting a package. Work may continue within the package only if its local STOP gates pass.

**Independent Sol review only when crossing these risks:**
1. Baseline TTS-input equivalence and cache invariants.
2. Source provenance, identity and correction precedence.
3. External RUAccent interpretation and crash-safe, fingerprint-validated inventory publication.
4. Human gold-ledger integrity, conflict/staleness, and statistical scoring.

Use an immediate extra Sol review only for a reproducible regression, a privacy/hash/cache invariant failure, conflicting source evidence, or nontrivial contract change. Pure documentation/status updates with an exact, auditable diff do not automatically require another full test/review cycle. Synthetic and offline tests are still required even if an independent review is deferred.

**Process alignment:** The Final ADR §§12–13 has been updated to permit owner-authorized, risk-based Sol reviews at work-package boundaries. All original technical contracts, per-subtask tests, STOP conditions and privacy/cache gates remain mandatory. Each package still requires explicit coordinator execution authorization.

## Work packages

### WP-0 — Readiness scouting and privacy

**Components:** 7.0b PASS, 7.0d assigned, 7.0c evidence / B1, 7.0e snapshot evidence / B2.  
**Lead:** Sol for read-only checks; Coordinator for gate decisions.  
**Output:** stable input contracts for WP-1 and explicit residual blockers.  
**Exit:** 7.0b Sol PASS; 7.0d PASS; current technical ADR contracts unchanged (only review cadence amended by owner direction). Synchronize stale 7.0b task metadata during the next authorized write, then execute WP-1.

### WP-1 — Reproduce and trace the existing TTS input

**Components:** T15-7.1a + T15-7.2.  
**Executor:** Sonnet 4.6.  
**Scope:** synthetic and local S2 baseline fixtures; SU trace, enumeration path, `phrase=None` vs empty carrier, exact input bytes.  
**Required local gates:** baseline D reproduced in `--check`; output equals current TTS input for every SU; synthesis/hash/cache/config untouched; source data remain ignored; full pytest and P4 privacy.  
**Independent QA gate:** Sol checks baseline reproducibility and non-regression at one pinned package SHA.  
**Status:** DONE; Sol independent PASS after R1–R3 corrections. Accepted source input baseline unchanged.

### WP-2 — Locate source words and record pronunciation facts

**Components:** T15-7.3 + T15-7.4.  
**Executor:** Sonnet 4.6.  
**Scope:** `WordOcc` fields 1–35 (F6 = not_run), exact source offsets and provenance, `source_fp`, `manifest_fp`, F1–F5 classification and precedence.  
**Required local gates:** round trip from source and analysis offsets, synthetic ambiguous/partial matches, fixed deterministic serialization, token- and context-change sensitivity, `PYTHONHASHSEED` tests, baseline non-regression, full pytest.  
**Independent QA gate:** Sol verifies provenance/fingerprints/precedence once for combined package.  
**Status:** DONE. R1–R7 corrected and independently accepted at code SHA `d3f51854a283b90b94e141ace35f5a62d952b00a`; WP-2 acceptance recorded.

### WP-3 — Advise with RUAccent and publish verified inventory

**Components:** T15-7.1b + T15-7.5 + T15-7.6.  
**Executor:** Sonnet 4.6, bounded internal checkpoints.  
**Scope:** locally pinned v4 historical TSV baseline, advisory F6 and `analysis_fp`, `occurrences.tsv` through the existing atomic inventory publisher, generation freshness and reader validation.  
**Required local gates:** B1 independently closed; historical TSV digest byte-identical; no changes to TTS input; all fingerprint mutation invariants; publication integrity, crash injection, reader refusal of mixed/stale generations; full pytest.  
**Independent QA gate:** Sol reviews offline RUAccent interface consistency, content fingerprinting and crash-safe publishing at the combined package SHA.  
**STOP before publication changes if the v4 historical baseline cannot be reproduced.**  
**Status:** DONE; independent Sol PASS supplied by owner at `205485b9eade65ca55af141f246703b7aaa71f0e`; WP-3 task metadata marked `done`, historical v4 bytes and S2 D preserved.

### WP-4 — Human gold review workflow and quality metrics

**Components:** T15-7.7 + T15-7.8.  
**Executor:** Sonnet 4.6.  
**Scope:** deterministic sample, local ignored gold/todo/version ledger, stale replacement, conflict/error handling, merge, score, Wilson gates.  
**Required local gates:** repeatable selection across hash seeds; stale→relabel→archive→active gold; byte-idempotent merge; crash-safe ledger; exact Wilson references and denominators; P4 privacy, full pytest.  
**Independent QA gate:** Sol tests correctness, privacy and idempotence for the entire package.  
**Status:** BLOCKED after independent Sol CHANGES_REQUIRED on historical yo label meaning. Architecture decision `tasks/T15-7-WP4-YO-ADR-ESCALATION.md` required before code correction. Existing 320 blank todo entries are preserved; suspend new yo-dependent labeling and any merge/score changes. After approved addendum and Sonnet correction, one targeted Sol re-review.

### WP-5 — Owner labels and real quality decision

**Components:** H04 and T15-7.9 (H04 starts when sample/todo is available).  
**Executor:** Owner for listening and gold labeling, Sol for evidence consistency, Coordinator for next decision.  
**Output:** aggregate stress-quality metrics, Wilson gates, risk decision, authorized short audio tests when appropriate. No full render without owner authorization.  
**Start:** WP-4 accepted, owner labeling completed.

## Effort estimates and time tracking (owner request, added 2026-11-13)

**Units:** approximate **active work-hours** for the named executor (development, debugging and local gates), not wall-clock elapsed time or a completion promise. The time for independent QA, the owner's labeling and queue delays is tracked **separately**. These ranges are planning estimates, **not observed history**; do not retrospectively label completed tasks as having actually taken the estimate. Source/model availability, contention for gamebox, queueing, hard STOP conditions and correction cycles can increase calendar duration significantly.

**Rule for future task decomposition:** every new `tasks/T*.md` / `tasks/G*.md` / `tasks/H*.md` and each work package must specify `estimate_active_h: <min>-<max>`, executor, dependencies, QA estimate and the time of the next blocking gate. On completion, record `actual_active_h` and `actual_elapsed_h` only when measured (otherwise `unknown`); update the estimate after a material scope change. Estimate and actual are never acceptance evidence. For asynchronous agent runs, measure active execution separately from approval/wait/owner time.

### Decomposed tasks — active effort, excluding independent QA

| Package | Task | Responsible | Estimated active h | Current status |
|---|---|---|---:|---|
| WP-0 | 7.0b — local S2/S4 ignore protection | Sonnet | 0.5–1.5 | DONE |
| WP-0 | 7.0c — offline RUAccent interface probes / B1 | Sol | 1–3 | DONE |
| WP-0 | 7.0d — manifest, units, 6C11 and status reconnaissance | Sol | 1–3 | DONE |
| WP-0 | 7.0e — snapshot disagreement analysis / B2 | Sol / coordinator | 1–2 | Investigation done; owner decision OPEN |
| WP-1 | 7.1a — frozen TTS input baseline and enum oracle | Sonnet | 2–4 | DONE |
| WP-1 | 7.2 — observational SUTrace and equivalence checks | Sonnet | 3–7 | DONE |
| WP-2 | 7.3 — WordOcc provenance, source/manifest FP, links | Sonnet | 5–10 | DONE |
| WP-2 | 7.4 — facts F1–F5, F6=not_run, §9 precedence | Sonnet | 3–6 | DONE |
| WP-3 | 7.1b — isolated historical v4 TSV byte baseline | Sonnet | 2–5 | DONE |
| WP-3 | 7.5 — RUAccent F6 and analysis_fp | Sonnet | 5–10 | DONE |
| WP-3 | 7.6 — v5 publisher, stale/tamper/crash-safe reader | Sonnet | 8–16 | DONE |
| WP-4 | 7.7 — deterministic sampling and local gold merge | Sonnet | 6–12 | DELIVERED; WP4 blocked on F1 |
| WP-4 | 7.8 — metrics, Wilson, COMPLETE/INCOMPLETE/ERROR | Sonnet | 4–8 | DELIVERED; independent F1 CHANGES_REQUIRED |
| WP-5 | H04 — owner listens and labels ~320 selected items | Owner | 4–10* | WAITING for 7.7 |
| WP-5 | 7.9 — final aggregate quality-gate report | Sol / coordinator | 1–3 | WAITING for 7.8 + H04 |

*H04 is deliberately a broad estimate based on short clips and familiar review workflow; it is highly sensitive to clip availability, ambiguous words, number of relabels and owner pace. Actual human effort must be measured; no automatic acceptance of sound quality.

### Package totals, including one independent QA at each exit

| Package | Implementation / owner h | Sol independent exit QA h | Total active h (non-calendar) | Status |
|---|---:|---:|---:|---|
| WP-0 | 3.5–9.5 | 1–2 | 4.5–11.5 | DONE (B2 owner choice open) |
| WP-1 | 5–11 | 1–3 | 6–14 | DONE |
| WP-2 | 8–16 | 2–4 | 10–20 | DONE |
| WP-3 | 15–31 | 3–6 | 18–37 | DONE; Sol PASS supplied |
| **WP-4** | **10–20** | **2–4** | **12–24** | **BLOCKED — architect F1** |
| **WP-5** | **5–13** | **1–2** | **6–15** | WAITING |

**Remaining planning baseline (WP-4 + WP-5): 18–39 active h**, before any change requests, waiting for the owner, offline model availability or source/audio prerequisites. Plan a **25–40% rework contingency** separately for these remaining packages (~5–16 additional h). Some owner H04 labeling can start after 7.7 and overlap with development of 7.8, so total active hours should **not** be presented as elapsed calendar hours.

**Operational tracking in each coordinator update:** show task ID, executor, `estimate_active_h`, `actual_active_h` if known, progress/status, blocking dependency, QA estimate, and next allowed action. Re-estimate remaining hours after each package-exit PASS or material defect.

## Other work outside T15-7

- T16/T17 playback/word-times compatibility remains separately gated and depends on snapshot authority and its own acceptance.
- Voice-naturalness tests, author listening, synthesis settings and full book rendering are separate owner-controlled milestones.
- Never move `main`, regenerate manifests, alter accepted 6C11, delete audio/cache manually, or upload manuscript/voice to cloud services by default.

## Coordinator status format

For every update show:
1. Top-level project phase.
2. **Current work package** and descriptive name.
3. Substeps with `PASS / IN PROGRESS / WAITING / BLOCKED / PLANNED`.
4. Assigned executor.
5. Single next action and exact blocking condition.
6. Estimated remaining active hours for the decomposed work (owner + agent + Sol separated), and measured actual time only if available.

This document is an execution and reporting plan, not an independent permission to bypass ADR requirements.
