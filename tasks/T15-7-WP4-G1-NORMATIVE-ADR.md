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

1. Source identity consists of five exact fields: source_key, form_source, unit_text_sha256, unit_kind, context_sha256. source_key = section + "|" + unit_id + "|" + unit_token_index, last component the zero-based Cyrillic source token ordinal independent of chunks. context_sha256 uses the current T15-7 §5 canonical H([u(prev),u(own),u(next)]) where u is {unit_id,kind,text_sha256} or null. A human label is current iff all five source fields still equal the current normalized source identity. An unrelated global source_fp/analysis_fp change cannot by itself stale the label. A changed source or neighbor context can. A historic yo label with no source е/Е or multiple source-native ё is NOT a valid source-only or legacy-restoration truth and must be rejected, not guessed.
2. The ten-field stress.tsv header remains exactly:
   source_key | form_source | unit_text_sha256 | unit_kind | context_sha256 | context | gold_vowel | yo_correct | labeler | date
   (vertical bars in this line mean TSV column separators; on disk exactly one TAB between fields). context ≤80 chars, local only. New stress rows must set yo_correct=na. Historical y/n is preserved without interpreting it as current restoration evidence.
3. gold_vowel grammar: canonical nonnegative ASCII decimal index i with i < source vowel count; variants:i|j[|k...] as at least two strictly increasing distinct valid SOURCE vowel indices; source-native "yo" only if form_source itself has exactly one ё/Ё; "ambiguous"; "unknown_name". "yo_unstressed" is invalid. A native ё that is not stressed must use a numeric index or variants rather than "yo". Source with multiple native ё and literal gold_vowel=yo is ambiguous and must fail validation (ERROR), never infer which native ё.
4. Human accepted source-stress truth is a SET of source-vowel indices only; neither WordOcc.form_synth nor SUTrace.prep_text (both after respell) nor a current YO dictionary can influence its meaning. Unique source-native yo and the corresponding numeric index are semantically identical. Two different valid nonempty source-vowel sets are different human judgments and conflict if both active.
5. Historical current-identity gold_vowel=yo with exactly ZERO native ё/Ё but at least one source е/Е is LEGACY_YO_UNRESOLVED, preserved in authoritative stress ledger but unscorable and not active; old synth-only yo_correct cannot supply current truth. It does not block a freshly human-authored numeric stress label with the exact current five-field identity. With no replacement, a selected key is INCOMPLETE, not PASS. An unrelated historical unselected legacy row is retained without making current sample incomplete. Never infer an old restoration from current analysis, date or synthesis.

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


## 5. G1.5: two independently authoritative ledgers, atomicity and freshness

1. Exactly two separate questions and authorities: source stress (stress_gold.tsv, with all historical source versions), and spelling restoration correctness (stress_gold.yo_evidence.tsv, with all historical exact candidates). No global two-file transaction or two-file atomicity is claimed. Archive is always a derived cache, never a third authority.
2. The stress-eval merge operation can write only the authoritative stress TSV plus an optional independent refresh of the non-authoritative archive. The new merge-yo operation can write only authoritative YO evidence TSV (and independently prepared YO todo if separately authorized). Both must validate *every* input row before any write and compare bytes/source identity/sample generation before atomic replace. Repeated semantically identical merge is a byte-identical no-op. No operation may change the other ledger, nor write S4 without an explicit later implementation/data authorization.
3. On score, independently pin: validated current inventory generation, source_fp, manifest_fp/analysis_fp and observer/config digests; current sample/2 record plus assignment digest; RAW file SHA256 for BOTH authoritative ledger bytes (use explicit JSON null if absent); exact selected pre-respell restored candidate fingerprints. Read both ledgers, parse/validate all rows, compute active source stress and candidate-level YO status, then re-read both ledger bytes, current pointer, sample, observed candidate/map/config immediately before any S3 score publication. Any mismatch => ERROR/nonzero, no false COMPLETE report.
4. Saving and later reading a score are different trust boundaries: every consumer of an old saved COMPLETE score must validate *both* current authoritative ledger byte digests, current generation, sample/2 identity and exact relevant observer fingerprints. A saved score lacking the second digest or a now-stale fingerprint is INVALID/STALE and cannot authorize a gate. The archive fingerprint is not in this freshness requirement.
5. Score working output is ignored S3, atomic same-directory tmp+fsync+rename with only these aggregate fields: schema="stress-score/2"; status; source_fp; analysis_fp; sample_fp; assignment_sha256; inventory_generation_fp; observation_contract_version; norm_content_sha256; yo_map_sha256; prep_config_sha256; gold_sha256; yo_evidence_sha256; counts; metrics; wilson; gates. No source strings, individual hashes or human rows. For INCOMPLETE, set metrics, wilson and gates null (only aggregate status/reasons/counts). For ERROR, do not publish a COMPLETE score. No book/audio text to cloud.
6. Missing YO file is allowed only when the current sample has zero YO_EVALUABLE candidates. When at least one candidate requires evidence, absent matching evidence is INCOMPLETE rc2; invalid sidecar schema, same-fingerprint contradictory answers or unsupported current observation is ERROR. Source stress may remain valid while YO evidence becomes stale; neither is backfilled from the other.
7. Concurrent readers/writers are not promised serializable cross-file snapshots by os.replace alone. Use an explicit local fence/recheck of both authoritative inputs and generation before publishing and on consuming saved score. A torn pair or changed digest => STALE/ERROR; no partial metric PASS. Crash cases are covered by T40–T41.

