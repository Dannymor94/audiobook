---
id: T15-7-WP4-G1-IMPLEMENTATION-PLAN
status: PLAN_READY_CODE_GO_NOT_GRANTED
owner: owner
coordinator: chatgpt
candidate_executor: claude-code-sonnet
independent_qa: codex-sol
normative_sha: a012c84240eb246b8072a735989f598b6ca566e2
implementation_authorized: false
s4_writes_authorized: false
merge_authorized: false
---

# T15-7 WP4 G1 — bounded implementation and acceptance plan

2026-11-14. **PLAN ONLY — NO CODE GO.** The owner explicitly approved the normative WP4 G1 ADR and new reconstructed T01–T42 register at PR #4 pinned SHA a012c84240eb246b8072a735989f598b6ca566e2, citing architect ACCEPT and independent Sol architecture PASS. This approval is of the architectural contract, not code, S4, PR merge, human labeling or rendering.

**Immutable authority for future work:** tasks/T15-7-WP4-G1-NORMATIVE-ADR.md and tasks/T15-7-WP4-G1-ORACLE-COVERAGE-MAP.md at exactly the pinned SHA above. G1 overrides older rev.2 only in its own subject matter; unaffected T15-7 synthesis, C2/6C11, source/manifest/analysis fingerprints, S2 golden baseline and P1–P6 remain binding. The earlier tasks/T15-7-FINAL-ADR.md rev.2 is not yet physically replaced: PR #4 remains DRAFT/unmerged. The O-map covers 42 concepts: 40 mapped, O17 replaced with sample/2, O38 void/replaced with derived-archive oracles.

## 1. Permanent non-negotiable invariants

- SOURCE TRUTH: Five-part human source identity (source_key, form_source, unit_text_sha256, unit_kind, context_sha256); source-only 0-based vowel indices; no post-respell or current form_synth interpretation of stored gold. Equal canonical source-vowel sets are one logical answer.
- C3: text/stress_gold.tsv is the SOLE authoritative stress VERSION LEDGER and retains every historical row. text/stress_gold.archive.tsv is only deterministic, non-authoritative SOURCE_STALE export. Never archive-first, delete historical rows, migrate S4 or select labels by latest date.
- HISTORICAL/CONFLICT: LEGACY_YO_UNRESOLVED preserved and excluded from ACTIVE; explicit human source-index relabel can coexist in same source identity. SOURCE_STALE excluded from current score but retained; A→B→A reactivates source-current versions from gold. Conflicting completed current human truths: ERROR / OWNER_ADJUDICATION_REQUIRED, not self-correction.
- STRESS MERGE ISOLATION (architect C1): a new stress merge depends ONLY on the current five-part source identity, authoritative stress gold and canonical source-only human annotation. It MUST NOT require sample/2, selected membership, analysis_fp, inventory generation, restoration candidate or YO ledger. New source-current keys outside current sample remain eligible for merge under this rule. Sampling, todo generation and scoring have their own sample/generation checks.
- OBSERVER (architect C2): exact source→chunk→raw-fragment ordinal witness. Direct yo.restore ONLY if pinned text_prep.yo_restore is enabled; disabled means compare unchanged original word to prepared pre-respell token and verify NONE. For EVERY SU including NONE, full L3 composed_final must byte-equal prepare_synth_text()[0] and composed_phrase must equal prepare_synth_text()[1] by type AND value (None differs from empty string). Failure => YO_OBSERVATION_UNSUPPORTED/ERROR; no fuzzy fallback; 6C11/synth remain unchanged.
- SAMPLE/2 (architect C3): hash FULL eligible key→stratum assignment and selected-by-stratum membership, six population N_s and selected n_s, observer version, norm/YO map/prep config content digests and source/analysis fingerprints; deterministic across input order/hash seed. Six strata omograph 100, top300 60, name 40, override_covered 40, yo_changed 40, tail 40 in existing first-match precedence. Pre-respell RESTORED, not post-respell form_synth, defines yo_changed. Exact sample and todo paths versioned by sample/2 fp16, with full 64-hex fingerprint validated on read.
- TODO: protect existing 320-row local text/stress_gold.todo.tsv and sample/1 BYTES. New versioned sample/todo destination absent => guarded creation ONLY AFTER owner data GO; existing equal bytes => no-op; different bytes => OWNER_TODO_PROTECTED and no overwrite, adding TODO_HAS_UNMERGED_LABELS when applicable. No automatic regeneration.
- YO EVIDENCE: separate local, ignored 16-field authoritative text/stress_gold.yo_evidence.tsv, independent human y/n judgment of exact, freshly verified pre-respell restoration_fp; all е→ё source-vowel indices and history preserved. Prior stress-gold yo_correct is only historical provenance. F1 exclusion predicate YO_EVALUABLE=RESTORED and f1_rule=null and f1_flag=none, count overlap without duplication. Exact A→B→A evidence may be reused only after current re-observation.
- FRESHNESS: two independently atomic authoritative ledgers (stress, YO), NEVER a single two-file transaction. All cooperating operations use OS-backed lock out/stress/eval/.wp4.lock and fail EVAL_LOCK_UNAVAILABLE without writes. Both raw byte digests plus generation, sample, observer must be fenced before score publication AND on reading persisted COMPLETE. On failure, previous S3 score bytes unchanged.
- SCORING: COMPLETE rc0 possible with completed ambiguous/unknown_name labels while stress accuracy denominator=0, accuracy=null, G_hint=INCONCLUSIVE. Missing required source human or current YO verdict INCOMPLETE rc2 and no partial passing metrics; invalid/conflicting/unsupported inputs ERROR. Wilson and gate thresholds as exact approved §7. No audio quality approval implied.
- PRIVACY: only invented synthetic fixtures tracked; P1/P4 for S2/S3/S4 destinations and transaction temps, no text/voice/per-row source/candidate hashes/human labels in Git, logs, public JSON or agent reports. No synth, voicecfg, pronounce, 6C11, manifests, config, model, cache or audio changes.

