# ALG-02 decision / ALG-03 next gate

## ALG-02 CLOSED — no production promotion

Owner review page ee7dc086b0651375; operator reports exact WAV/plan/receipt/key
identity verification. 8 pairs: candidate 1 win, 3 equal, 4 losses by ordinal
overall labels. Development 1/1/2; heldout 0/2/2. Baseline 3 OK / 2 UNSURE /
3 BAD; uppercase 1 OK / 2 UNSURE / 5 BAD. Tests reported 745 passed, 5 skipped.
No new TTS or production changes. No claim of word-level stress accuracy:
target-specific paired judgments are incomplete. Earlier isolated success
does not establish generalization. Close uppercase pilot, preserve its code
and evidence as research only. No more register, doubling or seed-only tuning.
Do not deploy any candidate merely because it won an overall comparison.

## ALG-03 — rhythm design, independent of stress

Code audit: chunker.enum_splits already recognizes depth-zero short enumeration
segments (20 character limit, subordinate/byline guards). chunker includes
enum_pause_ms in hashes of applicable chunks. voice_plan.source_anchors already
tracks exact source ordinal, offsets and boundary types. Assembly pause knobs
alone cannot correct timing inside spoken chunks. Reuse existing mechanisms
before creating another segmentation system.

First dry-run: measure current enum coverage on the frozen CH1 manifests
and the owner-marked rhythm failures; verify actual config and worker execution
path. Classify missed genuine lists, false-positive boundaries, protected spans
(quoted phrases, hyphenated words, preposition/clitic groups, numbers), and
whether existing splitting can harm voice continuity. Use exact source offsets;
never cut a word or introduce lexical changes. No guessing by text substring.
Compare existing rule with a conservative boundary planner using synthetic
positive/negative fixtures and private exact local examples. Default OFF;
preserve current hashes/audio and lock semantics. Do not change chunk identity
or global pause settings before impact is measured.

Gate: one focused controlled A/B only after the runtime GAMEBOX_REQUIRED guard
and owner-approved execution scope. Fixed model/reference/seed; isolate rhythm
from stress control. Evaluate naturalness, lexical integrity, stress and voice
independently; use local HTML with verified WAV lineage. No new render until
these prerequisites. Do not manually patch individual WAVs or replace narration
with original author recordings.

## ALG-04 — stress control architecture

Compare truly explicit phoneme/stress-conditioned alternatives rather than
more text casing tricks. Research public model capabilities, licenses including
training-data rights, offline CPU feasibility, voice cloning and verified
Russian stress control. Existing CF rights block is unchanged. No downloads or
inference until a candidate is justified and authorized. No claim of automatic
acoustic stress verification by dictionaries or Whisper.

Chapter 2 / FULL_RENDER remain NO_GO. GAMEBOX-FIRST enforcement is a mandatory
runtime prerequisite, not only documentation. No production promotion or merge.


## Implementation checkpoint

- `gamebox.py`: require Linux and the actual OS hostname danny-serv; no env bypass.
  Enforced at normal worker spawn/child entry, model loading (including cache
  hits), voice prompt computation, direct synthesize, and isolated stock pilot.
  Mock-only tests have explicit scoped patches; real tests do not.
  This is accidental-host prevention, not hardware attestation; custom external
  Qwen scripts outside the repository cannot be prevented by this Python guard.
  RAM/disk/queue lock preflight remains mandatory separately; do not treat host
  check alone as authorization to render. Audit other direct external adapter
  scripts before any future execution.
- `rhythm_audit.py`: read-only manifest JSONL audit, exact comma offsets from
  sequential consumption, legacy rule coverage, nested and numeric comma
  conflicts, conservative colon-led list candidates. Candidate boundaries are
  advisory, not verified syntax. Existing quote depth covers «», (), [];
  broader quote handling and clitic groups need further work. No synthesis,
  config, cache or text modification. Command on a private local machine:
  `uv run --no-sync python -m audiobook.rhythm_audit /path/to/manifest.jsonl`.
