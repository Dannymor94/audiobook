# T15-7 WP-2 — One Independent Acceptance Review

**Executor:** Codex Sol (read-only independent QA)  
**Work package:** WP-2 = T15-7.3 + T15-7.4, both reviewed as ONE deliverable  
**Repository:** `Dannymor94/audiobook`  
**Exact code SHA to review:** `48ff16bd3f9d170561a65bc1f195f6f39c6e91ca`  
**Base SHA:** `7ca0291bda75f495f72c514ff6e8bf0122a57bd8`  
**Implementation:** `cd69a62a3a7458bfa375d6bf09a45f59e1f2bf9b`  
**Agent delivery report:** `784ba3750f62d7896e277a8b4a2ed4d7a6799a72`  
**Post-report test fixup:** `48ff16bd3f9d170561a65bc1f195f6f39c6e91ca` (MUST be included)  
**Authorization:** REPO READ-ONLY. No code changes, claims, commits, pushes, synthesis, chunking, manifests, inventory publication, audio/cache modification or network access.  
**WP-3:** HOLD until independent acceptance and coordinator GO.

## Purpose

Verify whether the **actual on-disk API**, as of the final fixup, implements the whole normative WordOcc provenance/fingerprint and stress-fact contract. Do not accept the developer's self-reported 1,391 green tests as proof, especially because the final fixup says tests originally targeted stale/pyc API assumptions and the delivered report predates the final code SHA.

Review once at the combined WP-2 risk boundary. **No separate Sol reviews for 7.3 and 7.4.** Avoid reopening accepted 6C11/WP-1 without a reproducible new regression.

## Read from GitHub

- `tasks/T15-7-WP2.md` (original work-package contract and agent report)
- `tasks/T15-7-FINAL-ADR.md` §§3, 5–9, 11–13 (authoritative)
- `tasks/T15-7-WP1-ACCEPTANCE.md` (accepted input-trace baseline)
- `tasks/T15-7-EXECUTION-PLAN.md`; `CLAUDE.md`; `AGENTS.md`
- `src/audiobook/wordprov.py`, `src/audiobook/stress_facts.py`, `src/audiobook/stress_fp.py`
- `tests/test_wordprov.py`, `tests/test_stress_facts.py`
- Exact `base..target` commit chain including the final fixup; do not review only `cd69a62`.

## Acceptance gates (risk-ranked)

### G1 — Source provenance and actual integration

- Independently compare `process_section_occs` output to `unitmap.map_section`, source `load_units`, frozen manifest rows and the accepted `sutrace.trace_section` output on the existing 56-section / 5,127-SU snapshot. Do not request or print manuscript contents.
- Check L-a, L-b, L-c exact offsets and substrings; normal/unit/atom/analysis/SU coordinates; `source_key`; `unit_id` serialized decimal string vs production int; chunk_n, chunk_id, atom span and ordered token positions; one-to-one word occurrence identity, count and order.
- Confirm section ordering and source punctuation in L5; `build_analysis_text` must not invent terminal edits, punctuation, pad, respell or sentinel; validate coordinate links under length-changing synthetic transformations.
- Examine a specific **suspected multi-fragment hazard**: `process_section_occs` builds `chunk_to_trace[cid] = tr` for each trace. If a chunk contains multiple SUs, later fragments overwrite earlier ones. Construct an exact synthetic 2–3-fragment oracle with distinct fragment identities, verify positional alignment against ALL fragments in their production order, and reproduce or refute loss of early fragments. Check trace_unsupported / trace_mismatch propagation and fail-closed behavior.
- The Sonnet report explicitly says `ALL_56_SECTIONS` was skipped and `BASELINE_DIGEST_D_MATCH` was not separately measured. Re-run safe read-only corpus integration if local source/manifests are available. An absent model is not, by itself, a reason to skip pure offline provenance. If the required protected local data is unavailable, report **BLOCKED for the corpus gate**, do not claim real-corpus PASS from unit tests.

### G2 — Fingerprint domains and gold identity

- Verify `source_fp` uses canonical JSON/SHA-256 of normalized ordered source units, with exactly the specified `unit_id, kind, text_sha256`, tokenizer version and **excluded-sections policy**, and is independent of manifests, model, audio, seed and rules.
- **Suspected excluded-sections gap:** the function currently serializes `sorted(sections_units.items())` even when `excluded_sections` is provided. Probe whether mutating source text inside a truly excluded section incorrectly changes `source_fp`; distinguish exclusion-list identity changes from actual excluded-data exclusion.
- Verify `manifest_fp` actually covers all required analytic read fields (n/id/text/pause_after_ms/open_end/leadin), handles missing optional fields, and ignores QC/audio status/seed_override. Check all six per-field mutation cases plus irrelevant changes and section order. Verify manifest key-access dependency contract; a static tuple without detecting new reads may not satisfy the ADR requirement.
- Independently verify five-part `gold_identity` (source_key, form_source, unit_text_sha256, unit_kind, context_sha256), neighbor validity, unrelated edit stability, and source unit insertion effects.
- Confirm any re-export from `stress_fp.py` preserves the previous v4 API and causes no circular dependency or version bump.

