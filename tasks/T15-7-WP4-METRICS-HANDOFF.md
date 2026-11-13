## Milestone-A compatibility confirmation — 2026-11-13

**Coordinator integration verdict: GO.** Sonnet's T15-7.7 SHA `928bb6e6f129d7e3e982669d83073ebbeb4645a0` was inspected against this PR. It adds `src/audiobook/stress_eval.py`, `run.sh`, gold sampling and merge tests; none of those paths overlap the PR. The actual `stress_eval.py` exposes `_load_context(config)`, `_selection(context)`, `_verify_sample(record, path)`, `_read_ledger(path)`, `inspect_ledger(rows, context)`, `yo_changed(occ)`, `vowel_count(form_analysis)` and `EvalContext`, compatible with the outlined adapter. The local milestone-A report records 1,680 passed / 6 skipped and 320 owner todo rows; this is a developer-local gate, not an independent final WP-4 acceptance.

**Integration procedure**: Sonnet owns `task/T15`. First complete the existing 7.7 local safety checks, then integrate PR #1 from `task/T15-7-wp4-metrics-core` into Sonnet's own clean/exclusive worktree. Prefer a normal Git merge of the isolated branch, or cherry-pick only the PR commits, preserving the task branch's 928bb6e implementation. No force push or main-branch change. After integration run the two standalone math test modules, then the complete scorer workflow tests. The GitHub PR remains draft pending Sonnet's integration; do not treat a partial PR as the WP-4 acceptance.

**Current adapter contract:** Load `context = _load_context(config)` and `selection = _selection(context)`; call `_verify_sample(selection.record, _sample_path(selection.record))`; get `ledger, _ = _read_ledger(paths.TEXT / "stress_gold.tsv")`; resolve `state = inspect_ledger(ledger, context)`. For **every** selected source_key require a current valid label in `state.active`, otherwise return `INCOMPLETE` with rc 2; there must be no score falsely marked COMPLETE. Use `by_key = {occ.source_key: occ for occ in context.rows}`, `selection.strata_by_key[key]`, and `{stratum: selection.record["strata"][stratum]["N"] for stratum in STRATA}` for the metric core. Convert `gold_vowel` to the set of accepted vowel positions using the ADR's `accepted(g)` (index, variants, unique-ё; ambiguous/unknown_name -> empty) and take `yo_correct` from the independently human-labelled active row. `covered_by_override = (occ.status == "covered_by_override")`, `yo_changed` via `stress_eval.yo_changed(occ)`; `correct` requires resolved F6, usable gold and membership of f6_vowel. **Never derive truth from RUAccent** or treat an empty ledger as a metric PASS. Keep source/gold identity checks and atomic S3 score writing in `stress_eval.py`.

**Owner H04:** the current todo is 320 blank-label S4 rows and can be human-labelled on the local device now. Do not rerun `stress-eval sample` after filling the todo but before merging: the current implementation intentionally refuses unmerged edited todo (`TODO_HAS_UNMERGED_LABELS`) to prevent data loss. Do not transmit the rows or context to chat/cloud.

# WP-4 (T15-7.8) — Pure Metrics Core Integration Contract

**Status:** PROPOSED, isolated PR; not yet integrated into `task/T15`.  
**Executor:** ChatGPT, parallel to Sonnet's WP-4 milestone A.  
**Code:** `src/audiobook/stress_metrics.py`  
**Tests:** `tests/test_stress_metrics.py` (43) + `tests/test_stress_metrics_contract.py` (38) = **81 passed** independently with `PYTHONHASHSEED=1,2,3`, `PYTHONDONTWRITEBYTECODE=1`, `pytest -q -p no:cacheprovider`, `PYTHONPATH=src`; full audiobook suite NOT run here. The additional oracles use independent high-precision Decimal arithmetic, complementary Wilson identities, precise gate thresholds, and permutations.  
**Effort estimate:** ~4–8 h for complete 7.8 integration, this core only is a subset; do not mark 7.8 DONE.

