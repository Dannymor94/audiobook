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
