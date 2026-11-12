T15-7 FINAL ADR — rev. 2 (C3/C4 and U4–U6 integrated; authoritative)
STATUS: READY_FOR_FINAL_REVIEW
BASELINE_SHA: ab796cbaaa2594be1b4aff09366bdd0f977cd996
This document is normative on its own. All earlier T15-7 revisions, amendments and
addenda are superseded and are not referenced.
Implementation is not authorized by this document.

══════════════════════════════════════════════════════════════
1. ACCEPTED DECISIONS
══════════════════════════════════════════════════════════════
D1 RUAccent is advisory only. Its output never reaches the TTS input.
D2 The synthesis path is unchanged and only observed:
   manifest.text → voicecfg.prepare_text (yo_restore → strip_quotes →
   open_end/ensure_terminal) → [leadin] → pronounce.respell → apply_sentinel →
   engine; plus the enum-fragment path. synth, voicecfg and pronounce are not
   modified.
D3 Only the existing pronounce.yaml rules change pronunciation. They are promoted by
   the owner through the existing workflow after an ear failure; never
   automatically.
D4 6C11 (Atom, ChunkSpan, SectionMap, map_section, chunk_atoms, gates I1–I4) is
   reused unchanged and stays CLOSED.
D5 On any given manifest snapshot, T15-7 introduces no change to audio input (§11).
D6 risk.tsv and omographs.tsv keep their current production path and are
   byte-identical for identical inputs. T16/T17 consumer changes are separate tasks.
D7 Offline only. No synthesis, rendering, re-chunking, manifest rewrite or cache
   cleanup.
Identifier rule: chunk_id ≡ manifest_row["id"] everywhere in this document. No
manifest field named "chunk_id" is assumed.

══════════════════════════════════════════════════════════════
2. EVIDENCE REGISTRY
══════════════════════════════════════════════════════════════
R1  58 source sections, 2 exclusions — VERIFIED; 5,127 disk chunks — REPORTED.
R2  Rebuild with current config: 5,819 chunks (+692) — REPORTED; cause unknown.
R3  prepare_synth_text() returns (final_synth_text, phrase), no intermediate
    trace — VERIFIED.
R4  24 pronounce rules — VERIFIED; 806 matches — REPORTED; not approvals.
R5  U+0301 count 0 — REPORTED; recount on target units required (T15-7.0d).
R6  yo_restore changed 228 tokens before full preparation — REPORTED; diagnostic
    counter only.
R7  No persistent approval journal; decisions.py applies JSON without an approval
    log — VERIFIED.
R8  Three local offline RUAccent synthetic probes — REPORTED COMPLETED (T15-7.0c):
    process_all() returned strings using '+' stress notation; one probe changed е→ё.
    This establishes a provisional interface contract, NOT real-corpus stress accuracy.
    The executing agent's pinned model/files and evidence must be independently checked
    before B1 is marked QA-PASS; no manuscript inputs or audio were used.
R9  Code INVENTORY_ALGO_VERSION = 4 — VERIFIED; published v3 — REPORTED; v3 is not
    evidence for v4.
R10 Publisher order (§4) — VERIFIED FROM CODE; crash behaviour untested.

══════════════════════════════════════════════════════════════
3. FACTS F1–F6 AND APPROVAL CONTRACT
══════════════════════════════════════════════════════════════
Fact  Name               Source                        Values                     Gives expected  Affects
                                                                                  position?       synthesis?
F1    effective_rule     SU trace: pronounce.yaml rule f1_rule key|null;          never           yes, existing
                         whose respell match covers    f1_phrase bool;                            respell only
                         the token                     f1_flag none|span_ambiguous
F2    approved_decision  independently verifiable      f2_approval                only if approved never
                         persistent approval record    approved|unknown|none;     and f2_vowel
                         (none exists, R7)             f2_vowel int|null          non-null
                                                       (always null today)
F3    verified_form      form ∈ stress_verified.yaml   f3_verified bool           never           never
F4    gold               human label, evaluation only  §10 grammar                eval only       never
F5    source_mark        U+0301 in source token        f5_vowel null; f5_status   dormant (R5)    never
                         (dormant)                     none
F6    ruaccent           RUAccent on analysis string   f6_vowel int|null;         yes (tier 2)    never
                                                       f6_status (§6 field 31)
F2 semantics:
  approved — a persistent record names this rule or form, states human approval,
             and is checkable independently of pronounce.yaml. Unreachable until an
             owner-authorized source exists (O2).
  unknown  — F1 present and no such record. Today: all 24 rules.
  none     — F1 absent and no record.
  A position is never derived from pronounce.yaml replacements or respell output.
Existing rules keep working unchanged. No approval-management system is
introduced.

══════════════════════════════════════════════════════════════
4. PUBLICATION CONTRACT
══════════════════════════════════════════════════════════════
Existing publisher (VERIFIED), reused unchanged:
 1 create inventory.tmp  2 write summary.json  3 write current.json in tmp with
 the summary sha  4 copy tmp to gen/<gen_id>/  5 rename inventory → inventory.old
 6 rename inventory.tmp → inventory  7 delete inventory.old.
 _prepare_tmp_dir() handles leftovers on the next run. stress_fp.load_current()
 verifies the archived summary.json sha, not the individual TSVs.