## 6. G1.6: KEEP current C3 version-ledger, ACTIVE classification and M1–M5

### 6.1 Authoritative stress history and source states

- stress_gold.tsv is an **authoritative VERSION LEDGER**, not one physical row per source_key. All old source/context identities and historical human labels remain IN THIS SAME FILE. Do not move any row into an authoritative archive, delete or compact history.
- SOURCE_STALE = a syntactically valid historical row whose exact five-field source identity no longer matches resolved current normalized source. Keep it in the version ledger, exclude from current active/merge-conflict selection and score, and expose aggregate stale counts. An unrelated source_fp change without the five-field change never makes a row stale.
- LEGACY_YO_UNRESOLVED = current five-field source identity, historical gold_vowel=yo, exactly ZERO ё/Ё and at least one е/Е in *source*; it is historical but cannot be an ACTIVE stress truth. Preserve it in the same ledger. For a selected key with legacy only: INCOMPLETE until explicitly human-labeled numeric source stress. A valid new human numeric row with same identity is allowed; do not rewrite the legacy row, interpret old yo_correct or pretend a conflict. Old source-less legacy with differing five-field identity is SOURCE_STALE.
- ACTIVE: exactly one current valid semantic human answer after collapsing **equal canonical stress-vowel sets** or exact equal nonusable label kinds; duplicates counted but physically retained. A usable numeric label and equivalent source-native unique yo are identical semantic answers; a single ambiguous/unknown_name is completed human annotation without usable U.
- ERROR / HUMAN_CONFLICT: >1 distinct current usable stress-vowel sets; different current nonusable kinds; or current usable and completed nonusable judgments on the same source identity. The owner has explicitly prohibited any automatic human-error correction; conflicting labels remain in authority and are not selected by date, row order or source of the comment. An owner-authorized, separate history-preserving adjudication mechanism is out of scope and requires a future ADR.
- If source identity changes A→B and then reverts A, every old A row becomes CURRENT again and is reclassified from authoritative gold; if there is one canonical A judgment it becomes ACTIVE; if two conflicting A judgments exist, ERROR. A B row becomes SOURCE_STALE. There is NO chronological override.

### 6.2 M1–M5: safe operations with DERIVED archive (no archive-first transaction)

**M1 — validate before any write.** Validate current pinned sample/2 and source/generation identities, exact ten-field TSV grammar/header, each incoming todo source_key selected and same five-field identity/context, nonblank label grammar, date/labeler, batch duplicates, all existing authoritative historical rows and private output path guards. Blank todo rows are requests, not human labels. On invalid/stale/unexpected input, STOP, no writes.

