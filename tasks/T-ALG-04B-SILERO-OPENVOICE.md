# T-ALG-04B — explicit Russian stress + author tone color

Status: implementation in draft PR #47; CI and runtime unverified.
Pocket ALG-04: no promotion, no more synthesis; local close evidence still
pending. New direction separates pronunciation from timbre. No manuscript,
production, chapter 2, full-book render or automatic promotion.

## Pinned upstream evidence
- Silero source e382298387332f2bf461fe6eadfde99104611b0c:
  https://github.com/snakers4/silero-models/blob/e382298387332f2bf461fe6eadfde99104611b0c/README.md
  https://github.com/snakers4/silero-models/blob/e382298387332f2bf461fe6eadfde99104611b0c/LICENSE_CIS
  v5_cis_base MIT declaration, explicit + before stressed vowel, no auto
  stress/homographs, 24 kHz and SSML support. Fixed Russian speaker
  ru_bel_dmitriy chosen from documented ru_ prefixed speaker list; actual
  presence checked at load, no speaker shopping. Russian-only V5 and
  CIS Ext noncommercial licenses excluded.
- Official asset https://models.silero.ai/models/tts/ru/v5_cis_base.pt
  mutable URL, no independent publisher SHA-256 found. Local downloaded
  SHA frozen; do not misrepresent it as publisher authentication. It is
  executable torch.package pickle, not safe weights-only data. Review
  publisher trust, isolate OS-level with no network/secrets/private
  manuscript mounts; before loading require trusted-source acceptance.
- OpenVoice code https://github.com/myshell-ai/OpenVoice/tree/74a1d147b17a8c3092dd5430504bd83ef6c7eb23
  HF https://huggingface.co/myshell-ai/OpenVoiceV2/tree/fd981100305a0e4291f93a9ad169c6d9f7bed54a
  MIT declared, converter/checkpoint.pth SHA256
  9652c27e92b6b2a91632590ac9962ef7ae2b712e5c5b7f4c34ec55ee2b37ab9e
  published by HF. config v2, 22050 Hz, 1024 FFT, 256 hop, zero_g true.
  Code voice_conversion consumes spectrogram and source/target speaker
  embeddings, not Russian text. Cross-language fidelity unproven.
  Direct core avoids upstream full TTS/VAD/ASR/web stack and its dependency
  pins, stale STFT return_complex=False, permissive checkpoint loader.
  Use modern complex STFT equivalent, weights_only=True, strict=True;
  if model/checkpoint incompatible STOP, no blind relaxing missing keys,
  arbitrary pickle or runtime monkeypatch. Direct research core does not
  add optional downstream watermark; outputs must remain labeled synthesized
  research and private. License declarations are not independent legal
  clearance of training data. No production authorization.

## Single bounded experiment
Four public contextual sentences, two dev (замок homographs) and two heldout
(мука homographs), explicit stress on every multisyllabic word, same text for
before/after. One list sentence also exposes rhythm. All four Silero raw
utterances generated once, source embedding mean of those exact four
utterances, one clean local author mono 5–20s recording as target embedding.
No author-audio replacement or manual edits. Fixed seed 42, 8 CPU threads,
tau .3; no tuning. Source 24k -> native converter 22.05k; both listening
arms resampled from 22.05k to 24k, raw before/after preserved. This controls
resampling confound but does not make conversion lossless. Exactly 4 TTS
calls and 4 conversions, eight review clips. No repeated Qwen/Pocket runs.

Compare heard vowel ordinal, lexical integrity, author voice similarity,
rhythm and overall independently. Existing local HTML now has explicit
fields, plain sentence without stress markers and no condition identity.
Review count requires all fields and overall label. Both heldout baseline
and converted targets correct, lexical complete, converted voice acceptable,
no new rhythm regression or artifacts are minimum gate. If base stress
wrong, don't credit conversion; if converter alters stress/words, reject.
Unclear/blank no pass. Four cases not book-wide validation. Prior generic
OK/BAD labels did not establish control; do not ask owner to re-listen.

## Public-only provisioning
After exact latest green CI and owner dispatch, SOL on Mac: isolated env
using existing pinned huggingface_hub, run
`python -m audiobook.silero_openvoice_provision --out "$NEW_ASSETS"`.
Pin exact OV revision, MIT card, publisher Git blob config and LFS SHA
checkpoint. Only two HF files + official Silero file; verify sizes, digest
and config. Save publisher.json and inventory.json. Silero publisher digest
unavailable; report local SHA and source review. No private data.
Obtain clean pinned OV checkout and resolve hashed CPU dependencies in
separate env; only direct core plus torch/numpy/scipy/soundfile needed by
our runner, verify actual imports from pinned upstream (not full old
setup.py requirements). No global install. If unavailable, BLOCKED.
Do not start synthesis yet. Local model loading cannot be verified in
GitHub synthetic CI.