Integration:
- occurrences.tsv is written into inventory.tmp before step 2 and listed in
  summary.json.files: {"sha256","bytes","rows","schema":"occurrences/1"}.
  rows = number of data lines, excluding the header.
- summary.json keeps existing keys and adds: source_fp, manifest_fp, analysis_fp,
  counts {occurrences, aligned, unresolved_by_reason: {reason: int}}.
- No atomicity is assumed. read_occurrences():
  load_current() → for EVERY entry of summary.json.files verify sha256, bytes, rows,
  exact header and schema → recompute manifest_fp from disk and compare.
  Any failure → refuse, rc≠0. Crash between steps 5 and 6 (no `inventory`
  directory) → refuse until the next run recovers.
- INVENTORY_ALGO_VERSION 4 → 5 in the task that adds occurrences.tsv. No
  downgrade; the v3 artifact is not touched separately.
- Existing consumers must tolerate the new summary keys; if T15-7.0d shows
  otherwise, a compat change limited to ignoring unknown keys is allowed.
- Publisher redesign is out of scope.

══════════════════════════════════════════════════════════════
5. FINGERPRINTS AND IDENTITY
══════════════════════════════════════════════════════════════
Canonical serialization: json.dumps(obj, sort_keys=True, separators=(",",":"),
ensure_ascii=False).encode("utf-8") → sha256 → lowercase hex. Comparison by exact
equality only. Null is JSON null.

source_key = f"{section}|{unit_id}|{unit_token_index}"
  unit_token_index = 0-based index of the Cyrillic token in unit.text using the
  existing T15 tokenizer. Independent of chunking and sample order.

source_fp  = H({"algo":"source/1","tokenizer":"t15/<version>",
  "excluded_sections":[...],
  "sections":[{"section","units":[{"unit_id","kind","text_sha256"}]}]})
  Sections in norm.txt order. Excludes manifests, config, RUAccent, rules, seeds,
  audio.

manifest_fp = H({"algo":"manifest/1","fields":MANIFEST_FP_FIELDS,
  "sections":[{"section","rows":[{f: v(row,f) for f in MANIFEST_FP_FIELDS}]}]})
  MANIFEST_FP_FIELDS = exactly the manifest keys read by (a) T15/T15-7 analysis and
  (b) the SU chain (prepare_synth_text and callees). Mandatory minimum:
  "n", "id", "text", "pause_after_ms", "open_end", "leadin". "text" enters as
  text_sha256. Other keys (e.g. "cont") are included only if T15-7.0d cites them
  as read. Excluded: audio/QC status, durations, seed_override and every key not
  read by (a) or (b).
  Enforcement: manifest rows and config are wrapped in key-recording mappings
  during trace and analysis. On the real corpus and the synthetic suite,
  accessed_keys ⊆ MANIFEST_FP_FIELDS and accessed config paths ⊆ CONFIG_FP_KEYS,
  otherwise the test fails.

analysis_fp = H({"algo":"analysis/1","inventory_algo_version":5,"source_fp",
  "manifest_fp","ruaccent":ruaccent_content_identity(),
  "config_subset":{p: cfg[p] for p in CONFIG_FP_KEYS},
  "yo_dict_sha256","pronounce_sha256","verified_sha256","watch_sha256",
  "exclude_sha256","trace_algo":"sutrace/1"})
  ruaccent_content_identity = {"version", "init_params",
  "files":[[relative_path, sha256_of_content], ...] sorted} over every loaded file.

sample_fp = H({"algo":"sample/1","source_fp","analysis_fp","seed":"t15-7/1",
  "strata":[{"name","n"}...] in §10 order,"selected_keys_sha256"})
  selected_keys_sha256 = H(sorted list of selected source_keys).

Gold row identity: source_key, form_source, unit_text_sha256, unit_kind,
  context_sha256 = H([u(prev), u(own), u(next)]), where
  u(x) = {"unit_id","kind","text_sha256"} or null at section edges.
  A gold version is CURRENTLY VALID iff all five match the current source and
  the source_key resolves to exactly that unit/token. A different book-wide source_fp
  caused by an unrelated unit never by itself invalidates this row. Otherwise the
  version is STALE: counted and retained in the local history, not used for scoring.
  The canonical writer adds a new version when source/context identity changes;
  it never appends an identical duplicate of an active version. Legacy identical
  duplicates are coalesced by readers; conflicting active labels are forbidden (§10).

Change                             source manifest analysis sample gold rows
unit text/kind of U                ✓      –        ✓        ✓      U, U±1 stale
analytic manifest field            –      ✓        ✓        ✓      valid
manifest audio/QC status only      –      –        –        –      valid
RUAccent / config subset / yo dict –      –        ✓        ✓      valid
pronounce.yaml                     –      –        ✓        ✓      valid
sampling seed / sizes              –      –        –        ✓      valid
TTS seed / model / audio           –      –        –        –      valid
Resampling never discards labels.

