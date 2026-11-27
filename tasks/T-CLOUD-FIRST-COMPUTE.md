# CLOUD-FIRST — free compute architecture
Approved direction: owner, 2026-11-27. Research branch only. Replaces
blanket Gamebox-only policy for explicitly approved public cloud experiments.
Private manuscript, author recordings/latents, private WAVs, production cache
and private labels remain local until separate explicit data-transfer approval.
No full book render or production config/merge authorized. Mac no heavy TTS.

## Provider evidence (checked 2026-11-27)

| Provider | Advertised allowance / constraints | Route |
|---|---|---|
| Kaggle | Up to 30 GPU hours/week in official GPU tips; floating account quota, current notebook docs and official runtime update say 12h CPU/GPU (older tips say 9h), 20GB saved output, 4 CPU cores and ~29–30GB RAM; actual account/session limits authoritative. Plan 1h max initial job, later <=4h and below confirmed session limit. T4 x2 or L4 may be selectable, not guaranteed. Verify account and phone if required. | Primary public GPU batch; official CLI kernels push/status/output; private notebook by default |
| Colab free | Dynamic GPU/idle/VM limits, max 12h session, hardware not guaranteed; SSH/remote-control bypass prohibited on free managed runtime. | Manual notebook fallback; public short trials only, no keepalive hacks |
| Modal Starter | $30 monthly eligible compute; T4 $0.000164/s, L4 $0.000222/s, A10 $0.000306/s, CPU $0.0000131/core/s, RAM $0.00000222/GiB/s; network egress separately priced. Payment method may be required for GPU; official budgets docs describe separate net spend limit that stops workloads incurring extra charges; verify $0 net spend limit and <=$24 gross workspace budget in actual dashboard before enabling. | Automated bounded public GPU/CPU jobs; not active until billing safety confirmed |
| GitHub Actions | Standard hosted public-repo compute free, private Free $12/month included compute, Pro $18, storage 500MB/1GB respectively. Current account plan/balance unknown; larger GPU runners not assumed free. | CI, public CPU smoke and hash/manifest/report tests; small public test outputs only if allowance confirmed |
| Lightning AI | 1 free 4-CPU Studio, 4h restarts, first 10GB storage free per billing docs; up to $30 promotional starting credits, not recurring guaranteed, actual grant may differ. | Persistent development/prep; CPU tests, optional GPU one-off |
| HF ZeroGPU | 5 min/day authenticated free, 2min anonymous, 48GB large /96GB xlarge (2x quota), 60s default call; Gradio only, supported Python3.10/3.12 and Torch >=2.8; free hosting up to 2 spaces eligible verified account age >30d. | Single short public demo, not batch worker |
| Paperspace Gradient | free M4000 8GB if capacity, 6h shutdown, 1h idle, one free notebook; free machines public; legacy API deprecated. | Public Silero/OV CPU/small models if useful, not private or main Qwen |
| GitHub Codespaces | personal Free 120 core-hours/month = 60h 2-core; 15 GB-month storage, Pro 180/20; CPU only. | Manual dev fallback, avoid model cache consuming quota |
| OCI Always Free | 1500 OCPU-h +9000 GB-h/mo, approx 2 ARM OCPU/12GB, 200GB block storage, home-region capacity and idle reclaim. | Optional CPU coordinator or lightweight public preprocessing; ARM dependencies need qualification, not sole state |
| GCP Cloud Run | free eligible CPU/memory/request allowance with billing, GPU not assumed included; trial $300 cannot provision GPU before upgrade. | Deferred; no new billing |
| AWS | new-account $100 + up to $100 earned credits, free plan service restrictions; GPU not guaranteed. Studio Lab no new customers. | Deferred |
| Azure | eligible $200/30 days, GPU quota/eligibility not guaranteed. | Deferred |
| Saturn Cloud | old free-compute landing page redirects to dedicated inference site; current free notebook grant unverified. | Exclude until verified |
| Other GPU grants / trials / TPU | credits, access and model compatibility not guaranteed; no entitlement assumed. | Deferred, no TPU port before CUDA benchmark |

Official sources:
- https://www.kaggle.com/page/GPU-tips-and-tricks
- https://www.kaggle.com/docs/notebooks ; https://www.kaggle.com/product-feedback/302908
- https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md
- https://research.google.com/colaboratory/faq.html
- https://modal.com/pricing ; https://modal.com/docs/guide/budgets
- https://lightning.ai/pricing ; https://lightning.ai/docs/platform/overview/faq/billing
- https://huggingface.co/docs/hub/spaces-zerogpu
- https://docs.digitalocean.com/products/paperspace/machines/details/features/
- https://docs.digitalocean.com/products/paperspace/notebooks/getting-started/run-example-notebooks/
- https://docs.github.com/en/billing/reference/product-usage-included
- https://docs.github.com/en/actions/concepts/billing-and-usage
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://docs.cloud.google.com/free/docs/free-cloud-features
- https://cloud.google.com/run/pricing
- https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html
- https://docs.aws.amazon.com/sagemaker/latest/dg/studio-lab-availability-change.html
- https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/avoid-charges-free-account
- https://saturncloud.io/try/
- https://github.com/QwenLM/Qwen3-TTS

