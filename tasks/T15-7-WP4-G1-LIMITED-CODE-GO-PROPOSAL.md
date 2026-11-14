---
id: T15-7-WP4-G1-LIMITED-CODE-GO-PROPOSAL
status: PROPOSED_FOR_OWNER_NOT_AUTHORIZED
owner: owner
coordinator: chatgpt
candidate_executor: claude-code-sonnet
normative_sha: a012c84240eb246b8072a735989f598b6ca566e2
approved_plan_sha: 0afd382a276832816bb7e84a020a5b58ae8d5f58
base_code_sha: 201f0cd4e946f7f5405e47fe27153df9aeac17ef
implementation_authorized: false
real_corpus_readonly_authorized: false
s4_data_writes_authorized: false
merge_authorized: false
---

# T15-7 WP4 — proposed LIMITED CODE GO, NOT an authorization

**DO NOT DISPATCH SONNET based on this draft.** The owner approved the normative ADR and the corrected WP4 implementation plan with C1–C6, but has expressly withheld permission to modify production. This document is the requested proposal for a NEW, separate owner decision. It is not itself CODE GO.

## 1. Authority and exact commit pins

- Normative ADR, G1/C3 and reconstructed T01–T42: PR #4 SHA a012c84240eb246b8072a735989f598b6ca566e2. Architect ACCEPT and independent Sol architecture PASS, as reported by owner.
- Corrected approved IMPLEMENTATION PLAN C1–C6: tasks/T15-7-WP4-G1-IMPLEMENTATION-PLAN.md at commit 0afd382a276832816bb7e84a020a5b58ae8d5f58.
- Code baseline: 201f0cd4e946f7f5405e47fe27153df9aeac17ef. Changes between base and approved plan commit were confined to tasks/ Markdown, no production or tests.
- Only AFTER separate owner CODE GO: create exclusive implementation worktree and branch task/T15-7-wp4-g1-implementation from this **exact** BASE_CODE_SHA, not floating task/T15 or main. Normative ADR remains pinned separately as read-only reference; PR #3/#4 must remain unmerged and cannot be cherry-picked wholesale.

## 2. Scope of the permission to be proposed to owner

One bounded Sonnet 4.6 CODE GO covers sequential I1 -> I2 -> I3, synthetic S1 tests, required local owner-corpus MEMORY-ONLY read-only checkpoint AFTER I1, three separate phase commits, coordinator PASS between phases, and one independent Sol CODE review at final implementation SHA. This does NOT authorize real S3/S4 writes, H04 labels, full render or PR merge.

### 2.1 Exact file write allowlist (C4)

Production:
- src/audiobook/stress_eval.py
- NEW src/audiobook/stress_yo_observer.py (strictly read-only observer)
- run.sh ONLY IF the existing forwarding of stress-eval commands is proven insufficient; prefer no edit.

