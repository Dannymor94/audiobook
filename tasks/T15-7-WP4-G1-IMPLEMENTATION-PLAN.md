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

## 2. Proposed bounded future work — NO START WITHOUT SEPARATE CODE GO

Prefer coordinator ownership of planning, test review and independently reproducible synthetic assertions; Sonnet handles only the genuinely local-runtime-dependent production integration AFTER owner GO. Work on a new exclusive implementation branch, pinned against current base and approved ADR. Three checkpoints, ONE independent Sol code-exit review at the combined final SHA.

| Phase | Future deliverable | Narrow initial file scope | Exit evidence |
|---|---|---|---|
| WP4-I1 — observer and sample | Read-only exact source-to-fragment/pre-respell observer; full every-SU L3 parity; sample/2 population and selected digests, deterministic strata and versioned paths; compute F1 exclusions. No S4 files touched | Primarily src/audiobook/stress_eval.py and synthetic tests/test_stress_eval_sample.py; reuse G0 witness as test reference only, not unapproved PR #3 merge | T21–T32; disabled yo_restore with operative map; L3 None-vs-empty, 1-byte mismatch, NONE; O17/O32/O34/O35; sample/1/todo unchanged |
| WP4-I2 — retained C3 + YO history | Fix source-only gold semantics, LEGACY_YO_UNRESOLVED/SOURCE_STALE/ACTIVE and C3 M1–M5; stress merge isolated from sample/analysis; derived deterministic archive; independent 16-field YO evidence validate and merge-yo with single-file atomicity. Synthetic temp dirs only | Primarily src/audiobook/stress_eval.py, tests/test_stress_eval_merge.py and synthetic fixture helpers; run.sh only if strictly necessary for merge-yo CLI | T01–T20, T33–T40; old history preserved and no archive authority; duplicate/no-op, conflicts, crash/fail-closed; no owner S4 writes |
| WP4-I3 — scorer, locks, end-to-end | Bind source-only human stress and current exact YO truth to existing pure metric core; current and saved-score freshness using BOTH ledgers, sample and observer; OS-backed lock, safe atomic S3 publish, complete/incomplete/error, G-hint and YO gates | Primarily src/audiobook/stress_eval.py, tests/test_stress_eval_score.py and metric-contract synthetic tests; stress_metrics.py unchanged unless explicit escalation | T11/T12/T29/T37–T42; exact Wilson, T42 all-nonpositional COMPLETE rc0, score bytes preserved on crash/race, no false PASS |

Allowed paths above are a proposed LIMIT, not a grant. Any change to other production files, especially wordprov/sutrace/synth/voicecfg/pronounce/6C11, requires STOP and new architect/owner authorization. The earlier PR #3 test-only G0 work must not be silently merged or cherry-picked merely because it is useful.

## 3. Combined future acceptance gates, each mandatory

**A1 — T01–T42 traceability.** Every adopted T oracle has an invented deterministic fixture, exact expected output/status/count where meaningful and pytest node ID; all 42 test obligations accounted for, including O17 replacement and O38 derived archive replacement. No claim that a test already passes just because it is listed. Retained C3 T06/T27/T28 must preserve old passing safety, while three original Sol unsafe F1 regressions must fail under the old defect and pass after correction.

**A2 — Gold C3 / merge.** T06 current numeric or positional/nonpositional conflict => OWNER_ADJUDICATION_REQUIRED/ERROR, never newest date; T10 legacy numeric replacement active while legacy stays in stress_gold; T27 stale B remains in stress ledger, M4 exports identical derived stale copy only; T28 A→B→A recomputes ACTIVE from gold. New stress merge works on an unsampled but source-current valid key with changed unrelated analysis/restoration and no sample/2 record (C1). No S4 migration.