**M2 — resolve current identity against full version-ledger.** Recompute SOURCE_STALE, LEGACY_YO_UNRESOLVED, ACTIVE, duplicates and conflicts. Equivalent existing ACTIVE semantic answer ⇒ SKIP (idempotent). Different usable/complete current answer ⇒ ERROR, no new row; no auto-adjudication. If only stale/legacy/missing current truth ⇒ append a *new owner-authored* valid numeric/variants/native-yo/ambiguous/unknown_name row, leave all historical versions unchanged. At no point use yo_correct to decide human stress conflict or YO sidecar as source stress. A SOURCE_STALE row never blocks a valid new source identity.

**M3 — replace ONE authoritative stress file.** For a separately authorized merge, sort complete ledger deterministically, preserve all historical rows, guard both final and ignored same-directory txn paths (P1/P4), write whole TSV into exclusive-created temp, fsync temp; verify authoritative old bytes/current generation/sample remain exactly as pinned, os.replace the temp with stress_gold.tsv and fsync directory. Before rename old whole ledger valid; after rename new whole ledger valid. No archive participation in stress transaction. Existing local gold (0 rows in census) must not be recreated or overwritten until a future data-write GO.

**M4 — independently rebuild derived non-authoritative archive.** After M3, compute deterministic SOURCE_STALE subset of the complete authoritative gold ledger; use a second ignored same-directory temp and independent atomic replace to refresh stress_gold.archive.tsv. A crash after M3 but before M4 leaves valid authoritative gold and possibly stale archive; next explicitly authorized repair may rebuild archive. Score and merge *never read the archive as input*. LEGACY_YO_UNRESOLVED with current identity is retained in gold, not moved to archive merely because its human stress is unscorable. Archive-only apparent history is a local audit BLOCKED condition; it is never silently imported into gold.

**M5 — privacy, idempotence, concurrency and recovery.** Run git check-ignore for each S2–S4 final/temp path and require git ls-files --error-unmatch failure; check bytes/identity again before write, don't disclose S4/row values or per-token hashes. Re-running same merge must yield bit-identical gold and stable active state. In a crash between the two independently atomic gold/archive replacements, only gold is authoritative; archive repair cannot modify gold. Reverting source identity never chooses a latest-date label; contradictory current rows ERROR with no write. Do not write new/current 320 todo merely to run this audit or adopt this ADR.

### 6.3 YO merge separately (not a new stress-C3 version model)

The new merge-yo validates exact current candidate fingerprint, owner y/n, observer version, source identity, private sidecar header, map/config content provenance and selected sample identity. Duplicate matching restoration fingerprint+y/n ⇒ SKIP byte-idempotently; opposite y/n ⇒ ERROR; new candidate version with valid human evidence ⇒ append historical evidence without deleting earlier candidates; single same-file atomic temp/fsync/replace. It never writes stress_gold.tsv or archive. It does not give an automatic correction workflow for previously contradictory human source stress, nor does it permit S4 migration.

## 7. Quality metrics and gate policy retained with corrected truth sets

- S = all selected eligible observations with completed L; global COMPLETE requires L for every selected source key and Y for each selected YO_EVALUABLE candidate. E=eligible, R=f6_status resolved, U=accepted source-vowel set nonempty, C=f6_vowel ∈ U, O=omograph stratum, Y=selected YO_EVALUABLE with matching unique human verdict. Stratum membership is disjoint but RESTORED may also occur in another stratum.
- Per stratum and overall: coverage = |E∩R|/|E|; unresolved_rate = 1−coverage; accuracy_resolved = |E∩R∩U∩C|/|E∩R∩U|; suggestion_precision = |E∩R∩U∩C∩O|/|E∩R∩U∩O|; false_suggestion_rate=1−suggestion_precision; yo_precision = |Y with y|/|Y|; override_disagreement = wrong accepted-source-vowel result among E∩R∩U∩covered_by_override; population-weighted book estimate = Σ_s (N_s/ΣN)·rate_s for *defined* strata only, WITHOUT renormalizing weights when other strata undefined.
- Every defined rate reports integer k/n, raw float and Wilson 95% (z=1.959963984540054). Wilson p=k/n, d=1+z²/n, center=(p+z²/(2n))/d, half=z·sqrt(p(1−p)/n+z²/(4n²))/d; clip center±half to [0,1]. Denominator n=0 ⇒ rate and bounds NULL, no pass; comparison uses unrounded numbers, display four decimal digits.
- Numeric oracles: 40/40 Wilson lower 0.9124; 92/100 lower 0.8500 (actual ≈0.850019); 91/100 lower 0.8377; 73/73 lower 0.9500.
- G-hint PASS iff n≥80 and lower≥0.85; FAIL iff n≥1 and upper<0.85; else INCONCLUSIVE and unusable. A PASS *only* permits ordering T16 review batches by RUAccent; no automatic application or listener exposure.
- YO_WARN when any current selected YO_EVALUABLE candidate has y/n verdict n, or when |Y|≥1 and Wilson upper for yo_precision <0.95; else YO_NO_EVIDENCE, including zero applicable candidates. No quality PASS, no automatic toggling yo_restore.
- H04 real human labels remain HOLD; current gold=0, archive=0, todo=320 blank => expected scorer INCOMPLETE rc2 under both sample generations until a separately approved workflow. The current S4 census does not prove listening/audio quality.

