# CLOUD-QUOTA-01 — hard resource admission and reconciliation
Decision 2026-11-27: zero out-of-pocket spend, conservative quotas,
no automatic resubmission. Applies to every agent/provider. Supersedes
less restrictive scheduling clauses in T-CLOUD-FIRST-COMPUTE.md.

## Admission
- Live provider quota, refresh timestamp, active reservations and account
  spending status required before any compute submission. Unknown/stale
  quota, unknown cost, missing billing hard stop => BLOCKED, never guess.
  Use live quota within 5 minutes of admission. Never infer reset from
  calendar alone; read provider reset timestamp.
- Reserve 20% of confirmed allowance (round conservatively); account usage
  by other projects counts. Kaggle GPU 30h/week -> max total 24h, leave
  >=6h; if provider allowance falls, recompute. TPU 20h -> 16h, disabled
  until qualified. Modal $30 credits -> <=$24 gross, $0 net enforced by
  actual account hard limit; until proven disabled. Colab dynamic limits:
  no unattended submission with unknown quota, bounded manual sessions.
  Actions: <=80% included compute/storage; actual account allowance
  unverified, use bounded necessary CI/read-only checks, no paid fallback.
- Admission formula in same provider units:
  remaining - outstanding worst-case reservations - new job worst-case
  debit >= max(20% of current total, provider-required reserve).
  Also total used + reservations + new debit <= project ceiling.
  Reserve full configured runtime, not predicted mean; GPU multiplier
  must be known, otherwise conservatively charge number of allocated GPUs
  or refuse. Use one GPU initially. Do not mix GPU-hours and wall hours.
  Do not count quota spent twice: outstanding reservation covers possible
  future debit not already reflected, conservative full reservation is OK.
- Initial GPU test max 10min execution, max 1 job pending/queued/running/
  unknown across project GPU providers. No new GPU submissions until first
  smoke is reconciled. Later cap 30min per test; production batches <=4h
  only after measured RTF and explicit approval. No job crossing unknown
  quota reset/session boundary. Leave 20% of session time to save outputs.
- CPU preprocessing, hashing, report scoring and fixtures stay CPU.
  Cache pinned public weights only within permitted storage; no repeated
  downloads if verified reuse available. Account storage reserves apply
  separately, check artifacts/egress, avoid large Actions artifacts.

## Durable job ledger / lifecycle
- GitHub control plane must keep an append-only durable job record outside
  ephemeral runner. Record logical task, frozen input/code/model digests,
  provider/account, unique job key, exact remote version, requested device,
  reserved debit, quota snapshot/reset, state, actual timing, output hashes.
- States PLANNED -> RESERVED -> SUBMITTING -> SUBMITTED -> QUEUED/RUNNING
  -> COMPLETE_UNVERIFIED -> VERIFIED; terminal FAILED/CANCELLED only with
  provider evidence. UNKNOWN/LOST_CONTACT remain reserved and block
  duplicate/fallback. Only VERIFIED counts as valid result.
- Persist reservation and submission intent BEFORE external push. After
  ambiguous push reconcile by deterministic slug and exact version; never
  blindly retry. Use a single controller/writer and provider-wide
  concurrency lock; Actions concurrency alone is not durable remote lock.
- Separate submit, read-only status/collect, cancellation. Monitoring
  timeout is not remote failure or cancellation. Poll backoff 30s/60s/
  120s, bounded controller runs; resume same remote job, not new push.
  Queue time >30min => review; >2h request supported cancellation if
  available, otherwise owner UI action only if needed. No invented cancel
  command; verify terminal state before releasing reservation.
- Retry only after explicit terminal status, diagnosis, fresh quota and
  new recorded attempt. No retries for unknown status/OOM/billing issue.
  No automatic fallback to another service until prior job reconciled.
- Export per-case atomic outputs/receipts, verify SHA/format, retain
  partial artifacts; resume only missing cases when backend fingerprint
  matches. No private manuscript, voice, latents or labels in cloud.