══════════════════════════════════════════════════════════════
6. OCCURRENCES SCHEMA (WordOcc = occurrences.tsv row, same order)
══════════════════════════════════════════════════════════════
Encoding: UTF-8, LF, TAB separator, no quoting, header line first.
null = "" (empty); bool = "0"|"1"; int = decimal without sign or leading zeros;
enums lowercase.
Values must not contain TAB or LF (violation → AnnotationError).
Row order: section (norm.txt order), chunk_n, chunk_word_index.
Coordinate systems: UNIT = offsets in load_units() unit.text (normalized layer,
not DOCX); ATOM = offsets in Atom.text; ANA = offsets in the section analysis
string (§7 L5); SU = token index in the SU prep_text.

 #  field             type  null  meaning
 1  source_key        str   no    §5
 2  section           str   no    validated section id
 3  unit_id           str   no    load_units id, decimal string (type confirmed in 7.0d)
 4  unit_token_index  int   no    token index in unit.text
 5  norm_start        int   no    UNIT start
 6  norm_end          int   no    UNIT end; unit.text[norm_start:norm_end] == form_source
 7  form_source       str   no    source token
 8  chunk_n           int   no    manifest_row["n"]
 9  chunk_id          str   no    manifest_row["id"]
10  chunk_word_index  int   no    token index in manifest_row["text"]
11  atom_index        int   no    index in SectionMap.stream, inside the chunk span
12  atom_char_start   int   no    ATOM start
13  atom_char_end     int   no    ATOM end; norm_start = atom.start + atom_char_start
14  ana_start         int   no    ANA start
15  ana_end           int   no    ANA end
16  form_analysis     str   no    analysis[ana_start:ana_end]; = form_synth if aligned, else form_source
17  su_chunk_id       str   yes   SU chunk id (= chunk_id) when aligned
18  su_fragment       int   yes   fragment index; null for a non-fragment SU or unaligned
19  su_token_index    int   yes   SU token index when aligned
20  form_synth        str   yes   token in SU prep_text when aligned
21  alignment_status  enum  no    aligned | prep_token_mismatch | fragment_mismatch |
                                  trace_unsupported | trace_mismatch
22  f1_rule           str   yes   pronounce.yaml key
23  f1_phrase         bool  no    the rule key spans >1 token
24  f1_flag           enum  no    none | span_ambiguous
25  f2_approval       enum  no    approved | unknown | none
26  f2_vowel          int   yes   null today
27  f3_verified       bool  no
28  f5_vowel          int   yes   null (dormant)
29  f5_status         enum  no    none
30  f6_vowel          int   yes   RUAccent vowel index
31  f6_status         enum  no    resolved | no_stress | multi_stress | invalid_mark |
                                  tokenization_mismatch | not_run
32  expected_source   enum  no    decision | source_mark | conflict | ruaccent | none
33  expected_vowel    int   yes
34  status            enum  no    ok | covered_by_override | unresolved
35  reason            str   no    ""; or one unresolved reason code; or, for status=ok, applicable informational reason codes from §9 joined by ";" in §9 order (no duplicates)
Vowel index: 0-based index among characters in "аеёиоуыэюя" of lower(form_analysis).
Links (exact, no search):
  L-a unit.text[norm_start:norm_end] == form_source
  L-b stream[atom_index].text[atom_char_start:atom_char_end] == form_source, and
      span.atom_start ≤ atom_index < span.atom_end for chunk_id
  L-c analysis = build_analysis_text(section_map, rows);
      analysis[ana_start:ana_end] == form_analysis
Round trip: serialize(parse(tsv)) is byte-identical to tsv.

══════════════════════════════════════════════════════════════
7. DATA FLOW
══════════════════════════════════════════════════════════════
L0 load_units()          normalized units.
L1 map_section()         6C11 on the target snapshot.
L2 manifest rows         snapshot manifests (manifest_fp); chunk_id = row["id"].
L3 SU trace              SU = (chunk_id, fragment_index | null). The existing
                         public step functions are composed in prepare_synth_text
                         order (cited in 7.0d). Per SU, composed final ==
                         prepare_synth_text(...)[0] and composed phrase == [1],
                         byte-equal (phrase compared with None/"" distinguished),
                         otherwise trace_mismatch. Any occurrence on the real
                         corpus → STOP.
                         pad_len = len(post_pad) − len(prep_text), only if post_pad
                         ends with prep_text; otherwise trace_unsupported.
                         Respell spans come from pronounce.build_pattern with
                         respell's single-pass iteration; reconstruction must
                         equal the actual respell output, otherwise trace_mismatch.
L4 alignment             tokens(row["text"]) vs concatenation of tokens(prep_text)
                         over the chunk's SUs: equal counts and pairwise equality
                         under fold(lower, ё→е) → aligned. Tokens before pad_len
                         never map to an occurrence.
L5 analysis string       6C11 section string with every token replaced by
                         form_analysis; source punctuation only (no terminal
                         edits, leadin, respell or sentinel).
L6 RUAccent              on L5, per sentence (existing T15 sentence function) →
                         F6. T15-7.0c reported that process_all() emits strings
                         containing '+' stress markers and may replace е with ё.
                         Match tokens by occurrence index, strictly validate
                         token count/order under fold(lower, ё→е), and never
                         propagate the returned spelling into the TTS input.
                         Runtime integration is gated by B1 independent QA.
                         Where RUAccent has not run, f6_status=not_run.
L7 precedence            §9.
L8 publish               §4; historical TSVs via the unchanged path.
L9 evaluation            §10.
Respell match → tokens: tokens of prep_text intersecting
[match.start − pad_len, match.end − pad_len). Whole tokens → F1 set (phrase if >1).
A partial token → f1_flag=span_ambiguous. A match entirely inside the pad is not
mapped and is counted per SU as override_in_pad.

