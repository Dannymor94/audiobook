---
id: T15-7-WP1-FIX
title: Repair enum equivalence and config dependency enforcement in WP-1
status: todo
owner:
agent: claude-code
branch: task/T15
order: 9
depends_on: [T15-7-WP1]
---

# T15-7 WP-1 FIX — Close Independent Findings R1–R3

**Executor:** Claude Code Sonnet 4.6  
**Reviewer:** Codex Sol (ONE targeted review after all fixes).  
**Coordinator authorization:** GO — limited corrective implementation; **WP-2 remains HOLD**.  
**Failed reviewed code SHA:** `1f2d1833a44bc69ceaa93501900380a0bc72d197`.  
**Task published after latest documentation-only commit:** verify actual `origin/task/T15` before work.  
**Repository:** `Dannymor94/audiobook`; branch `task/T15`.

## Background and sources (read from GitHub; no owner downloads)

- `tasks/T15-7-FINAL-ADR.md` — normative §§5, 7, 11–13.
- `tasks/T15-7-WP1.md` — package specifications.
- `tasks/T15-7-EXECUTION-PLAN.md`, `tasks/T15-7-WP0-ACCEPTANCE.md`.
- `CLAUDE.md`, `AGENTS.md`, `tasks/README.md`.
- `src/audiobook/sutrace.py`, `tests/helpers/t15_7_fixture.py`, `tests/test_sutrace.py`, synthetic enum oracle, and the **existing** production `synth.py`, `voicecfg.py`, `leadin.py`, `pronounce.py` (read-only).
- This task file.

Sol independently reviewed the full WP-1 on `1f2d183...`: privacy/scope PASS; original 56-section, 5127-SU baseline digest D reproduced; 5127/5127 normal SUs matched and full pytest 1303 passed / 5 skipped. WP-1 is nevertheless **CHANGES_REQUIRED** because three *synthetically reproduced* defects exist. Do not repeat architectural scouting or reopen 6C11.

## Objective

Fix **R1, R2 and R3 in ONE Sonnet work cycle**; add focused regression tests; run one local full test pass. Do not call Sol between fixes. Sol independently reviews the final pinned SHA once. Include N1 improvement if it remains in scope; N2 is an advisory permitted status, not an automatic defect.

## R1 — A single fragment must use the original row text

**Observed failure:** `sutrace.trace_section` uses normalized/split fragment text when `enum_pause_ms>0` but `chunk_fragments(...)` returns exactly one item. Production `synth._synth_one_chunk` uses **unmodified `row["text"]`** for `len(frags)==1`.

**Required change:**
- Branch on **`len(frags)` exactly as production does**, regardless of enum_pause_ms: singleton uses `row["text"]`, `row_leadin(row)`, and `row.get("open_end",False)`; its SU identity has `fragment=None`.
- Multiple fragments use production's `frag_text` handling, question-mark trim only for enumerated fragments, `leadin.AUTO` and `open_end=False`, with integer fragment indexes.
- Add public-path synthetic regression `row["text"]=" Hi. "`, `pauses_ms.enum_pause_ms=100`, empty pronunciation table. Compare fake-engine production argument against trace exactly, including whitespace; `status=ok` must never hide a byte mismatch.

## R2 — Baseline must capture ALL production enum synthesis units

**Observed failure:** `tests/helpers/t15_7_fixture.py::_capture_section` always produces one record per manifest row; production can create multiple SUs on enum split.

**Required change:**
- Use the SAME existing `synth.chunk_fragments` and `synth.prepare_synth_text` functions (no duplicate business transformation). For `len(frags)==1`, call preparation on the original row as production; for `len(frags)>1`, use the exact per-fragment production defaults and question-mark handling.
- Store deterministic SU identities `section / row["id"] / fragment:int|null` in actual execution order; keep stored chunk hash and analytic fields contract.
- Test against the already committed synthetic 3-fragment oracle, **independently comparing to a fake-engine call trace of production `_synth_one_chunk`**, then comparing baseline capture to that reference.
- Include the singleton test from R1 and `phrase=None` vs `phrase=""`.
- **Do not overwrite/refresh the existing local S2 baseline merely to pass.** For current production config `enum_pause_ms=0`, `--check` must still match the already accepted aggregate digest:
  `0346b71f7b3f3c2078a144b56a8374a8998bf6b722d25af1fe0ce2a07ec1a5d6`.
- For synthetic `enum_pause_ms>0`, write any extra scratch fixture only under safely Git-ignored, isolated S2 scratch; never treat the current v3 published inventory as a v4 baseline.

## R3 — Enforce exact nested config-path dependencies

**Observed failure:** `_KeyRecordingConfig` only captures top-level accesses; a nested `text_prep.UNDECLARED_NESTED` read is invisible. `trace_section` also calls `chunk_fragments(..., config)` and reads `pauses_ms` outside the wrapper.

