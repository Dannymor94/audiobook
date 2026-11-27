# T-ALG-07 — chapter quality inventory (research)

Goal: one local report and prioritized review queue for a chapter, without
rerendering or replacing any audio. No approval or automatic fixes.

## Sources and identity

- Mandatory: existing chapter manifest JSONL and explicit SHA256, canonical
  chunks directory. Enumerate manifest IDs, verify regular WAV file paths,
  hash every present WAV, recheck after reporting. Presence is not decoded
  audio validation. Existing manifest CER/flags/status are historical hints
  because QC has no per-WAV digest; do not treat as fresh acoustic evidence.
- Optional: existing dual stress consensus occurrences.jsonl, frozen SHA.
  Reuse build_ledger full occurrence validation; disagreement, single source,
  unresolved and alignment error are text risks, not proven audio defects.
  Agreement is not pronunciation verification. Token-run categories and
  coverage retained; no claims about 100% heard correctness.
- Optional: ALG-05 existing controls, results_PRIVATE.json and summary.json
  (all frozen digests, with findings). Validate manifest/audit/control
  identity, exact occurrences and current WAV digests; recompute dev
  thresholds, signals and aggregate split counts from existing evidence.
  Known human gold wrong stress / lexical error stays a defect even if CTC
  uncertain or not flagged. CTC remains experimental, not independent gold.
  This validates internal scoring consistency, not recognizer inference.
- Optional: ALG-06 frozen rhythm plan and private paired WAV directory.
  Candidate hash must match current chapter WAV; recompute read-only
  measurements with existing rhythm_acoustic_measure.evaluate. Report
  numeric paired differences without assuming quality thresholds.
- Optional: explicit independent human evidence for exact chapter WAV.
  Manifest SHA, chunk hash, WAV SHA, dimension (stress, lexical, rhythm,
  voice, artifacts), rating (ok/bad/unsure), independently_reviewed:true.
  Duplicate chunk/dimension or stale identities reject. Assertion of review
  is external evidence, not proof by itself. Older labels.yaml uses short
  hash prefixes and generic OK; cannot automatically promote it to this
  format. Do not copy generic labels to five independent dimensions.
  No automatic speaker similarity detector claimed.

## Output and use

`python -m audiobook.chapter_quality --manifest "$MANIFEST" --manifest-sha256 "$MANIFEST_SHA" --chunks-dir "$CHUNKS" --out "$NEW_REPORT"`

Optional flags `--findings`, `--human`, `--ctc-controls`, `--ctc-results`,
`--ctc-summary`, `--rhythm-plan` each require matching `--<name>-sha256`.
CTC bundle requires all three plus findings; rhythm requires
`--rhythm-audio-root` with actual matching paired recordings. Human JSON
{manifest_sha256:"...",rows:[{id:"0001",hash:"...",wav_sha256:"...",
dimension:"voice",rating:"ok",independently_reviewed:true}]}.

New output directory outside repo/canonical output/chunk directory:
- chapter_PRIVATE.json: per-chunk identity, historical hints, optional
  measurements, human ratings and reasons.
- queue_PRIVATE.tsv: prioritized chunk IDs (incomplete, human_defect,
  review, unverified, human_review_ok). No claim that human_review_ok
  authorizes release. Quantitative rhythm measurements alone do not mark
  a defect or prove naturalness. Missing evidence is unmeasured.
- summary.json: aggregate inventory, coverage of each human dimension,
  text accounting, detector/rhythm measured counts, input digests.

Only aggregate summary may leave local machines. Never transmit private
reports, manuscript or audio. No models loaded, no ASR or TTS, no writes
to source, manifest or canonical WAVs. No release_ready true path.
Ten synthetic cases cover incomplete inventory, stress accounting, human
evidence identity, CTC consistency, measured rhythm not a quality pass.
Actual report cannot be generated without local chapter files. No new
production integration, merge or full render.

## Local order
ALG-04B first acoustic experiment after gamebox availability; ALG-05/06
diagnostic only if genuine controls/reference recordings available.
ALG-07 can generate baseline chapter inventory with mandatory inputs and
add optional evidence when available. No need to wait for every module.
Do not start a separate manual re-labeling campaign solely to fill report.
Latest CI pending. No new agents while power unavailable.