══════════════════════════════════════════════════════════════
8. SNAPSHOT POLICY
══════════════════════════════════════════════════════════════
- T15-7 analyses only the existing disk snapshot (manifest_fp). No re-chunk, no
  manifest rewrite.
- Precondition for 7.2 and later: the disk snapshot passes the accepted 6C11 gates
  against the current normalized units (56/56), checked read-only in 7.0d.
  Failure → STOP for 7.2+ and escalate. This does not reopen 6C11.
- 5,127 vs 5,819 is diagnosed read-only in 7.0e and decided by the owner (B2).
- One generation = one manifest_fp; readers refuse a mix.
- After an owner-approved regeneration: source_key and gold remain valid where
  units are unchanged; occurrences are republished under the new manifest_fp.

══════════════════════════════════════════════════════════════
9. PRECEDENCE AND CASE MATRIX
══════════════════════════════════════════════════════════════
EXPECTED (inventory; gold never enters the inventory):
 T1 F5 ok and/or F2 approved with f2_vowel:
    exactly one present → it (source_mark | decision); both equal → source_mark;
    both differ → conflict, expected_vowel=null.
 T2 else F6 resolved → ruaccent, f6_vowel.
 T3 else → none, null.
In evaluation, gold is the truth for scoring. F1, F3 and F2 unknown/none never give
a position. SYNTHESIS: existing respell only.
U4 normative rule: "complete validated F1" means a whole-token respell span whose
boundaries are unambiguous after removing pad_len. A partial/ambiguous span cannot
qualify as covered_by_override, including when another portion of the same phrase
covers a whole token; the ambiguous affected token is unresolved. An F1 match fully
inside lead-in is informational only (override_in_pad) and maps to no WordOcc.
The status classifier MUST evaluate ambiguity before complete F1 coverage.

status / reason (the first matching row sets status; reason codes as listed):
 alignment_status ≠ aligned            unresolved / <alignment_status>
 f1_flag = span_ambiguous              unresolved / override_span_ambiguous
 complete validated F1 covers token    covered_by_override / ""   (F6 recorded only)
 expected_source = conflict            unresolved / conflict
 f6_status ∈ {no_stress, multi_stress, invalid_mark, tokenization_mismatch}
                                       unresolved / <f6_status>
 f6_status = not_run (T1 empty)        unresolved / ruaccent_not_run
 otherwise                             ok / ""
Info reasons appended (";"-separated) when status=ok:
 ruaccent_disagreement (F6 ≠ T1 value), verified_disagreement (F3 true and
 f6_vowel ≠ expected_vowel from T1, when T1 exists).
Errors (AnnotationError, rc≠0, nothing published): RUAccent init/runtime error;
U+0301 in any unit → SOURCE_MARK_UNSUPPORTED; link violation L-a/L-b/L-c; TAB/LF in
a value; trace_mismatch on the real corpus.

══════════════════════════════════════════════════════════════
10. QUALITY: SAMPLING, GOLD, METRICS, WILSON, GATES
══════════════════════════════════════════════════════════════
Universe: rows of read_occurrences() of the current generation.
Eligible: alignment_status = aligned and form_analysis has ≥2 vowels. One-vowel
rows are reported only as counts.
Strata (disjoint; assigned in this order; first match wins):
 omograph          form is a homograph per the existing T15 detector (cited in 7.0d)   n=100
 top300            fold(form_source) is among the 300 most frequent folded forms of
                   eligible rows (ties by form ascending)                               n=60
 name              existing T15 name rule                                               n=40
 override_covered  status = covered_by_override                                         n=40
 yo_changed        form_synth ≠ form_source and they differ only by ё/е                  n=40
 tail              every other eligible row                                             n=40
 N_s = eligible population of the stratum. If N_s < n_s, take all.
Selection: within a stratum sort by sha256(("t15-7/1|" + source_key).encode()) and
take the first n_s.
Sample record: out/stress/eval/sample/<sample_fp[:16]>.json
{sample_fp, source_fp, analysis_fp, strata:{name:{N,n}}, keys:[sorted source_keys]}.

Gold file text/stress_gold.tsv (local, ignored). Header:
 source_key form_source unit_text_sha256 unit_kind context_sha256 context gold_vowel
 yo_correct labeler date
 context: ≤80 characters around the token, local only.
 gold_vowel grammar: ^\d+$ | ^variants:\d+(\|\d+)+$ | ^yo$ | ^ambiguous$ |
 ^unknown_name$. Indexes must be < the vowel count of form_source. "yo" is allowed
 only if form_source contains exactly one "ё" (or form_synth does, for yo_changed).
U5 normative grammar: "yo_unstressed" was INTENTIONALLY REMOVED, and MUST be
rejected as an unknown label. If ё is not the stressed vowel, gold_vowel is the
0-based index of the vowel that IS stressed (or variants:i|j when both are accepted).
If that cannot be established, use ambiguous or unknown_name as applicable.
The independent yo_correct field records whether the orthographic ё-restoration is
correct; it does not encode stress placement. No implicit label conversion.
 yo_correct ∈ {y, n, na}; y or n is required when the row has the yo_changed
 property.
 date = YYYY-MM-DD.
 accepted(g): index i → {i}; variants → set; yo → {index of ё}; ambiguous and
 unknown_name → not usable.