**Required change:**
- Implement recursive read-tracking for actual mapping access methods used by the existing functions (including `.get`, `[]`, `in` as applicable), recording **full dotted paths**, not merely top-level names. Nested dictionaries returned by get must remain tracked.
- Pass the same instrumented config to `chunk_fragments`, `voicecfg.prepare_text` and `leadin.fires`; record enum-related `pauses_ms.enum_pause_ms` and `pauses_ms.sentence` when accessed. Do not change production helpers.
- Declare an explicit allowlist of **verified source-level configuration paths** consistent with the ADR's `CONFIG_FP_KEYS` rule, e.g. `text_prep.yo_restore`, `text_prep.strip_quotes`, `text_prep.open_end`, `text_prep.ensure_terminal`, `render.leadin.phrase`, `render.leadin.max_chars`, `pauses_ms.enum_pause_ms`, `pauses_ms.sentence` as accessed; handle container paths/prefixes deterministically.
- Derive any additional allowed path solely from an actual read in the inspected source, documenting it in tests. **Do not add all arbitrary config keys to the allowlist**, silently ignore unknowns, or redesign the later `analysis_fp`.
- Synthetic negative tests MUST show nested unexpected reads fail closed, including via a wrapped `text_prep` mapping. Another test must demonstrate enum access under `pauses_ms` is recorded. Normal and enum SUs must still exactly match production.

## Integration coverage / nonblocking N1,N2

- Existing `test_sutrace_matches_baseline` checks only the first section. Make the local-S2 integration verification cover the **complete 56-section / 5127-SU disk baseline**, with exact identity/order, `final_sha256`, `phrase_sha256` and status, without printing book text/per-SU hashes.
- In environments without the local private S2 baseline, ordinary public/synthetic tests may skip the corpus integration, but a **WP-1 acceptance command must explicitly FAIL/BLOCK** rather than treating that skip as proof. Do not commit real S2 records.
- `trace_unsupported` is an allowed ADR §7 status; keep its behavior as specified and test that downstream acceptance does not silently count non-ok status as full success. Do not widen scope merely because the status is not raised.
- Do not change the 6C11 or TTS pipeline to satisfy tests.

## Allowed tracked changes

- `src/audiobook/sutrace.py`
- `tests/helpers/t15_7_fixture.py`
- `tests/test_sutrace.py`
- `tests/fixtures/t15_7/synthetic/*` (only if necessary, explicitly synthetic)
- `tasks/T15-7-WP1-FIX.md` status and sanitized report metadata
- `tasks/T15-7-WP1.md` only if its status/report needs to remain `review` with reference to correction.

**Everything else READ-ONLY**, especially `synth.py`, `worker.py`, `engine.py`, `chunker.py`, `voicecfg.py`, `pronounce.py`, `unitmap.py`, `config.yaml`, manifests, `out/stress`, cache, audio and the approved Final ADR.

Local ignored output: `out/t15_7/baseline/` only for safe read-only validation or isolated scratch fixtures. Do not overwrite the existing baseline or delete unrelated files.

## Acceptance and safety gates

1. R1 singleton exact engine-input equivalence, correct identity and no false `ok`.
2. R2 synthetic multi-fragment baseline matches independent fake-engine oracle (3 distinct SUs), and real `--check` reproduces the original 5127-SU D without regenerating manifests.
3. R3 full path recording: nested unknown reads rejected, enum keys recorded, all actual paths within declared allowlist.
4. All 56 sections and 5127 real SUs match original `prepare_synth_text` baseline exactly, with no non-ok statuses in acceptance.
5. Full pytest, focused tests, `PYTHONHASHSEED=1,2,3` synthetic determinism, `git diff --check`, Git privacy P1/P4 and no production imports of new modules all PASS.
6. Record exact test arithmetic and any skipped tests. Report aggregate counts/digests only.
7. Preserve the frozen 56/5127 snapshot despite `ensure_manifest_current` returning SystemExit across 56 sections; no re-chunking, synthesis, inventory publication, or full render.

**STOP:** Any requirement cannot be proven safely; any unexpected baseline digest change; actual real-corpus trace mismatch; any new dependency requiring production modifications; any privacy or cache regression; failing tests. Do not broaden the task or attempt WP-2.

## Delivery and independent QA

One commit or several logically scoped commits are acceptable; push the entire fix as one reviewable package to `task/T15` (no force-push). Before pushing, verify current remote branch SHA and preserve other worktrees. Request ONE targeted Sol re-review of R1–R3 and the WP-1 invariants at the new final SHA. Do not request another complete architecture review.

### Mandatory Report (English)

```text
TASK: T15-7-WP1-FIX
STATUS: PASS | CHANGES_REQUIRED | BLOCKED
BASE_SHA:
FINAL_REMOTE_SHA:
R1_SINGLETON_ENUM:
R2_MULTI_FRAGMENT_BASELINE:
R3_NESTED_CONFIG_GUARD:
BASELINE_D_MATCH:
ALL_56_SECTIONS_SU_MATCH:
ENUM_FAKE_ENGINE_ORACLE:
NONE_VS_EMPTY:
NON_OK_STATUSES:
TESTS_ADDED:
TEST_ARITHMETIC:
FOCUSED_PYTEST:
FULL_PYTEST:
DETERMINISM:
P1_P4_PRIVACY:
PRODUCTION_IMPORT_GUARD:
GIT_DIFF_CHECK:
CHANGED_TRACKED_FILES:
COMMIT_SHA:
PUSH_CONFIRMED:
BLOCKERS:
SOL_REVIEW_REQUIRED: YES — ONE TARGETED REVIEW
NEXT_WORK_PACKAGE_STARTED: NO
```

**STOP after reporting. WP-2 remains HOLD until independent Sol acceptance.**
