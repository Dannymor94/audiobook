---
id: T15-7-WP2-FIX
title: Correct SU fragment provenance, stress facts, fingerprints and TSV validation
status: doing
owner: codex-gpt-6
agent: claude-code
branch: task/T15
order: 11
depends_on: []  # Corrective work while T15-7-WP2 remains in review
---

# T15-7 WP-2 FIX — Close Independent Findings R1–R7 in One Package

**Executor:** Claude Code Sonnet 4.6  
**Coordinator authorization:** GO for this bounded **single corrective package**, not WP-3.  
**Independent QA:** **ONE targeted Codex Sol review after all seven findings are closed**, against the final pinned SHA; no Sol review between internal milestones unless a protected invariant fails.  
**Repository:** `Dannymor94/audiobook`  
**Branch:** `task/T15`. Verify the actual `origin/task/T15` HEAD and worktree ownership before modifications; never force/reset/stash other agents' work.  
**Rejected WP-2 SHA:** `48ff16bd3f9d170561a65bc1f195f6f39c6e91ca`  
**Original WP-2 base:** `7ca0291bda75f495f72c514ff6e8bf0122a57bd8`  
**Published Sol review task:** `tasks/T15-7-WP2-REVIEW.md`  
**Independent verdict:** CHANGES_REQUIRED, 7 reproduced blocking defects; current independent synthetic contract checks **17 failed / 4 passed**, production suite **1,391 passed / 5 skipped**. Sol scratch scripts in `/tmp/wp2-review...` are *not available in this agent's worktree*. Reproduce findings with new committed synthetic tests, not by asking the owner to transfer scratch files.

## Reference documents — read directly from GitHub

- `tasks/T15-7-FINAL-ADR.md` — authoritative §§3, 5–9, 11–13; especially L0–L5, §6 TSV schema, U4, §9.
- `tasks/T15-7-WP2.md`, `tasks/T15-7-WP2-REVIEW.md`, `tasks/T15-7-EXECUTION-PLAN.md`
- `tasks/T15-7-WP1-ACCEPTANCE.md` and accepted `sutrace.py` / WP-1 baseline
- `CLAUDE.md`, `AGENTS.md`, `tasks/README.md`
- Current `wordprov.py`, `stress_facts.py`, `stress_fp.py`, `unitmap.py`, `sutrace.py`, `synth.py`, `pronounce.py` and associated tests (existing production code read-only).

**Do not reopen accepted 6C11 mapping or reproduce the whole original architecture review.** Sol independently confirmed on the existing disk snapshot:
- 56 target sections, 4,624 source units, 77,998 atoms, 5,127 chunks/SUs.
- 76,036 Cyrillic WordOcc records; L-a/L-b/L-c violations **0**.
- Existing real snapshot: 76,033 aligned, 3 `prep_token_mismatch`; 5,124 fully aligned chunks, 3 mismatched chunks. **Do not suppress or force-align these three.**
- TTS baseline digest `D = 0346b71f7b3f3c2078a144b56a8374a8998bf6b722d25af1fe0ce2a07ec1a5d6`; bytes and mtime unchanged by Sol.
- No live multi-fragment chunks on current snapshot; **synthetic enum branch remains mandatory**.
- No manuscript text or per-word/per-SU hashes may enter reports or Git.

## Working method

Fix R1–R7 in **three internal milestones**, testing each locally. Continue automatically from A to B to C when the respective local gates pass. Do not request intermediate Sol review or separate agent sessions. If a critical ADR conflict, privacy leak, irreproducible baseline, or production hash/input/cache change occurs, STOP and report minimal evidence. If a fix requires an unsupported change to normative SUTrace structure, STOP and escalate the precise conflict rather than silently changing the contract.

### Milestone A — Correct every SU fragment and fail-closed trace status (R1, R2)

**R1 — Multiple SU fragments must not be overwritten.**