Todo file text/stress_gold.todo.tsv: same header, rows for selected keys without a
valid gold row, gold fields empty.

C3 GOLD LEDGER / STALE REPLACEMENT / MERGE (normative):
  Authoritative file: text/stress_gold.tsv (S4, ignored by Git). It is a VERSION
  LEDGER, not a unique-source_key mapping: it retains old versions of annotations
  when source/context identity changes. Header is exactly the gold header above;
  no new columns are required. Historical versions remain in this same file.
  Read-only local archival export: text/stress_gold.archive.tsv (S4, ignored),
  derived deterministically from the authoritative ledger's currently stale rows.
  The archive is NON-AUTHORITATIVE, so a stale/missing export can be safely rebuilt.
  Never use the export as input to scorer or merge.

  Validity for each ledger row: recompute §5's five-part row identity against the
  CURRENT source and the source_key's unit/token. No global source_fp match is
  required for an otherwise unchanged occurrence. Rows with invalid identity are
  STALE, retained but excluded from active selection. For each selected source_key:
    0 currently valid rows -> todo requests relabeling; score INCOMPLETE (rc=2).
    1 currently valid row  -> ACTIVE and used for scoring.
    >1 identical currently valid rows -> logically collapse to one active label;
       report duplicate count; future merges do not append duplicates.
    >1 differing currently valid label pairs (gold_vowel, yo_correct) -> ERROR;
       do not choose the latest date or overwrite a valid human decision.
  Non-selected stale rows remain in history; stale rows are never scored.

  stress-eval merge(input_todo):
    M1 Validate sample record and sample_fp, present source identity, gold grammar,
       source_key, form_source, contextual SHA, date and labeler. Reject stale
       incoming labels and unexpected keys BEFORE writing. No automatic relabeling.
    M2 Compare incoming row against currently valid ledger rows with the SAME key:
       identical semantic label -> SKIP (idempotent no-op); differing semantic
       label -> ERROR (active conflict); absent active row -> append new version.
       Historical STALE versions never block a new valid annotation for that key.
       A source_key is not reassigned when only context or chunking changes.
    M3 Canonicalize and sort all ledger records deterministically; preserve historical
       versions; write a SAME-DIRECTORY ignored temp (e.g. text/stress_gold.txn-N.tsv)
       as complete replacement, flush+fsync, then os.replace to gold.tsv and fsync
       the directory. Before rename: old ledger intact. After rename: new ledger
       complete. Never modify in-place or perform a two-file transactional update.
    M4 Rebuild text/stress_gold.archive.tsv from currently stale ledger rows using
       its own ignored temp + atomic replace. The ledger is always authoritative;
       a crash after M3 and before M4 leaves valid gold intact. On the next merge
       or explicit local archive repair, the export is rebuilt. Scoring reads only
       the authoritative ledger and never rewrites either gold or its archive.
       Old versions are never deleted.
       An interrupted temp is never treated as active data. Repeat merge of the
       same incoming records yields identical gold.tsv bytes and active selection.
    M5 Both authoritative ledger and derived export are subject to S4 ignore/index
       guards BEFORE any write. No source text or labels enter Git or reports.

  MANDATORY synthetic oracle:
    initial valid gold -> change neighbouring unit context -> old row becomes
    stale -> todo includes same source_key -> merge accepts new valid label ->
    original row remains in ledger and is present in archived export -> scorer
    uses ONLY new current label. Repeating merge is byte-idempotent; injected
    crash before/after os.replace preserves one complete authoritative ledger.
    Two different current labels for the same key always yield ERROR, with no
    partial write. Reverting source to an older identity is checked strictly:
    if multiple conflicting rows become current, scorer refuses; no guess.

Sets over the sample S (selected keys with a valid, unambiguous ACTIVE gold row):
 E eligible; U usable gold; R f6_status = resolved; C f6_vowel ∈ accepted(gold);
 O stratum = omograph; Y has the yo_changed property and yo_correct ∈ {y,n}.
Metrics, per stratum s (and overall over S):
 coverage_s              = |E∩R| / |E|
 unresolved_rate_s       = 1 − coverage_s
 accuracy_resolved_s     = |E∩R∩U∩C| / |E∩R∩U|
 suggestion_precision    = |E∩R∩U∩C∩O| / |E∩R∩U∩O|
 false_suggestion_rate   = 1 − suggestion_precision (Wilson bounds mirrored)
 yo_precision            = |Y ∩ {yo_correct=y}| / |Y|
 override_disagreement   = among E∩{covered_by_override}∩R∩U: |¬C| / count (info)
 Book estimate (report only) = Σ_s (N_s/N)·rate_s over strata where rate_s is defined.
Every rate is reported as k, n, rate and Wilson [lower, upper].

Wilson 95%: z = 1.959963984540054; p = k/n; d = 1 + z²/n;
 center = (p + z²/(2n))/d; half = z·sqrt(p(1−p)/n + z²/(4n²))/d;
 lower = max(0, center − half); upper = min(1, center + half).
 n = 0 → undefined. Comparisons use unrounded floats; reports round to 4 decimals.
 Reference values: 40/40 → lower 0.9124; 92/100 → 0.8500 (0.850019 ≥ 0.85);
 91/100 → 0.8377; 73/73 → 0.9500.
