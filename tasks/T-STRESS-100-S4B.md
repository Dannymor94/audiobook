# S4b — isolated Voicy v3 matched probe

S4a owner coarse blind comparison: stock plain 5 accepted/1 near/2 rejected;
raw U+0301 0/0/8; 6 regressions, 0 improvements. Do not use raw acute on
stock Qwen. Stress accuracy remains unrated.

Preflight: operator confirmed public adapter revision
e644ae00257fdd4db0e51b11057370dff6be8bc2, exact existing base
fd4b254389122332181a7c3db7f27e918eec64e3, 392 BF16 tensors / 196 matrices,
rank 16, alpha 32, 17,432,576 params, SHA256
702338d0e81ef8d04715ebd19ebe5eaf43b83446c04ee37f1a9108a9235f2b99.
Apache-2.0 declared; training-data rights not independently established.
Research only; not approved for distribution or production.

Upstream reference: https://github.com/olluorg/voicy/blob/master/scripts/stress_ft_merge.py
and scripts/stress_ft_train.py, docs/adr/0023-stress-marks-by-lora.md.
Implementation independently follows W += B @ A * alpha/r, FP32 computation
rounded to original BF16, then FP32 inference. Only talker.model layer
projections are touched in memory; no PEFT or disk checkpoint changes.
Strict exact config, name/shape/dtype/finite/inventory and file-digest checks.
If actual pinned artifact differs from expected schema, STOP and report
public metadata; do not improvise mapping or bypass checks.

Gamebox only, isolated checkout, green CI, persistent root storage, detached
execution and log/PID/exit status. No /tmp output, no competing jobs, no
production edits. Check RAM, disk, snapshot and reference. Provision the
already verified adapter.json and adapter.safetensors via existing trusted
local transfer from Mac to a new persistent gamebox directory. If those files
are no longer available, download only these two public files from the exact
pinned revision in a separate network-enabled provisioning step before any
private processing; verify config Git blob against the earlier preflight and
weights SHA256, then disconnect external network. Never execute upstream code.
The published adapter config must have base=Qwen/Qwen3-TTS-12Hz-1.7B-Base
and base_revision=fd4b254389122332181a7c3db7f27e918eec64e3 (not a local path).
Before loading the large model, run the lightweight check:

uv run --no-sync python -c 'from pathlib import Path; import sys; from audiobook.stress_voicy import read_adapter; read_adapter(Path(sys.argv[1])); print("ADAPTER_PREFLIGHT_PASS")' "$ADAPTER_DIR"

If mismatch remains, report exact public config metadata and stop; no bypass.
Use same reference WAV/text, ICL, CPU FP32, 8 threads, temp 1.0, seed 42,
same library versions, max_new_tokens=256 as actual S4a run.
Reuse completed durable S4a baseline. Example:

uv run --no-sync python -m audiobook.stress_control_baseline --snapshot "$STOCK_SNAPSHOT" --ref-wav "$REF_WAV" --ref-text-file "$REF_TEXT_FILE" --temperature 1.0 --seed 42 --threads 8 --baseline-run "$S4A_RUN" --voicy-adapter "$ADAPTER_DIR" --out "$NEW_PERSISTENT_PRIVATE_OUT"

Exactly 8 new marked takes. Stop if integration/provenance mismatch or runtime
failure; no retries or changed settings. Actual start, first two elapsed times,
RTF, revised estimate and final duration. Stock generation mean 24.4s/take,
so indicative compute only ~3.3min plus startup and merge; real estimate
must use observed candidate throughput. No guarantee.

After generation verify complete inventory and hashes, prepare mixed blind
pack with 8 preserved stock plain clips + 8 Voicy marked clips (no stock rerender):
uv run --no-sync python -m audiobook.stress_control_review prepare --run "$S4A_RUN" --voicy-run "$S4B_RUN" --review "$NEW_PRIVATE_REVIEW" --shuffle-seed 20261125

Keep condition key private. Report aggregate generation, merge, timing and
pack counts. If no independent qualified listener, report UNRATED. Owner's
prior coarse ratings cannot establish measured stress accuracy. Mixed
comparison tests the candidate strategy, not adapter-vs-mark causal isolation.
No production promotion, no full chapter/book render, FULL_RENDER=NO_GO.
