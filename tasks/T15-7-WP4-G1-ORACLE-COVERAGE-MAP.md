---
id: T15-7-WP4-G1-ORACLE-COVERAGE-MAP
status: AWAITING_ARCHITECT_SIGNOFF
branch: task/T15-7-wp4-g1-normative-adr
---

# T15-7 WP4 — Architect original-concept O01–O42 → reconstructed T01–T42

**Status:** Mapping supplied for architect review; NOT signed, adopted or implementation-authorized.

**Authority and provenance:** Original-concept O01–O42 descriptions came from the architect's explicit coordinator handoff. The previous archive-authoritative numbering is rejected by the owner. This map adopts no claim of verbatim equivalence. The new normative candidate retains `stress_gold.tsv` as the sole authoritative stress version-ledger; `stress_gold.archive.tsv` is a derived, non-authoritative export. The original 42-item contents are represented below as a concept mapping, not uploaded private corpus data.

**Meaning of mapped:** The referenced reconstructed T-test(s) and normative sections collectively cover the concept. Multiple O concepts may map to one T test; one O concept may require several T tests. **VOID** means the historical assertion conflicts with the retained-C3 owner decision and is replaced with an explicit new oracle. Actual pytest node IDs and implementation PASS are future work, not asserted here.

| Original | New T / section | Disposition and exact retained-C3 meaning |
|---|---|---|
| O01 | T05, T10, T13 | Legacy synth-only yo remains unresolved; todo and INCOMPLETE until explicit source-index label |
| O02 | T07, T29, T38 | Numeric source stress persists; new exact current restoration needs YO evidence |
| O03 | T08 | Moving restored yo cannot change the human source-vowel index |
| O04 | T35 | A→B→A reuses only freshly reverified exact restoration_fp |
| O05 | T09 | Source-native unique yo and corresponding numeric index are one semantic stress truth |
| O06 | T06 | Different current accepted source-vowel sets require OWNER_ADJUDICATION_REQUIRED |
| O07 | T11, T12 | Ambiguous and unknown_name complete annotation without usable stress accuracy |
| O08 | T11, T12, T42 | All non-positional labels can complete labeling, while zero usable denominator yields G_hint INCONCLUSIVE |
| O09 | T29, T38 | Missing matching current YO verdict => INCOMPLETE and no passing gate |
| O10 | T37 | Opposite YO judgments for one fingerprint => ERROR |
| O11 | T33 | Two forward restorations plus one n count as one incorrect candidate |
| O12 | T26, T30 | Post-respell-only yo is not pre-respell RESTORED |
| O13 | T31 | Unproven source/chunk/fragment ordinal yields UNSUPPORTED; never fuzzy-match |
| O14 | T36 | Same mtime with different normalized YO-map content must be detected via bytes |
| O15 | T36, T35 | Fresh reobservation of identical candidate permits reusing its human verdict |
| O16 | T34 | Different candidate fingerprint requires new judgment; old retained |
| O17 | T21 | sample/1 assignment collision captured as characterization; sample/2 rejects |
| O18 | T21 | Selected stratum swap changes sample/2 digest/fp |
| O19 | T21 | Selected key union unchanged but stratum assignment changed => old sample stale |
| O20 | T24, T25 | Original 320-row todo protected; no silent replacement or migration |
| O21 | T40 | Authoritative gold atomic replace survives crash before/after rename |
| O22 | T41 | Dual-ledger change before score publish gives ERROR and preserves prior score |
| O23 | T41 | Persisted COMPLETE is rejected as stale after dependencies change |
| O24 | T07, T38 | Historical ten-column yo_correct is not rebound to a current candidate |
| O25 | T42 | No current YO_EVALUABLE allows absent YO ledger and YO_NO_EVIDENCE |
| O26 | T38 | Missing YO ledger with current restoration produces INCOMPLETE |
| O27 | T02, T03, T27 | Source-identity change keeps old row in authoritative gold, now SOURCE_STALE |
| O28 | T17, T28 | A→B→A reclassification from gold; if conflicting A answers then ERROR |
| O29 | T39 | Invalid evidence schema/fingerprint/version gives ERROR |
| O30 | T22, T42 | Seeds 1/2/3 deterministic, P1/P4 privacy and baseline contracts |
| O31 | T10 | Legacy current-identity row remains in gold; new numeric version appended, legacy non-competing; retry no-op |
| O32 | T24, T25; §3.6 | Different existing todo bytes cause OWNER_TODO_PROTECTED; filled unmerged labels guarded |
| O33 | T07, T34 | Stress merge independent of sample/analysis/restoration; YO merge bound to current restoration_fp, not sample |
| O34 | T16, T18, T29 | F1-excluded RESTORED stays outside Y; no YO todo |
| O35 | T31; §4.8 | Full L3 composed_final/phrase exact equivalence, including None versus empty |
| O36 | T41; §5.7 | Unavailable OS-backed evaluation lock fails closed EVAL_LOCK_UNAVAILABLE |
| O37 | T06 | Current ambiguous↔numeric answer conflict needs OWNER_ADJUDICATION_REQUIRED |
| O38 | VOID / REPLACED by T19, T27, T40 | Original archive dedup is VOID because archive is derived, non-authoritative; replacement oracle demands deterministic byte-identical rebuild without treating archive as authority |
| O39 | T06, T17, T28 | Conflicting current versions in authoritative gold produce ERROR; no archive-based bypass |
| O40 | T10 | Legacy synth-only yo is excluded from competing active decisions |
| O41 | T37 | Same-fp opposite YO judgments rejected even when candidate is historical/noncurrent |
| O42 | T39; §4.7 | Other observer-contract version preserved as history but not matched; unsupported unknown version fails closed |

## Completeness gates

- Input concepts: **42/42** enumerated exactly once, O01–O42.
- Disposition: **41 MAPPED + 1 VOID/REPLACED (O38)**; no unaccounted concept.
- Original O38 is not silently dropped: replacement checks derived archive byte-identical rebuild and prohibition on archived authority through T19/T27/T40.
- New reconstructed register: T01–T42, exactly 42 numbered synthetic oracles; not all 42 must map to exactly one original concept because new tests also address approved protocol gaps.
- Critical crosschecks: O33→T07/T34 (source-only merge); O35→T31 (§4.8 exact L3); O36→T41 (§5.7 lock); O32→T24/T25 (§3.6 protected todo); O41→T37 (historical same-fp conflict); O42→T39 (§4.7 version isolation).
- This map does not establish test execution, independent Sol PASS or architect sign-off. Owner adoption and production-code authorization are separate subsequent gates.

**Requested architect decision:** On the exact pinned PR #4 SHA containing this file and the revised normative ADR, explicitly ACCEPT the reconstructed 42-oracle register as new authoritative contract under retained C3, or return exact CHANGES_REQUIRED IDs. Do not sign for architect or merge PR #3/#4.
