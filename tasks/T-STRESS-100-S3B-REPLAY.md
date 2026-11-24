# STRESS-100 S3b — private replay and context review queue

Use preserved consolidated book/lexicon evidence from #41. No model inference,
no new dictionary download, no TTS, no source or production edits.

Run in isolated green checkout:

uv run --no-sync python -m audiobook.stress_context_replay --book-text-dir "$BOOK_TEXT_DIR" --audit-dir "$SAVED_BOOK_AUDIT" --lexicon-dir "$SAVED_LEXICON" --out "$NEW_PRIVATE_OUT"

The command verifies source hashes, lexical-audit binding, full inventory and
exact reproduction of the original per-occurrence audit from saved predictor
outputs. For rows rejected by either aligner, it extracts diagnostic
candidates only from a unique target and two unchanged adjacent neighbors,
or from a fully aligned predictor. It keeps each occurrence distinct and
separates same-position ё/е conflicts from stress-position conflicts.
All other conflicts remain in the queue. Do not promote candidates into
production or count them as approved decisions. Context outside a matched
triple may have changed predictor behavior; these candidates are not gold.

Return only aggregate counts: original alignment errors, recovery categories,
queue size, distinct forms, flags (overlapping), and timing. No text or paths.
Report actual STARTED_AT and FINISHED_AT with timezone, ACTUAL_DURATION;
estimate only if measured evidence supports it. Keep private artifacts.
This is a separate small CPU-only replay to execute after the current S4a/S5a
local job; do not interrupt the existing operator. FULL_RENDER=NO_GO.
