# A1/A2 — local stress-map build (Mac)

Timebox: three working days from the actual A kickoff, no extension for unresolved words.
Lead implements; operator runs locally only after exact PR HEAD CI success.
Use existing private S1/S2/S3 outputs and existing RUAccent weights. No new model
downloads, TTS, production changes, book uploads, or dependency changes.
Run with external network disabled and existing environment.

## Preflight and build

Resolve actual canonical normalized book directory, independent expected-sections JSON,
previous whole-book audit (not chapter subset), previous lexical-evidence directory,
and original pinned Wiktionary gzip. Reuse existing local paths; do not fabricate
missing files or recreate historical provenance. Use an isolated exact checkout of
PR #47 and ensure audiobook.paths.MODELS points to the real existing local models.
Check space and local installed RUAccent version and loaded inventory names.
If loaded dictionary schema differs, report public schema/attribute types only;
do not improvise or edit the library. Record actual start and deadline in MSK.

One paired RUAccent run on Mac (original full line + lowercase Title-case copy where
changed). It records the model-tree hashes before/after, actual loaded matched
dictionary subset including homographs, settings and runtime versions. Keep
original-case selection as v1; lowercase is a diagnostic, not a proven improvement.
No repeated inference for the two builds. Use new private persistent directories.

    uv run --no-sync python -m audiobook.stress_map collect --book-text-dir "$BOOK_TEXT_DIR" --expected-sections "$EXPECTED_SECTIONS_JSON" --out "$FRESH_EVIDENCE"

Then two independent invocations with the same frozen inputs and exact HEAD:

    uv run --no-sync python -m audiobook.stress_map build --book-text-dir "$BOOK_TEXT_DIR" --expected-sections "$EXPECTED_SECTIONS_JSON" --audit-dir "$BOOK_AUDIT_DIR" --lexicon-dir "$LEXICON_DIR" --dictionary "$WIKTIONARY_GZIP" --evidence "$FRESH_EVIDENCE" --builder-commit "$HEAD" --out "$MAP_RUN_1"
    uv run --no-sync python -m audiobook.stress_map build --book-text-dir "$BOOK_TEXT_DIR" --expected-sections "$EXPECTED_SECTIONS_JSON" --audit-dir "$BOOK_AUDIT_DIR" --lexicon-dir "$LEXICON_DIR" --dictionary "$WIKTIONARY_GZIP" --evidence "$FRESH_EVIDENCE" --builder-commit "$HEAD" --out "$MAP_RUN_2"
    cmp "$MAP_RUN_1/stress_map.jsonl" "$MAP_RUN_2/stress_map.jsonl"
    cmp "$MAP_RUN_1/manifest_PRIVATE.json" "$MAP_RUN_2/manifest_PRIVATE.json"
    cmp "$MAP_RUN_1/risk_queue_PRIVATE.jsonl" "$MAP_RUN_2/risk_queue_PRIVATE.jsonl"

Optional exact human decisions in a private JSONL passed identically to both runs
with --decisions. Each record must include id/hash/start/end/ordinal/word,
authority="human", stress_index and reason; no inferred confirmations. Initially
omit if no actual approved decisions exist. All unresolved remain accounted.
Historical Silero version is recorded; old weight hash was not captured, not
retroactively attributed. Actual fresh RUAccent file hashes are captured.
Map schema uses normalized line IDs and exact Unicode codepoint offsets; not
production chunk IDs. Risk queue v1 is deliberately UNMAPPED, with broad prior
error-form flags and separately counted unresolved exact error anchors. Later
link to the production source/section map by exact evidence; never fuzzy guessing.
This is a usable lexical inventory, not a completed audio listening pack.
Risk counts may exceed initial expectation. Report counts rather than suppressing
flags. No private manuscript/map/word records in GitHub; only aggregate metrics,
hashes and local path references as appropriate. Report actual start/end/duration,
first observed throughput if available, map completeness/status/risk/changed-case
counts, two SHA matches, and any blockers. No claims of verified pronunciation.

## Independent C read-only preparation

On gamebox inspect canonical production checkout/config, queue list and worker/lock
status, RAM/disk/persistent output; reconcile canonical section inventory, existing
completed chunks/sections, accepted/locked outputs and missing/pending jobs.
Use existing CLI, no queue insertion, no synth/chunk execution, no cache changes.
Report aggregate counts and concrete remaining work, no private contents. Actual
render still requires explicit owner GO. B remains blocked by rights decision.
FULL_RENDER=NO_GO.