## Acoustic execution after separate GO
Verified gamebox only, persistent filesystem >=2GiB, >=15GiB available
RAM, canonical idle queue/lock, OS-level offline least-privilege isolation
(including trusted package import; HF flags not sandbox), external hard
timeout, actual PID/log/exit and timing. No production dependency changes.
Reference existing authorized clean mono WAV 5–20s, exact hash. On gamebox
dry-run:
`python -m audiobook.silero_openvoice_pilot --assets "$ASSETS" --inventory "$INVENTORY" --inventory-sha256 "$INV_SHA" --reference "$REF" --reference-sha256 "$REF_SHA" --upstream "$OV_CHECKOUT" --canonical-out "$CANONICAL_OUT" --out "$NEW_PLAN"`.
Run same args new out plus --execute --plan-sha256 "$PLAN_SHA" only
after approved frozen plan. No fallback or retries. Verify exact plan,
receipt/source/WAV hashes, READY and production controls; preserve originals.
Use local HTML `python -m audiobook.stress_pilot_review --source "$COPIED_RUN" --out "$NEW_REVIEW" --private-key "$SEPARATE_KEY" --expected-pairs 4 --policy silero-openvoice-control-v1`
and direct WAV fallback. Verify playback and export in actual browser.
Qualified local listener if available; owner only for useful comparison.
No main merge or production promotion.

## Lead implementation
silero_openvoice_provision.py, silero_openvoice_pilot.py, tests for marked
sentence, asset hash and resampling; review.py optional structured fields,
stress_pilot_review.py checks shared raw source hashes and blind key; tests
for eight players, structured fields and changed source rejection. These
are synthetic tests, not actual inference/CPU verification. Fixed single
speaker and sample cases are lead choices, not owner-approved production
settings. No download or TTS performed by lead.

## License evidence correction (2026-11-27)

Operator reported public provisioning BLOCKED: pinned HF model_info returns
card_data null, no files downloaded. Exact prior HEAD cce34ae CI success
independently verified. Official exact-revision HF tree and converter checkpoint
pages both display MIT; the checkpoint page explicitly lists our pinned SHA256.
Pinned publisher GitHub README blob a720f28d4b8735e57f3d42514a2d054e18aeb62f
at OV_SOURCE explicitly declares V1/V2 MIT and commercial use. Public publisher
release evidence is accepted for this exact repository/revision/checkpoint only.
This is not independent training-data rights clearance. New provisioner
requires exact API model ID, revision, publisher checkpoint SHA256, and
reviewed evidence record; missing API license uses that reviewed record,
explicit contradictory license always rejects. Evidence persisted in both
publisher and inventory JSON and checked before model load. No generic
missing-license exception or operator override. Existing Silero source trust
and mutable URL limitations unchanged. After latest exact green CI, SOL may
resume public provisioning in new output directory; no TTS/model loading.
Gamebox SSH timeout remains separate blocker. CPU dependency resolution is
not proof of native imports. No code change by operator.

## Power-outage progress: actual public provisioning PASS (2026-11-27)

GitHub Actions PR-triggered smoke run 45957660226 at 8d0a5bbfa26b18e559f7008bffc674a8aed5627b,
job 140367790948: actual provisioner executed successfully with HF hub 1.33.0.
All three public files downloaded; actual OpenVoice checkpoint publisher
SHA and config Git blob verified. No private data, model loading or TTS.
Observed exact SHA256:
- silero.pt ba41b18f6a707ad93605a162998865e7c087153d2e010a26dd02229dab0e672a
- config.json 9dfff60350b8c63f2c664efd92a61b2516efb22671466960f0e5dfebd881fa47
- checkpoint.pth 9652c27e92b6b2a91632590ac9962ef7ae2b712e5c5b7f4c34ec55ee2b37ab9e
Inventory SHA256 7955e05acf8188bf4d19c40510d885bf5eaf8333319f53ca5c21d6759a4f4165.
Silero and config hashes are now frozen in source; changed byte identities
reject even if local inventory rewritten. Silero observed SHA is not
publisher-signed. Cloud runner ephemeral, weights not persisted or uploaded;
local machine must still download same bytes. No repeated cloud downloads
on subsequent commits (explicit smoke commit gate).

Added silero_openvoice_score.py with nine synthetic tests. Local read-only
unblinding verifies READY/plan/receipts, page/key, all labels and source/review
WAV digests, arm identity and target. Explicit categorical stress/lexical/
voice/rhythm ratings only. Development counts separate; heldout gate requires
both baseline and converted correct stress and lexical integrity, candidate
voice yes, no rhythm regression and candidate overall OK. Blank fields on
any clip prevent diagnostic pass. Unclear heldout required measurements
fail; no automatic production authorization. Score command after local review:
`python -m audiobook.silero_openvoice_score --source "$COPIED_RUN" --review-dir "$REVIEW" --private-key "$KEY" --labels "$LABELS"`.
Outputs aggregate counts and case IDs/reasons, not private comments or audio.
This automates evidence checking/scoring, NOT machine listening or acoustic
stress recognition. Existing energy-based detector remains unreliable; no
new detector claimed. Latest CI must pass before local dispatch. Native
runtime, offline sandbox, voice and rhythm remain unverified. No new TTS.
