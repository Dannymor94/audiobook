# CLOUD-03: first Kaggle public GPU smoke

Owner account screenshot shows GPU 0/30h, TPU 0/20h, private dataset/model
storage 0/214.75GB each. GPU quota is weekly, actual API quota required.
Account verification completed per owner; token presence not assumed.

First bounded experiment authorized 2026-11-27: exact fixed public Silero
v5 CIS Base, ru_bel_dmitriy stock voice; four synthetic Russian phrases,
no manuscript, author recordings, clone, private datasets or production
cache. No Qwen/OpenVoice yet. Separate entrypoint cloud/kaggle/public_smoke.py
does CUDA probe, checks GPU memory, downloads official package in temporary
directory, verifies pinned SHA256 before executable pickle load, then uses
CUDA only. Records GPU, versions, download/load/inference time, duration/RTF
and each PCM WAV SHA. Internet enabled for public download; offline flags
are not OS sandbox. No credentials passed to notebook; no attached data.
No production guard modifications.

Controller cloud/kaggle/submit_smoke.py uses official kaggle==2.2.5 CLI,
auth via GitHub secret KAGGLE_API_TOKEN (not printed), reads actual quota,
requires >=1h remaining before 600s max job, unique slug from run ID,
private script kernel, T4 accelerator request, checks exact returned
version and polls terminal state, downloads outputs and validates 4 WAV
hashes and headers. No automatic retry/resubmission. Small verified
public output artifact retained three days. No paid resources. 
Workflow .github/workflows/kaggle-public-smoke.yml triggered only by exact
one-shot commit on same-repo research PR and first run attempt; no arbitrary
repo upload. Actual GPU allocation, compatibility and render success
unverified until output receipt verified. If missing secret, owner adds
secret through GitHub UI; then lead explicitly triggers a new bounded
workflow commit, not a blind retry. Never post token in chat.

Initial exact HEAD 24d3c4d1ee07830a045d839370334866df879eea
CI 46019695304, Kaggle workflow 46019695614. Controller job
140575819018 reached quota/render step. No confirmed Kaggle submission
or render yet at time of this record.