- Code finding: with enum_pause_ms > 0, chunk_fragments splits multiple
  sentences even if no enumeration is found; build_manifest hashes the enum
  option only when an enumeration is found. This risks stale cache identity.
  Checked repository config enum_pause_ms=0, not private runtime config.
  Do not enable enum_pause_ms or modify legacy caches. Before any rhythm pilot,
  resolve this mismatch and explicitly bind candidate input, segmentation,
  pause and seed to identity. Existing question-tail removal and short
  independent fragments also need evaluation.
- New synthetic tests added. Final commit CI not yet confirmed at checkpoint.
  No private manifest audit performed by lead because the file remains local.

## Follow-up

CI run 45781915089: 757 passed, 3 failed, 3 deselected. Two failures were legacy stub/missing-model tests requiring narrowly scoped guard mocks; one was the read-only audit test assuming the fixture did not create fake_home. Fixed all three fixtures without weakening the runtime guard. Existing worker_config already rejects nonzero enum_pause_ms; extend the same rejection to direct _synth_one_chunk before any engine call. No new legacy hash format or migration; unsafe old split remains disabled. New rhythm pilot will not use this path. Exact HEAD CI must be green before local checkout.

Local dry-run only: on Mac use the frozen CH1 manifest (actual audit manifest SHA256 prefix db6ec668, operator verified eight reviewed chunk hashes; previous 12fee108… reference was MP3 digest, not manifest; use full local digest, never infer from prefix). Run rhythm_audit once, keep rows and manuscript private. Report aggregate chunk counts, number of legacy/protected conflicts and unhashed risks, and for reviewed IDs 0042/0087/0019/0225/0043/0080/0045/0062 whether each has valid candidate comma offsets; manually classify missed boundaries locally by syntax, not audio editing. Confirm historical enum_pause_ms=0 and unchanged manifest/audio. No model calls or synthesis. Use report to select next conservative single-stream punctuation/prosody pilot; no automatic promotion.


## CH1 dry-run received / syntax planner checkpoint

Operator report: exact prior HEAD 65be3c854e865446b75a4b8b39eeca66d6820435
CI green (run 45783071959 verified by lead). Local report: 238 chunks;
legacy 50 chunks/81 offsets; conservative planner 3/9; protected legacy
conflicts 0; unhashed multi-sentence risk 62; enum_pause_ms=0. None of eight
reviewed chunks have automatic candidates. Manual syntax review found 13
comma offsets across five chunks, three inside protected quotation (excluded
from automatic candidates); two legacy false-positive constructions in
0019 and 0225. 45/45 control files unchanged; 759 passed/5 skipped reported.
Exact manuscript and offsets remain private. No render authorization.

New rhythm_syntax.py: parser-independent UD coordination boundary proposals
using ordered exact token spans, full source coverage, rooted acyclic tree,
contiguous nominal/adjectival/adverbial component spans and exact comma gaps.
Conservative quote/bracket/decimal guards. No punctuation changes, no waveform
edits, no cache writes. Six synthetic tests. This is a candidate generator
only; no parser adapter or real CH1 evaluation yet. Recall and precision
are unmeasured. Do not treat tree evidence as acoustic pause proof.

Parser research: Natasha/Slovnet is compact and CPU-oriented, trained for news;
test on book style, pin library/model/embedding versions and weights hashes,
verify model and training-data terms before deployment.
https://github.com/natasha/slovnet
https://github.com/natasha/natasha
Stanza has a UD dependency API but Russian SynTagRus corpus is CC BY-NC-SA 4.0;
do not infer commercial clearance from model repository Apache-2.0 alone.
https://stanfordnlp.github.io/stanza/depparse.html
https://universaldependencies.org/treebanks/ru_syntagrus/index.html
No downloads/install yet. Select a parser only after provenance review.
Next: private exact-span adapter dry-run and evaluate against owner-reviewed
development boundaries plus heldout (protected quote offsets excluded);
measure false positives/misses before selecting an isolated single-stream
prosody experiment. Do not fit exclusively to these eight chunks.
No TTS or gamebox required for current checkpoint. B BLOCKED, CH2/FULL_RENDER NO_GO.

## Local parser adapter checkpoint

