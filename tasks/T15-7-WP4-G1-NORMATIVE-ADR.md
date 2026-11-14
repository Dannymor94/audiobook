---
id: T15-7-WP4-G1-NORMATIVE-ADR
title: "WP-4 G1 unified source-stress and YO-evidence normative candidate; existing C3 retained"
status: PROPOSED_NORMATIVE_PENDING_INDEPENDENT_REVIEW
owner: owner
branch: task/T15-7-wp4-g1-normative-adr
implementation_authorized: false
s4_migration_authorized: false
---

# T15-7 WP-4 G1 — unified normative ADR candidate

**STATUS: PROPOSED FOR INDEPENDENT REVIEW, NOT YET ADOPTED.**
Date: 2026-11-14. Scope: source-only gold, completeness, sample/2, pre-respell YO evidence, two ledgers, retained C3, M1–M5, score freshness, private S4 safety, T01–T42.
Owner authorization: G1.1–G1.5 APPROVED IN PRINCIPLE; G1.6 RETAIN EXISTING C3 VERSION-LEDGER APPROVED; proposed one-active-physical-row plus authoritative archive REJECTED; S4 MIGRATION NOT AUTHORIZED. Only proposal drafting and one independent architectural review are authorized. Existing T15-7 FINAL ADR rev.2 remains operative until a later separate adoption decision. All unaffected synthesis and inventory contracts of that document stay unchanged. No production or S4 change may result from this draft.

## 0. Authorities and invariant boundaries

- Single authoritative human *stress* version history: local ignored text/stress_gold.tsv, containing all versions. The derived local ignored text/stress_gold.archive.tsv remains NON-AUTHORITATIVE, rebuildable from stale rows of the former. It is not an input to scorer, merge, active-label selection, or recovery.
- Single separate authoritative human *restoration* history, when independently approved for creation: local ignored text/stress_gold.yo_evidence.tsv, with local todo text/stress_gold.yo.todo.tsv. It never supplies or overrides a source stress coordinate.
- No archive-first two-file transaction, no migration, deletion, automatic adjudication, resampling, gold edits or new sidecars without separate explicit permission.
- Read-only observation changes neither source nor synthesis path. Keep 6C11, synth, voicecfg, pronounce, manifests, model, cache, audio, TTS inputs and seeds untouched; no text/voice sent to cloud.
- Evidence: owner-local G0 current-snapshot census verified 51,629/51,629 eligible and 320/320 selected source-to-pre-respell matches (unsupported 0). G0 targeted 52/52 PASS at 650127b9; older full suite 1845 PASS/11 SKIP. Owner-local S4 read-only census at 355507df: 17/17 synthetic PASS, stress_gold=0 data rows, archive=0, todo=320 all blank, selected RESTORED=40, YO_EVALUABLE=40, F1 excluded=0. These are agent-reported observations, not independent Sol acceptance. Do not generalize these counts to future snapshots.

## 1. G1.1: human stress truth is from source only

1. Source identity consists of five exact fields: source_key, form_source, unit_text_sha256, unit_kind, context_sha256. source_key = section + "|" + unit_id + "|" + unit_token_index, last component the zero-based Cyrillic source token ordinal independent of chunks. context_sha256 uses the current T15-7 §5 canonical H([u(prev),u(own),u(next)]) where u is {unit_id,kind,text_sha256} or null. A human label is current iff all five source fields still equal the current normalized source identity. An unrelated global source_fp/analysis_fp change cannot by itself stale the label. A changed source or neighbor context can.
2. The ten-field stress.tsv header remains exactly:
   source_key | form_source | unit_text_sha256 | unit_kind | context_sha256 | context | gold_vowel | yo_correct | labeler | date
   (vertical bars in this line mean TSV column separators; on disk exactly one TAB between fields). context ≤80 chars, local only. New stress rows must set yo_correct=na. Historical y/n is preserved without interpreting it as current restoration evidence.
