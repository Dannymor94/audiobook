# STRESS-100 / S3a — auxiliary lexical evidence

This stage uses the already generated private S1 audit. It does not rerun
predictors, modify the text, or choose a pronunciation by dictionary majority.

Public asset: https://raw.githubusercontent.com/eugenysilin/russian-ukrainian-stress-data/main/data/ru-stress-dict.gz
Expected SHA256: adf32b9cd1059597a14519a8f9348f9dc53e9dfb79e0e42989e884e108f41185.
Source: Wiktionary contributors; derivative by eugenysilin, CC BY-SA 4.0.
Keep attribution and license when redistributing the data or derivatives.
Do not publish private lexical evidence or manuscript. The table discards
alternative readings, so its hits are candidates, not contextual truth.
The CI smoke downloads only the public asset and tests public fixture words.

After S1 and S2 and green CI on this branch, provision the hash-verified public
asset separately from private inference, and run locally offline:

`uv run --no-sync python -m audiobook.stress_lexicon --book-text-dir "$BOOK_TEXT_DIR" --audit-dir "$BOOK_AUDIT_DIR" --dictionary "$LOCAL_PUBLIC_DICT" --out "$NEW_PRIVATE_LEXICAL_DIR"`

Reports: aggregate dictionary hits, evidence categories, no automatic approvals.
Keep individual occurrences and source hashes local where necessary.
S3b contextual adjudication is still pending; use occurrence-specific evidence,
especially homographs, ё, names and other nonstandard tokens. Do not count
dictionary support as resolved or measured acoustic coverage. No synthesis,
production changes, full render, or merge.