Gates:
 G-hint (suggestion_precision): PASS iff n ≥ 80 and lower ≥ 0.85;
   FAIL iff n ≥ 1 and upper < 0.85; otherwise INCONCLUSIVE.
   INCONCLUSIVE counts as FAIL for usage.
   PASS allows only ordering T16 batches by RUAccent. Never shown to the listener,
   never applied.
 YO: YO_WARN iff count(yo_correct=n) ≥ 1 or (|Y| ≥ 1 and upper < 0.95);
   otherwise YO_NO_EVIDENCE. No quality claim; owner report only; yo_restore is
   never changed automatically.
Score result: COMPLETE (rc 0); INCOMPLETE (rc 2: a selected key has no valid gold);
ERROR (rc ≠ 0: sample record mismatch with the recomputed selection, malformed
Gold ledger rows, conflicting currently valid labels, fingerprint mismatch).
Distinct STALE versions of a source_key are NOT duplicate-row errors. Exact duplicate
current labels are deterministically coalesced and counted (never double-scored).
Output: out/stress/eval/score/<sample_fp[:16]>.json, written tmp + rename:
{source_fp, analysis_fp, sample_fp, gold_sha256, counts, metrics, wilson, gates,
status}. Contains no book text.
Text-level metrics never stand in for listening (T16/T17).

══════════════════════════════════════════════════════════════
11. CACHE, PRIVACY, STORAGE, DEFAULT-OFF
══════════════════════════════════════════════════════════════
C2-a NO REGRESSION (per task, same snapshot), compared with the baseline fixture:
  identical SU set; per SU: final_sha256 = sha256(final_synth_text.encode("utf-8")),
  phrase_sha256 = null if phrase is None else sha256(phrase.encode("utf-8")) (""
  yields e3b0c442…b855, distinct from null); stored chunk hashes; values of
  MANIFEST_FP_FIELDS; ensure_manifest_current result; impact value == baseline
  impact value.
  SU record: {"section","chunk_id","fragment":int|null,"final_sha256",
  "phrase_sha256":str|null}.
C2-b SNAPSHOT READINESS (informational, 7.0e): disk vs rebuild counts per section,
  config source per section, baseline impact value. Absolute impact=0 is not
  claimed.
I3 synth, worker, voicecfg, pronounce and engine do not import the new modules (AST).
I4 config.yaml unchanged; nothing synthesis-affecting is added (default-off holds
  trivially).

