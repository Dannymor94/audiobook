# CONTROL-RENDER-1 recovery batch — 2026-11-27
Owner GO: execute consecutive independent work, report once at material checkpoint.
Baseline PR47 43c88afe8b8b8acb7cedffc4e61329395e13f3d4: five workflows green.
This file supplements, not replaces T-CLOUD-FIRST-COMPUTE.md,
T-CLOUD-QUOTA-01.md and T-ALG-09-QUALITY-BATCH-RECOVERY.md. Original
CLOUD-05 remains optional Modal; no reuse of existing task IDs.
No private transfer, full book render, paid resources or GPU submission.

## Owner priority override — 2026-11-27
VOICE FIRST. SFX-01, music, asset acquisition and mixing are HOLD until the clean narrated book is completed. No further SFX work. Existing draft artifacts remain isolated and must not be merged as part of voice delivery. Cloud preparation is a means, not a release prerequisite: prioritize the existing local chapter evidence, complete stress map, actual pronunciation and targeted repairs. No speculative detectors or new infrastructure unless they unblock measurable audio quality. The existing GPU hold and full-book owner listening gate remain binding.

## Binding hybrid execution plan — owner clarification 2026-11-27

Cloud = short experiments and rapid evidence, not the production pipeline.
Local = complete book, private voice, long calculations and persistent cache.
Run independent cloud and local CPU tracks in parallel when resources and
access permit; neither waits for the other unless there is a real dependency.
Choose cloud only when expected queue + setup + inference + export is shorter
than the qualified local alternative. Reuse existing evidence and weights.
Do not spend cloud quota on ordinary CI, repeated downloads or full chapters.

| Order | Work | Execution location / exit |
|---|---|---|
| 1A | ROOT-01/02 | Local Mac CPU: trace exact known-error source, map, final synthesis input and tokenizer identity; gamebox if existing WAV/runtime required. No new TTS for boundary audit. |
| 1B | STRESS-100 | Local Mac CPU: complete existing occurrence map, resolve conflicts and unknowns, bind exact manifest; parallel with 1A/2A where possible. |
| 2A | Short public acoustic probes | Colab CPU first for explicit-stress Silero; Kaggle/Colab GPU only after GPU hold and admission resolved. Fixed public synthetic cases and non-author voices, 4–8 short clips, initial <=10 min compute, existing stricter quota rules prevail. Deliver small phone-playable MP3/HTML via authorized private artifact, not public manuscript. |
| 2B | CH1-RECOVERY | Local gamebox: verify reachability/resources/idle lock, reconcile existing manifest/WAVs, run ALG09 baseline and inventory independent gold controls. Can proceed without cloud. |
| 3 | ROOT-03 | Local gamebox: existing bounded Silero + OpenVoice author-voice pilot if ready; compare qualified cloud public evidence and stock baseline; qualify one engine, no blind promotion. CF rights HOLD. |
| 4 | ROOT-04/05 | Local: calibrate existing acoustic verifier on independent controls; public short benchmark may run in cloud, private and large-scale inference on gamebox. Measure recall, false accepts, abstention; no CER-only approval. Bounded repair, preserve cache. |
| 5 | CH1-AUDIO | Local gamebox: qualified targeted repairs and contiguous chapter preview. Use existing WAVs; check lexical/stress/voice/rhythm/artifacts. No full book render yet. |
| 6 | RELEASE | Owner accepts first chapter, then explicitly authorizes full book. Long synthesis, all chapters, full acoustic QC, assembly/mastering/export on gamebox; Mac light management and listening. |
| ongoing | CLOUD-QUOTA-01 | Retain 1200 GPU-s UNKNOWN hold; no repeat deletion, GPU retry or failover; fresh quota/terminal evidence/verified billing and durable admission before enabling. Not a blocker for local work. |
| deferred | SFX-01 | HOLD until clean narrated book completed; no acquisition, placement or mix. |

Cloud transfer rule: no private manuscript, voice, latents, private WAVs or
labels unless separately and explicitly authorized for the exact provider
and data class. Public test output cannot establish author-voice quality.
Phone delivery of private audio must use an existing authorized private
channel; do not infer permission to upload from the request for listening.
Owner listens to useful calibration evidence and final chapter, not every
test. Short public runs are diagnostic only. Local production remains
Gamebox-only; Mac does no heavy TTS. Zero spend, 20% quota reserve and
one outstanding GPU job across providers remain binding.

## CPU admission / routing
- No external CPU job without verified account quota, cost and reserve, or documented free manual bounded session under existing policy. No automated Colab login or session keepalive.
- Colab notebook is a draft artifact, manual only. It must not be started before offline tests pass and actual account admission is confirmed. Fixed built-in public speaker only. A 600-second parent window and child timeouts bound script execution, not provider resource accounting. No actual provider run yet.
- CPU GitHub Actions only bounded necessary checks, existing account balance not independently verified. Do not send chapter data as an artifact.
- Gamebox steps need actual machine access; a GitHub issue is not a running local task. No new heavy jobs until machine/queue verified.
- GPU block does not prohibit safe code/preparation or local existing-audio analysis.
- Do not reopen already accepted infrastructure work just because audio quality is not yet demonstrated.

## Evidence per checkpoint
Exact commit, observed CI status, actual commands/elapsed where executed,
artifact hashes, blocked items and next actionable dependency. No claim
of completion from plan alone. No agent dispatch unless a real local
execution channel is available.