3. gold_vowel grammar: canonical nonnegative ASCII decimal index i with i < source vowel count; variants:i|j[|k...] as at least two strictly increasing distinct valid SOURCE vowel indices; source-native "yo" only if form_source itself has exactly one ё/Ё; "ambiguous"; "unknown_name". "yo_unstressed" is invalid. A native ё that is not stressed must use a numeric index or variants rather than "yo".
4. Human accepted source-stress truth is a SET of source-vowel indices only; neither WordOcc.form_synth nor SUTrace.prep_text (both after respell) nor a current YO dictionary can influence its meaning. Unique source-native yo and the corresponding numeric index are semantically identical. Two different valid nonempty source-vowel sets are different human judgments and conflict if both active.
5. Historical current-identity gold_vowel=yo with no source-native ё is LEGACY_YO_UNRESOLVED, preserved byte-for-byte in authoritative stress ledger but unscorable and not active; old synth-only yo_correct cannot supply current truth. It does not block a freshly human-authored numeric stress label with the exact current five-field identity. With no replacement, a selected key is INCOMPLETE, not PASS. An unrelated historical unselected legacy row is retained without making current sample incomplete. Never infer an old restoration from current analysis, date or synthesis.

## 2. G1.2: distinct annotation, stress-usability and YO-evidence completeness

1. L = completed valid human source-stress annotation for a selected current identity; U = usable nonempty source-vowel set for stress accuracy; Y = unique valid human judgment of the exact current YO_EVALUABLE restoration candidate. Valid "ambiguous" and "unknown_name" satisfy L but not U. Valid numeric/variants/source-native yo satisfy L and U. Missing/stale/partial/malformed or LEGACY_YO_UNRESOLVED do not satisfy L.
2. Every selected key requires exactly one *semantic* current L. Identical semantic judgments in multiple physical rows are coalesced logically; all physical versions stay in stress_gold.tsv. Two current distinct usable sets conflict; two differing completed nonusable classes or usable versus nonusable also conflict and require separate owner adjudication. Only LEGACY_YO_UNRESOLVED is a non-competing historical exception. Never choose by date, labeler, agent or most recent merge.
3. Every selected independent RESTORED with YO_EVALUABLE true requires exactly one candidate-matching y/n human YO verdict; conflicting current verdicts for the same candidate fingerprint = ERROR. If missing, the entire score is INCOMPLETE rc2 even if stress annotations are otherwise complete.
4. Status matrix:
   * COMPLETE rc0 only if every selected L present, every selected YO_EVALUABLE verdict present, no relevant source-observer error, no conflict, all sample/generation/ledger fingerprints fresh;
   * INCOMPLETE rc2 if a selected L is missing/legacy-unresolved or required YO verdict absent; expose aggregate counts only, metrics/wilson/gates null, never partial passing gate;
   * ERROR nonzero if malformed wire data, sample mismatch, failed source identity, conflicting labels, unsupported needed pre-respell mapping, stale output or violated privacy fence.
5. A completed ambiguous/unknown_name observation is excluded from the appropriate accuracy denominator, not from the selected label-completeness count or ordinary model-resolution coverage denominator. A rate with denominator 0 is undefined/null. A gate based on it is INCONCLUSIVE/NO_EVIDENCE, never PASS.

## 3. G1.3: sample/2 identity, strata and existing H04 todo

1. Read only validated current v5 WordOcc inventory. Eligible iff aligned and form_analysis contains >=2 vowels. Count one-vowel aligned observations separately. Duplicate source_key in inventory => ERROR.
2. Six disjoint strata in first-match order: omograph target 100; top300 target 60; name 40; override_covered 40; yo_changed 40; tail 40. Reuse current T15 name/homograph and folded source form frequency rules; descending frequency and lexicographic folded-form tie-break. The override_covered flag is the existing validated WordOcc status.
3. yo_changed for sample/2 means proven forward pre-respell е/Е→ё/Ё source-token RESTORED under §4, NOT mere post-respell WordOcc.form_synth difference. It is an observation *property* independent of which stratum wins precedence. Separately YO_EVALUABLE filters F1; do not use different restoration signals for sample classification, YO matching and candidate counting. F1 exclusions are explicitly reported, not silently redefined as NONE.
4. Within each stratum rank by SHA256(UTF8("t15-7/2|" + source_key)), tie-break key ascending, take min(target, population). Sample record and fingerprint commit to sorted exact selected key→stratum assignments, not just key set/counts. Canonical serialization H(x) is SHA256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")) lowercase hex.
5. sample_fp = H({"algo":"sample/2","source_fp":source_fp,"analysis_fp":analysis_fp,"seed":"t15-7/2","targets":[{"name":str,"n":int} in normative stratum order],"selected":[{"source_key":key,"stratum":name} sorted by key],"assignment_sha256":H(sorted key/stratum pairs),"observation_contract_version":"yo-observation/1"}).
   Sample S3 record stores this fp, source_fp, analysis_fp, per-stratum N/n, selected keys, per-key assigned stratum and observer version. A membership swap with the SAME selected keys and SAME counts produces a different sample_fp.
