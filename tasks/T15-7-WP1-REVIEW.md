# T15-7 WP-1 — Independent Integration Review (7.1a + 7.2)

**Executor:** Codex Sol — Independent Reviewer  
**Repository:** `Dannymor94/audiobook`  
**Reviewed SHA:** `1f2d1833a44bc69ceaa93501900380a0bc72d197`  
**Base SHA:** `5b49ba85bb2531b8b02779e4bd93739962319b28`  
**Mode:** READ-ONLY for tracked repo, production code, manuscript, manifests, audio and cache. Disposable ignored local baseline fixtures may be created ONLY as necessary for an independent replay; never overwrite an existing user baseline. No commits/pushes/merge.

## Goal

Independently accept or reject the **entire WP-1 as one work package**, rather than reviewing its internal 7.1a and 7.2 separately. Do not use Sonnet's report as proof.

Read directly from GitHub:
- `tasks/T15-7-FINAL-ADR.md` §§11–13
- `tasks/T15-7-WP1.md`
- `tasks/T15-7-WP0-ACCEPTANCE.md`
- `tasks/T15-7-EXECUTION-PLAN.md`
- `CLAUDE.md`, `AGENTS.md`
- Changed production-adjacent code and tests in the base..target diff.

## Review Gates

### G1 — Commit scope, privacy and baseline
- Verify commit range and exact changed paths. Production `synth.py`, `voicecfg.py`, `pronounce.py`, `chunker.py`, `unitmap.py`, `config.yaml`, manifests/cache untouched.
- Independently check P1/P4: synthetic fixture provenance, no real book text, actual corpus-derived hashes, gold, model or audio in Git/staging. Avoid printing sensitive values.
- Verify `T15-7.0b` legitimately moved to `done` after independent PASS, and WP1 is in `review`.
- Verify S2 `out/t15_7/baseline/` ignored and untracked. D as an aggregate SHA-256 is reportable; individual hashes/row text are NOT.

### G2 — Genuine immutable baseline (7.1a)
- Capture or replay with the actual pre-existing preparation function `synth.prepare_synth_text` (not a second implementation). Confirm output record identity and order for all 56 sections and 5,127 disk SUs.
- Compare stored records (SU final text SHA-256, phrase SHA-256 with `None` vs empty, stored row hash and analytic fields) and `--check` digest D:
  `0346b71f7b3f3c2078a144b56a8374a8998bf6b722d25af1fe0ce2a07ec1a5d6`
- Verify this D only on the same known corpus/config/pronounce snapshot. If local S2 is absent, inspect test skip behavior and reproduce in a safe isolated environment if possible, without overwriting an existing baseline. If impossible, BLOCKED (do not infer baseline PASS from skipped tests).
- Confirm true results of `ensure_manifest_current` (reported SystemExit in all 56) and `impact` (reported 11 lost / 11 rendered). Inspect safety of those read-only calls. This is **snapshot readiness information**, not authorization to regenerate manifests or render.
- Verify synthetic enum oracle covers *the production enumeration branch* and the expected fragment identities/phrase handling, not merely independent test data constructed from the same flawed trace.

### G3 — Observational trace equivalence (7.2)
- Independently compare `sutrace.trace_section` with the original `synth.prepare_synth_text` for **every SU in all 56 sections**, not just the first section chosen by the current integration test. Report mismatched SU counts only; never print strings or per-SU digests.
- Check `None` vs `""`, lead-in AUTO/stored/fallback, padding, longest-key pronunciation replacement, punctuation/sentinel and enum split handling.
- Check `pad_len`, matches spans, key-recording guard and accessed CONFIG keys against actual code. In particular, evaluate whether nested config reads and `pauses_ms` are instrumented or bypass the guard. Do not automatically fail for a naming difference; require the actual approved contract.
- **Potential fail-open path:** `_trace_su` can return `trace_unsupported` when a suffix invariant fails, while `trace_section` explicitly raises only for `trace_mismatch`. Verify whether this violates the ADR's fail-closed STOP behavior using a synthetic monkeypatch/probe if safe.
- **Potential skip gap:** baseline integration tests use `skipif(not BASELINE_PATH.exists())`; evaluate whether all material gates are still demonstrated when an independent local baseline is absent.
- Verify `sutrace` is imported nowhere on the production path and does not modify synthesis-input bytes/cache hashes (I3, C2-a).

### G4 — Reproducible checks and test arithmetic
- Run focused tests and full `uv run pytest -q` in a safe local worktree. Independently check `1293 + 10 = 1303` passes and five skipped; explain any variation. Use `PYTHONDONTWRITEBYTECODE=1` and controlled scratch to avoid unwanted repo writes.
- Confirm deterministic tests and any missing required scenario. Inspect `git diff --check`.
- Reject a claimed WP1 PASS if reproducibility, actual all-SU equivalence, privacy or critical failure handling is unproven; distinguish `CHANGES_REQUIRED` (proven defect) from `BLOCKED` (missing independent local evidence).

## Output — English only

```text
TASK: T15-7-WP1-INDEPENDENT-REVIEW
STATUS: PASS | CHANGES_REQUIRED | BLOCKED
REVIEWED_SHA:
BASE_SHA:
DIFF_SCOPE:
G1_PRIVACY_AND_SCOPE:
G2_BASELINE_REPRODUCTION:
  SECTIONS:
  SU_COUNT:
  DIGEST_D_MATCH:
  ENUM_PRODUCTION_BRANCH:
  ENSURE_MANIFEST_CURRENT:
  IMPACT:
G3_TRACE:
  ALL_SECTION_SU_EQUIVALENCE:
  NONE_VS_EMPTY:
  RESPELL_MATCHES_AND_PAD:
  CONFIG_KEY_GUARD:
  FAIL_CLOSED_STATUSES:
  PRODUCTION_INVARIANTS:
G4_TESTS:
  FOCUSED:
  FULL_PYTEST:
  TEST_ARITHMETIC:
  DIFF_CHECK:
BLOCKING_FINDINGS: [ID | file:function:line | reproduction | smallest correction]
NONBLOCKING_FINDINGS:
FINAL_VERDICT:
RECOMMENDATION_FOR_WP2:
```

**STOP after reporting.** No fixes, no new code, no rendering, no inventory publication, no manifest regeneration, no work on WP-2. Return concise reproducible evidence. The coordinator decides whether Sonnet proceeds.
