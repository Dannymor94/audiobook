# T-ALG-04 — explicit pronunciation and voice control

Status: DESKTOP RESEARCH / NO SYNTHESIS AUTHORIZED
Date: 2026-11-26. Depends on closed ALG-03, not on successful promotion.
Retain existing Qwen stock baseline and all private accepted artifacts. No main
merge, no chapter 2 or full render, no manual waveform repair.

## Decision basis
ALG-02 uppercase failed quality; ALG-03 syntax heldout recall 0/7, actuator
overall 2 wins/1 tie/1 loss, heldout 1/0/1, stress complaints 2 vs 2 and no
direct rhythm evidence. Stop stress spelling/case/punctuation/seed-only
iterations. Correct lexical stress map remains useful, not acoustic proof.

## Candidate screen (public upstream sources, no weights loaded)

1. Pocket TTS phoneme community model (primary phoneme feasibility candidate):
https://huggingface.co/gabrione/pocket-tts-phonemes-multilang
https://huggingface.co/gabrione/pocket-tts-phonemes-multilang/tree/main
https://github.com/kyutai-labs/pocket-tts
https://huggingface.co/kyutai/pocket-tts
Community card declares 14 languages including Russian, word-level IPA with
primary/secondary stress, voice reference cloning, 24-layer derivative,
0.3B parameter model, ~1.34 GB weights. Card declares CC BY 4.0 weights,
base CC BY 4.0, MLS/FLEURS CC BY 4.0, Common Voice 17 CC0. Bundled lexicon/
rules CC BY-SA 4.0; use separate existing vetted stress map and explicit
approved G2P convention; review attribution and exact upstream provenance.
Official Pocket TTS CPU claims are not measurements of this fine-tune.
Official base currently does not natively support Russian. Community card
reports word stress listening in Italian, not Russian; ASR WER not stress.
Most serious limitation: input removes punctuation and lacks question
intonation. Not production-ready for expressive audiobook. Use only as a
diagnostic candidate for explicit phoneme/stress controllability; don't
pretend arbitrary IPA edits work. Pin actual full revision, tokenizer,
config, codec and library; inspect model.yaml/loading API, establish fully
offline load, reject unknown tokens and prove stress contrasts in token IDs.
Do not blindly trust auto-generated HF quickstart (uses orthographic English).
The card's fallback rule table Russian stress-inclusive exactness 0.460 is
G2P evaluation, not acoustic accuracy; cannot use fallback as ground truth.

2. Silero CIS base + OpenVoice V2 (secondary, more complete conceptual
architecture for audiobook):
https://github.com/snakers4/silero-models
https://github.com/snakers4/silero-models/wiki/SSML
https://github.com/snakers4/silero-models/blob/master/LICENSE_CIS
https://github.com/myshell-ai/OpenVoice
https://huggingface.co/myshell-ai/OpenVoiceV2
Silero v5_cis_base MIT per upstream, Russian ru_ speakers, mandatory explicit
+ stress before vowel, SSML break/rate/pitch support claimed. Fixed speakers,
not a zero-shot author clone. Russian-only V5 licenses differ; don't substitute
a noncommercial weight. OpenVoice V2 MIT declared, zero-shot tone-color
conversion, Russian not native base-TTS language. Cross-language conversion
of a complete Russian utterance is a hypothesis; may alter intelligibility,
timing or speaker similarity. Test full automated two-stage engine only,
never manually repair or splice existing Qwen audio. Verify exact source
and converter weight licenses/provenance, actual Russian conversion API,
CPU performance, offline dependencies and unchanged pronunciations. If
conversion destroys stress or voice, retire. This is not a decision to
replace existing author voice.

3. ESpeech-TTS-1_RL-V2 (defer):
https://huggingface.co/ESpeech/ESpeech-TTS-1_RL-V2
https://github.com/SWivid/F5-TTS
Russian F5-based code and RUAccent example, declared Apache 2.0 weights;
actual parent checkpoint/data lineage not confirmed, upstream F5 pretrained
weights CC BY-NC. No proof of reliable manual control or CPU performance.
Blocked for commercial adoption until ancestry clarified. No provisioning.

4. Piper (fallback for training route):
https://github.com/OHF-Voice/piper1-gpl
Direct eSpeak phoneme input and custom phoneme training documented; GPLv3
runtime, individual voices/training lineage differ. No established zero-shot
author voice; custom training requires authorized aligned dataset and
compute feasibility. Defer until simpler candidate evaluation. No training.

## Next gate (lead-owned, no operator task yet)
- Audit exact public model config/tokenizer/API and full revision/license
  inventory. No manuscript/ref upload; no inference provider.
- Prepare one reusable engine-neutral test protocol using public synthetic
  Russian homograph/stress contrasts and a few frozen private error cases
  only after technical feasibility. Separate tests of controllability
  (same phoneme sequence except intended stress, same reference/settings)
  and end-to-end voice/lexical fidelity/rhythm. Require explicit unknown
  token rejection and preserved source identity; no automatic stress fixes.
- At most one bounded primary engine trial after scope approval and exact
  CI. No repeated existing Qwen runs; reuse comparable verified baselines
  only if provenance and text match. Gamebox-only all TTS, CPU one worker,
  persistent isolated output, canonical heavy lock, no fallback, actual
  RAM/disk and timing evidence. Do not promise base model speeds.