**A3 — Observer/sampling.** T30/T32 feature disabled + map entry that WOULD restore must yield verified NONE, never compare unconditionally to direct yo.restore. T31 full every-SU composed_final UTF-8 and composed_phrase exact parity with production prepare_synth_text, including None-versus-empty; L3 mismatch halts before any write. T21–T25 full eligible/selected sample digests: change of an UNSAMPLED eligible stratum changes fp; selected membership swap changes fp; iteration order/hash seeds 1,2,3 identical. Exact versioned paths, no original 320-row todo overwrite.

**A4 — YO evidence.** T16/T18/T29 predicate and exclusion counters; T33–T39 candidate-level whole-word y/n, sorted source vowel indices, same fp opposite verdict ERROR even if historical, observer version isolation, fresh map/config bytes, exact restoration A→B→A. Missing current matching YO verdict yields INCOMPLETE rc2; no backfill from old ten-field yo_correct.

**A5 — Atomicity, lock, dual freshness.** T40 crash before/after authoritative gold rename and between gold/archive refresh yields complete old/new stress history and repairable non-authoritative archive. T41 lock unavailable or mutation of either ledger, sample, generation or observer before score publish/reuse => ERROR/STALE, existing score bytes UNCHANGED; both authoritative byte digests pinned. No archive reads as authority or cross-file atomicity claim.

**A6 — Metrics/privateness.** T42 all selected human labels valid ambiguous/unknown_name with required YO evidence => COMPLETE rc0, accuracy null, G_hint INCONCLUSIVE; zero YO_EVALUABLE permits absent YO ledger and YO_NO_EVIDENCE; zero denominators never pass. Independently recompute Wilson lower 40/40=0.9124, 92/100=0.8500, 91/100=0.8377, 73/73=0.9500 (threshold comparisons use unrounded floats). Validate P1/P4 no tracked S2–S4 or manuscript, no synth/cache/6C11 impact.

**A7 — Test and private baseline gate.** At the final implementation SHA (after a later CODE GO): run focused new 42-oracle synthetic suite, earlier G0 52 tests and S4 synthetic 17 tests, full pytest with 0 uninvestigated FAIL; focused PYTHONHASHSEED 1/2/3. Report exact PASS/FAIL/SKIP and node IDs, explain skipped tests (including previously five S2-baseline-dependent checks) rather than silently counting them as exercised. Offline owner-local read-only checks may compare the prior S4 snapshot (gold=0/archive=0/todo=320 blank/RESTORED=40/excluded=0/evaluable=40, eligible=51,629) and protected file hashes; a changed snapshot is a STOP/investigate, not permission to regenerate. No private S4 write without separately approved data GO.

**A8 — Independent review and release control.** Sonnet must report base/head SHA, narrow diff, test nodes/counts, P1/P4, protected-file parity counts, source-only/l3/dual-fence cases, explicit no-S4-write attestations. One independent Sol WP4 CODE review at final pinned SHA returns PASS, CHANGES_REQUIRED or BLOCKED with independent evidence. Coordinator may mark WP4 PASS only after Sol PASS and owner confirmation of next stage. Sol architecture PASS does not certify future implementation.

## 4. Separation of permissions

- **ALLOWED NOW:** planning/documentation and static, non-mutating checks only.
- **NOT YET ALLOWED:** calling Sonnet to edit production; modifying tests as part of production rollout; touching owner data; creating YO evidence files; sample/2 or todo generation; running H04, merging PR #3/#4 or a new implementation PR.
- **FUTURE CODE GO:** owner must explicitly authorize synthetic-only bounded WP4-I1/I2/I3 implementation with a named worktree/branch and permitted file set. Code GO does not authorize owner S4/data changes.
- **FUTURE S4 GO:** separately authorize each owner-local sample/todo/evidence write workflow, only after reviewed code and safeguards. No automatic legacy S4 migration.
- **OTHER HOLD:** WP5, T16/T17 and full render remain prohibited even if later WP4 code receives a passing test run.

**Final plan status:** NORMATIVE_ADR_APPROVED_AT_PINNED_SHA / IMPLEMENTATION_PLAN_READY / CODE_GO_NOT_GRANTED / WP4_BLOCKED / NO_S4_MIGRATION.
