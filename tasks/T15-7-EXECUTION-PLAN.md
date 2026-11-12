# T15-7 — Execution Plan: Capability-Sized Work Packages

**Status:** COORDINATOR PLAN; pending a narrow update to the final ADR's per-task review rule before batching replaces that rule.  
**Date:** 2026-11-12  
**Repository:** `Dannymor94/audiobook`  
**Branch:** `task/T15`  
**Authority for technical contracts:** `tasks/T15-7-FINAL-ADR.md`. This operational plan does not silently supersede normative acceptance, safety, dependencies, or privacy requirements.  
**Owner preference:** group Sonnet 4.6's implementable work and require independent Sol review at meaningful risk boundaries, not every tiny substep.

## Roles and workflow

- **Owner:** approves sound quality, snapshot authority, external compute, and any full-book render or merge.
- **ChatGPT Coordinator:** prioritizes and scopes work packages, tracks dependencies, chooses QA gates, and accepts scoped deliverables based on evidence.
- **Claude Chat Architect:** resolves actual contract contradictions; no architecture reopen without new evidence.
- **Claude Code Sonnet 4.6:** implements bounded work packages, runs local tests after each internal milestone, commits to assigned branch/worktree, and STOPs at gates.
- **Codex Sol:** scouts evidence and independently reviews only at specified high-risk integration gates or on reproducible failures.

## Current position

- **Production 6C11, TD-1–TD-4:** CLOSED. Do not re-audit.
- **Final T15-7 ADR:** approved after independent acceptance.
- **T15-7.0b (ignore local gold files):** independent Sol PASS on `7cb8688589f81992c8c4e50cb04e9996e7c2b533`; task metadata still says `review`; synchronize to `done` before 7.1a.
- **T15-7.0d:** read-only scouting assigned to Sol via `tasks/T15-7.0d-SCOUT.md`; report pending.
- **T15-7.0c / B1:** offline RUAccent probes reported; their pinned reproducibility evidence still needs independent acceptance for dependent tasks.
- **T15-7.0e / B2:** snapshot discrepancy investigated; owner has not authorized a future rendering snapshot.
- **T15-7.1a onward:** not yet authorized.

## Workload and review strategy

Package work into approximately two adjacent implementation tasks (up to three if tightly connected) and one observable output. A package should have a coherent data flow, bounded file scope and one major invariant risk. Sonnet must run focused tests at each internal step and full pytest before submitting a package. Work may continue within the package only if its local STOP gates pass.

**Independent Sol review only when crossing these risks:**
1. Baseline TTS-input equivalence and cache invariants.
2. Source provenance, identity and correction precedence.
3. External RUAccent interpretation and crash-safe, fingerprint-validated inventory publication.
4. Human gold-ledger integrity, conflict/staleness, and statistical scoring.

Use an immediate extra Sol review only for a reproducible regression, a privacy/hash/cache invariant failure, conflicting source evidence, or nontrivial contract change. Pure documentation/status updates with an exact, auditable diff do not automatically require another full test/review cycle. Synthetic and offline tests are still required even if an independent review is deferred.

**Normative process conflict:** The approved ADR §12/§13 currently requires `Sol review at a pinned SHA before the next task`. Before authorizing execution across original task boundaries without intervening Sol review, obtain a narrowly scoped procedural correction to this one rule (owner-approved risk gates above) and verify it does not weaken any technical acceptance or STOP condition. No revised implementation permissions are implied until then.

## Work packages

### WP-0 — Readiness scouting and privacy (current)

**Components:** 7.0b PASS, 7.0d assigned, 7.0c evidence / B1, 7.0e snapshot evidence / B2.  
**Lead:** Sol for read-only checks; Coordinator for gate decisions.  
**Output:** stable input contracts for WP-1 and explicit residual blockers.  
**Exit:** 7.0b status synchronized; 7.0d PASS or exact bounded blocker; approved ADR unchanged.

### WP-1 — Reproduce and trace the existing TTS input

**Components:** T15-7.1a + T15-7.2.  
**Executor:** Sonnet 4.6.  
**Scope:** synthetic and local S2 baseline fixtures; SU trace, enumeration path, `phrase=None` vs empty carrier, exact input bytes.  
**Required local gates:** baseline D reproduced in `--check`; output equals current TTS input for every SU; synthesis/hash/cache/config untouched; source data remain ignored; full pytest and P4 privacy.  
**Independent QA gate:** Sol checks baseline reproducibility and non-regression at one pinned package SHA.  
**Start:** after WP-0, ADR/process gating, and explicit coordinator authorization.

### WP-2 — Locate source words and record pronunciation facts

**Components:** T15-7.3 + T15-7.4.  
**Executor:** Sonnet 4.6.  
**Scope:** `WordOcc` fields 1–35 (F6 = not_run), exact source offsets and provenance, `source_fp`, `manifest_fp`, F1–F5 classification and precedence.  
**Required local gates:** round trip from source and analysis offsets, synthetic ambiguous/partial matches, fixed deterministic serialization, token- and context-change sensitivity, `PYTHONHASHSEED` tests, baseline non-regression, full pytest.  
**Independent QA gate:** Sol verifies provenance/fingerprints/precedence once for combined package.  
**Start:** WP-1 PASS.

### WP-3 — Advise with RUAccent and publish verified inventory

**Components:** T15-7.1b + T15-7.5 + T15-7.6.  
**Executor:** Sonnet 4.6, bounded internal checkpoints.  
**Scope:** locally pinned v4 historical TSV baseline, advisory F6 and `analysis_fp`, `occurrences.tsv` through the existing atomic inventory publisher, generation freshness and reader validation.  
**Required local gates:** B1 independently closed; historical TSV digest byte-identical; no changes to TTS input; all fingerprint mutation invariants; publication integrity, crash injection, reader refusal of mixed/stale generations; full pytest.  
**Independent QA gate:** Sol reviews offline RUAccent interface consistency, content fingerprinting and crash-safe publishing at the combined package SHA.  
**STOP before publication changes if the v4 historical baseline cannot be reproduced.**  
**Start:** WP-2 PASS and B1 closed.

### WP-4 — Human gold review workflow and quality metrics

**Components:** T15-7.7 + T15-7.8.  
**Executor:** Sonnet 4.6.  
**Scope:** deterministic sample, local ignored gold/todo/version ledger, stale replacement, conflict/error handling, merge, score, Wilson gates.  
**Required local gates:** repeatable selection across hash seeds; stale→relabel→archive→active gold; byte-idempotent merge; crash-safe ledger; exact Wilson references and denominators; P4 privacy, full pytest.  
**Independent QA gate:** Sol tests correctness, privacy and idempotence for the entire package.  
**Start:** WP-3 PASS.

### WP-5 — Owner labels and real quality decision

**Components:** H04 and T15-7.9 (H04 starts when sample/todo is available).  
**Executor:** Owner for listening and gold labeling, Sol for evidence consistency, Coordinator for next decision.  
**Output:** aggregate stress-quality metrics, Wilson gates, risk decision, authorized short audio tests when appropriate. No full render without owner authorization.  
**Start:** WP-4 accepted, owner labeling completed.

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

This document is an execution and reporting plan, not an independent permission to bypass ADR requirements.
