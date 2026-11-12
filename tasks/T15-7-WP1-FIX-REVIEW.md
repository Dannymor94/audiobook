# T15-7 WP-1-FIX — Independent Targeted Acceptance

**Executor:** Codex Sol — Independent Reviewer  
**Repository:** `Dannymor94/audiobook`  
**Code commit:** `aee1150d4ba866e53db2a560ac5635b89a8873eb`  
**Final report SHA:** `1a5e65fe9d75a2a1a2997fb79354144fa5e99176`  
**Original rejected WP-1 SHA:** `1f2d1833a44bc69ceaa93501900380a0bc72d197`  
**Scope:** Targeted re-review of R1, R2, R3 and necessary invariants only.  
**Mode:** READ-ONLY. No code modifications, synthesis, manifest rebuilding, inventory publication, commit or push.

## Objective

Verify that Sonnet's one-package R1–R3 correction actually closes the **three independently reproduced defects**, without changing the accepted production synthesis path. Do not repeat unrelated architecture or historical 6C11 audits.

**Read directly from GitHub:**
- `tasks/T15-7-WP1-FIX.md` (required corrections and Sonnet's delivery report)
- `tasks/T15-7-WP1.md`
- `tasks/T15-7-WP1-REVIEW.md` (prior Sol findings)
- `tasks/T15-7-FINAL-ADR.md`, especially §§5, 7, 11–13
- `CLAUDE.md`, `AGENTS.md`
- Code diff `1f2d1833a44bc69ceaa93501900380a0bc72d197..aee1150d4ba866e53db2a560ac5635b89a8873eb`, and documentation-only diff `aee1150d4ba866e53db2a560ac5635b89a8873eb..1a5e65fe9d75a2a1a2997fb79354144fa5e99176`

## Review order

### 1. Exact scope and privacy
- Ensure code diff changes only `src/audiobook/sutrace.py`, `tests/helpers/t15_7_fixture.py`, `tests/test_sutrace.py`; final report commit changes only `tasks/T15-7-WP1-FIX.md`.
- Confirm production `synth`, `voicecfg`, `leadin`, `pronounce`, `chunker`, `worker`, `engine`, config, manifests, caches, and audio are unchanged.
- Run P1/P4 checks against the actual tracked/index/staged/new-file state; do not print or commit restricted real-corpus content, per-SU hashes, or manuscript excerpts.

### 2. R1 — Singleton enum uses exact original row text
- Independently replay the previously failing synthetic case: `row["text"] = " Hi. "`, `pauses_ms.enum_pause_ms=100`.
- Confirm that production `_synth_one_chunk` (fake engine) and public `trace_section` use the SAME untouched original `row["text"]` when `len(frags)==1`, including whitespace, stored/AUTO phrase and open_end.
- Confirm `fragment=None`, `status=ok` only for truly identical final input, and proper handling of `len(frags)>1`.

### 3. R2 — Complete production-equivalent baseline for enumeration
- Use the existing synthetic multi-fragment oracle. Compare the real production `_synth_one_chunk` fake-engine calls, the baseline helper `_capture_section`, and `trace_section`.
- Require 3 fragment identities, identical final text and phrase hashes; independently exercise the singleton path as well.
- On the existing 56-section frozen disk snapshot, verify 5,127 SUs and the accepted aggregate D `0346b71f7b3f3c2078a144b56a8374a8998bf6b722d25af1fe0ce2a07ec1a5d6`.
- `--check` must reproduce D **without rewriting the accepted S2 baseline**. If the local S2 file is missing, do not treat `pytest skip` as acceptance; return BLOCKED for real-corpus evidence if safe independent reproduction is impossible.
- Confirm `ensure_manifest_current` remains SystemExit in 56/56 and recorded impact remains 11 lost / 11 rendered, not an assumed fresh manifest.

### 4. R3 — Real enforcement of nested configuration dependencies
- Verify recursive dotted-path tracking, including `.get`, `[]`, and `in`, returns shared access history for nested mappings.
- Independently show that reading an unknown nested `text_prep` key triggers the public acceptance/guard path and fails closed. A synthetic test of `cfg._accessed` alone is **not** enough; the boundary enforcing `DECLARED_CONFIG_PATHS` must reject it.
- Confirm that `synth.chunk_fragments` receives the instrumented config, including `pauses_ms.enum_pause_ms` and `pauses_ms.sentence` when accessed.
- Inspect every declared path against source-level reads; reject hidden bypasses or permissive allowlisting of arbitrary keys. Preserve production semantics.

### 5. N1/N2 and overall safety
- Independently verify all 56 sections / 5,127 SUs: ordered identities, final and phrase hashes, 0 mismatches and 0 non-ok statuses. No restricted values in report.
- Confirm ordinary tests cannot claim a corpus PASS merely because the ignored S2 fixture is unavailable (skips are not evidence). State exactly which check gates fail/skip without S2.
- `trace_unsupported` is a permitted status by ADR; ensure any final integration acceptance explicitly rejects non-ok records. Do not require redesign merely for having this status.
- Confirm `phrase=None` differs from `phrase=""` and original TTS input/hash/cache logic is untouched.
- Independently run focused and full pytest and deterministic synthetic cases under at least `PYTHONHASHSEED=1,2,3`, using scratch outside the project where required. Verify change in test count: 1303 -> 1316 passed, 5 skipped (unless explained).
- Check `git diff --check`.

## Acceptance and STOP

- PASS only if all three reproduced R1–R3 cases are closed, the baseline and privacy invariants remain intact, and independent evidence is reproducible at the pinned code SHA.
- CHANGES_REQUIRED only for verified defects, with a minimal reproducible correction.
- BLOCKED for unavailable local corpus or unexecutable checks; distinguish from implementation failure.
- No new architecture cycle or expanding scope into WP-2.
- Do not change the repository, branch/worktree state, manifests or S2 baseline.

## Required output (English only)

```text
TASK: T15-7-WP1-FIX-INDEPENDENT-ACCEPTANCE
STATUS: PASS | CHANGES_REQUIRED | BLOCKED
CODE_SHA:
FINAL_REPORT_SHA:
DIFF_SCOPE:
R1_SINGLETON_PRODUCTION_PARITY:
R2_MULTI_FRAGMENT_FAKE_ENGINE_PARITY:
R2_BASELINE_D_56_5127:
R3_NESTED_CONFIG_FAIL_CLOSED:
R3_ENUM_CONFIG_PATHS:
N1_ALL_SECTION_EQUIVALENCE:
N2_NON_OK_AND_MISSING_S2_HANDLING:
PHRASE_NONE_VS_EMPTY:
PRIVACY_AND_PRODUCTION_SAFETY:
FOCUSED_TESTS:
FULL_PYTEST:
DETERMINISM:
DIFF_CHECK:
BLOCKING_FINDINGS: [ID | exact path:function:line | reproduction | minimal correction]
NONBLOCKING_FINDINGS:
FINAL_VERDICT:
WP2_RECOMMENDATION:
```

**STOP after reporting. WP-2 remains HOLD until coordinator review of this independent verdict.**