## 8. Privacy, baseline and rollout restrictions

- S1 only synthetic invented tests tracked. S2 real-corpus fixtures ignored under out/t15_7/baseline/. S3 inventory/sample/score ignored under out/stress/. S4 gold/todo/old version history/YO sidecar/transactions ignored under text/stress_gold*.tsv. Check gitignore and untracked for final AND txn before every authorized write. No book text, S4 labels, per-token values/short-fragment hashes in Git, chat or logs.
- Original TTS path and baseline are unchanged; no synthesized output changes or audio renders are authorized. Require source/manifest/analysis fingerprints, old S2 golden baseline, exact outputs and hash seeds 1/2/3 when a future code patch is reviewed. No production, H04, S4 write, sample regeneration, merge of PR #3, WP5/T16/T17 or render may start from this proposal.
- Future implementation must occur only after the owner adopts a reviewed final ADR AND separately grants code GO; independent Sol implementation review at a pinned implementation SHA is distinct from the one independent Sol architecture review requested now.
- This document is a *single self-contained WP-4 normative candidate*; unaffected global T15-7 decisions still derive from accepted rev.2. The separate owner decision retains the current C3 model, not the proposed authoritative-archive/one-active-physical-row model.


## 9. T01–T42 — complete proposed regression-oracle register

**Provenance limitation:** The owner's architect handoff mentions an original T01–T42 table but did not supply that original table. The exact original 42-row numbering was not found in the inspected tracked repository files. **The 42 rows below are an independently reconstructed, self-contained proposed register, not an assertion of verbatim identity with the architect's unpublished table.** Independent Sol must reconcile meanings and numbering (especially T06/T27/T28) against the original if available, and mark differences explicitly. This is an ADR-review gate rather than license to guess provenance. All test inputs must be synthetic/invented, with no manuscript excerpts, source_key values, owner S4 rows or per-token hashes in reports.