- Current `wordprov.process_section_occs` stores `chunk_to_trace[cid] = tr` and loses all but the last fragment. Replace this with a deterministic ordered **(chunk_id, fragment)** structure. Concatenate per-fragment token streams in actual engine invocation order, preserving each word's **fragment index and fragment-local SU token index**. Keep normal singleton SU `fragment=None`.
- No cross-fragment substring searching or realignment, and no change to production splitting or accepted `SUTrace` semantics.
- Create a synthetic three-fragment literal oracle based on the existing production/fake-engine path; expected occurrence tuples: `(aligned,0,0)`, `(aligned,1,0)`, `(aligned,2,0)`. Verify fragment-specific association survives through `apply_facts`, not just provenance.
- Preserve full counts and offsets on a normal single-SU chunk.

**R2 — Explicitly carry non-ok SUTrace statuses.**

- Before attempting positional alignment, check **every** contributing SU status. Preserve `trace_unsupported` as an alignment status; `trace_mismatch` must fail closed (ADR real-corpus STOP), with no silent mapping or status `aligned`.
- Synthetic negative probes: unsupported trace with empty text; matching text but status `trace_unsupported`; matching text but `trace_mismatch`; mixed-status fragments in one chunk. Distinguish mismatch from ordinary `prep_token_mismatch`; no false success.
- Acceptance cannot count a non-ok trace as fully aligned.

**Local gate A:** synthetic 3-fragment oracle and non-ok status probes pass, L-a/L-b/L-c remain exact, and no new source text/trace is committed from the actual book.

### Milestone B — Correct F1 evidence, fingerprints and status precedence (R3, R4, R5, R6)

**R3 — F1 matches are in PRE-respell padded coordinates.**

- Sol reproduced a false `covered_by_override` from comparing `SUTrace.matches` (pre-respell offsets) to `SUTrace.prep_text` (post-respell engine input). Length-changing replacements and lead-in can shift tokens; the current `_classify_f1` uses the wrong coordinate domain.
- Implement **validated positional translation or a genuinely observed pre-respell token-span source**, preserving the existing single-pass `pronounce.build_pattern/respell` semantics and fragment-specific SU association. Verify the transformation against the actual final text and recorded matches, including pad/lead-in offsets and sentinel; **fail closed** if it cannot be proven exact.
- The synthetic probe with three neighboring source tokens, differing replacement lengths and all three whole-token rules must attach each rule to its own source occurrence; no wrong-token F1 or false `covered_by_override`. Include sentence/phrase and partial-span ambiguity cases; ADR U4 ambiguity wins over coverage, match fully in lead-in is ignored.
- Do **not** guess vowel positions from rule keys, replacements or the final speech string.
- Prefer implementation entirely within `wordprov.py` / `stress_facts.py` using existing validated observations. If genuinely impossible without extra observation, a **minimal, additive, read-only** helper in `sutrace.py` and corresponding `tests/test_sutrace.py` is conditionally allowed **only if the exact accepted SUTrace nine-field public contract, final-input bytes, original functions and WP-1 baseline remain unchanged**. Independently compare helper output to the existing synthesis preparation path. Do not broaden to production synth/voicecfg/pronounce or change the cache.

**R4 — Excluded sections must actually be excluded from source payload.**

- `source_fp` currently serializes every supplied section even if in `excluded_sections`. Keep exclusion-policy identity in the hashed canonical representation, but filter excluded section source units out of the `sections` payload.
- Test: edit text in an excluded section → unchanged source_fp; edit included source → changed; change excluded-section policy → changed; input section order must not change the deterministic result. Keep normalized-source ordering and tokenizer version per ADR.

**R5 — Record manifest dependencies, not only static declared fields.**

