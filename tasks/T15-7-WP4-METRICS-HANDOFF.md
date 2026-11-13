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
