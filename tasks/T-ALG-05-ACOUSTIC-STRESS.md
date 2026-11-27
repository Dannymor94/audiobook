# T-ALG-05 — acoustic stress evidence (research)

Status: pure likelihood scorer implemented; real acoustic calibration not run.
Does not delay ALG-04B (Silero + OpenVoice) and cannot authorize rendering.
No manuscript/audio/reference sent to cloud. Existing production behavior and
legacy phoneme_check unchanged.

## Research and decision (2026-11-27)

- Prior local S5a showed lexical ambiguity (топлива / топливо) before stress
  evaluation. Existing stress_acoustic_calibration.py preserves occurrence
  identity and refuses ambiguous windows; reuse that contract, not first-hit
  word matching. Existing phoneme_check.py relies on greedy CTC labels, vowel
  reduction, and a duration/energy heuristic. Greedy CTC emission spans are
  not necessarily vowel duration; same fully articulated vowel quality is
  not proof of correct stress. No production trust.
- https://pmc.ncbi.nlm.nih.gov/articles/PMC5503100/ — Russian lexical stress
  uses vowel quality/reduction and duration, while pitch has a smaller role
  than phrase-level prominence. Do not equate higher F0 or energy with stress.
- https://huggingface.co/datasets/egnch/tiny-voca-ru-dataset/blob/641a71953589e7faceab6022b55f599e03578043/README.md
  — recent independent synthetic Qwen dataset uses competing stress CTC
  alignment (facebook/wav2vec2-lv-60-espeak-cv-ft); publisher reports about
  56% recall at <=1% false alarm. Those are their results, not ours.
  Their filtered/relabelled synthetic corpus is NOT independent gold for
  testing a related detector. Source code Apache-2.0 at
  https://github.com/yilbegan/tiny-voca-ru/tree/ce5da767253437bc7dba4c1bf1d6cfc11091b865
  (train/align.py has CTC Viterbi alignment and recognizer-specific mappings,
  frontend/g2p.py has contextual reductions). No upstream code copied or
  dependency installed; avoid assuming their mapping matches our XLSR vocab.
  Dataset CC-BY-4.0 declared; data/training provenance not independently cleared.
- https://huggingface.co/TeraSpace/TeraAnaly — audio stress head is promising
  in principle but CC-BY-NC-SA-4.0, not selected for a commercial pipeline.
  https://huggingface.co/TeraSpace/accentik — despite 'audio v3' name, inference
  predicts stress from text, not sound. Not an acoustic validator.
- https://huggingface.co/datasets/stilletto/ruslan-stressed — human recordings
  but LLM-added transcript stresses, not independently heard vowel gold.
  Can be a future source of rights-reviewed human-labeled controls, not
  automatically validated ground truth. No dataset downloads in this stage.

## Implemented

src/audiobook/stress_ctc_evidence.py: pure NumPy forward CTC marginal log
likelihood over all paths collapsing to each exact phone sequence. Compare
all reviewed stress ordinals on the same normalized frame posterior matrix;
require equal phone inventory length, identical nonvowel positions, supported
phone IDs, no collapsed duplicate hypotheses, adequate frames. If alternate
stress does not change recognized phones (e.g. some и/у/ы cases), abstain.
Do not invent IPA from the dictionary or move only a stress mark in a
recognizer without a stress token. Only rank hypotheses, not a probability
of correct stress. Absolute fit and runner-up margin per frame both must
pass explicit frozen development-calibrated thresholds. No defaults.
Uncertain errors count as missed; lexical-error controls tracked separately.
No release_ready true path. Eleven synthetic test cases include exhaustive
enumeration of all short CTC paths (including repeated labels), comparison,
abstention, malformed probabilities and control outcome counts.
No model import/load, no actual acoustic performance claim.

## Next bounded evaluation after local availability

1. Reuse existing verified WAVs; no new TTS for detector. Prefer existing
   independently listened controls with explicit heard stress and lexical
   integrity (not generic OK/BAD). Bind exact WAV SHA, chunk hash and word
   ordinal/span; lexical ambiguities remain separate. Use occurrence-bound
   word_windows/contextual_window from existing calibration, or independently
   verified phonetic windows. No arbitrary search for matching audio.
2. Use existing locally pinned XLSR recognizer
   facebook/wav2vec2-xlsr-53-espeak-cv-ft rev
   2c733782da5604684829819a5eb744c193fe9398 only after verify actual model
   files/vocab/config hashes and safe offline load; don't use current
   _snapshot() fallback. Extract actual full log_softmax posterior, no
   decoding or filtering. Explicit reviewed candidate phone sequences for
   each possible stress position, validated against this exact vocabulary.
   Never substitute unknown IDs or assume vowel identity from spelling.
   First pilot focuses on reduction-sensitive vowels, reports unsupported
   cases as uncertainty; no forced inference for same-phone alternatives.
3. Freeze development/heldout split by distinct lexical forms and speakers
   where available, before thresholds. No leakage across paired takes.
   Collect enough both correct and wrong controls; if existing labels
   insufficient, report sample limitation rather than request a full new
   owner review or infer negatives. Select conservative thresholds on dev
   only with declared grid and denominators, freeze before heldout, report
   counts including uncertainty, recall, false flags, lexical false flags
   and coverage. No claims of 100% accuracy. Any heldout gate for deployment
   needs predeclared representative sample and owner approval; current work
   only diagnostic. No production edits or automated audio repair.
4. Integration runner still to implement after actual control and
   recognizer identity established. No agent now, no audio inference in CI.
   Existing ALG-04B experiment remains first priority when power returns.