Selected spaCy ru_core_news_sm as the first adapter target (not a production
model decision): integrated POS and dependency heads with character offsets,
CPU pipeline, public model metadata MIT. Public Natasha spaCy proposal names
Nerus and Navec as MIT resources, but Nerus consists of Lenta.ru articles;
underlying content/weight rights are not independently cleared. Verify the
exact release metadata and source terms before commercial deployment. Sources:
https://spacy.io/models/ru
https://github.com/natasha/natasha-spacy
https://github.com/natasha/nerus
https://github.com/natasha/navec

Added rhythm_spacy.py, four synthetic adapter tests. No new project dependency,
model download, production configuration change, or TTS. CLI accepts only
explicit local model directory, SHA-256 tree digest, exact spaCy/model versions;
CPU, no NER/lemmatizer, exact token and sentence coverage, unresolved rows
reported rather than guessed. Keep full private results local. For a later
approved research-only parser trial, install the pinned parser in a separate
Python environment, independently verify package/model provenance and digest,
then run the module with frozen manifest and those exact pins. No automatic
synthesis. Compare actual candidate offsets against local development and
heldout annotations, explicitly account for unknown/missing gold; no blanket
accuracy claim. No further local operator task until exact HEAD CI is green
and provenance is settled. Parser integration tests with actual weights not
run by lead. No production promotion.

## Evaluation gate and single local research handoff

Public source review: spaCy model repository declares MIT and its
LICENSES_SOURCES names Nerus with MIT; Nerus itself acknowledges ~700K
Lenta.ru articles. https://huggingface.co/spacy/ru_core_news_sm/blob/main/LICENSES_SOURCES
https://github.com/natasha/nerus . These are declared permissions, not a legal
review of all underlying third-party articles. Research-only parser evaluation
may proceed under this scope; commercial production adoption remains unapproved.
Use official pinned ru_core_news_sm 3.8.0 and compatible spaCy 3.8.x (pin exact
installed release and dependency lock); confirm release metadata and license
from the actual downloaded wheel, record wheel SHA256 and local model tree
SHA256, no rolling main URL. If exact release identity cannot be verified, stop.

Added rhythm_eval.py plus three tests. CLI reads frozen manifest JSONL,
private predictions JSON from rhythm_spacy and private gold JSON of shape
{manifest_sha256, rows:[{id,hash,split,positive:[comma offsets],negative:[comma offsets]}]}.
Validate full manifest and chunk identities. Count TP/FP/FN separately for
development and heldout, preserve unknown predictions, count unresolved known
positives as misses, count protected proposals across all rows. No claim of
precision on unlabeled proposals. No model or text change.

Single local Mac task after exact PR HEAD CI success: use separate research
venv with pinned dependencies and local weights, no TTS project dependency
changes. Verify full frozen CH1 manifest SHA and 238 chunk inventory. Before
running parser, freeze independent annotations on existing reviewed chunks
plus an additional small preselected heldout set (at least 8 distinct chunks
including lists and negatives, chosen without inspecting parser predictions;
existing 8 all development because already examined). Mark only confidently
judged positive/negative comma offsets; protected quotes are excluded from
positive scope. Run rhythm_spacy once, then rhythm_eval. Report aggregate
metrics, unlabeled/unresolved counts, protected violations, per-split sample
sizes, known positives found/missed, exact model/version/digest evidence and
unchanged original files. Keep text, offsets, annotations and reports private;
public report aggregate only. No synthesis, no production change. If parser
produces no relevant candidates or protected violations, do not tune blindly.
Acceptance for a subsequent isolated acoustic experiment: zero protected
proposals, at least one confirmed positive in heldout, no known false positive
among heldout proposed boundaries, report all unknowns; each selected pilot
boundary still manually validated locally. These are small-pilot selection
criteria, not production quality thresholds. No automatic promotion.

## Syntax evaluation decision — FAIL for acoustic gate