| ID | Synthetic stimulus | Exact required oracle |
|---|---|---|
| **T01** | Five-field source identity unchanged; analysis_fp and yo map change | Numeric source stress remains same source-vowel index and CURRENT; no fresh stress label required |
| **T02** | Source token text changes | Old identity SOURCE_STALE retained in authoritative gold; selected absent new label => INCOMPLETE rc2 |
| **T03** | Neighbor unit changes, same target token | Context_sha mismatch makes old row SOURCE_STALE; new owner-authored current annotation can append without deleting old |
| **T04** | Unique native source ё with gold_vowel=yo | Source-native vowel index usable, independent of prepared/respell form |
| **T05** | Source has no ё but historical synth-only gold_vowel=yo | LEGACY_YO_UNRESOLVED retained; selected stress L incomplete; no current form_synth inference |
| **T06** | LEGACY_YO_UNRESOLVED same current five-field source identity plus new human numeric label | New numeric source-only row becomes uniquely ACTIVE, old legacy remains in authoritative stress ledger, no duplicate/conflict, historical yo_correct ignored; SOURCE_STALE never falsely inferred |
| **T07** | Numeric gold with yo_correct=na; later yo_restore toggle | Current numeric label remains valid; no GOLD_INVALID or forced stress re-label based on new post-respell YO |
| **T08** | Restored ё moves between two different source е positions | Human source-vowel gold unchanged; old candidate y/n must NOT apply to new restoration_fp |
| **T09** | Source-native unique yo and equivalent numeric label for same current identity | Equal canonical source-vowel sets => one logical ACTIVE with duplicate count; both physical rows retained |
| **T10** | Two different current numeric vowel sets for same identity | HUMAN_CONFLICT ERROR, no newest-date or agent-based resolution |
| **T11** | Only ambiguous label for selected current source | L complete, U false, no inclusion in accuracy denominator; no false INCOMPLETE solely due ambiguity |
| **T12** | Only unknown_name label for selected current source | L complete, U false, excluded from applicable stress accuracy; denominator=0 has null metric |
| **T13** | No selected human gold and 320 blank owner todo | INCOMPLETE rc2, metrics/wilson/gates null; no generated human truth |
| **T14** | Wrong header, invalid date or label, malformed TSV, partial filled row | Prevalidation ERROR before any write; preserve original S4 bytes |
| **T15** | variants unsorted, duplicate or out-of-range; yo_unstressed label | All invalid ERROR; source vowels 0-based, strictly distinct ascending variants only |
| **T16** | Current source context A→B→A with only one original A label | A reactivates as CURRENT on return, B becomes SOURCE_STALE; no date preference or data loss |
| **T17** | A→B→A source return with two contradictory A judgments | HUMAN_CONFLICT ERROR; do not choose last, B or archive |
| **T18** | Old B source row after change to current A and new valid A label | Only A scored; B retained in gold; derived archive includes B stale |
| **T19** | Archive missing/stale due crash after authoritative gold replacement | Scorer still trusts gold only; separate archive repair reproduces SOURCE_STALE export; no archive-first write |
| **T20** | Archive contains historical row absent from authoritative gold | Read-only compatibility audit BLOCKED; do not import/archive-promote row or delete it |
| **T21** | sample/1 selected keys and stratum counts identical but two selected assignments swap | sample/2 sorted key→stratum digest/fingerprint differs; old sample record rejected |
| **T22** | Repeat sample/2 with different WordOcc iteration and PYTHONHASHSEED=1,2,3 | Same sample/2 selected keys, assignments and SHA256 fingerprint |
| **T23** | Six strata precedence and target sizes, top300 ties, insufficient population | Exactly omograph→top300→name→override_covered→yo_changed→tail and 100/60/40/40/40/40; take-all for undersized, no overlap |
| **T24** | Attempt sample regeneration while owner todo has filled unmerged labels | STOP TODO_HAS_UNMERGED_LABELS and no S4/sample overwrite |
| **T25** | Existing 320 blank sample/1 todo when sample/2 is introduced | No silent overwrite or migration merely because blank; owner new sample GO required |
| **T26** | Direct pre-respell yo.restore versus post-respell-only ё in form_synth | Only verified pre-respell forward change is RESTORED; post-respell addition not YO ground truth |
| **T27** | Selected RESTORED with f1_rule non-null, f1_flag none | T27: one F1 rule exclusion; excluded_union=1, excluded_f1_rule=1, excluded_flag=0; YO_EVALUABLE false; no mandatory y/n |
| **T28** | Selected RESTORED with BOTH f1_rule non-null and f1_flag non-none; plus flag-only control | T28: both increments rule=1 flag=1 both=1 but union ONLY=1; flag-only increments flag=1 and union=1; never double-count; excluded from YO denominator and mandatory y/n |
| **T29** | Selected RESTORED with f1_rule null and f1_flag none | YO_EVALUABLE true; matching human y/n required or INCOMPLETE rc2 |
| **T30** | Native source ё only; disabled yo_restore; later respell introduces ё | No new pre-respell restoration: NONE; not YO_EVALUABLE, no invented evidence |
| **T31** | Exact source→chunk-word→fragment ordinal across single/two fragments, quotes/open_end/carrier | Word and offset agree exactly or UNSUPPORTED ERROR; never fuzzy match/guess based on final SUTrace |
| **T32** | Direct yo.restore(source word) vs verified pre-respell prepared word after punctuation handling | Exact match, only forward e→ё; other edits/reverse, text length or case mismatch => UNSUPPORTED |
| **T33** | One word with two forward е→ё changes; one owner n verdict | Sorted two source-vowel indices validate against spelling; one candidate-level n, one wrong observation (not per-edit count) |
| **T34** | Source A observation/restoration candidate changes to B for same source identity | Different restoration_fp; old A human verdict cannot be reused for B; B requires new y/n |
| **T35** | Source/candidate A→B→A, all five source-identity fields and observer version exact | Old A y/n reusable only after fresh current A observation; no B substitution, old rows retained |
| **T36** | YO map changes content with same max mtime but pre-respell candidate stays same | Fresh bytes digest catches change; reobserve; same exact candidate fp may reuse prior y/n only after fresh verification |
| **T37** | YO sidecar duplicate exact fp with same y/n; duplicate exact fp with opposite y/n | First idempotent, second ERROR; all candidate history retained in same authoritative YO ledger |
| **T38** | Current YO_EVALUABLE but sidecar absent or exact observation_fp missing | INCOMPLETE rc2; no fallback to historic stress yo_correct, timestamp or model label |
| **T39** | YO candidate spelling/indices inconsistent, unknown observer version, invalid TSV, ignored-path failure | ERROR before merge-yo or score write; no private row/text or per-row hashes in public JSON |
| **T40** | Inject crash before/after gold atomic replace and between gold replace/derived archive refresh | Old/new full gold survives with all historical rows; archive may be stale but never authoritative; read/repair doesn't alter gold |
| **T41** | Mutate gold or YO bytes, inventory generation, sample assignments or observer inputs before score publish / saved COMPLETE reuse | Fence detects any mutation and yields ERROR/STALE with no false COMPLETE; two authoritative digests pinned; archive excluded |
| **T42** | Rate denominators=0, 40/40, 92/100, 91/100, 73/73 Wilson; G-hint/YO gate; P1/P4 and baseline | Undefined metrics null, no gate PASS; Wilson lower 0.9124/0.8500/0.8377/0.9500, n≥80+lower≥.85 for hint PASS; no source leaks, S4 writes, synthesis or cache changes |