STORAGE CLASSES
 S1 Synthetic fixtures (no corpus data):     tests/fixtures/t15_7/synthetic/   tracked in Git
 S2 Real-corpus fixtures (any per-SU,        out/t15_7/baseline/               ignored, local
    per-chunk, per-token or short-fragment
    hash; any corpus-derived value)
 S3 Corpus-derived working data              out/stress/** (inventory, eval)   ignored, local
 S4 Gold / todo / version history            text/stress_gold*.tsv             ignored, local
    Includes text/stress_gold.archive.tsv and same-directory ignored *.txn-*.tsv
Rules:
 P1 Before writing any S2–S4 file: `git check-ignore -q <path>` succeeds and
    `git ls-files --error-unmatch <path>` fails, otherwise rc≠0, nothing written.
 P2 Real-corpus fixtures are never committed. Each S2 fixture has an aggregate
    digest D = sha256 of the canonical fixture file. D, counts and statuses may
    appear in reports; per-item values may not.
 P3 Independent verification: Sol regenerates S2 locally at the baseline SHA with
    `--check` and compares D and counts. Restricted values are never published.
 P4 Privacy check (t15_7_privacy_check, run before EVERY commit and in acceptance):
    inspect `git status --porcelain`, `git ls-files`, `git diff --cached --name-only`,
    `git diff --cached`, `git diff <base>..HEAD`, and all newly tracked files under
    tests/. Reject any tracked/staged S2–S4 path (including temp/archive/export),
    any exact per-SU/per-chunk/per-token corpus-derived hash, or any verbatim
    corpus passage/real-corpus fixture introduced by this task. For new synthetic
    test data, verify it was generated from explicitly synthetic source strings.
    Do NOT fail merely because an ordinary Russian word coincides with a token in
    the book: token vocabulary overlap alone is not evidence of disclosure.
    A privacy scanner should compare provenance and exact restricted signatures,
    and report only counts/flags; never emit the matched source text or digest.
    Existing tracked normalized source files are not retroactively reclassified
    as task-induced leaks; changes to them remain prohibited by this task.
 P5 Agent reports: aggregates, verification statuses, error classes, D values. No
    book text, codepoints or short-fragment hashes.
 P6 Offline; no synthesis.

══════════════════════════════════════════════════════════════
12. IMPLEMENTATION TASKS
══════════════════════════════════════════════════════════════
Every implementation task: test arithmetic «base N + added M (+ modified K) =
total», exact pytest command and result on the SHA, P4 privacy check, C2-a where
code changes, Sol review at a pinned SHA before the next task.

T15-7.0b  Class: WRITE (repo), needs explicit authorization + Sol review
  Deps: none. Files: .gitignore.
  Deliverable: rules for text/stress_gold*.tsv and out/t15_7/ (if out/ is not
    already ignored, also out/).
  Acceptance: check-ignore succeeds for text/stress_gold.tsv,
    text/stress_gold.todo.tsv, out/t15_7/baseline/x, out/stress/eval/x;
    ls-files shows none of them.
  STOP: an existing tracked file matches a new rule.
T15-7.0c  Class: REPO READ-ONLY; writes only in scratch outside the repo;
  no network. Deps: none. Recon has REPORTED 3 completed synthetic offline probes:
  local process_all() returned '+'-marked strings and one probe transformed е→ё.
  Deliverable/QA: pinned local weights/config identity, raw probe artifacts kept
  offline, token-order and repeatability checks, non-sensitive PASS/FAIL report.
  STOP: an independent replay does not reproduce the interface or requires network.
  This is interface evidence, not human stress-quality gold.
T15-7.0d  Class: REPO READ-ONLY; in-memory runs only, no publish, no manifest write;
  scratch outside the repo.
  Deps: none. Deliverable (citations file:function:line + counts):
    manifest keys read by analysis and the SU chain; config paths read; step
    functions of prepare_synth_text; unit_id type and stability; existing homograph
    and name detectors; consumer tolerance of new summary keys; U+0301 recount on
    target units; 6C11 gates on the disk snapshot (56/56); publisher leftovers
    present locally.
  STOP: SU chain not composable without copying logic; 6C11 gates fail; any used
    function writes to the repo or out/.
T15-7.0e  Class: REPO READ-ONLY; in-memory rebuild only.
  Deps: none. Deliverable: snapshot readiness report (C2-b), counts only.
  STOP: the rebuild path writes manifests → stop without running.
T15-7.1a  Class: WRITE. Deps: 7.0b, 7.0d, coordinator approval of this ADR.
  Files: tests/helpers/t15_7_fixture.py, tests/fixtures/t15_7/synthetic/*,
    out/t15_7/baseline/* (local).
  Deliverable: S2 C2-a fixture at baseline (SU records, chunk hashes, analytic
    manifest fields, ensure_manifest_current result, baseline impact) with digest D;
    S1 synthetic enum_pause_ms>0 fixture; --check mode.
  Acceptance: --check at baseline reproduces D; P1, P4.
  STOP: not reproducible.
T15-7.1b  Class: WRITE (local only). Deps: 7.1a, B1 closed.
  Files: out/t15_7/baseline/tsv/*.
  Deliverable: v4 historical TSV sha baseline on current inputs (local), digest D_tsv.
  Note: until B1 closes, the historical byte-identity gate stays BLOCKED; never
    substitute the published v3.
T15-7.2  Class: WRITE. Deps: 7.1a.
  Files: src/audiobook/sutrace.py, tests/test_sutrace.py.
  Deliverable: SUTrace(section, chunk_id, fragment, prep_text, pad_len, matches,
    final_sha256, phrase_sha256, status); trace_section(); key-recording wrappers.
  Acceptance: byte equality for every SU (final and phrase, None vs ""); respell
    reconstruction; pad rule; enum synthetic; accessed keys ⊆ declared; C2-a; I3.
  STOP: trace_mismatch on the real corpus.
T15-7.3  Class: WRITE. Deps: 7.2.
  Files: src/audiobook/wordprov.py, src/audiobook/stress_fp.py, tests/test_wordprov.py.
  Deliverable: WordOcc fields 1–21; source_key; alignment; build_analysis_text;
    source_fp; manifest_fp; gold identity helper; U+0301 guard.
  Acceptance (C4): S1 literal oracle for L-a/L-b/L-c; round trip;
    source_fp stable under manifest-only changes; manifest_fp sensitive to every
    relevant analytic manifest-field mutation; status-only manifest changes do not
    affect source_fp or manifest_fp; neighbour-unit staleness; U+0301 synthetic;
    PYTHONHASHSEED 1/2/3. analysis_fp is NOT required at this stage.
  STOP: link violation on the real corpus.
T15-7.4  Class: WRITE. Deps: 7.3.
  Files: src/audiobook/stress_facts.py, tests/test_stress_facts.py.
  Deliverable: fields 22–35 with F6 = not_run; resolve_expected; status/reason per §9.
  Acceptance: one test per §9 row; F2 only unknown/none; AST shows no position
    derived from respell or pronounce data.
T15-7.5  Class: WRITE. Deps: 7.4, B1 closed (7.0c PASS).
  Files: src/audiobook/ruaccent_adv.py, src/audiobook/stress_fp.py, tests.
  Deliverable: F6 on the L5 string; ruaccent_content_identity; analysis_fp with
    CONFIG_FP_KEYS.
  Acceptance (C4): real probe + mocks for every f6_status (including е→ё
    normalization without injecting the spelling into TTS); no terminal edits in
    the analysis string; file content changes → analysis_fp changes while
    source_fp remains stable; changes to any MANIFEST_FP_FIELDS reflected in
    manifest_fp propagate into analysis_fp; status-only changes do not. These
    assertions become executable HERE because analysis_fp is implemented here.
  STOP: real output differs from the 7.0c report.
T15-7.6  Class: WRITE. Deps: 7.5, 7.1b, 7.0b.
  Files: src/audiobook/stress_inventory.py (publication/summary only),
    src/audiobook/stress_fp.py, CLAUDE.md (version note), tests.
  Deliverable: occurrences.tsv via the existing publisher; summary keys;
    read_occurrences(); INVENTORY_ALGO_VERSION = 5; consumer compat if 7.0d requires.
  Acceptance (C4): tampering (sha, bytes, rows, header) → refuse; any change in
    current relevant source_fp, manifest_fp, analysis_fp vs published generation
    → STALE and refuse; irrelevant audio/QC status change → unchanged validity;
    crash injection at steps 1–7 → reader never accepts an inconsistent state;
    historical TSV digest == D_tsv; P1, P4. Preserve the existing publication and
    recovery contract; do not refactor the publisher.
  STOP: historical TSV bytes differ.
T15-7.7  Class: WRITE. Deps: 7.6, 7.0b.
  Files: src/audiobook/stress_eval.py, run.sh, tests/test_stress_eval_sample.py.
  Deliverable: `./run.sh stress-eval sample` (strata, selection, sample record,
    todo for selected keys WITHOUT an active valid gold label), and
    `./run.sh stress-eval merge` implementing the full C3 contract in §10.
    Allowed files also include tests/test_stress_eval_merge.py and the local S4
    gold ledger/derived archive, never tracked by Git.
  Acceptance: determinism under PYTHONHASHSEED 1/2/3; selection changes only per
    the §5 table; stratum assignment per §10; N_s < n_s takes all; grammar
    rejection; P1/P4 guards; exact stale→relabel→archive→active score synthetic
    oracle through active gold resolution (the scorer-level oracle is in 7.8);
    conflicting ACTIVE labels ERROR; repeated merge yields byte-identical
    authoritative ledger; crash-before/after-rename injection preserves a complete
    ledger and recoverable archive export.
  STOP: conflicting active labels or incomplete/unsafe local write.
T15-7.8  Class: WRITE. Deps: 7.7.
  Files: src/audiobook/stress_eval.py, tests/test_stress_eval_score.py.
  Deliverable: `./run.sh stress-eval score`: §10 sets, metrics, Wilson, gates,
    COMPLETE/INCOMPLETE/ERROR, score JSON.
  Acceptance: Wilson reference values (40/40, 92/100, 91/100, 73/73) to 1e-9;
    92/100 → PASS, 91/100 → INCONCLUSIVE, synthetic upper < 0.85 → FAIL;
    yo cases (one "n" → YO_WARN; all "y" with small n → YO_NO_EVIDENCE);
    stale gold versions ignored with counts, active row chosen only by the §10
    C3 validity rule, end-to-end stale→relabel→archive→score uses the NEW active
    gold row, same-key conflicting active labels ERROR, selected key without
    valid active label INCOMPLETE rc 2; sample record mismatch → ERROR; output
    contains no corpus tokens (P4).
T15-7.9  Class: REPO READ-ONLY; score/report outputs written only under ignored
  local out/stress/eval/, not to repository-tracked files. Deps: 7.8, H04.
  Deliverable: gate report to the architect: counts, rates, Wilson bounds, gates,
    D values. No text.
  Acceptance: report consistent with score JSON (Sol recomputes locally).
H04  Owner labels the todo (~320 rows) and runs merge. Deps: 7.7.

══════════════════════════════════════════════════════════════
13. INDEPENDENT QA (Sol, per task at a pinned SHA)
══════════════════════════════════════════════════════════════
- Regenerate S2 at baseline (--check), compare D and counts; C2-a identical after
  each task; impact == baseline value.
- Mutation tests for every fingerprint domain, including status-only invariance.
- Key-recording guard on the real corpus.
- S1 literal oracle for links and round trip; one test per §9 row.
- Reader rejects tampered, mixed and mid-switch states.
- Wilson and gate boundaries as §10.
- P4 privacy check result; no restricted values in any report.
- Determinism (PYTHONHASHSEED 1/2/3); exact pytest command and result.
- No audio-quality claims from tests.

══════════════════════════════════════════════════════════════
14. BLOCKERS AND OWNER DECISIONS
══════════════════════════════════════════════════════════════
B1 RUAccent runtime interface (R8): 3 synthetic offline probes are REPORTED PASS,
   including process_all() with '+' markers and one е→ё change. B1 gate closes only
   when coordinator/Sol verifies pinned local model/config and repeatability evidence
   without disclosure. No claim of production stress accuracy. Until then, B1
   holds 7.1b, 7.5 and dependent stages; after acceptance, those tasks may be
   authorized in dependency order.
B2 Snapshot authority (R2): does not block 7.0b–7.4. Blocks T16/T17 and render
   planning. Owner decision after 7.0e.
B3 No approval journal (R7): non-blocking; F2 = unknown. Owner O2.
B4 Publisher crash behaviour (R10): tested in 7.6; local leftovers in 7.0d.
O1 Who labels gold. O2 Approval journal. O3 Action on YO_WARN.

══════════════════════════════════════════════════════════════
15. RECOMMENDATION
══════════════════════════════════════════════════════════════
Independent final review of this SINGLE authoritative rev. 2. C3, C4 and U4–U6
are incorporated in §§5, 7, 9–14. No architecture redesign or additional ADR cycle.
After coordinator approval: 7.0b is WRITE and needs separate authorization; 7.0c
recon has REPORTED successful probes requiring independent evidence verification;
7.0d and 7.0e remain read-only. 7.1a follows 7.0b/7.0d and approval, with local
privacy fixtures. Remaining tasks obey their dependencies and B1/B2 gates.
No repository change, synthesis, manifest regeneration or rendering is authorized
by this document. STOP.