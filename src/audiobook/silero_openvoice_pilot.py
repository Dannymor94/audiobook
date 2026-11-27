"""ALG-04B: four contextual Russian sentences, before/after voice conversion.

Standalone research only. Never operates on manuscript or production audio.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter

from audiobook.pocket_preflight import sha
from audiobook.rhythm_pilot import preflight
from audiobook.silero_openvoice_provision import OV_SOURCE, verify_inventory

POLICY = "silero-openvoice-control-v1"
SPEAKER = "ru_bel_dmitriy"
SEED = 42
CASES = (
    ("01", "development", "На холм+е сто+ял з+амок.", "замок", 1),
    ("02", "development", "На двер+и вис+ел зам+ок.", "замок", 2),
    ("03", "heldout", "На стол+е леж+али хл+еб, с+ыр и мук+а.", "мука", 2),
    ("04", "heldout", "Э+то был+а насто+ящая м+ука.", "мука", 1),
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_cases(cases=CASES):
    vowels = "аеёиоуыэюя"
    for _, _, text, target, ordinal in cases:
        words = re.findall(r"[а-яё+]+", text.lower())
        found = []
        for word in words:
            plain = word.replace("+", "")
            if any(c not in "абвгдеёжзийклмнопрстуфхцчшщъыьэюя" for c in plain):
                raise ValueError("INVALID_WORD")
            if word.count("+") > 1 or ("+" in word and
                    (word.endswith("+") or word[word.index("+")+1] not in vowels)):
                raise ValueError("INVALID_STRESS_MARK")
            if sum(c in vowels for c in plain) > 1 and "+" not in word:
                raise ValueError("MISSING_MULTISYLLABLE_STRESS")
            if plain == target:
                if "+" not in word:
                    raise ValueError("MISSING_TARGET_STRESS")
                found.append(1+sum(c in vowels for c in word.split("+")[0]))
        if found != [ordinal]:
            raise ValueError("TARGET_ORDINAL_MISMATCH")


def make_plan(inv, reference_sha, versions):
    validate_cases()
    trials = []
    for cid, split, text, target, ordinal in CASES:
        ih = digest(text.encode("utf-8"))
        trials.append(dict(chunk_id=cid, chunk_hash=ih, split=split, status="planned",
                           seed=SEED, carrier=None, baseline_sha256=ih,
                           candidate_sha256=ih, text=text,
                           target=dict(word=target, vowel_ordinal=ordinal, split=split)))
    return dict(policy=POLICY, inventory=inv, reference_sha256=reference_sha,
                versions=versions, speaker=SPEAKER, seed=SEED, cpu_threads=8,
                tau=0.3, source_rate=24000, converter_rate=22050,
                review_rate=24000, trials=trials)


def valid_audio(wav, rate):
    import numpy as np
    if (wav.ndim != 1 or not rate <= len(wav) <= 30*rate
            or not np.isfinite(wav).all() or not np.any(wav)):
        raise ValueError("INVALID_AUDIO")
    return wav


def spec(wav, cfg):
    """Pinned upstream spectrogram math using modern complex STFT."""
    import torch
    data = cfg["data"]
    n, hop, win = (data[k] for k in ("filter_length", "hop_length", "win_length"))
    x = torch.from_numpy(wav).float()[None]
    x = torch.nn.functional.pad(x[:, None], ((n-hop)//2, (n-hop)//2),
                                mode="reflect").squeeze(1)
    stft = torch.stft(x, n, hop_length=hop, win_length=win,
                      window=torch.hann_window(win), center=False,
                      normalized=False, onesided=True, return_complex=True)
    return torch.sqrt(stft.abs().square()+1e-6)


def resample(wav, source, target):
    import numpy as np
    from math import gcd
    from scipy.signal import resample_poly
    g = gcd(source, target)
    return np.asarray(resample_poly(wav, target//g, source//g), dtype=np.float32)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("assets", "inventory", "reference", "upstream", "canonical-out", "out"):
        p.add_argument("--"+key, type=Path, required=True)
    p.add_argument("--inventory-sha256", required=True)
    p.add_argument("--reference-sha256", required=True)
    p.add_argument("--plan-sha256")
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    from audiobook.gamebox import require_gamebox
    require_gamebox()
    if a.execute and not a.plan_sha256:
        raise ValueError("FROZEN_PLAN_REQUIRED")
    if any(os.environ.get(k) != "1" for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")):
        raise ValueError("OFFLINE_FLAGS_REQUIRED")
    from audiobook import paths, jobqueue
    from unittest.mock import patch
    canonical = a.canonical_out.resolve(strict=True)
    upstream = a.upstream.resolve(strict=True)
    out = a.out.resolve()
    if (out.exists() or any(out.is_relative_to(r) for r in
            (canonical, paths.ROOT.resolve(), upstream, a.assets.resolve()))
            or not (canonical/"queue").is_dir() or os.environ.get(jobqueue.LOCK_HELD_ENV)):
        raise ValueError("ISOLATED_OUTPUT_AND_LOCK_REQUIRED")
    preflight(out.parent.resolve(strict=True))
    def git(*args):
        return subprocess.check_output(["git", "-C", str(upstream), *args], text=True).strip()
    def verify():
        if (git("rev-parse", "HEAD") != OV_SOURCE
                or git("status", "--porcelain", "--untracked-files=all")
                or sha(a.inventory) != a.inventory_sha256
                or sha(a.reference) != a.reference_sha256):
            raise ValueError("INPUT_IDENTITY_MISMATCH")
        return verify_inventory(a.assets, json.loads(a.inventory.read_bytes()))
    inv = verify()
    versions = {n: importlib.metadata.version(n) for n in
                ("torch", "numpy", "scipy", "soundfile", "librosa")}
    versions["python"] = sys.version
    plan = make_plan(inv, a.reference_sha256, versions)
    data = json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()
    if a.execute and digest(data) != a.plan_sha256:
        raise ValueError("FROZEN_PLAN_MISMATCH")
    with patch.object(jobqueue, "queue_root", return_value=canonical/"queue"), jobqueue.heavy_command_lock("silero-openvoice"):
        if any(j.get("status") in ("pending", "running", "unreadable") for j in jobqueue.list_jobs()):
            raise ValueError("CANONICAL_QUEUE_NOT_IDLE")
        out.mkdir(mode=0o700, exist_ok=False)
        (out/"plan_PRIVATE.json").write_bytes(data)
        if not a.execute:
            print("PLANNED_ONLY: "+digest(data))
            return 0
        # The operator must enforce OS-level offline sandboxing and review
        # trusted Silero package provenance before its executable pickle load.
        import numpy as np
        import soundfile as sf
        import torch
        torch.set_num_threads(8)
        torch.manual_seed(SEED)
        started = datetime.now(timezone.utc).isoformat()
        clock = perf_counter()
        ref, sr = sf.read(a.reference, dtype="float32")
        if ref.ndim != 1 or not 5*sr <= len(ref) <= 20*sr:
            raise ValueError("MONO_CLEAN_REFERENCE_5_TO_20_SECONDS_REQUIRED")
        ref = valid_audio(resample(ref, sr, 22050), 22050)
        model = torch.package.PackageImporter(str(a.assets/"silero.pt")).load_pickle("tts_models", "model")
        model.to(torch.device("cpu"))
        if SPEAKER not in model.speakers:
            raise ValueError("PINNED_SPEAKER_UNAVAILABLE")
        native = {}
        timings = {}
        with torch.no_grad():
            for t in plan["trials"]:
                cid = t["chunk_id"]
                t0 = perf_counter()
                torch.manual_seed(SEED)
                wav = model.apply_tts(text=t["text"], speaker=SPEAKER, sample_rate=24000)
                native[cid] = valid_audio(wav.detach().cpu().numpy(), 24000)
                sf.write(out/f"{cid}_silero_raw.wav", native[cid], 24000, subtype="FLOAT")
                timings[cid] = perf_counter()-t0
        del model
        sys.path.insert(0, str(upstream))
        from openvoice.models import SynthesizerTrn
        if Path(sys.modules["openvoice.models"].__file__).resolve() != upstream/"openvoice/models.py":
            raise ValueError("UNEXPECTED_CONVERTER_MODULE")
        cfg = json.loads((a.assets/"config.json").read_bytes())
        converter = SynthesizerTrn(len(cfg.get("symbols", [])),
                                  cfg["data"]["filter_length"]//2+1,
                                  n_speakers=cfg["data"]["n_speakers"],
                                  **cfg["model"]).cpu().eval()
        ckpt = torch.load(a.assets/"checkpoint.pth", map_location="cpu", weights_only=True)
        converter.load_state_dict(ckpt["model"], strict=True)
        del ckpt
        with torch.no_grad():
            source_wavs = {k: resample(v, 24000, 22050) for k,v in native.items()}
            source_specs = {k: spec(v, cfg) for k,v in source_wavs.items()}
            source_se = torch.stack([converter.ref_enc(v.transpose(1,2)).unsqueeze(-1)
                                    for v in source_specs.values()]).mean(0)
            target_se = converter.ref_enc(spec(ref, cfg).transpose(1,2)).unsqueeze(-1)
            if not torch.isfinite(source_se).all() or not torch.isfinite(target_se).all():
                raise ValueError("INVALID_SPEAKER_EMBEDDING")
            with (out/"receipts_PRIVATE.jsonl").open("x", encoding="utf-8") as log:
                for t in plan["trials"]:
                    cid = t["chunk_id"]
                    t0 = perf_counter()
                    s = source_specs[cid]
                    torch.manual_seed(SEED)
                    converted = converter.voice_conversion(
                        s, torch.LongTensor([s.size(-1)]), sid_src=source_se,
                        sid_tgt=target_se, tau=0.3)[0][0,0].cpu().float().numpy()
                    valid_audio(converted, 22050)
                    sf.write(out/f"{cid}_converted_raw.wav", converted, 22050, subtype="FLOAT")
                    # Matched 22.05k -> 24k review rate; originals preserved.
                    for arm, x, elapsed in (("baseline", source_wavs[cid], timings[cid]),
                                           ("candidate", converted, perf_counter()-t0)):
                        wav = valid_audio(resample(x, 22050, 24000), 24000)
                        path = out/f"{cid}_{arm}.wav"
                        sf.write(path, wav, 24000, subtype="FLOAT")
                        rec = dict(chunk_id=cid, arm=arm, status="generated", seed=SEED,
                                   carrier=None, plan_sha256=digest(data),
                                   input_sha256=t[arm+"_sha256"], generation=plan["inventory"],
                                   source_wav_sha256=sha(out/f"{cid}_silero_raw.wav"),
                                   wav=path.name, wav_sha256=sha(path), samples=len(wav),
                                   elapsed_s=elapsed)
                        log.write(json.dumps(rec)+"\n")
                        log.flush()
                        os.fsync(log.fileno())
        if verify() != inv:
            raise ValueError("INPUTS_CHANGED")
        (out/"READY_PRIVATE.json").write_text(json.dumps({
            "pairs": 4, "plan_sha256": digest(data),
            "receipts_sha256": sha(out/"receipts_PRIVATE.jsonl"),
            "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": perf_counter()-clock}), encoding="utf-8")
    print("READY: four before/after voice conversion pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
