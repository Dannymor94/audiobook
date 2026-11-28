"""ALG-08: private descriptive voice similarity; never speaker identification or release approval."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re

import numpy as np

from audiobook.rhythm_acoustic_measure import frozen
from audiobook.chapter_quality import chapter_rows

MODEL_REPO = "Wespeaker/wespeaker-voxceleb-resnet34"
MODEL_REV = "ff1ac5bca8ef11e90662b879aa923979e0bd277b"
MODEL_NAME = "voxceleb_resnet34.onnx"
MODEL_SHA = "9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1"
MODEL_SIZE = 26534127
POLICY = "voice-similarity-wespeaker-v1"


def unit(x):
    v = np.asarray(x,dtype=np.float64)
    if v.shape != (256,) or not np.isfinite(v).all():
        raise ValueError("INVALID_EMBEDDING")
    norm = float(np.linalg.norm(v))
    if not np.isfinite(norm) or norm < 1e-8:
        raise ValueError("DEGENERATE_EMBEDDING")
    return v/norm


def cosine(a,b):
    return float(np.clip(np.dot(unit(a),unit(b)),-1.,1.))


def reference_profile(refs):
    if not 3 <= len(refs) <= 12:
        raise ValueError("THREE_TO_TWELVE_REFERENCES_REQUIRED")
    vectors = np.stack([unit(r) for r in refs])
    centroid = unit(vectors.mean(axis=0))
    # Leave-one-out comparison avoids scoring a reference against itself.
    loo = [cosine(v, unit(np.delete(vectors,i,axis=0).mean(axis=0)))
           for i,v in enumerate(vectors)]
    return centroid,dict(count=len(loo),loo_median=float(np.median(loo)),
                         loo_min=min(loo),loo_max=max(loo))


def compare_embedding(vector,centroid,profile):
    score = cosine(vector,centroid)
    return dict(cosine=score,reference_loo_median=profile["loo_median"],
                delta_from_reference_median=score-profile["loo_median"],
                below_observed_reference_range=score<profile["loo_min"],
                diagnostic_only=True)


def provision(out: Path):
    """Public bytes only; no model load or audio. New destination required."""
    from huggingface_hub import HfApi,hf_hub_download
    import shutil
    if out.exists() or not out.parent.is_dir():
        raise ValueError("NEW_OUTPUT_REQUIRED")
    info = HfApi(endpoint="https://huggingface.co",token=False).model_info(
        MODEL_REPO,revision=MODEL_REV,files_metadata=True,token=False)
    if info.id!=MODEL_REPO or info.sha!=MODEL_REV:
        raise ValueError("MODEL_REVISION_MISMATCH")
    card = info.card_data
    # Unlike a missing license, contradictory metadata always blocks.
    # This exact LFS pointer revision has a publisher-declared Apache-2.0
    # license on its official commit page; preserve reviewed evidence.
    license_value = card.get("license") if card is not None else None
    if license_value not in (None,"apache-2.0"):
        raise ValueError("MODEL_LICENSE_CONFLICT")
    s = next((s for s in info.siblings or [] if s.rfilename==MODEL_NAME),None)
    if s is None or s.size!=MODEL_SIZE or getattr(s.lfs,"sha256",None)!=MODEL_SHA:
        raise ValueError("PUBLISHER_DIGEST_MISMATCH")
    cached = hf_hub_download(MODEL_REPO,MODEL_NAME,revision=MODEL_REV,token=False)
    out.mkdir(mode=0o700)
    path=out/MODEL_NAME
    shutil.copyfile(cached,path)
    if path.stat().st_size!=MODEL_SIZE:
        raise ValueError("MODEL_SIZE_MISMATCH")
    frozen(path,MODEL_SHA)
    print(json.dumps(dict(repo=MODEL_REPO,revision=MODEL_REV,sha256=MODEL_SHA,
                          license="apache-2.0",api_license=license_value,
                          evidence=f"https://huggingface.co/{MODEL_REPO}/commit/{MODEL_REV}")))
    return 0


def load_encoder(model_path: Path):
    import onnxruntime as ort
    data = frozen(model_path,MODEL_SHA)
    if len(data)!=MODEL_SIZE:
        raise ValueError("MODEL_SIZE_MISMATCH")
    opts=ort.SessionOptions()
    opts.intra_op_num_threads=4
    opts.inter_op_num_threads=1
    opts.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
    session=ort.InferenceSession(data,sess_options=opts,providers=["CPUExecutionProvider"])
    ins,outs=session.get_inputs(),session.get_outputs()
    if (len(ins)!=1 or len(outs)!=1 or ins[0].name!="feats" or outs[0].name!="embs"
            or ins[0].type!="tensor(float)" or len(ins[0].shape)!=3
            or ins[0].shape[-1]!=80 or outs[0].shape[-1]!=256):
        raise ValueError("UNEXPECTED_ONNX_CONTRACT")
    return session


def embed(session,data: bytes,*,minimum_s: float):
    import soundfile as sf
    import torch
    import torchaudio
    audio,sr=sf.read(io.BytesIO(data),dtype="float32")
    if (audio.ndim!=1 or not 8000<=sr<=96000
            or not minimum_s*sr<=len(audio)<=30*sr or not np.isfinite(audio).all()
            or float(np.sqrt(np.mean(audio.astype(np.float64)**2)))<1e-4):
        raise ValueError("UNSUITABLE_AUDIO")
    # Documented WeSpeaker inference: 16kHz, 80 mel bins, 25ms/10ms,
    # Hamming, utterance mean normalization, PCM16-scale amplitudes.
    # No VAD/cropping/rescaling by peak or synthesis.
    x=torch.from_numpy(audio.copy())[None]*32768.
    if sr!=16000:
        x=torchaudio.functional.resample(x,sr,16000)
    feats=torchaudio.compliance.kaldi.fbank(x,num_mel_bins=80,frame_length=25,
                                           frame_shift=10,sample_frequency=16000,
                                           window_type="hamming",dither=0.)
    feats=(feats-feats.mean(dim=0)).unsqueeze(0).numpy().astype(np.float32)
    result=session.run(["embs"],{"feats":feats})[0]
    if result.shape!=(1,256):
        raise ValueError("UNEXPECTED_EMBEDDING_SHAPE")
    return unit(result[0])


def prepare(manifest,plan,root):
    rows=chapter_rows(manifest)
    if plan["policy"]!=POLICY or plan["manifest_sha256"]!=hashlib.sha256(manifest).hexdigest():
        raise ValueError("MANIFEST_MISMATCH")
    refs,candidates=plan["references"],plan["candidates"]
    if not 3<=len(refs)<=12 or not 1<=len(candidates)<=64:
        raise ValueError("BOUNDED_INVENTORY_REQUIRED")
    seen=set()
    snapshots={}
    def read(item):
        name=item["wav"]
        if not re.fullmatch(r"[a-zA-Z0-9_-]+\.wav",name):
            raise ValueError("UNSAFE_WAV_NAME")
        path=root/name
        d=item["wav_sha256"]
        if d in seen or path in snapshots:
            raise ValueError("DUPLICATE_AUDIO")
        data=frozen(path,d)
        seen.add(d)
        snapshots[path]=d
        return data
    reference_bytes=[]
    for r in refs:
        if (r.get("author_recording") is not True
                or r.get("independent_of_synthesis_reference") is not True
                or r.get("clean_single_speaker_reviewed") is not True):
            raise ValueError("INDEPENDENT_REFERENCE_REQUIRED")
        reference_bytes.append(read(r))
    by_id={}
    for c in candidates:
        cid=c["id"]
        if (cid in by_id or cid not in rows or rows[cid]["status"]!="done"
                or rows[cid]["hash"]!=c["hash"]):
            raise ValueError("CANDIDATE_IDENTITY_MISMATCH")
        by_id[cid]=(c,read(c))
    return reference_bytes,by_id,snapshots


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--provision",type=Path)
    for name in ("manifest","plan","audio-root","canonical-chunks","canonical-out","model","out"):
        p.add_argument("--"+name,type=Path)
    for name in ("manifest","plan"):
        p.add_argument("--"+name+"-sha256")
    p.add_argument("--execute",action="store_true")
    a=p.parse_args()
    if a.provision is not None:
        if a.execute or a.manifest is not None or a.plan is not None:
            raise ValueError("PROVISION_ONLY")
        return provision(a.provision)
    if any(getattr(a,n) is None for n in ("manifest","plan","audio_root",
                "canonical_chunks","canonical_out","model","out","manifest_sha256","plan_sha256")):
        raise ValueError("COMPLETE_PRIVATE_INPUTS_REQUIRED")
    import os
    from audiobook.gamebox import require_gamebox
    require_gamebox()
    if any(os.environ.get(k)!="1" for k in ("HF_HUB_OFFLINE","TRANSFORMERS_OFFLINE")):
        raise ValueError("OFFLINE_FLAGS_REQUIRED")
    from audiobook import paths,jobqueue
    from audiobook.rhythm_pilot import preflight
    from unittest.mock import patch
    canonical=a.canonical_out.resolve(strict=True)
    out=a.out.resolve()
    if (out.exists() or any(out.is_relative_to(r) for r in
           (paths.ROOT.resolve(),canonical,a.audio_root.resolve(),a.canonical_chunks.resolve()))
            or not (canonical/"queue").is_dir() or os.environ.get(jobqueue.LOCK_HELD_ENV)):
        raise ValueError("ISOLATED_OUTPUT_AND_LOCK_REQUIRED")
    preflight(out.parent.resolve(strict=True))
    manifest=frozen(a.manifest,a.manifest_sha256)
    plan_bytes=frozen(a.plan,a.plan_sha256)
    refs,by_id,snapshots=prepare(manifest,json.loads(plan_bytes),a.audio_root)
    for cid,(c,_) in by_id.items():
        frozen(a.canonical_chunks/f"{cid}.wav",c["wav_sha256"])
    frozen(a.model,MODEL_SHA)
    if not a.execute:
        print(json.dumps(dict(status="PREFLIGHT_ONLY",references=len(refs),
                              candidates=len(by_id),release_ready=False)))
        return 0
    with patch.object(jobqueue,"queue_root",return_value=canonical/"queue"), jobqueue.heavy_command_lock("voice-similarity"):
        if any(j.get("status") in ("pending","running","unreadable") for j in jobqueue.list_jobs()):
            raise ValueError("CANONICAL_QUEUE_NOT_IDLE")
        import torch
        import importlib.metadata
        torch.set_num_threads(4)
        session=load_encoder(a.model)
        centroid,profile=reference_profile([embed(session,x,minimum_s=5) for x in refs])
        rows=[]
        for cid,(c,data) in by_id.items():
            try:
                vector=embed(session,data,minimum_s=2)
            except ValueError as exc:
                if str(exc)!="UNSUITABLE_AUDIO":
                    raise
                rows.append(dict(id=cid,hash=c["hash"],wav_sha256=c["wav_sha256"],
                                 status="uncertain",reason="unsuitable_audio"))
                continue
            rows.append(dict(id=cid,hash=c["hash"],wav_sha256=c["wav_sha256"],
                             status="measured",**compare_embedding(vector,centroid,profile)))
        for path,d in snapshots.items():
            frozen(path,d)
        for cid,(c,_) in by_id.items():
            frozen(a.canonical_chunks/f"{cid}.wav",c["wav_sha256"])
        frozen(a.manifest,a.manifest_sha256)
        frozen(a.plan,a.plan_sha256)
        frozen(a.model,MODEL_SHA)
        measured=[r for r in rows if r["status"]=="measured"]
        summary=dict(policy=POLICY,manifest_sha256=a.manifest_sha256,
                     plan_sha256=a.plan_sha256,model_sha256=MODEL_SHA,
                     candidates=len(rows),measured=len(measured),
                     uncertain=len(rows)-len(measured),
                     median_cosine=float(np.median([r["cosine"] for r in measured])) if measured else None,
                     below_observed_reference_range=sum(r["below_observed_reference_range"] for r in measured),
                     reference_profile=profile,release_ready=False,
                     versions={n:importlib.metadata.version(n) for n in ("torch","torchaudio","onnxruntime","numpy","soundfile")})
        out.mkdir(mode=0o700,exist_ok=False)
        (out/"voice_PRIVATE.json").write_text(json.dumps(rows,indent=2),encoding="utf-8")
        (out/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
        # No raw embeddings, reference centroid, audio or text saved/exported.
        print(json.dumps(summary))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