Operator report at HEAD 679021b7bf00898d27aff0b40d9f4aa0176b2d1f: verified GitHub CI success run 45790983523; spaCy 3.8.7 / ru_core_news_sm 3.8.0; 238/238 parsed, 34 proposals in 18 chunks, 32 outside annotated chunks, 0 protected proposals. Development TP2 FP0 FN8; heldout TP0 FP0 FN7. Gold is preliminary operator syntax annotation, not independent human verification. No globally measured precision; 100% dev precision on two proposals is weak. 159/159 controls unchanged (operator report), tests 772 passed/5 skipped reported. Syntax acoustic gate FAIL. No parser adoption, no blind rule tuning. Existing automatic planner remains OFF.

Separate actuator feasibility from boundary detection: before investing in another parser, establish whether stock Qwen can obey a single safe stronger punctuation mark in a continuous input. Added rhythm_actuator.py dry-run only: requires exact annotated positive comma with matching chunk hash/split, excludes protected, locked, numeric and terminal boundaries; same carrier, seed, dictionary, sentinel and open_end; both arms use normal preparation, only one comma-to-semicolon difference permitted, exact comma ordinal checked, input SHA256 recorded. Semicolon is a hypothesis, not a proven pause instruction. Never mutate manuscript, production hashes or audio. Synthetic tests added; no acoustic execution implementation yet.

Next acoustic feasibility pilot (distinct from failed parser gate, requires explicit scope approval and CI): use at most four pairs, two development and two fresh heldout, with independently validated linguistic boundaries (not parser predictions), one internal comma each. Freeze before inference. Same actual generation identity and seed/carrier, one worker on verified gamebox, existing canonical heavy lock, resource/disk checks, private new output, no production write. Render one continuous string per arm, no fragment joins or waveform pause insertion. Compare rhythm at the exact boundary, lexical integrity, target and other stress, voice, overall acceptability. Offline HTML paired review with exact receipt identities. Gate: heldout improvement at least one, no heldout regression, no new lexical/stress/voice defects among any accepted candidates. No acoustic claim until evidence. If fail, retire punctuation actuator; prioritize model capability research instead of more parser iterations. Successful actuator alone does not authorize automatic boundary selection or production deployment. Keep source annotations and audio local. No new TTS now; B BLOCKED, CH2/FULL_RENDER NO_GO.


## Owner GO — bounded actuator feasibility only

Prior actuator planner HEAD 19ba39b02510865ab56cf5de77ba6c850ecdd7a3 CI
success, run 45811164080 verified. Owner approved four-pair scope, not any
production render. Added rhythm_pilot.py, exact four distinct targets with
two development/two heldout, independently reviewed positive boundaries,
pinned full manifest/gold/targets and dry-run plan SHA256, same historical
config, one continuous input per arm, fixed seed/carrier, one CPU worker,
no retries, gamebox OS host check, 15 GiB available RAM, 2 GiB free persistent
local filesystem, canonical heavy lock and idle queue. New private output
outside project/production roots, per-arm WAV receipt, final READY only
after all eight succeed and identity recheck. Uses existing generation_identity
(snapshot name and reference/latents digests, not full hardware attestation
or model-weight byte verification); operator must verify pinned model snapshot
and actual runtime identity independently. Tests added; no real TTS tested by lead.

After exact latest PR #47 HEAD CI green, local operator:
1. Freeze four reviewed comma boundaries (two prior development chunks, two
   fresh heldout not in prior reviewed/gold sets); independently review syntax
   without exposing candidate audio, do not invent independent review.
   Use gold schema from rhythm_eval with independently_reviewed=true only
   for actually independently verified rows; targets JSON list of
   {chunk_id,offset}. Retain full source and annotations privately.
2. On gamebox danny-serv, use isolated historical CH1 workspace and actual
   canonical out. Verify full manifest digest, both copies byte identical,
   all current hashes, production controls, model/reference/latents, free RAM,
   persistent local path, no active tasks. No Mac TTS. 
3. Run `uv run --no-sync python -m audiobook.rhythm_pilot --gold "$GOLD" --gold-sha256 "$GOLD_SHA" --targets "$TARGETS" --targets-sha256 "$TARGETS_SHA" --manifest-sha256 "$MANIFEST_SHA" --canonical-out "$CANONICAL_OUT" --out "$NEW_DRY_RUN"`.
   Dry-run produces only private plan. Verify all four exactly one punctuation
   edit, same baseline/candidate seed and carrier. Do not substitute targets
   after observing audio. If any preflight fails, BLOCKED.
