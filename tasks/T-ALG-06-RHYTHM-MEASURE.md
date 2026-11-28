# T-ALG-06 — measured rhythm and pace (research)

Goal: separate actual reading pace and intra-phrase boundary timing from
subjective overall voice quality. No automatic changes to text or audio.

## Existing mechanisms and gap
- pace.py compares median ms/character by chapter; it cannot identify
  rushed enumeration items or omitted internal pauses.
- rhythm_audit.py/rhythm_eval.py operate on text boundary candidates.
  ALG-03 comma/semicolon actuator did not pass heldout listening; do not
  repeat that intervention or assume all commas require pauses.
- stress_acoustic_calibration.word_windows binds complete ASR lexical
  sequence and monotonic timestamps. Reuse it instead of approximate
  substring matching.

## Implemented
rhythm_acoustic_measure.py (standalone, default production impact zero)
compares up to 64 existing same-text reference/candidate pairs using exact
manifest digest and chunk hash, verified WAV SHA256 and existing ASR word
timestamp evidence bound to each WAV. No models or inference. Reports
words/minute between first and last aligned word, orthographic syllable
rate proxy, rate over summed word spans, edge timing, every internal
word gap and original punctuation offset. Separates plain, comma, clause,
sentence and ambiguous boundaries. Protected commas never classified as
normal comma gaps. Low-energy fraction in ASR gaps: 10ms RMS windows,
relative -35dB below per-recording 95th-percentile RMS, purely descriptive
not VAD or verified pause length. Exact paired rates and gap deltas; no
universal optimum or automatic acceptance. Full lexical mismatch, uncertain
timestamps, unsupported text or short text abstain. Nine synthetic cases
cover exact measurements, abstention, audio evidence binding and relative
energy. No acoustic accuracy or naturalness claim from these tests.

## Local input / command
Frozen manifest JSONL existing done rows. Private plan JSON:
{policy:"rhythm-paired-measurement-v1",manifest_sha256:"...",pairs:[
{id:"...",hash:"...",reference_text_independently_verified:true,
 reference:{wav:"ref.wav",wav_sha256:"...",asr:{wav_sha256:"...",words:[{w:"...",s:0.1,e:0.3,p:0.95}]}},
 candidate:{wav:"candidate.wav",wav_sha256:"...",asr:{wav_sha256:"...",words:[...]}}}
]}
Reference must be existing authorized author recording of EXACT same text;
not arbitrary reference voice prompt. Operator verification flag is an
assertion, not independent proof. ASR timestamps are estimates; lexical
matching folds е/ё and cannot detect wrong stress or subtle word corruption.
Pairs with numbers, foreign tokens, hyphenated words etc can be unsupported.
No automatic alignment or extraction; inventory actual matched recordings
when local availability returns. No new synthesis or relistening required
for the initial descriptive analysis. If none available, BLOCKED, don't
invent reference. Use copied private audio under a separate root, mono WAVs
up to 60s each, no reused paths; output outside repo/canonical/audio-root.

`python -m audiobook.rhythm_acoustic_measure --manifest "$MANIFEST" --manifest-sha256 "$MANIFEST_SHA" --plan "$PLAN" --plan-sha256 "$PLAN_SHA" --audio-root "$PAIR_AUDIO" --out "$NEW_REPORT"`

Produces rhythm_PRIVATE.json with per-boundary values and summary.json
with aggregate coverage and median rate delta. Only aggregate summary may
leave local machines. Existing text/audio unchanged, no automatic edits.
The runner uses no models and is light CPU; real large inventory checks on
gamebox. No private audio or manuscript to cloud. CI synthetic fixtures only.

## Next
ALG-04B remains first local acoustic experiment; ALG-05 read-only stress
calibration when genuine controls available; ALG-06 read-only existing
matched audio inventory, then measure. Use actual independently annotated
author pauses and listener rhythm ratings for future validation; no tuned
thresholds or waveform repair before that. No full book render or main merge.
Latest CI pending. No agent dispatch while local machines unavailable.