- Use qualified local listener where available; avoid owner listening until
  a meaningful candidate is identified. Blind HTML with independent
  categorical fields for stress, lexical fidelity, target voice, rhythm,
  overall; no inference from general preference. Heldout remains separate;
  sample-level gates are not book-wide proof.
- Production promotion requires explicit owner approval, legal clearance,
  direct Russian acoustic evidence and voice/rhythm non-regression.
  If neither candidate can satisfy controls, consider rights-cleared
  phoneme-conditioned custom training, not more punctuation experiments.

No dependency, download, synthesis, code integration or production change
in this research checkpoint. Research is based on upstream declarations,
not independent license clearance or measured engine behavior.

## Source-level API audit and token-channel gate

Pinned upstream code: mynah-org/mynah-s2s commit
 a696db20e2877a080df503d9bad11f315a3429ff (public GitHub tree retrieved).
Inspect hybrid/tts/phonemes/batch.py, server.py, labs/phoneme_tts/ipa_words.py,
README.md and pyproject.toml at that exact revision. The stock HF quickstart
is misleading: upstream PhonemeBatchTTS.load constructs a local YAML replacing
weights_path, lookup_table.tokenizer_path, tokenizer format and n_bins=4000,
removing separate fallback weights. Its stream([(ipa, voice_latents)], seed=...)
passes raw IPA straight to the conditioner; no normal text preparation. Voice
latents use the first 5 s of a local reference by default. Upstream sampler
requires the trainer-compatible per-row pad state and 24-layer BOS-before-voice.
Reference environment Python 3.12, pocket-tts 4.0.1, torch 2.13.0 (recipe CUDA
index; CPU wheel compatibility must be verified), tokenizers 0.22.2,
phonemizer 3.6.0 and eSpeak-ng 1.51. Do not install the whole GPU voice-agent
stack or alter the audiobook venv. No global apt/system changes. Pin and hash
all actual wheels in a separate research environment.

Training stress tokens use byte fallback, not necessarily a dedicated token.
Upstream admits phone/energy stress metrics failed to separate models; the
Italian listening evidence does not establish Russian stress accuracy. A
controlled marker-only test demonstrates responsiveness, not correct Russian
phonetics: normative Russian evaluation must also account for vowel reduction,
palatalization and lexical context with separately reviewed phoneme strings.
Question/list prosody remains a known limitation; do not promote as audiobook
engine even if stress channel passes. Default sampler temp=.3, cfg=2.0,
voice_sec=5, max_frames=375, n_steps=1, eos_threshold=-1, eos_countdown=1 are
upstream evaluation defaults, not measured optimum for this author.

Added src/audiobook/pocket_preflight.py and five synthetic tests. It checks
four regular local assets (model.yaml, manifest.json, tokenizer.json,
model.safetensors), explicit full 40-hex revision and exact SHA-256 inventory,
Russian/stress manifest declaration, lossless token round-trip without unknown/
special IDs, distinct token sequences for four synthetic stress contrasts.
No model import/load, no inference, no acoustic proof. Synthetic probes are not
normative IPA for Russian words. Full artifact identity is operator-supplied;
self-computed hashes alone do not authenticate origin. This gate intentionally
fails closed if normalization alters probes or upstream schema differs.

BLOCKER: web access could retrieve the model card, but raw model.yaml,
manifest.json, HF model API and tree did not return usable bytes; container
network cannot resolve huggingface.co. Exact HF revision and asset hashes not
verified. Do not invent a revision or use rolling main for inference. No weights
or tokenizer downloaded by lead. Before a local test, obtain full model revision
from official HF metadata, save exact revision card, license/manifest/asset
metadata, verify publisher LFS SHA-256 of model.safetensors where available,
and ensure files are regular copies (not HF cache symlinks). Use pinned
huggingface_hub model_info/files_metadata and snapshot_download(revision=...,
allow_patterns=the four required files plus license/card) in public-only
provisioning. Record actual filenames/digests in JSON {repo_id,revision,files:
{filename:sha256}}; run preflight in isolated env with exact inventory SHA.
No private manuscript/reference used in provisioning. If license/revision or
manifest cannot be verified, stop; no substitution. Local preflight is not
permission for TTS. Next acoustic trial requires actual token evidence and
engine runner implementation, not just synthetic CI. Keep all existing Qwen
artifacts. No production changes.

## Public provisioning implementation

Added pocket_provision.py and two synthetic tests. After exact CI green, local
operator may run on Mac in separate research environment with exact pinned
huggingface_hub 1.33.0 and tokenizers 0.22.2:
`python -m audiobook.pocket_provision --out "$NEW_PUBLIC_ASSET_DIR"`.
First resolution obtains full commit from official HF API, immediately rereads
metadata by that immutable revision, requires declared CC-BY-4.0 and exact
publisher metadata for five files (including README). Uses Git blob SHA1 for
non-LFS files and publisher LFS SHA256 for weights; downloads only those files,
verifies size/digest, checks Russian/stress manifest and tokenizer before weights.
No automatic alternative model or revision, no private files, no inference,
no dependency changes to production, no gamebox needed. Record publisher.json,
inventory.json, revision and inventory SHA, actual tokenizer results from
pocket_preflight CLI with PyYAML 6.0.3. On failure preserve partial artifacts;
report exact blocker; do not silently loosen checks. This resolves metadata
locally only; synthetic tests do not establish actual HF API compatibility,
license provenance or Russian acoustic quality. Do not start TTS yet.