- Owner escalation only for real spending decision, access/verification,
  private transfer or material policy exception. Routine checks lead.

## Immediate implementation status
Existing Kaggle job dannymorozov/audiobook-public-smoke-46019695614/1:
submission confirmed 2026-11-27T14:51:50Z; GPU quota 30h; status queued
through 15:04:49Z; controller stopped at 15:05:09Z (not remote cancel).
Reserve full 10min conservative allocation; state UNKNOWN until queried.
Disable original submit workflow; use read-only reconciliation of exact
remote version, no new GPU work. Until durable admission/ledger is
implemented and tested, all subsequent submissions blocked.
Read-only monitor can query quota, exact version status and retrieve
existing outputs if complete. No new kernel, no credentials logged.


## Implementation checkpoint — 2026-11-27
- Prior exact CI 46036247958: 875 passed, 3 deselected.
- Read-only reconcile run 46039132028 / job 140642052419 at 17:06:30 UTC:
  exact version still queued, 0.00h used, 30.00h remaining, refresh
  2026-11-28 00:00 UTC. Queue age >2h14m. No render result.
- Official pinned Kaggle CLI v2.2.5 docs and implementation inspected:
  no separate kernel execution cancellation command; kernels delete is
  destructive, not equivalent to cancellation. Do not delete the notebook.
  If a stop/cancel control exists in the exact notebook UI, owner can
  cancel that execution; reconcile terminal state before releasing hold.
- cloud/ledger/gpu-events.jsonl stores the exact legacy queued job and
  provider observation. Original job predates frozen plan digest; preserve
  null instead of inventing one. Reserve 1200 GPU-seconds (600s runtime
  times conservative 2 GPUs), because actual accounting multiplier has
  not been established. This is a conservative planning hold, not actual
  provider consumption or a proven provider limit.
- src/audiobook/cloud_quota.py: pure deterministic admission, five-minute
  quota freshness, exact reset horizon, reserve 20%, conservative rounding
  allowance, qualified one-GPU <=600s public route, zero-spend gate,
  append-only hash-linked event replay, expected-tip CAS and terminal
  receipt checks. Active/unknown states block another GPU route. 16 test
  cases including real legacy hold. No new provider call in this module.
- Original submit workflow and direct legacy entrypoint disabled; obsolete
  unreserved push path removed. Read-only reconciliation remains usable.
- This is not yet a live atomic remote scheduler: actual durable store
  revision CAS and authenticated provider state verification must be wired
  to admission/submission, cancellation/queue deadline must be enforceable,
  and account billing/GPU accounting must be verified before enabling
  submissions. A hash chain is not independent proof of provider receipts.
  No automatic fallback, retry or new GPU job. Latest CI pending.


## Owner-approved disposable notebook deletion
- Exact HEAD 73711f2158ffe80d83a23fabd94c5fc34dd478e8 CI 46042314039:
  891 passed, 3 deselected.
- Official SDK cancellation attempt 46043839229: exact /1 queued,
  session ID not exposed, no cancel request sent.
- Owner explicitly authorized deleting the disposable notebook only.
  Run 46044963641 / job 140661799351 on 2026-11-27T17:50:48Z:
  Kaggle confirmed notebook deletion, exact version inaccessible afterward.
  This does not independently prove worker termination.
- Ledger appended UNKNOWN observation with evidence; 1200 GPU-seconds
  hold retained. One-shot destructive/cancel workflows retired.
  New GPU submission remains locked; no retry or fallback until provider
  confirms terminal state or owner approves a separately specified,
  bounded risk policy after reconciliation. No claim quota consumed.
- Next: verify current quota and active-session evidence through supported
  provider interfaces, not an inaccessible deleted notebook status.
  Prepare public CPU and Colab packaging without submitting GPU jobs.
  Do not repeat deletion. No private inputs, paid resource, or merge.
