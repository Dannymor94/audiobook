# H04 — Local Owner Gold-Labeling Guide (T15-7)

**Type:** operator instructions; no source text, voice, gold labels, or audio in Git.
**Status:** READY. Milestone A was accepted at `928bb6e`; the local sample/todo contains 320 blank annotation rows and owner labeling may begin. Keep those rows on the local device.
**Expected size:** up to 320 selected occurrences across six strata, often fewer if a stratum is small.
**Estimated owner active effort:** 4–10 hours as an initial planning range; actual time depends on listening needs and ambiguity.
**Authority:** `tasks/T15-7-FINAL-ADR.md` §10, particularly the C3 version-ledger and U5 grammar.

## What the owner actually does

1. Run the documented local `./run.sh stress-eval sample` **after WP-4 milestone A is accepted locally**; do not start before its CLI exists. This validates the current v5 generation and creates an ignored, local `text/stress_gold.todo.tsv`. Leave `text/stress_gold.tsv`, any existing ledger versions, archived export, and the sample record intact.
2. Open the todo locally. Preserve every generated identity and context field. Do not edit `source_key`, `form_source`, `unit_text_sha256`, `unit_kind`, `context_sha256` or `context` (which is at most 80 characters). The generated rows are requests for labels, **not model predictions to accept**.
3. For each row, provide the actual **human** accent judgment, the independent `yo_correct` judgment when applicable, a nonempty human `labeler`, and `date` in `YYYY-MM-DD` format. Check against a trustworthy pronunciation or listening reference. Do not infer truth merely from RUAccent, F1 respell, TTS output or a previous automated guess.
4. Follow the exact grammar below. Save a copy in an **ignored S4 path**, never upload it or paste book rows into a chat. **Do not run `stress-eval sample` again after editing the todo and before merging:** the current 7.7 implementation deliberately rejects a todo with unmerged labels (`TODO_HAS_UNMERGED_LABELS`) rather than overwriting work. The currently implemented merge CLI takes the explicit file path: `./run.sh stress-eval merge text/stress_gold.todo.tsv` (optionally `--sample <local sample.json>`). Merge checks all labels and the current five-part source identity before writing.
5. If merge rejects stale rows, regenerate the todo for the current source and re-label those rows. If a currently valid human gold row conflicts, do not resolve by choosing the latest date; stop and review the evidence manually. Repeat merges of identical labels should make **no changes** to the ledger.
6. After the complete set is labeled, `./run.sh stress-eval score` may produce summary metrics (no book text). A missing active label means INCOMPLETE (rc 2), not PASS. Send only aggregate counts/metrics and the final score status to the coordinator.

## Field grammar — mandatory

Gold header is **exactly** ten TAB-separated columns, in this order:

```text
source_key	form_source	unit_text_sha256	unit_kind	context_sha256	context	gold_vowel	yo_correct	labeler	date
```

`gold_vowel` options:

| Value | Meaning |
|---|---|
| `0`, `1`, `2`, ... | Zero-based index of the actually stressed **vowel** in `form_source`; not the character index |
| `variants:0\|1` | Distinct accepted stressed vowel indices (use only when both pronunciations are genuinely correct) |
| `yo` | The unique `ё` is stressed; allowed only when the spelling conditions in ADR §10 hold |
| `ambiguous` | Stress cannot be established reliably |
| `unknown_name` | Name with no reliable pronunciation reference |

**Do not use `yo_unstressed`** — it is explicitly invalid. If `ё` is not stressed, provide the index of the vowel that *is* stressed, or mark ambiguous.

`yo_correct` options: `y` (restoration correct), `n` (incorrect), `na` (not applicable). For rows with the **yo_changed property**, `y` or `n` is mandatory; this is independent of `gold_vowel`. A `yo_changed` word can appear in another stratum because selection is first-match-wins.

### Synthetic index illustration (NOT book content)

`молоко` has three vowels in source order. If its final vowel is stressed, `gold_vowel=2` (not its character offset). A different source spelling or ambiguous pronunciation must be evaluated independently. These illustrations never enter an actual gold file.

## Safety and efficiency

- Gold files, contextual fragments, per-word identities and listening material stay exclusively on the owner's local machine under ignored S4/S3 paths. Never commit, upload, email or paste them to cloud AI. Only counts, high-level statuses and global digests may leave the machine.
- Group labeling into small sessions and save reviewed local copies before merge. Do not create competing valid ledger versions to “undo” a label: correct the evidence under the approved C3 conflict/stale process.
- `stress_gold.archive.tsv` is a **derived** record of stale rows, not the authoritative ledger; never edit or use it as scorer input. Do not delete older gold versions.
- A text-based quality score does **not** replace listening/voice-quality review; no T16/T17 or full render is authorized here.

**Operational handoff:** tell the coordinator only how many labels are complete/unresolved/unknown_name, counts per stratum, and whether merge/score returns COMPLETE, INCOMPLETE or ERROR. Never include word text or row-level hashes.
