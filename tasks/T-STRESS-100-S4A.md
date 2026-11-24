# STRESS-100 S4a — bounded baseline stress control experiment

Goal: measure whether the installed stock Qwen responds to U+0301 before
introducing a different checkpoint. This is a raw paired input experiment, not
production preprocessing parity. Eight synthetic public sentences (ordinary
words and homographs), two conditions each, maximum 16 takes, same reference,
seed within each pair, temperature, CPU/float32 and thread count. No retries or
full-chapter generation. No new weights or third-party code. No production
config/cache/output changes.

Use an isolated local checkout, offline, exact existing trusted stock Qwen
snapshot and the authorized production reference WAV and clone mode. Confirm
reference mode/text and settings from local production evidence; do not guess.
Use reference text file for ICL, or --xvector-only if that is the actual mode.
If the existing checkpoint is not safetensors or cannot load offline, STOP.
Example (replace placeholders locally, choose exact reference mode):

uv run --no-sync python -m audiobook.stress_control_baseline --snapshot "$STOCK_SNAPSHOT" --ref-wav "$REF_WAV" --ref-text-file "$REF_TEXT_FILE" --temperature "$TEMPERATURE" --seed "$SEED" --threads "$THREADS" --out "$NEW_PRIVATE_OUT"

The script creates randomized numbered WAVs and private mapping/provenance,
records elapsed time/RTF and failures, no retry. All assets stay local. The
operator must confirm model snapshot identity is stock Qwen, not a modified
checkpoint; script records hashes but is not an allowlist. Use only already
authorized local assets. Do not upload reference, audio, or book text.

First complete one S5a R2 replay on the existing known defect under #42
instructions. Preserve ASR evidence. If uncertain or missed, do not keep
tuning this heuristic; it is not release-grade. S4a is independent of that
detector and may run even if S5a fails. Report generation counts, RTF,
provenance aggregate and any blocker. If independent qualified local rating
is available, rate stress and lexical accuracy blind to condition before
unblinding; otherwise report unrated, not inferred accuracy. No new owner
listening requested at this point. Later make one compact matched comparison
with a legally suitable candidate, not repeated arbitrary seed searches.

CF checkpoint remains blocked for production and for download/inference
pending data-rights assessment. Voicy candidate also needs provenance review.
No automatic acceptance. Full render NO_GO.
