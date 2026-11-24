# S4a independent blind assessment

Prerequisite: completed S4a run on gamebox, preserved on persistent private
storage, exact green #43 provenance. This lightweight postprocessing may run
on Mac after authorized local transfer. No new inference, no new synthesis.

Prepare:
uv run --no-sync python -m audiobook.stress_control_review prepare --run "$S4A_RUN" --review "$NEW_PRIVATE_REVIEW" --shuffle-seed 20261124

The operator keeps key_PRIVATE.json separate from the assessor. Only the
blind directory is provided to an independent qualified local Russian
listener; it contains exact copied WAVs and ratings.tsv without condition
or expected accent. No cloud upload, no owner relistening required for now.
If no qualified listener is available, report UNRATED and preserve the pack.

For each clip: lexical=ok/error/uncertain (whole sentence), heard_vowel=1..N
(ordinal of the perceived stressed vowel in the target, not character index)
or unknown, naturalness=good/poor/uncertain. For lexical error/uncertain use
heard_vowel=unknown. Do not guess. Save completed TSV separately before
unblinding. Report assessor provenance and whether truly blind; tool cannot
authenticate listener qualification or honesty. No expected stress lookup
during rating, no changes to recordings.

Score:
uv run --no-sync python -m audiobook.stress_control_review score --run "$S4A_RUN" --review "$NEW_PRIVATE_REVIEW" --ratings "$COMPLETED_TSV" --out "$NEW_PRIVATE_SCORE_JSON"

Report only aggregate outcomes per condition, paired improvements/regressions,
uncertain/lexical errors, generation failures, naturalness and timing.
Eight synthetic pairs, one seed per pair, do not extrapolate to book accuracy.
If marked condition improves stress without lexical or naturalness harm,
consider a separate matched confirmation on known real controls. If not,
prioritize alternative stress-aware TTS after rights and model review.
If no ratings, no inference of effectiveness from successful synthesis or ASR.
No production promotion or full render.
