# T-ALG-09 — single chapter quality batch and local recovery

Status: implementation complete; latest CI and real local execution pending.
One bounded package, not a series of independent owner confirmations.
No production changes, model inference, rerender, audio replacement or merge.

## Delivered
1. ALG-08 verified prior HEAD 14e6730904f12abdab95bb9f734fd7395acd0b1a:
   CI 45979270666, 864 passed / 3 deselected / 5 warnings. Public ONNX
   contract and download verified in run 45979179139. No private data.
2. chapter_quality.verify_ctc normalizes canonical decimal vowel ordinal
   keys after JSON reload, rejects collisions/invalid keys; regression
   test uses actual ranked evidence. Previously JSON serialization made
   integer score keys into strings and the report could reject valid CTC.
3. waveform_screen.py integrated into chapter_quality CLI: decode and
   validate mono WAV, finite samples, supported duration/rate/size, exact
   SHA identity. Digital silence, near-full-scale peaks, DC offset are
   diagnostic signals only; not perceptual artifact proof. Corrupt or
   unsupported files remain incomplete and excluded from listening pack.
   No waveform changes.
4. quality_batch.py: single frozen local plan; validates optional evidence
   bundle completeness and SHA, runs fixed chapter_quality module (no
   shell), generates report and bounded review pack, rechecks canonical
   WAV inventory and input digests before REPORT_READY. Actual started /
   finished UTC and elapsed in run_PRIVATE.json. Failed runs never count
   as ready; preserve partial evidence, use new directory on retry.
5. Existing review.render reused for local UTF8 HTML and copied exact WAVs.
   Max 12 clips per batch: human defects first, then review flags, then
   up to four deterministic spread-out unverified samples if space.
   No incomplete or already human_review_ok clips. Full queue stays in
   report. Generic OK/BAD never promoted to independent dimension gold.
   Page identity binds manifest and exact audio; no automatic import.

## Single local command
Create private plan JSON with absolute paths and independently checked
digests (do not fabricate optional evidence):
{
  "policy":"chapter-quality-batch-v1",
  "manifest":{"path":"/absolute/chapter/manifest.jsonl","sha256":"..."},
  "chunks_dir":"/absolute/chapter/chunks",
  "evidence":{},
  "review_limit":12
}
Optional evidence keys: findings, human, ctc-controls, ctc-results,
ctc-summary, rhythm-plan, voice-results, voice-summary. Each value is
{path:absolute path,sha256:exact digest}. Complete bundles only.
rhythm-plan requires rhythm_audio_root. No automatic discovery by name,
no silently substituted old evidence. Missing optional sources explicitly
listed in receipt; available sources may be added later with a new plan.
Run on gamebox for full chapter:
`python -m audiobook.quality_batch --plan "$PRIVATE_PLAN" --plan-sha256 "$PLAN_SHA" --out "$NEW_BATCH"`
No model imports/inference; optional rhythm measurements use existing
matched audio. Output outside canonical/repo, locally only.
Read report/summary.json and run_PRIVATE.json. Open listen/review.html only
if selected > 0. No user review needed for mere baseline inventory; lead
decides whether flagged clips merit listening. A batch cannot authorize
release. Tests use synthetic fixtures; real chapter data still unavailable.

## When electricity/network returns — one operator handoff
SOL Medium, local operator only, no code changes. Verify gamebox identity
(danny-serv Linux), RAM/disk, idle canonical queue, persistent disk (not
tmpfs/dangling Downloads); verify pinned latest green PR47 HEAD and clean
separate research checkout. No Mac TTS fallback. Record actual times and
evidence-based duration estimates only when measurable.
A. Resume ALG-04B public asset provisioning against frozen SHA identities;
   verify pinned isolated CPU dependencies/imports, no model load/TTS.
B. In same availability session, produce ALG-09 baseline for chapter 1
   using existing canonical manifest and WAVs (no optional evidence unless
   exact and available). Share only aggregate counts, timing and readiness.
C. Inventory whether independent actual author recordings and labeled
   control WAVs exist; no new recording, relabeling or generated gold.
   Report available counts and blockers for ALG-05/06/08, not private files.
D. Stop before any ALG-04B inference or private model inference; obtain
   separate lead authorization after A/B/C evidence. ALG-04B first acoustic
   experiment, then only diagnostics justified by actual available controls.
   No full chapter rerender without owner GO. No further speculative
   detector development before actual audio results.

The lead performs accessible GitHub work. Agent only performs inaccessible
local steps when available. Bundle routine related work; escalate only
material blocker or owner decision.
