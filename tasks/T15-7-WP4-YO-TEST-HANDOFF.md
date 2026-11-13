# T15-7 WP-4 historical ё gold — synthetic regression handoff

**Status:** PREPARED / ADR BLOCKED. This is NOT an approved normative correction.  
**Owner rule:** coordinator self-executes safely separable work; architecture decision stays with Claude Chat + owner.  
**Base:** `task/T15`, current blocked WP-4 code.  
**Only functional addition:** `tests/test_stress_eval_yo_adr_oracles.py`.  
**Planning:** targeted correction estimated 2–5 Sonnet active hours + 1–2 Sol targeted QA hours, subject to architect-approved persistence/migration design. These are *new planning estimates*, not actual measured time.

## What was independently prepared

Three original **synthetic** restored-ё moves against an unchanged source/context identity are encoded as `pytest.mark.xfail(strict=True)` cases. A fourth positive test verifies the five-part source gold identity does not change when only synthesized spelling differs. Synthetic strings only; no production text, audio, hashes or manifests.

The three strict xfails specifically prohibit this silent failure:

1. Historical `gold_vowel=yo` was attached to one vowel under an earlier restoration.
2. Source-only five-part identity remains equal, but the current synthetic restoration moves ё to another vowel.
3. The current scorer/ledger reports the same old gold row as ACTIVE and derives a different accepted stressed-vowel index using current `form_synth`.

The test accepts **either** a preserved original stress index or an explicitly stale/nonactive old row, but it does NOT decide which mechanism the new ADR should select. The current code is expected to fail these assertions (recorded as XFAIL, not PASS). On new ADR approval, modify expected outcomes if needed, remove all xfail markers, and require ordinary PASS — an unexpected XPASS with strict=True intentionally stops the suite until this has been done.

**Execution status:** These tests have been authored against actual GitHub source and existing synthetic helpers. No full audiobook runtime/corpus was available to the coordinator; no claim is made that this separate test file has been executed locally. Sonnet must execute the focused tests when integrating after ADR approval. The original independent Sol review has already reproduced all three F1 behaviors on its local runtime; this branch does not count as a second Sol review.

## Exact activation after architect decision

- Read approved ADR amendment **before** modifying `stress_eval.py` or the human ledger.
- Test target:

```bash
PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  uv run pytest -q -p no:cacheprovider tests/test_stress_eval_yo_adr_oracles.py
```

- Add the other original Sol cases (removal of a restored ё, introduction of restored ё with numeric gold and `yo_correct=na`) as **ADR-specific** PASS oracles, including deterministic stale/restore and collision behavior. Do not predeclare how legacy labels should migrate while design is undecided.
- Require no silent inference of old restored-ё position, no automatic relabel and no loss of C3 history.
- Run the entire WP-4 full suite, independent seed checks, P1/P4 scan, WP1 D and v4 D_tsv parity. WP5 and rendering HOLD until Sol PASS on final corrected WP4 SHA.
- This branch/PR must **not** merge into the blocked branch as an implemented fix; its xfail cases document the defect. No code, data, model or audio other than tests/plan docs has changed.

## Exact current reference evidence

- Combined code: `f4a8dea2026fb35b104e81d396672bd96d9b0c59`.
- Independent Sol CHANGES_REQUIRED; WP4 report: `tasks/T15-7-WP4.md`.
- ADR decision request: `tasks/T15-7-WP4-YO-ADR-ESCALATION.md`.
- Prior full reported suite: 1798 passed, 6 skipped, but does not close F1.
- Owner S4 files retain their bytes; 320 todo entries are blank and score is INCOMPLETE rc2.