6. Existing local 320-row H04 stress_gold.todo.tsv is protected S4. Even though all 320 rows were blank in the authorized audit, sample/2 cannot overwrite, silently relabel, regenerate or adopt it without later owner permission. Policy change invalidates use of sample/1 record as sample/2. If an edited todo contains unmerged human labels, fail with TODO_HAS_UNMERGED_LABELS rather than destroy it. No new sample record/todo is written merely by drafting this ADR.

## 4. G1.4: exact pre-respell restoration evidence

1. The real synth order is raw fragment → voicecfg.prepare_text (possible yo.restore) → carrier/padding → pronounce.respell → sentinel → engine. Observe only the exact SOURCE-aligned word after yo.restore and BEFORE respell. WordOcc.form_synth and SUTrace.prep_text are post-respell; neither is a source of restoration truth.
2. A versioned read-only "yo-observation/1" witness must map source_key → current five-field source identity → raw manifest chunk → 0-based chunk-word ordinal → exact raw fragment ordinal. Independently compare direct yo.restore(source token, fresh content-pinned map) with the correct token in voicecfg.prepare_text of the verified fragment. Verify NFC, case, token length and *only forward* е/Е→ё/Ё edits. Source-vowel indices of all replacements must be sorted/distinct/in range and reproduce spelling exactly. Missing raw manifest, mtime-stale map, misalignment, mixed/phrase edits, reverse edits, wrong quote/carry/punctuation or ambiguous fragment => UNSUPPORTED/ERROR, NEVER a guessed NO_RESTORATION.
3. Observer yields NONE, RESTORED(candidate, sorted source-vowel indices, restoration_fp), or UNSUPPORTED(reason). NONE is proved absence of forward restoration in the pre-respell path. Source-native ё is not newly restored. A YO change introduced only by later respell is not a RESTORED observation.
4. YO_EVALUABLE = RESTORED AND (f1_rule is null) AND (f1_flag == "none"). Count exclusions separately for rule-only, flag-only, both, and their union (never double count). F1-excluded RESTORED is not YO precision numerator/denominator and does not require a human YO verdict. An unsupported observation is not hidden by exclusion. The sample yo_changed stratum can contain RESTORED rows regardless of F1 flags, but evidence/gate use YO_EVALUABLE only.
5. Authoritative private S4 YO evidence TSV header is exactly 16 tab-separated fields:
   schema_version, source_key, form_source, unit_text_sha256, unit_kind, context_sha256, restored_form_pre_respell, restored_vowel_indices, observation_contract_version, restoration_fp, norm_content_sha256, yo_map_sha256, prep_config_sha256, yo_correct, labeler, date.
   schema_version="yo-evidence/1"; observation_contract_version="yo-observation/1"; restored_vowel_indices string is strictly ascending ASCII decimal indices joined with "|" (not prose); yo_correct is human y/n for the ENTIRE exact candidate, labeler nonblank, date valid ISO YYYY-MM-DD. A "y" means ALL forward restorations correct, "n" means at least one wrong. Multiple changes still count as exactly ONE candidate in YO precision. Only private S4 may contain source words, candidate spellings and row-level fingerprints.
6. restoration_fp = H({"algo":"yo-evidence/1","observation_contract_version":"yo-observation/1","source_identity":{"source_key":value,"form_source":value,"unit_text_sha256":value,"unit_kind":value,"context_sha256":value},"restored_form_pre_respell":candidate,"restored_vowel_indices":[i,...]}).
   The three global digests norm_content_sha256, yo_map_sha256, prep_config_sha256 are pinned provenance, NOT part of human candidate equivalence. Any changed global map/config requires fresh observation; if exact source identity, candidate, indices and observer version reappear after A→B→A, a historical identical restoration_fp y/n may be reused. A different candidate requires NEW human evaluation. Never silently transplant old y/n from stress gold.
7. Identical restoration_fp+same y/n is a logical duplicate/idempotent. Identical fp+opposite y/n is ERROR, not latest-date winner. Different fp versions persist in the YO ledger without replacing earlier history. Local ignored YO todo can request human evidence only with exact present source/candidate/version fp, no automatic y/n.