Synthetic test paths:
- tests/test_stress_eval_sample.py
- tests/test_stress_eval_merge.py
- tests/test_stress_eval_score.py
- tests/test_stress_metrics_contract.py
- NEW tests/test_stress_yo_observer.py
- tests/fixtures/t15_7/synthetic/** (invented S1 fixtures only)
- tests/helpers/ only for clearly necessary synthetic scaffolding, path identified in phase report.

Documentation: the implementation plan, a new tasks/T15-7-WP4-G1-IMPLEMENTATION-REPORT.md, directly related WP4 task status/review Markdown.

All OTHER production files are change-DENIED, including voicecfg.py, synth.py, sutrace.py, pronounce.py, chunker.py, unitmap.py, wordprov.py, stress_fp.py, stress_inventory.py, stress_metrics.py, model, synthesis configuration, manifests, corpus publisher, source, cache and audio. Read-only imports and calls to existing production functions for a FULL L3 proof are permitted; modifications are not. Any extra file/dependency needs explicit new owner approval, not broad interpretation of "necessary".

### 2.2 I1 — 13 T oracles, common safety mechanisms, two-part local read-only checkpoint (C1/C2)

Assigned: T16, T18, T21, T22, T23, T24, T25, T26, T30, T31, T32, T33, T36. First implement on fabricated temporary fixtures: exact source-chunk-fragment ordinal and pre-respell observer, enabled/disabled yo.restore, all-SU FULL L3 exact composed_final UTF-8 and composed_phrase type+value equality with production prepare_synth_text (including NONE). Implement sample/2 full population/selected assignment digests, six strata, versioned paths, protected todo logic. Implement OS-backed lock, P1/P4 path guards, atomic one-file temporary/fsync/replace and OWNER_TODO_PROTECTED in I1; I2/I3 reuse.

Only after I1 commit, its 13 synthetic oracles and FULL pytest PASS, perform the following offline OWNER-LOCAL check, if this future CODE GO is separately approved:
- NO cloud transfer, synthesis, audio, S3/S4 writes, sample/merge/merge-yo/score commands, sample/2 todo creation, corpus publication, pycache/temp/log changes in protected paths. Read and compute in memory; protect original files.
- PRECHECK original pinned G0 source_fp, manifest_fp, analysis_fp locally. Missing or mismatch => SNAPSHOT_DRIFT/STOP BEFORE count comparison.
- I1-A: replay exact original 320 keys from existing sample/1 todo READ ONLY. For the SAME G0 snapshot: eligible source mapping 51,629/51,629; original selected mapping 320/320; unsupported 0; selected RESTORED=40, YO_EVALUABLE=40, excluded F1 union=0.
- I1-B: independently compute sample/2 in MEMORY ONLY from current validated eligible population. Same G0 snapshot: eligible source mapping 51,629/51,629; population RESTORED=223; unsupported=0; FULL L3 mismatches=0 for ALL SUs including NONE. sample/2 selected keys=320 ONLY IF all stratum populations suffice. sample/2 selected YO counts are measured only, NOT compared with the old sample/1 40/40/0.
- Verify deterministic sample/2 fingerprint for PYTHONHASHSEED 1/2/3 and iteration order.
- Local BEFORE/AFTER protected byte parity: 0 modified files, old 320-row todo unchanged. Report only aggregate counts and safe statuses; NEVER print individual keys, hashes, labels, manuscript fragments or private paths.

**I1 exit requires coordinator explicit PASS before I2 begins.** Any fingerprint/snapshot drift, unsupported observation, L3 byte or phrase mismatch, insufficient populations where 320 was expected, protected file change or attempted S3/S4 write => STOP; no silent baseline repin or workaround.

### 2.3 I2 — 22 T oracles, original three Sol F1 regressions

Assigned: T01–T10, T14, T15, T17, T19, T20, T27, T28, T34, T35, T37, T39, T40; exactly 22, PLUS the original three Sol F1 regressions. On SYNTHETIC tmp fixtures only:
- source-only human source-vowel truth, LEGACY_YO_UNRESOLVED, SOURCE_STALE, current ACTIVE and conflict ERROR;
- preserve all historical stress versions in authoritative stress_gold.tsv; archive derived-only ten-column SOURCE_STALE export; crash-safe M1–M5, byte-identical idempotent retry;
- new human numeric source answer may coexist with retained legacy unresolved row; A->B->A reactivates from gold; never choose newer date;
- separate candidate-bound, 16-column YO evidence ledger and merge-yo; exact restoration_fp and human y/n, independent one-file atomicity;
- stress merge MUST work for valid source-current keys OUTSIDE selected sample, with no sample/2, analysis_fp, inventory generation, restoration candidate or YO ledger dependency.

**I2 exit:** stage's 22 T oracles + 3 original F1 regressions + full pytest PASS, coordinator PASS. Do not touch real owner S4.

### 2.4 I3 — 7 T oracles and one independent Sol CODE review

Assigned: T11, T12, T13, T29, T38, T41, T42; exactly 7. Score must distinguish COMPLETE rc0 (including nonpositional source annotations with null accuracy and G_hint INCONCLUSIVE), INCOMPLETE rc2 (missing selected stress/YO truth), and ERROR (malformed/conflicting/stale). Pin and recheck both independent authoritative raw ledger byte digests, generation, observer and sample/2 before publish and on consuming persisted COMPLETE; fail-closed OS lock EVAL_LOCK_UNAVAILABLE, old score bytes unchanged on ERROR. Use exact Wilson and gate rules; never automatic synthesis changes.

**Final exit:**
- 42/42 approved synthetic T test oracles with exact test node IDs and PASS; three original unsafe Sol F1 regressions PASS after correction;
- earlier G0 52 and S4 synthetic 17 cases rerun, full pytest with 0 unexplained FAIL; precise PASS/FAIL/SKIP/XFAIL counts;
- all FIVE previously S2-dependent skipped tests MUST ACTUALLY RUN and PASS on an available valid local offline S2 baseline. If missing/invalid: BLOCKED_S2_BASELINE / no WP4 CODE PASS, even with other green tests. Other SKIPs require exact node ID and reason;
- reproducible with PYTHONHASHSEED 1/2/3, P1/P4, 0 protected file modifications, no change to synthesis/model/cache/6C11/manifests/audio;
- exactly ONE independent final Sol CODE review of exact final implementation SHA, diff and tests. Architectural Sol PASS cannot count as code review.

## 3. Three separate commits and STOP protocol (C3/C5/C6)

One exclusive implementation branch, three sequential phase commits I1, I2, I3. Each submission: parent/head SHA, complete changed paths, focused and full pytest collected/PASS/FAIL/SKIP/XFAIL/node IDs, local aggregate parity and reasons for STOP. Coordinator verifies I1 before authorizing I2 and I2 before I3. Do not bypass tests or widen file scope.

STOP triggers: unsupported or ambiguous source mapping; any all-SU L3 mismatch; missing/different pinned G0 source/manifest/analysis identity; changes in protected files; missing S2 baseline; failed 42-oracle subsets, lock or path guards; attempted real S3/S4 write; additional production file requirement; cloud transmission of text/voice; archive-first migration; synthesis/cache/manifest/model/audio changes; any PR merge, H04, WP5, T16/T17 or full render.

## 4. Proposed owner authorization text — NOT YET GRANTED

A future owner message may explicitly state:

OWNER DECISION — T15-7 WP4 LIMITED CODE GO

Decision: APPROVE LIMITED CODE GO under approved plan commit SHA 0afd382a276832816bb7e84a020a5b58ae8d5f58 and normative ADR SHA a012c84240eb246b8072a735989f598b6ca566e2.

Authorize Sonnet 4.6 for three sequential stages I1->I2->I3 on exclusive branch task/T15-7-wp4-g1-implementation based on fixed CODE SHA 201f0cd4e946f7f5405e47fe27153df9aeac17ef, with exact §2.1 write allowlist, one phase commit, full tests and coordinator PASS before next phase.

Explicitly allow ONLY offline owner-local memory-only read-only verification after I1 as in approved plan §5.2, with no real S3/S4 data writes or sample/merge/merge-yo/score commands on owner files. Require the two-part I1-A original sample/1 and I1-B in-memory sample/2 checks, complete L3 and protected parity.

Keep all mandatory 42 oracles, three Sol F1 regressions, five S2 baseline cases genuinely executed and PASS, deterministic seeds, P1/P4, and one independent final Sol CODE review. Require STOP on any declared blocker.

Not authorized: S4, existing 320-row todo, H04, migration, PR #3/#4 merge, synthesis/model/cache/manifest/audio, WP5, T16/T17, full render. Such work needs a separate owner decision.

STATUS: CODE GO GRANTED / S4 DATA GO NOT GRANTED.

Until the owner separately and expressly approves this GO, STATUS remains CODE_GO_PENDING and Sonnet must NOT start. STOP.