- `manifest_fp` reads a static tuple; it does not enforce the ADR §5 contract that **actual manifest and SU-analysis key accesses** are recorded and checked against `MANIFEST_FP_FIELDS`.
- Introduce instrumented read-only row mappings or an equivalent exact access recorder (including `row["id"]`, `row.get`, membership checks and related analysis/trace reads), on synthetic and existing snapshot paths.
- A synthetic added access to `unexpected_analytic` through an observed reader (e.g., mocked `row_leadin`) must **raise a controlled failure**, not merely change the hash silently; no whitelist-all workaround.
- Verify the declared six analytic fields n/id/text/pause_after_ms/open_end/leadin and any explicitly justified actual extra field. **Exclude** audio/QC status, duration, seed_override and fields not read for analysis/SU text. Ensure checksum mutation tests cover every relevant field, missing optional values and irrelevant-status stability.
- Guard may run in an explicitly defined validation pipeline without modifying protected production modules. Do not alter existing WP-1 config-path guarding.

**R6 — Respect a valid T1 when F6 has not run.**

- `classify_status` currently treats all `f6_status=not_run` as unresolved. It must return `unresolved/ruaccent_not_run` only when **T1 has no valid expected value**, after higher-priority status rules.
- Synthetic valid `decision` and `source_mark` with non-null vowel and F6 `not_run` must yield `ok` with the correct reason, not unresolved. If both T1 positions disagree, conflict stays unresolved. Do not make owner approvals/F5 active on real corpus or touch any live human journal.

**Local gate B:** all R3–R6 independent-style synthetic probes pass; exact original §9 priority remains; no source, manifest, TTS baseline or hash/cache mutation.

### Milestone C — Strict canonical TSV grammar and lossless round trip (R7)

- `wordprov.to_tsv_row`, `from_tsv_row`, `parse_tsv` and `parse_occ_row` currently accept invalid values.
- Implement shared complete **ADR §6, all 35 fields** validation: exact header/order/column count; required non-null; bool only `0` or `1`; nonnegative canonical decimal ints with no leading zeros/sign; nullable ints `""` or canonical; exact allowed lowercase enums; TAB/LF forbidden inside values; no silently discarded extra columns; reject invalid Unicode/control input when it violates the grammar.
- The approved error type is `unitmap.AnnotationError`, not a generic permissive conversion. Use a consistent safe code on malformed TSV without logging a sensitive value.
- `serialize_tsv(parse_tsv(valid_tsv))` must be **byte-identical**, including valid final LF input. Define and enforce the exact canonical writer/reader end-of-file behavior without weakening the ADR; add byte tests for final LF and malformed header, empty required columns, bool `2`, signed/zero-padded integer, invalid enum, TAB/LF in fields, extra/missing columns.
- Do not invent a new TSV schema, change WordOcc field order or publish `occurrences.tsv` (that is WP-3).

**Local gate C:** all R7 valid and invalid tests pass; full round-trip equality, no private source rows/IDs in tests.

## Allowed tracked changes

Normal scope:
- `src/audiobook/wordprov.py`
- `src/audiobook/stress_facts.py`
- `src/audiobook/stress_fp.py` only if necessary for scoped fingerprint/re-export preservation
- `tests/test_wordprov.py`
- `tests/test_stress_facts.py`
- `tests/fixtures/t15_7/synthetic/*` if genuinely needed
- `tasks/T15-7-WP2-FIX.md` status and safe delivery report

**Conditional R3 scope only:** `src/audiobook/sutrace.py`, `tests/test_sutrace.py`, strictly as specified in milestone B; state why in final report.

Everything else **READ-ONLY**, especially `unitmap.py` (closed 6C11), production `synth.py`, `worker.py`, `engine.py`, `chunker.py`, `voicecfg.py`, `pronounce.py`, config, manifests, manuscript, audio, cache, `out/stress`, publisher, and the Final ADR.

## Final test / privacy / STOP gates