## Scope split / no conflicts

- **Sonnet 7.7:** `src/audiobook/stress_eval.py` (sampler, ledger, merge), `run.sh` routing, local S3/S4 state, corresponding tests. Do not overwrite these with this PR.
- **This PR:** pure mathematics of ADR §10, no disk I/O, no source data, no ledger reads, no calls to RUAccent, no build-system changes. It adds `stress_metrics.py`, the two standalone synthetic test modules, this handoff, a source-free H04 owner guide and a future Sol QA checklist.
- **Sonnet 7.8 integration:** after A local gates pass, merge/cherry-pick this PR into the WP-4 task branch and add an adapter in `stress_eval.py` and scorer-level end-to-end tests. Resolve changes against current head; do not merge directly into `main`.

## Adapter mapping

After `read_occurrences()` verifies the current v5 inventory, sample_fp is checked and the authoritative gold ledger resolves **one active human label per selected source_key**, map each selected item to:

```python
from audiobook.stress_metrics import Observation, calculate_metrics
observation = Observation(
    stratum=sample_assigned_stratum,            # one of six ADR strata
    eligible=occ.alignment_status == "aligned" and vowel_count >= 2,
    resolved=occ.f6_status == "resolved",
    usable_gold=bool(accepted_vowel_indices),   # ambiguous/unknown_name -> False
    correct=(occ.f6_status == "resolved"
             and bool(accepted_vowel_indices)
             and occ.f6_vowel in accepted_vowel_indices),
    yo_changed=derived_yo_changed_property,    # ADR §10, not stratum membership alone
    yo_correct=active_gold.yo_correct,          # human decision: y/n/na
    covered_by_override=occ.status == "covered_by_override",
)
result = calculate_metrics(observations, {stratum: N_s, ...})
```

The adapter must derive `derived_yo_changed_property` from the approved source/synth spelling comparison, not solely `stratum == "yo_changed"`; the strata are exclusive but Y is a property across all strata. `correct` is never inferred from F1/respell. `N_s` includes **all** disjoint eligible populations, not just selected/labelled rows. Validate gold `yo_correct` grammar before calling the core.

## Caller responsibilities (NOT implemented by this PR)

- Check sample record, current source_fp/analysis_fp and versioned gold validity before computing metrics.
- Reject missing active labels as INCOMPLETE (rc 2), stale/conflicting/malformed gold or sample as ERROR (rc nonzero); no automatic labeling or implicit COMPLETE.
- Build final ignored S3 score JSON and atomically write it, with required summary fields and **no text/identity in output**.
- Implement the mandatory stale→relabel→archive→score end-to-end synthetic oracle and full test suite.
- Keep the original WP-3 v5 inventory and TTS/S2/D_tsv unchanged; independent Sol reviews **the combined WP-4 only once at exit**.

## Score API

- `wilson_interval(k,n)` -> exact unrounded (lower,upper), (None,None) when n=0.
- `calculate_metrics(observations, population_by_stratum)` -> `counts`, `metrics.overall`, `metrics.by_stratum`, `metrics.book_estimates`, `gates`.
- Every rate: `{k,n,rate,lower,upper}`; undefined n=0 represented as null rate/bounds.
- `gates.G_hint`: PASS / FAIL / INCONCLUSIVE (INCONCLUSIVE is unusable); `gates.hint_allows_ordering_only` is true only for PASS.
- `gates.YO`: YO_WARN / YO_NO_EVIDENCE, not a quality PASS.
- Book estimates use `Σ_s (N_s/N)*rate_s` only for defined strata and **do not renormalize**.
- Rounding to 4 decimal digits is presentation only; comparisons use full precision.

**No independent Sol review needed for this partial PR alone.** Sonnet runs all local gates on integration; one independent acceptance at full WP-4 package SHA.
