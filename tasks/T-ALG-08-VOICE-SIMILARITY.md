# T-ALG-08 — independent descriptive speaker similarity

Research, not a production acceptance gate. Goal: prioritize potential
timbre drift without repeated full-chapter listening. No voice identity
verification or automatic release decision.

## Decision and public evidence

Selected WeSpeaker VoxCeleb ResNet34 (256-dimensional embeddings,
ONNX 26,534,127 bytes) instead of another Qwen/OpenVoice encoder, to avoid
direct dependence on the generator's own similarity representation.
Publisher declared Apache-2.0; exact release:
https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34/commit/ff1ac5bca8ef11e90662b879aa923979e0bd277b
SHA256 9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1.
Code inspected at
https://github.com/wenet-e2e/wespeaker/tree/9fecd6cb4f47475d01761d87c826298dff4ef18c
cli/speaker.py and bin/export_onnx.py: feats[B,T,80] -> embs[B,256],
16kHz mono, 80 mel bins, 25ms frame / 10ms shift, Hamming, utterance
mean normalization. Explicit zero dither, PCM16-scale float conversion,
CPU only, no VAD; runtime parity not yet measured. Exact asset and contract
verified by intended one-shot public smoke; do not claim PASS until logs
show PUBLIC_ENCODER_CONTRACT_PASS. Public synthetic feature matrix only,
no speech, author, manuscript, or TTS in cloud. No cloud model cache/upload.
Alternative SpeechBrain ECAPA Apache-2.0 not selected to avoid additional
dependencies and model trial. Publisher licenses are not independent
training-data rights clearance.

Research caveat: https://www.isca-archive.org/interspeech_2022/deja22_interspeech.pdf
compares embedding metrics to human perceptual judgments; 
https://onlinelibrary.wiley.com/doi/10.1111/1556-4029.15250
examines effects of language mismatch, duration and speech style.
Speaker similarity is not naturalness, rhythm, stress or intelligibility.
VoxCeleb-trained embeddings require validation for Russian audiobook audio.
No universal similarity threshold, no percentage of voice match.

## Implemented

voice_similarity.py: public provisioner verifies exact repo/revision/LFS
size/SHA, rejects contradictory license, uses reviewed publisher declaration
if API license absent. ONNX CPU session exact tensor contract; local
preflight and guarded execution on gamebox, existing audio only.
Three to twelve independent clean author references, 5–30s, not the
synthesis prompt; 1–64 candidate existing chapter WAVs, 2–30s. Match
manifest/chunk/WAV hashes and canonical candidate bytes, reject duplicates.
No new audio collection inferred from memory. Reference leave-one-out
cosines describe natural variability; candidate cosine against normalized
reference centroid, difference from observed reference median and below
observed range (exploratory review signal, not statistically calibrated).
Independent reference flags are operator assertions; if no independent
references exist BLOCKED. No raw embeddings or centroid saved. No source
changes, no render, no automatic approval.

`python -m audiobook.voice_similarity --provision "$NEW_PUBLIC_DIR"`
uses pinned HF hub; local CPU environment needs compatible pinned
torch/torchaudio, numpy, soundfile, onnxruntime (smoke 1.23.2).
Do not change production dependencies. On gamebox with actual offline
isolation and idle canonical lock:
`python -m audiobook.voice_similarity --manifest "$MANIFEST" --manifest-sha256 "$MANIFEST_SHA" --plan "$PLAN" --plan-sha256 "$PLAN_SHA" --audio-root "$PAIR_AUDIO" --canonical-chunks "$CHUNKS" --canonical-out "$CANONICAL_OUT" --model "$ONNX" --out "$NEW_REPORT"`
default preflight only; --execute after approved local diagnostic.
Plan schema {policy:"voice-similarity-wespeaker-v1",manifest_sha256:"...",
references:[{wav:"ref.wav",wav_sha256:"...",author_recording:true,
independent_of_synthesis_reference:true,clean_single_speaker_reviewed:true}],
candidates:[{id:"0001",hash:"...",wav:"candidate.wav",wav_sha256:"..."}]}.
No private input online. Aggregate only; voice_PRIVATE.json local only.

Chapter quality optional --voice-results and --voice-summary, both with
matching --<name>-sha256. Exact model/manifest/WAV/summary checked.
Below observed reference range enters review queue, not human defect.
Nine synthetic tests (eight voice math/inventory plus one report integration).
These are not acoustic accuracy tests. Actual waveform preprocessing,
reference inventory, native CPU runtime, Russian calibration and human
correspondence remain unverified. ALG-04B first local priority. No agents
while local machines unavailable. Latest CI and public smoke pending.