1. Independently derived synthetic literal oracles for R1–R7 — not only tests calling the same new implementation twice.
2. **Real offline snapshot gate:** 56 sections, 76,036 WordOcc, 0 violations of L-a/L-b/L-c, original three `prep_token_mismatch` cases remain explicitly counted/traceable; all 5,127 baseline SUs, identity/order and input hashes unchanged. New source-to-SU remapping must be verified across **every** word on the existing disk snapshot, without forcing all rows `aligned`. Report counts only; no corpus excerpts.
3. Accepted WP-1 `--check` at existing S2 baseline digest `0346b71f7b3f3c2078a144b56a8374a8998bf6b722d25af1fe0ce2a07ec1a5d6`; do not regenerate S2, manifests or synthesis. If unavailable, mark this gate BLOCKED, not PASS based on skipped tests.
4. Verify preserved gold identity semantics and original v4 `stress_fp` API.
5. Focused pytest and full `uv run pytest -q`, exact test arithmetic and result, synthetic determinism under `PYTHONHASHSEED=1,2,3` in bytecode-disabled/offline mode.
6. Check `git diff --check` for changed code, P1/P4 safety (no real corpus text or word/fragment hashes or protected S2–S4 in staged/committed files); inspect all tracked additions. Safe scratch outside the repository only or approved gitignored S2; do not erase preexisting data.
7. No changes to production TTS input, `pronounce.yaml`, config/manifest/cache, accepted 6C11; no sound synthesis/full render, RUAccent, inventory publisher, gold scoring, or WP-3.

**STOP** on any real-corpus link error, missing/corrupt safety prerequisites, F1 coordinate evidence that cannot be verified, unresolved ADR contradiction, protected write, privacy leak, baseline D mismatch or failing tests. Do not adjust the accepted snapshot to make tests pass. If a suspected normative contradiction prevents a bounded fix, report exact file:function:line and an English narrow architect question; do not spontaneously start another redesign.

## Git and handoff

Work from a verified clean/exclusive worktree. Local commits between milestones are allowed for recoverability; no intermediate Sol reviews. Final push (no force) to `task/T15` with this task status `review` and a sanitized final report. The independent reviewer will check the **latest actual implementation SHA including any fixup**, not an earlier report SHA. STOP after report; **WP-3 stays HOLD**.

### Mandatory report (English)

```text
TASK: T15-7-WP2-FIX
STATUS: PASS | BLOCKED | FAIL
INITIAL_REMOTE_SHA:
FINAL_REMOTE_SHA:
MILESTONE_A_R1_MULTIFRAGMENT:
MILESTONE_A_R2_TRACE_FAILURES:
MILESTONE_B_R3_F1_PRE_RESPELL:
MILESTONE_B_R4_EXCLUDED_SOURCE:
MILESTONE_B_R5_MANIFEST_ACCESS_GUARD:
MILESTONE_B_R6_T1_NOT_RUN:
MILESTONE_C_R7_STRICT_TSV:
CONDITIONAL_SUTRACE_MODIFICATION: YES | NO (reason)
REAL_CORPUS_56_SECTIONS_AND_76036_OCCURRENCES:
SOURCE_LINK_LA_LB_LC_ERRORS:
ALIGNMENT_STATUS_COUNTS:
SUTRACE_SU_COUNTS_AND_HASH_PARITY:
BASELINE_D_CHECK:
P1_P4_PRIVACY:
TESTS_ADDED_OR_MODIFIED:
TEST_ARITHMETIC:
FOCUSED_TESTS:
FULL_PYTEST:
PYTHONHASHSEED_1_2_3:
GIT_DIFF_CHECK:
TRACKED_CHANGED_FILES:
COMMITS:
PUSH_CONFIRMED:
BLOCKERS:
SOL_REVIEW_REQUIRED: ONE TARGETED PACKAGE-EXIT REVIEW
WP3_STARTED: NO
```

**STOP after WP-2-FIX. WP-3 remains HOLD until independent Sol acceptance and coordinator GO.**