### Acceptance of this register

- Each T01–T42 is a contract to create **at least one independent deterministic synthetic fixture**, an expected result including exact count/status, and a traceable pytest node ID **after separate implementation approval**. The production implementation may not claim these as PASS merely because this document enumerates them. The special T06, T27 and T28 cases must be fully independent tests and fail against known pre-fix semantics.
- Retain the original three Sol F1 reproductions: removal of restored ё, introduction of restored ё, and movement of restored ё between source е vowels without any source identity change.
- For temporal semantics include A→B→A cases for both source context and exact YO candidate restoration; duplicate same-fp and conflicting same-fp semantics; all single-file crash points and dual-ledger stale-score races.
- The owner-local data state (gold=0, archive=0, 320 unfilled todo, 40 YO_EVALUABLE, 0 F1 excluded) remains a measured read-only **snapshot**, not a synthetic oracle or a guarantee about future cases.
- Independently verify current complete protected-file parity and earlier five S2-baseline-dependent tests in the final acceptance environment. The 17/17 S4-audit test PASS and 52/52 G0 test PASS are prior task-reported results, not evidence that a future code patch passes this new normative suite.

## 10. Authority and next approval gates

| Decision or activity | State |
|---|---|
| G1.1–G1.5 design principles | Owner approved IN PRINCIPLE |
| G1.6 existing authoritative stress version-ledger | Owner APPROVED |
| Proposed one-active-row and authoritative archive | Owner REJECTED |
| Any S4 migration or rewrite | NOT AUTHORIZED |
| This ADR draft + one independent Sol architecture review | AUTHORIZED |
| Adoption/replacement of current authoritative T15-7 FINAL ADR rev.2 | PENDING after independent review and owner acceptance |
| Production implementation, merge PR #3, H04, sample/2 regeneration | NOT AUTHORIZED |
| WP-4 quality closure; WP5/T16/T17/full render | BLOCKED / HOLD |

**NEXT ACTION:** independent Sol architectural review of an EXACT pinned SHA of this candidate, against the owner decision, current C3, and the 42 test oracles. Reviewer responds PASS / CHANGES_REQUIRED / BLOCKED with concrete line-level corrections, including whether the missing architect-origin T01–T42 table precludes adoption. Only after the owner accepts a reviewed final ADR may the coordinator ask separately for code implementation permission. **STOP.**