## Architecture and data boundary
GitHub = control plane (code, public fixtures, manifest schemas, aggregate
receipts, issue task state). Compute = independent worker adapters. Never
upload repository checkout with unreviewed content or mount personal Drive.
Build an explicit allowlisted export from reviewed tracked files + public
synthetic cases + rights-reviewed reference fixture. No personal voice in
cloud under this authorization; public sample requires legitimate permission
for cloning/processing, documented provenance and digest. Prefer non-cloning
built-in synthetic voices as initial smoke; no arbitrary reference voice.
Public output review WAVs may be returned in private workspace/authorized
artifact, never auto-published. All private book-specific preprocessing,
gold, labels, author voice, practice recordings, synthesis and mastering
remain local until a separate provider/data authorization. Do not equate
private notebook or encryption at rest with local-only processing.

## Routes
- Public ALG04B Silero + OpenVoice: CPU sufficient for initial 4 pairs;
  Kaggle CPU or explicit bounded public GitHub CPU job if resource/budget
  verified. Rights-reviewed non-author public fixture only. Validate native
  loading then synth. GPU acceleration separate backend qualification.
- Qwen3-TTS 1.7B public stress/rhythm benchmark: Kaggle CUDA first, Colab
  second, Modal if hard billing gate; 1 GPU initially, T4 FP16 SDPA/eager
  (no BF16/FlashAttention2 assumption), L4 BF16 where supported. Same
  pinned model/seed/settings within pairs; dtype/device/attention change
  generation identity; GPU vs CPU not bitwise parity. OOM stops, no
  silent smaller model/precision/backends.
- ALG05 public CTC validation / Whisper: Kaggle or Colab GPU for model
  inference; CPU pure scoring in Actions. Private controls gamebox only.
- ALG06/07/09 pure rhythm/report/waveform: GitHub Actions synthetic tests;
  Lightning CPU/Codespaces for public datasets; actual chapter locally.
- ALG08 ONNX WeSpeaker public smoke CPU (already passed); actual author
  measurements local. Do not mistake synthetic feature test for voice QC.
- Public audio effects sourcing/license inventory CPU; private placement
  map, source manuscript, audio mix/master remain local.

## Scheduling and zero-spend
Default actual out-of-pocket ceiling USD0. No subscriptions, card entry,
paid upgrades, multiple accounts or limit evasion. Account owner verifies
available quotas, storage/egress/charges and spending controls. Metered
provider disabled until documented hard spending prevention or explicit
owner paid exception; warning-only budgets insufficient. Never assume
credits cover storage, egress, APIs or idle. No automatic paid fallback.
At admission check provider/account quota, observed GPU, disk, timeout,
model hashes, actual runtime environment, data class and plan digest.
Reserve at least 20% quota and time for checkpoint/export. First one worker,
one paired batch, <=30min compute cap and <=1h total job cap. Later size
from measured RTF, setup and p95 chunk time, cap by remaining quota and
session. No unattended keepalive; no automatic retry after OOM/unknown
billing. Each logical case has one lease per backend/plan; stop duplicate
submissions, poll official API with backoff; mark expired/failed and resume
only missing completed-case receipts in new session. Keep all A/B arms on
same runtime fingerprint. Save atomic WAV+receipt per case, hash export,
verify before checkpoint accepted; ephemeral disk not durable. Storage
allowance verified, avoid repeated weight transfers; models cached only
where allowed, no private artifacts. Actual STARTED/FINISHED/elapsed,
provider job id, git/model/reference/plan digest, GPU, VRAM, dtype,
torch/CUDA/attention/seed, setup vs inference time, RTF, peak RAM/VRAM,
quota debit/cost, exit and artifact hashes. No invented ETAs.
Compare throughput end-to-end including cold start/download/queue time;
don't select by GPU brand alone. No automatic changes to production cache.

## Implementation phases (ordered, bundle routine work)
CLOUD-01: policy + provider matrix (this document). Approved public tests;
  existing production gamebox guard stays fail-closed. No hostname spoof
  or env bypass. No cloud TTS path yet.
CLOUD-02: isolated public runner and explicit allowlist export, frozen
  per-job manifest, bounded budget/time admission, public input-only
  guard before model load, tests for private/unknown input rejection,
  no import or production entrypoint changes. Separate cloud experimental
  entrypoint; runtime provider checks and receipts, not security attestation.
  Never relax require_gamebox for canonical production modules.
CLOUD-03: Kaggle notebook and CLI packaging (private notebook, public
  fixtures, Internet only for explicit verified downloads). Owner connects
  account once via official credential secret UI; no token in chat/code.
  Colab notebook same runner, owner starts from browser. No need for
  gamebox or Mac. Confirm real account quota and availability.
CLOUD-04: run one bounded public ALG04B pilot and Qwen benchmark (same
  approved fixture, 4 pairs or fewer initially), verify WAVs/receipts,
  native GPU/CPU compatibility and performance. No auto owner relisten
  before useful results. Keep legacy private gamebox plan intact.
CLOUD-05: Modal adapter optional only with verified spending safeguard
  and account access; Lightning/ZeroGPU only if clear need. No needless
  registration on all providers.
CLOUD-06: actual private chapter scope requires explicit owner data
  approval and review of provider visibility/terms/retention/access/
  licensing, per-provider transfer list and deletion/export policy;
  chapter-by-chapter approval unchanged. Do not block public work on it.

Owner need only connect Kaggle initially, then Colab if necessary; lead
does code, packaging, GitHub and analysis. Cloud account access is not
currently verified. No paid resource has been purchased or cloud TTS run.