## 2. Three sequential implementation phases — proposed only, NO CODE GO

Implementation branch, once expressly authorized by owner: task/T15-7-wp4-g1-implementation, based on exact CODE SHA 201f0cd4e946f7f5405e47fe27153df9aeac17ef (approved PR #4 code baseline). The present task/T15 has advanced from that SHA only in tasks/ documentation as independently checked at c6d26c79399196789006108fdd91cdb7681ba495. PR #3 and PR #4 remain draft and unmerged. Pin the branch to the exact commit; do not start from a moving ref.

| Phase | Scope and prerequisite infrastructure | Assigned normative oracles (disjoint) | Mandatory stage exit |
|---|---|---|---|
| I1 — observer, L3, sample/2 | Exact source→fragment→pre-respell observer, L3 parity for ALL SU, YO/F1 counters, sample/2, versioned todo policies. **Build common OS lock, P1/P4 path guards, guarded atomic rename/fsync and protected-todo handling in I1**, tested only on invented S1 tmp_path | **T16, T18, T21, T22, T23, T24, T25, T26, T30, T31, T32, T33, T36** — 13 | All 13 + full pytest, then coordinator PASS of the two-part memory-only owner-local I1 census (§5.2) before I2 |
| I2 — source-only C3 gold and YO evidence | Legacy/source-stale/ACTIVE, version-history retention, independent source-only merge and separate current-restoration_fp merge-yo; reuse I1 lock/atomic/guards | **T01–T10, T14, T15, T17, T19, T20, T27, T28, T34, T35, T37, T39, T40** — 22, plus 3 original Sol F1 regressions | All 22 + F1 regressions + full pytest, coordinator stage PASS before I3 |
| I3 — scorer and dual freshness | COMPLETE/INCOMPLETE/ERROR, Wilson/YO gates, two-ledger freshness, saved score fence, error-no-overwrite; reuse I1 helpers | **T11, T12, T13, T29, T38, T41, T42** — 7 | All 7, final 42/42 trace, mandatory S2, full pytest, seeds 1/2/3, P1/P4 and one final independent Sol CODE review |

Exactly 13 + 22 + 7 = 42, without duplicates or omitted T01–T42. Three ordered, separate implementation commits I1/I2/I3; never start the next stage until coordinator verifies the previous stage's focused oracles and full regression suite. No extra independent Sol reviews per stage unless STOP/escalation conditions arise. Each stage report contains exact base/head SHA, changed paths, pytest node IDs and PASS/FAIL/SKIP/XFAIL, and protected-file parity.

The approved normative ADR is pinned independently at a012c84240eb246b8072a735989f598b6ca566e2. This proposal neither merges PR #4 nor imports PR #3.

## 3. Combined future acceptance gates, each mandatory

**A1 — T01–T42 traceability.** Every adopted T oracle has an invented deterministic fixture, exact expected output/status/count where meaningful and pytest node ID; all 42 test obligations accounted for, including O17 replacement and O38 derived archive replacement. No claim that a test already passes just because it is listed. Retained C3 T06/T27/T28 must preserve old passing safety, while three original Sol unsafe F1 regressions must fail under the old defect and pass after correction.

**A2 — Gold C3 / merge.** T06 current numeric or positional/nonpositional conflict => OWNER_ADJUDICATION_REQUIRED/ERROR, never newest date; T10 legacy numeric replacement active while legacy stays in stress_gold; T27 stale B remains in stress ledger, M4 exports identical derived stale copy only; T28 A→B→A recomputes ACTIVE from gold. New stress merge works on an unsampled but source-current valid key with changed unrelated analysis/restoration and no sample/2 record (C1). No S4 migration.

**A3 — Observer/sampling.** T30/T32 feature disabled + map entry that WOULD restore must yield verified NONE, never compare unconditionally to direct yo.restore. T31 full every-SU composed_final UTF-8 and composed_phrase exact parity with production prepare_synth_text, including None-versus-empty; L3 mismatch halts before any write. T21–T25 full eligible/selected sample digests: change of an UNSAMPLED eligible stratum changes fp; selected membership swap changes fp; iteration order/hash seeds 1,2,3 identical. Exact versioned paths, no original 320-row todo overwrite.

**A4 — YO evidence.** T16/T18/T29 predicate and exclusion counters; T33–T39 candidate-level whole-word y/n, sorted source vowel indices, same fp opposite verdict ERROR even if historical, observer version isolation, fresh map/config bytes, exact restoration A→B→A. Missing current matching YO verdict yields INCOMPLETE rc2; no backfill from old ten-field yo_correct.

**A5 — Atomicity, lock, dual freshness.** T40 crash before/after authoritative gold rename and between gold/archive refresh yields complete old/new stress history and repairable non-authoritative archive. T41 lock unavailable or mutation of either ledger, sample, generation or observer before score publish/reuse => ERROR/STALE, existing score bytes UNCHANGED; both authoritative byte digests pinned. No archive reads as authority or cross-file atomicity claim.

**A6 — Metrics/privateness.** T42 all selected human labels valid ambiguous/unknown_name with required YO evidence => COMPLETE rc0, accuracy null, G_hint INCONCLUSIVE; zero YO_EVALUABLE permits absent YO ledger and YO_NO_EVIDENCE; zero denominators never pass. Independently recompute Wilson lower 40/40=0.9124, 92/100=0.8500, 91/100=0.8377, 73/73=0.9500 (threshold comparisons use unrounded floats). Validate P1/P4 no tracked S2–S4 or manuscript, no synth/cache/6C11 impact.

**A7 — Test and private baseline gate.** At the final implementation SHA (after a later CODE GO): run focused new 42-oracle synthetic suite, earlier G0 52 tests and S4 synthetic 17 tests, full pytest with 0 uninvestigated FAIL; focused PYTHONHASHSEED 1/2/3. Report exact PASS/FAIL/SKIP and node IDs, enumerate ALL SKIPs with exact node IDs/reasons; the five previously S2-baseline-dependent cases MUST execute and PASS against valid local S2, never remain SKIP. Missing S2 => BLOCKED_S2_BASELINE. Offline owner-local read-only checks may compare the prior S4 snapshot (gold=0/archive=0/todo=320 blank/RESTORED=40/excluded=0/evaluable=40, eligible=51,629) and protected file hashes; a changed snapshot is a STOP/investigate, not permission to regenerate. No private S4 write without separately approved data GO.

**A8 — Independent review and release control.** Sonnet must report base/head SHA, narrow diff, test nodes/counts, P1/P4, protected-file parity counts, source-only/l3/dual-fence cases, explicit no-S4-write attestations. One independent Sol WP4 CODE review at final pinned SHA returns PASS, CHANGES_REQUIRED or BLOCKED with independent evidence. Coordinator may mark WP4 PASS only after Sol PASS and owner confirmation of next stage. Sol architecture PASS does not certify future implementation.

## 4. Separation of permissions

- **ALLOWED NOW:** planning/documentation and static, non-mutating checks only.
- **NOT YET ALLOWED:** calling Sonnet to edit production; modifying tests as part of production rollout; touching owner data; creating YO evidence files; sample/2 or todo generation; running H04, merging PR #3/#4 or a new implementation PR.
- **FUTURE CODE GO:** owner must explicitly authorize synthetic-only bounded WP4-I1/I2/I3 implementation with a named worktree/branch and permitted file set. Code GO does not authorize owner S4/data changes.
- **FUTURE S4 GO:** separately authorize each owner-local sample/todo/evidence write workflow, only after reviewed code and safeguards. No automatic legacy S4 migration.
- **OTHER HOLD:** WP5, T16/T17 and full render remain prohibited even if later WP4 code receives a passing test run.

**OWNER_APPROVAL_OF_PLAN: PENDING.** The architectural ADR approval and independent Sol PASS do not constitute this separate plan's approval or a CODE GO. A proposed code-go must identify the future implementation branch, allowed paths, synthetic-only scope and exit tests; S4 writes require a still later separate owner decision.

**Final plan status:** NORMATIVE_ADR_APPROVED_AT_PINNED_SHA / IMPLEMENTATION_PLAN_READY / CODE_GO_NOT_GRANTED / WP4_BLOCKED / NO_S4_MIGRATION.

## Independent architecture QA exit — PASS (2026-11-14)

**Approved ADR pin:** PR #4 `a012c84240eb246b8072a735989f598b6ca566e2`. Owner explicitly APPROVED the G1 normative contract and reconstructed T01–T42. An independent Sol **DOCUMENT architecture PASS** has now been reported at the **same pinned SHA** and the architect's external `ACCEPT_RECONSTRUCTED_T01_T42_AT_PINNED_SHA` closes previous provenance HOLD. Reviewer specifically checked R1–R8, retained C3 version-ledger, source-stale / return A→B→A, todos protected even if empty, pre-respell/L3 every-SU proof, persisted-score safety and 42/42 O coverage (40 mapped, O17 replaced, O38 void/replaced). The pinned PR #4 docs still contain obsolete review-request statuses; do not rewrite the approved pin to make metadata look current.

**Limits of PASS:** no pytest was run in this independent document review; private S4 and future T01–T42 code behavior were NOT independently retested. This closes **architecture review only**, not implementation acceptance. The **plan approval remains separate and PENDING**, and **CODE GO remains NOT GRANTED**. The future I1 real-corpus read-only checkpoint, exact allowlist, three phase commits, all five S2-dependent tests and final independent Sol CODE review remain mandatory future gates.

## 5. Corrected limited IMPLEMENTATION GO proposal — C1–C6 closed, NOT YET AUTHORIZED

This replaces prior draft §5 refinements. The owner-approved normative ADR is pinned at PR #4 SHA a012c84240eb246b8072a735989f598b6ca566e2, but plan approval and production CODE GO are separate owner decisions.

### 5.1 Exact file allowlist and allowed read-only imports (C4)

Only after CODE GO, Sonnet may **modify**:
- Production: src/audiobook/stress_eval.py; new src/audiobook/stress_yo_observer.py; run.sh only if the existing stress-eval forwarding is proven insufficient (prefer no run.sh change).
- Synthetic tests: tests/test_stress_eval_sample.py; tests/test_stress_eval_merge.py; tests/test_stress_eval_score.py; tests/test_stress_metrics_contract.py; new tests/test_stress_yo_observer.py; tests/fixtures/t15_7/synthetic/** for invented S1 fixtures; tests/helpers/ only as needed for synthetic scaffolding.
- Task documentation/reports: tasks/T15-7-WP4-G1-IMPLEMENTATION-PLAN.md, tasks/T15-7-WP4-G1-IMPLEMENTATION-REPORT.md and directly related task status/review Markdown.

All other **production files are modification-DENIED**, notably voicecfg.py, synth.py, sutrace.py, pronounce.py, chunker.py, unitmap.py, wordprov.py, stress_fp.py, stress_inventory.py and stress_metrics.py. DENIED means **do not edit**, NOT **do not import**. Read-only imports and calls into existing synth, voicecfg, pronounce, wordprov, sutrace, stress_fp and stress_inventory are expressly allowed where the observer must use actual production preparation/L3 functions. No third production helper, new dependency, change of inventory algorithm, synthesis/config/cache/source, or model alteration without separate owner scope amendment.

PR #3 stays draft. Do not merge PR #3 or cherry-pick it wholesale. Its stress_yo_g0_readonly.py research probe may be used as a reference ONLY; reconstruct and independently test the observer inside the approved new module.

### 5.2 Two-part I1 read-only local corpus checkpoint (C1)

**Before any count comparison, validate owner-local G0 identity**: the current source_fp, manifest_fp and analysis_fp MUST equal the reference values of the originally pinned G0 census. Compare locally and report aggregate match flags only, not raw per-key hashes or words. If baseline fingerprint values are unavailable or different, issue SNAPSHOT_DRIFT / STOP before evaluating census numbers. No silent repinning, resampling or data edits.

**I1-A — replay original G0 membership from protected sample/1 todo, READ ONLY.** Read the original 320-row local stress_gold.todo.tsv to obtain exact sample/1 keys; do NOT regenerate or modify it. For identical G0 fingerprints require: eligible source mapping **51,629/51,629**; original selected mapping **320/320**; unsupported **0**; sample/1 selected RESTORED **40**, YO_EVALUABLE **40**, F1 excluded_union **0**. This is a characterization of the OLD sample only.

**I1-B — sample/2 solely IN MEMORY.** Recompute from full eligible population, with no creation of real sample/score/todo files. On identical pinned G0 population require eligible mapping **51,629/51,629**, population RESTORED **223**, unsupported **0**, and **0 L3 mismatches** for EVERY SU including NONE. Assert byte-exact composed_final and exact phrase type/value (None differs from empty string). Expect **320 sample/2 selected keys only if sufficient populations exist**; otherwise STOP and request corrected stage gate, never fabricate missing keys. Verify full sample/2 fp unchanged across PYTHONHASHSEED=1,2,3 and iteration order. Sample/2 selected RESTORED, selected YO_EVALUABLE and F1 excluded are **observed counters, not pass thresholds**: specifically NEVER compare them to old sample/1 40/40/0.

**Read-only fence**: Owner-local real run must be offline and memory-only with no S3/S4 writes, sample/merge/merge-yo/score/file-generating commands, sample/2 todo creation, corpus/manifest/config/inventory publication, audio, cloud text/voice, cache, logs or incidental pycache/temp writes in protected paths. Before/after byte-hash parity of protected files locally: changed protected files **0**. Outputs restricted to aggregate counts and status. A mismatch, unsupported mapping, L3 mismatch, missing/changed fingerprint, protected-file change, or attempted S3/S4 write is STOP. I2 cannot start without an explicit coordinator I1 PASS.

**Synthetic-only exception:** After CODE GO, invented S1 fixtures in tmp_path may exercise I1 lock, P1/P4, atomic writes, todo guards and failure injection without touching owner S3/S4.

### 5.3 Sequential implementation gates, original F1 and S2 (C2/C5)

I1 must implement and synthetic-test common **OS-backed lock, P1/P4 ignore/index guards, single-file atomic temporary write+fsync+replace and OWNER_TODO_PROTECTED**; these mechanisms belong in approved stress_eval.py/observer module and must NOT be deferred to I3. I2/I3 reuse them. Implementing gated sample/todo writing logic does NOT authorize running it against real S4.

At each phase, run the exact assigned T-oracles in §2 and the FULL pytest suite with no unexplained FAIL; record actual test node IDs, seed/skip counters, SHA, file diff and protected-file parity. I1 requires coordinator read-only PASS before I2. I2 requires its 22 assigned oracles and all three original Sol F1 regressions PASS before I3. I3 requires its seven assigned oracles and a final 42/42 traceability matrix.

Final exit requires existing 52 G0 synthetic and 17 S4 synthetic tests, full pytest, Python hash seeds 1/2/3, privacy P1/P4, protected-file parity, and all five previously S2-baseline-dependent SKIPs **actually executed and PASS**. Missing/invalid S2 baseline => BLOCKED_S2_BASELINE/STOP; these five may NOT remain SKIP. Other SKIPs require node IDs and specific documented explanations. Exactly one independent Sol CODE review at the final pinned implementation SHA is mandatory after local test evidence; no claim of code PASS from previous architecture review.

### 5.4 Fixed code base and PR relationship (C3)

**BASE_CODE_SHA = 201f0cd4e946f7f5405e47fe27153df9aeac17ef** (the exact code base of approved PR #4). Verified that changes between this commit and task/T15 at c6d26c79399196789006108fdd91cdb7681ba495 were **task documentation only**, not production/test code.

Only AFTER explicit owner CODE GO, create **task/T15-7-wp4-g1-implementation** from this exact BASE_CODE_SHA; never from a floating branch name. Normative ADR remains pinned separately at a012c84240eb246b8072a735989f598b6ca566e2; consult it without merging PR #4. No PR #3 cherry-pick/merge; reuse research observations only as reference.

### 5.5 Hard STOP conditions (C6)

- Any required modification outside the exact §5.1 allowlist: STOP and request owner scope amendment.
- Real-corpus unsupported > 0, any L3 mismatch, missing/ambiguous ordinal, or unverified phrase None/empty equivalence: STOP.
- Any G0 source_fp, manifest_fp or analysis_fp reference missing or not matching the current local snapshot: SNAPSHOT_DRIFT/STOP **before** checking expected counts.
- Any protected file changes, even one byte, during the read-only real run: STOP.
- Missing or invalid S2 fixture: BLOCKED_S2_BASELINE/STOP; all five previously skipped tests must really execute and PASS.
- Any attempted real S3/S4 write during memory-only run (sample, merge, merge-yo, score, todo, inventory, logs or temp files): STOP.
- Any code touching manuscript, human labels, real gold/archive/YO sidecar or existing 320-row todo; cache/manifest/model/audio/synth; cloud transfer; PR #3/#4 merge; WP5/T16/T17, H04 or full render: STOP.
- Failure of assigned phase oracles, full pytest, lock, P1/P4 or fingerprint parity: STOP; do not advance automatically.

### 5.6 Permissions separation

**CURRENT STATUS: PLAN_CORRECTED_PENDING_OWNER_APPROVAL / CODE_GO_NOT_GRANTED.** This documentation correction is neither owner plan approval nor a code GO. Owner must first approve this plan, then separately issue bounded GO for the named implementation branch and §5.1 paths, explicitly including the memory-only I1 owner-local checkpoint. GO never authorizes real S4 writes, owner labeling or rendering. Each phase must pass its coordinator gate. PR #3/#4 remain draft and unmerged.