### G3 — Facts F1–F6 and precedence

- Verify F1 span matching uses the **correct coordinate space**: `SUTrace.matches` are offsets in **pre-respell padded text**, while `SUTrace.prep_text` is the **post-respell final TTS text**; replacements can change lengths. Validate with synthetic length-changing respell, lead-in padding, a full-token rule, phrase span and partial-token ambiguity. A valid override must cover the intended source token, not a shifted token. No vowel position may be inferred from respell.
- Check exact ADR U4 rule: ambiguity before coverage; phrase spans, full/partial overlaps; matches entirely in lead-in never attach to a source WordOcc.
- F2: `unknown` for F1 without an independent approval journal, `none` otherwise, f2_vowel null; never infer approved.
- F3 verified forms read without creating missing files; F5/U+0301 guard; F6 remains `not_run` with null vowel and does not invoke RUAccent.
- Validate `resolve_expected` T1/T2/T3 including conflict, and the FULL §9 status/reason precedence, all informational reasons with ordering and de-duplication. Do not count speculative scenarios as defects; reproduce actual counterexamples.
- Verify `apply_facts` preserves fields 1–21 while populating fields 22–35 and uses the correct fragment-specific trace for each occurrence.

### G4 — TSV, reproducibility, privacy, and non-regression

- Independently validate the exact 35-column schema, header, types, null/bool/int grammar, tab/newline rejection, ordering, and **byte-identical serialize(parse(tsv))** for synthetic valid records; ensure malformed values do not silently coerce to valid values. Check `parse_tsv` validates the exact header and does not silently accept invalid/extra columns or lines.
- Verify 1,316 prior passed + 75 new = 1,391 passed and 5 skipped at the **final fixup SHA**; run focused tests and full pytest with bytecode disabled, no cacheprovider and isolated scratch. Check `PYTHONHASHSEED=1,2,3` determinism on the actual full new test modules, not only two fingerprint tests.
- Verify accepted WP-1 local baseline digest D = `0346b71f7b3f3c2078a144b56a8374a8998bf6b722d25af1fe0ce2a07ec1a5d6` via safe `--check` if local S2 exists; never regenerate/overwrite it to make the check green. A missing S2 file is lack of evidence, not a changed digest.
- Independently verify P1/P4 and allowed diff scope: exactly wordprov.py, stress_facts.py, stress_fp.py, test_wordprov.py, test_stress_facts.py and task metadata. No actual manuscript, token/fragment hashes, files under S2–S4, audio, models or private data staged/committed. Production synth/voicecfg/pronounce/unitmap/manifest/cache unchanged.
- Verify no use of stale `.pyc` artifacts masking actual API. Use clean interpreter/bytecode-disabled tests. Historical Markdown hard-break whitespace is nonblocking, but new code diffs must be clean.

## Verdict rule

**PASS:** all essential structural, fingerprint, F1 and TSV contracts demonstrated, including real-corpus link gate when accessible; no blocking privacy or production regressions.

**CHANGES_REQUIRED:** one or more reproducibly demonstrated contract violations; cite exact code location, synthetic reproduction, shortest bounded correction. Propose **ONE combined Sonnet fix**, not separate architectural or review tasks for each issue.

**BLOCKED:** necessary local protected inputs or safe execution are missing; list exact missing evidence. Do not treat missing model/audio as automatically blocking pure read-only checks.

## Required report (English, concise, no manuscript text)

```text
TASK: T15-7-WP2-INDEPENDENT-REVIEW
STATUS: PASS | CHANGES_REQUIRED | BLOCKED
BASE_SHA:
REVIEWED_FINAL_SHA:
COMMIT_CHAIN_AND_SCOPE:
G1_SOURCE_LINKS_AND_COUNTS:
G1_56_SECTION_REAL_SNAPSHOT:
G1_MULTIFRAGMENT_SU:
G1_ANALYSIS_OFFSETS_AND_PUNCTUATION:
G2_SOURCE_FP_EXCLUSION:
G2_MANIFEST_FP_MUTATIONS_AND_KEY_GUARD:
G2_GOLD_IDENTITY:
G3_F1_PRE_VS_POST_RESPELL_COORDINATES:
G3_F2_F3_F5_F6:
G3_SECTION9_PRECEDENCE:
G4_TSV_STRICT_ROUNDTRIP:
G4_BASELINE_D_AND_NONREGRESSION:
G4_TESTS:
G4_PRIVACY:
BLOCKING_FINDINGS: [ID | file:function:line | exact reproduction | minimal fix]
NONBLOCKING_FINDINGS:
FINAL_VERDICT:
WP3_RECOMMENDATION:
```

**STOP after independent reporting. No code changes, commits or starting WP-3.**
