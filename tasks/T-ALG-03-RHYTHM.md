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