4. Same args with a different new private output directory, add
   `--execute --plan-sha256 "$DRY_PLAN_SHA"`. Detached persistent log with
   verified PID/start/exit; report actual STARTED_AT, ETA based on prior measured
   RTF and input lengths, FINISHED_AT and DURATION. Never run retries or a
   second experiment without approval. On failure retain all artifacts.
5. Only if READY and all eight receipts verified, privately copy run to Mac,
   generate `uv run --no-sync python -m audiobook.stress_pilot_review --source "$COPIED_RUN" --out "$NEW_REVIEW" --private-key "$SEPARATE_KEY" --expected-pairs 4 --policy single-stream-comma-semicolon-v1`.
   Verify offline playback, correct UTF-8, four pairs, eight WAVs, autosave,
   JSON export, no unblind. Return exact local review.html and WAV paths.
   Prompt owner to rate boundary pause/continuity, stress, words, voice and
   overall separately in comments; no new UI. Do not upload audio/text.
6. No production changes or chapter 2/full render. Report aggregate technical
   evidence only, retain private receipts and gold. If independent boundaries,
   CI, runtime or plan parity unavailable, stop rather than approximate.

## Freshness reconciliation — pilot scope only

Operator report: independent second-agent review agrees on all 14 comma labels, not human validation; frozen four targets and gold exist privately. SSH to Linux danny-serv restored and preflight passed. Prior exact HEAD 83daaa7 CI success run 45812019733, 781 passed/5 skipped reported; 300/300 production controls unchanged. Dry run stopped at section freshness (six differing chunk identities); no audio or plan. The exact six IDs and reasons are not available to lead. Production guard remains unchanged.

For this isolated four-pair pilot only, verify full ordered source ID/ordinal/text inventory against a fresh in-memory build using the same table snapshot. Require all four selected rows to match fresh hash, leadin, open_end and cont exactly. Non-target differences in those fields are recorded in the frozen private plan, never overwritten or rendered. Keep canonical/isolated manifest byte equality, frozen gold/targets hashes, independent review and existing runtime guards. Rebuild and recheck config, table, source inventory and trials after execution. Any selected drift or global source inventory mismatch remains BLOCKED: restore exact historical inputs in isolated workspace only, prove parity, or report blocker; do not change targets or production files. This is safe because no production cache writes are made by the pilot. Full chapter rendering still requires original strict whole-section freshness. No bypass flag. After exact new HEAD CI green, resume same frozen four targets, dry-run once then execute only if selected parity succeeds. Report six mismatch IDs/fields and whether selected intersection is empty (no manuscript content), actual timing and eight WAV/HTML review on success. No new annotation cycle, no retries, no new TTS scope. B BLOCKED; CH2/FULL_RENDER NO_GO.

## Final close — NO PROMOTION

Operator verified page c883d1fbe7b0beaf, all 8 owner labels, blind key, frozen
plan, READY and WAV receipts. Candidate overall wins/ties/losses 2/1/1;
development 1/1/0, heldout 1/0/1. Baseline 0 OK/2 unsure/2 bad; candidate
2 OK/0 unsure/2 bad. Explicit stress complaints baseline/candidate 2/1 dev,
0/1 heldout, 2/2 total; these are complaints, not accuracy denominators.
Owner generally prefers B voice, but B includes both conditions; one heldout
baseline had explicit voice instability. No direct rhythm ratings in either
split. Acoustic rhythm gate NOT DEMONSTRATED. Candidate heldout loss also
violates no-regression criterion. Close actuator and syntax planner as research
only; do not promote punctuation changes. No repeated listening or tuning.
Operator-reported run 17:04:09–17:18:22 UTC, 14m12.4s; 300/300 production
controls unchanged; 787 passed/5 skipped locally. Exact prior HEAD 842b5f54
CI success independently confirmed by lead. Private files not directly
accessible to lead; do not label audio independently verified by lead.
Next ALG-04 capability research, no new TTS authorized. Preserve all artifacts
and stress map. B remains BLOCKED; CH2/FULL_RENDER NO_GO.
