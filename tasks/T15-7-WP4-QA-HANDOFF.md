# T15-7 WP-4 — One Independent Sol Package-Exit Review

**Status:** PREPARED, not started. Use only after Sonnet delivers the combined **7.7 + 7.8** WP-4 at the final pinned SHA.  
**Review duration estimate:** 2–4 active hours; revise if blocking defects require another correction.  
**Target:** `task/T15`, not this partial metrics branch.  
**Normative authority:** `tasks/T15-7-FINAL-ADR.md` §5, §10 C3/U5, §11 P1–P6, §12 7.7/7.8; `tasks/T15-7-WP4.md`.  
**Review cadence:** ONE Sol exit review, not separate 7.7 and 7.8 reviews. The metrics-core PR is not the complete package.

## Independently verify

**Q1 — Scope / regressions:** Record exact final SHA, code/test/task diff, clean worktree, full pytest count, `PYTHONHASHSEED=1,2,3` focused runs and P1/P4. Confirm no change to WP-1 TTS baseline, v4 historical TSV D_tsv, source text, publisher v5/archives, config/manifests, cache, model, audio or 6C11. No manuscript excerpts/hashes in output.

**Q2 — Sampler literal oracle:** Read the validated current v5 `read_occurrences()`; synthetic-only fixtures. Eligibility = aligned, ≥2 vowels in analysis form. Classify in **omograph → top300 → name → override_covered → yo_changed → tail** order with disjoint populations. Independently compare top300 frequencies/ties, n targets (100/60/40/40/40/40), take-all when N_s<n_s, SHA-256 seed ordering, exact selected keys and sample_fp mutation domains. Stable across hash seeds and input order. Single-vowel rows count-only.

**Q3 — Gold grammar & independent ledger oracle:** Header exact (10 fields), vowel indices 0-based within form_source, `variants:i|j` genuinely distinct/in-range, `yo` allowed only for unique ё, reject `yo_unstressed`, `yo_correct=y/n/na` with `y/n` required for yo_changed, date format, labeler nonempty, context≤80, five-part source/context identity and current sample fingerprint. Prevalidate whole input before writes. Synthetic stale neighbor edit → old version retained, becomes STALE → todo includes key → merge accepts new identity → original archived → score uses **only** new active gold. Repeated merge byte-identical; conflicting valid ACTIVE labels ERROR, exact duplicate semantics collapse; reverting identity can produce conflict. Crash before/after `os.replace` leaves a complete ledger and recoverable derived export. Archive is never authoritative.

**Q4 — Scorer decision oracle:** Independently calculate §10 counts, denominators, rates, Wilson and weighted per-stratum estimates. Use at least one independent high-precision reference (not the same implementation imported twice). Check 40/40, 92/100, 91/100, 73/73 and 1e-9 matching, 92/100 hint PASS, 91/100 INCONCLUSIVE, upper<0.85 FAIL, n<80 not PASS. YO_WARN if any incorrect ё judgment; otherwise YO_NO_EVIDENCE even for a tiny perfect sample. Distinguish strata membership vs yo_changed property across other strata. Undefined n=0 is null, not zero. No rounding before decisions; no renormalization of book population weights when stratum rate undefined. Verify exact `S,E,R,U,C,O,Y` set semantics and `override_disagreement` denominator.

**Q5 — Package integration / safe outputs:** Current sample and source/analysis fingerprints must be checked before returning any result. Missing active gold for a selected key → INCOMPLETE **rc 2**; malformed/mixed/stale sample/gold or conflicting active labels → ERROR **nonzero**; COMPLETE **rc 0** only after synthetic fully valid labels. Score JSON in ignored S3 is atomic and contains only aggregates and allowed digests, no book text or gold rows. The pure `stress_metrics.py` and its separate contract tests must be correctly adapted, not treated as a substitute for sample/ledger validation.

**Q6 — Real snapshot (aggregate only):** 56 sections / 5,127 SUs / 76,036 occurrences; retain 76,033 aligned and three `prep_token_mismatch`; independently confirm accepted S2 D `0346b71f7b3f3c2078a144b56a8374a8998bf6b722d25af1fe0ce2a07ec1a5d6`; v4 `D_tsv=105711f20d92f337642b66924eba30317dba4e2f393676d07739e83d7ebc11c6`. Do not claim H04 real human gold accuracy until owner supplies labels. Real S4 outputs remain ignored/untracked. Never use raw corpus data in the report.

## Verdict and required reply

Return `PASS`, `CHANGES_REQUIRED` with exact synthetic reproduction/minimal correction, or `BLOCKED` with missing evidence. Never accept a developer's test totals as independent evidence. If something is missing but only because real owner H04 has not labeled gold, distinguish implementation PASS from actual quality result INCOMPLETE.

```text
TASK: T15-7-WP4-INDEPENDENT-ACCEPTANCE
FINAL_CODE_SHA:
STATUS: PASS | CHANGES_REQUIRED | BLOCKED
Q1_SCOPE_AND_PRIVACY:
Q2_SAMPLING_AND_SAMPLE_FP:
Q3_GOLD_LEDGER_C3_AND_CRASH:
Q4_METRICS_WILSON_AND_GATES:
Q5_SCORE_STATUS_AND_JSON:
Q6_REAL_CORPUS_BASELINES:
FULL_PYTEST:
HASH_SEEDS:
INDEPENDENT_PROBES:
BLOCKING_FINDINGS:
NONBLOCKING_FINDINGS:
WP5_RECOMMENDATION:
```

**READ-ONLY.** No source edits, code commits, regeneration of manuscripts/manifests, full rendering, model downloads, sample/gold publication or automatic labeling. STOP after reporting.
