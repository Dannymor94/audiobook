# S5a — calibration of existing acoustic heuristic (read-only)

This is a bounded diagnostic, not a new stress detector or production QC.
Use current local Chapter 1 manifest and preserved consolidated ch1 audit.
Do not download weights or render audio for this task. If Whisper/phoneme
weights are absent, report BLOCKED. Run offline on exact private v2 chunk WAVs.

Prepare a private JSON array of controls from already human-labeled evidence.
Each object has id, hash, ordinal (1-based Cyrillic word ordinal), start,
end (source codepoint span), word, gold (wrong_stress/correct/lexical_error),
expected_index (zero-based stressed vowel character index; null for lexical
error), and wav_sha256 (full digest of the exact known audio). Use exact
owner-reviewed sample identity, pack/index and assembly lineage; no guessing
from chunk-level labels or deriving gold from predictor agreement. Include all
five owner-known controls where exact word and WAV identity can be established.
Include independently already accepted occurrence-level clean controls if
available; do not treat every word of an accepted chunk as labeled. Report
unmapped or unknown controls separately. No new owner listening.

Run:
`uv run --no-sync python -m audiobook.stress_acoustic_calibration --manifest "$MANIFEST" --audit-dir "$CH1_AUDIT" --chunks-dir "$V2_CHUNKS" --controls "$PRIVATE_CONTROLS_JSON" --out "$NEW_PRIVATE_OUT"`

Record local model snapshot digests, exact prepared TTS input stress evidence
(if absent, mark unknown), five controls' source-vs-heard lexical identity
and counts only in GitHub. Preserve private results. No extra synthesis,
production edits or merge. The detector uses exact full-sequence ASR
matching and occurrence ordinal, then existing phoneme heuristics;
estimated timestamps, ASR mismatches and low confidence limit coverage.
A not_flagged signal is not proof of correctness. A miss on any known
stress error means the heuristic is not suitable for release decisions.
Even all controls passing is not a representative accuracy estimate.
