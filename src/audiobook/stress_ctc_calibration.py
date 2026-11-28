"""ALG-05 local read-only acoustic calibration on frozen existing evidence."""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import re
import sys
import importlib.metadata

import numpy as np

from audiobook.pocket_preflight import sha
from audiobook.stress_acoustic_calibration import (
    validate_controls, word_windows, contextual_window, expected_form,
)
from audiobook.stress_consensus import VOWELS, WORD
from audiobook.stress_ctc_evidence import rank_hypotheses, decide, summarize_gold

REVISION = "2c733782da5604684829819a5eb744c193fe9398"
MODEL_ID = "facebook/wav2vec2-xlsr-53-espeak-cv-ft"
ASSETS = {"config.json", "vocab.json", "pytorch_model.bin"}
MARGINS = (.02, .05, .1, .2, .4)
FITS = (-5., -3., -2., -1.)
HEX = re.compile(r"[a-f0-9]{64}")


def frozen(path: Path, digest: str) -> bytes:
    if path.is_symlink() or not path.is_file() or not HEX.fullmatch(digest):
        raise ValueError("INVALID_FROZEN_FILE")
    data = path.read_bytes()
    import hashlib
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("FROZEN_FILE_MISMATCH:" + path.name)
    return data


def model_inventory(root, inv):
    if (root.name != REVISION or inv["revision"] != REVISION
            or inv["repo_id"] != MODEL_ID or set(inv["files"]) != ASSETS
            or root.is_symlink() or not root.is_dir()):
        raise ValueError("WRONG_RECOGNIZER")
    if set(p.name for p in root.iterdir()) != ASSETS:
        raise ValueError("UNEXPECTED_MODEL_FILES")
    for name, digest in inv["files"].items():
        p = root / name
        if p.is_symlink() or not p.is_file() or not HEX.fullmatch(digest) or sha(p) != digest:
            raise ValueError("MODEL_ASSET_MISMATCH:" + name)
    vocab = json.loads((root / "vocab.json").read_bytes())
    cfg = json.loads((root / "config.json").read_bytes())
    if (not vocab or any(type(v) is not int for v in vocab.values())
            or set(vocab.values()) != set(range(len(vocab)))
            or len(vocab) != cfg["vocab_size"] or vocab["<pad>"] != cfg["pad_token_id"]
            or cfg["model_type"] != "wav2vec2"):
        raise ValueError("VOCAB_CONFIG_MISMATCH")
    return vocab, cfg["pad_token_id"]


def prepare(rows, findings, controls, pronunciations, vocab, blank):
    selected = validate_controls(rows, findings, controls)
    if len(selected) > 64:
        raise ValueError("PILOT_LIMIT_64")
    row_map = {r["id"]: r for r in rows}
    forms = {}
    chunks = {}
    audio_hashes = {}
    for c in selected.values():
        split = c["split"]
        if split not in ("development", "heldout") or c.get("independently_reviewed") is not True:
            raise ValueError("INDEPENDENT_SPLIT_REQUIRED")
        # No repeated lexical form, source chunk or audio across splits.
        for table, key in ((forms, c["word"].lower().replace("ё", "е")),
                           (chunks, c["id"]), (audio_hashes, c["wav_sha256"])):
            if key in table and table[key] != split:
                raise ValueError("SPLIT_LEAKAGE")
            table[key] = split
        if not re.fullmatch(r"[0-9]+", c["id"]) or row_map[c["id"]]["status"] != "done":
            raise ValueError("INVALID_AUDIO_ROW")
        word = c["word"]
        n = sum(v.lower() in VOWELS for v in word)
        if c["gold"] != "lexical_error":
            expected_form(word, c["expected_index"])
            expected = sum(v.lower() in VOWELS for v in word[:c["expected_index"]+1])
            heard = c.get("heard_ordinal")
            if (type(heard) is not int or not 1 <= heard <= n
                    or (heard == expected) != (c["gold"] == "correct")):
                raise ValueError("INDEPENDENT_HEARD_ORDINAL_REQUIRED")
    # Require both classes before threshold fitting, not just favorable examples.
    for split in ("development", "heldout"):
        for gold in ("correct", "wrong_stress"):
            if sum(c["split"] == split and c["gold"] == gold for c in selected.values()) < 3:
                raise ValueError("INSUFFICIENT_GOLD:" + split + ":" + gold)
    # Reviewed IPA is supplied externally, never inferred from expected stress.
    # Each record is occurrence-specific so context-dependent variants stay bound.
    by_key = {(p["id"], p["ordinal"]): p for p in pronunciations}
    if len(by_key) != len(pronunciations) or set(by_key) != set(selected):
        raise ValueError("HYPOTHESIS_INVENTORY_MISMATCH")
    result = []
    for key, c in selected.items():
        p = by_key[key]
        if (p["hash"], p["word"], p.get("independently_reviewed")) != (c["hash"], c["word"], True):
            raise ValueError("HYPOTHESIS_IDENTITY_MISMATCH")
        n = sum(v.lower() in VOWELS for v in c["word"])
        expected_form(c["word"], c["expected_index"])
        expected = sum(v.lower() in VOWELS for v in c["word"][:c["expected_index"]+1])
        seqs = p["phones"]
        if set(seqs) != {str(i) for i in range(1, n+1)}:
            raise ValueError("ALL_STRESS_VARIANTS_REQUIRED")
        # Do not silently drop unsupported labels, whitespace or specials.
        unsupported = any(t not in vocab or t.startswith("<") or t in ("|", " ")
                          or vocab[t] == blank for seq in seqs.values() for t in seq)
        hypotheses = None if unsupported else {int(k): [vocab[t] for t in v] for k,v in seqs.items()}
        result.append(dict(control=c, expected_ordinal=expected, hypotheses=hypotheses,
                           vowel_positions=p["vowel_positions"]))
    return result


def calibrate(rows):
    dev = [r for r in rows if r["split"] == "development"]
    options = []
    for margin in MARGINS:
        for fit in FITS:
            signals = [decide(r["evidence"], expected_ordinal=r["expected_ordinal"],
                              min_margin=margin, min_fit=fit) for r in dev]
            false = sum(s == "stress_suspect" and r["gold"] != "wrong_stress"
                        for r,s in zip(dev, signals))
            caught = sum(s == "stress_suspect" and r["gold"] == "wrong_stress"
                         for r,s in zip(dev, signals))
            if false == 0 and caught > 0:
                options.append((caught, margin, fit))
    if not options:
        return None
    # Prefer greater recall, then stricter thresholds; no heldout data involved.
    _, margin, fit = max(options)
    return dict(min_margin=margin, min_fit=fit)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "audit", "controls", "asr", "hypotheses",
                 "model-inventory", "model-dir", "chunks-dir", "canonical-out", "out"):
        p.add_argument("--"+name, type=Path, required=True)
    for name in ("manifest", "audit", "controls", "asr", "hypotheses", "model-inventory"):
        p.add_argument("--"+name+"-sha256", required=True)
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    from audiobook.gamebox import require_gamebox
    require_gamebox()
    if any(os.environ.get(k) != "1" for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")):
        raise ValueError("OFFLINE_FLAGS_REQUIRED")
    from audiobook import paths, jobqueue
    from audiobook.rhythm_pilot import preflight
    from unittest.mock import patch
    canonical = a.canonical_out.resolve(strict=True)
    out = a.out.resolve()
    if (out.exists() or any(out.is_relative_to(r) for r in
            (canonical, paths.ROOT.resolve(), a.model_dir.resolve(), a.chunks_dir.resolve()))
            or not (canonical/"queue").is_dir() or os.environ.get(jobqueue.LOCK_HELD_ENV)):
        raise ValueError("ISOLATED_OUTPUT_AND_LOCK_REQUIRED")
    preflight(out.parent.resolve(strict=True))
    names = ("manifest", "audit", "controls", "asr", "hypotheses", "model_inventory")
    def read_inputs():
        return {n: frozen(getattr(a,n), getattr(a,n+"_sha256")) for n in names}
    data = read_inputs()
    rows = [json.loads(l) for l in data["manifest"].splitlines() if l.strip()]
    findings = [json.loads(l) for l in data["audit"].splitlines() if l.strip()]
    inv = json.loads(data["model_inventory"])
    vocab, blank = model_inventory(a.model_dir, inv)
    controls = json.loads(data["controls"])
    plan = prepare(rows, findings, controls, json.loads(data["hypotheses"]), vocab, blank)
    asr_list = json.loads(data["asr"])
    asr = {r["id"]: r for r in asr_list}
    required = {c["id"] for c in controls}
    if len(asr) != len(asr_list) or not required <= asr.keys():
        raise ValueError("ASR_INVENTORY_MISMATCH")
    wavs = {}
    for c in controls:
        cid = c["id"]
        if asr[cid]["wav_sha256"] != c["wav_sha256"]:
            raise ValueError("ASR_AUDIO_MISMATCH")
        if cid not in wavs:
            wavs[cid] = frozen(a.chunks_dir / f"{cid}.wav", c["wav_sha256"])
    if not a.execute:
        print(json.dumps(dict(status="PREFLIGHT_ONLY", controls=len(controls),
                              chunks=len(wavs), release_ready=False)))
        return 0
    # Operator must enforce external hard timeout and OS-level offline isolation.
    # Trust inventory digest from reviewed prior provisioning, not arbitrary local files.
    with patch.object(jobqueue, "queue_root", return_value=canonical/"queue"), jobqueue.heavy_command_lock("stress-ctc"):
        if any(j.get("status") in ("pending", "running", "unreadable") for j in jobqueue.list_jobs()):
            raise ValueError("CANONICAL_QUEUE_NOT_IDLE")
        import torch
        import soundfile as sf
        from transformers import Wav2Vec2ForCTC
        from audiobook.phoneme_check import _to16k
        torch.set_num_threads(8)
        model = Wav2Vec2ForCTC.from_pretrained(str(a.model_dir), local_files_only=True,
                                             weights_only=True, use_safetensors=False).cpu().eval()
        allowed = {i for t,i in vocab.items() if not t.startswith("<") and t not in ("|", " ") and i != blank}
        row_map = {r["id"]: r for r in rows}
        decoded = {cid: sf.read(io.BytesIO(data), dtype="float32") for cid,data in wavs.items()}
        results = []
        for item in plan:
            c = item["control"]
            cid = c["id"]
            audio, sr = decoded[cid]
            if audio.ndim != 1 or sr <= 0 or not np.isfinite(audio).all():
                raise ValueError("INVALID_AUDIO")
            text = row_map[cid]["text"]
            words = asr[cid]["words"]
            windows = word_windows(text, words, len(audio)/sr)
            window = windows.get(c["ordinal"]) if windows is not None else contextual_window(
                text, words, len(audio)/sr, c["ordinal"])
            e = dict(status="uncertain", reason="missing_window_or_phones")
            if window is not None and item["hypotheses"] is not None:
                start, end = window
                clip = audio[int(start*sr):int(end*sr)]
                if .1*sr <= len(clip) <= 5*sr:
                    x = _to16k(clip, sr)
                    if float(x.std()) > 1e-6:
                        x = (x-x.mean())/(x.std()+1e-7)
                        with torch.no_grad():
                            logits = model(torch.tensor(x[None], dtype=torch.float32)).logits
                            lp = logits.log_softmax(-1)[0].cpu().numpy()
                        e = rank_hypotheses(lp, item["hypotheses"],
                                            vowel_positions=item["vowel_positions"],
                                            blank=blank, allowed_phone_ids=allowed)
            results.append(dict(id=f"{cid}:{c['ordinal']}", split=c["split"], gold=c["gold"],
                                expected_ordinal=item["expected_ordinal"], evidence=e))
        thresholds = calibrate(results)
        for r in results:
            r["signal"] = decide(r["evidence"], expected_ordinal=r["expected_ordinal"],
                                 **thresholds) if thresholds is not None else "uncertain"
        summary = summarize_gold(results)
        summary.update(thresholds=thresholds, diagnostic_only=True,
                       calibration_status="FROZEN_DEV" if thresholds else "NO_DEV_THRESHOLD",
                       input_sha256={n:getattr(a,n+"_sha256") for n in names},
                       versions={n:importlib.metadata.version(n) for n in ("torch","transformers","numpy","soundfile","scipy")},
                       python=sys.version)
        if read_inputs() != data:
            raise ValueError("INPUTS_CHANGED")
        model_inventory(a.model_dir, inv)
        for c in controls:
            if frozen(a.chunks_dir / f"{c['id']}.wav", c["wav_sha256"]) != wavs[c["id"]]:
                raise ValueError("WAV_CHANGED")
        out.mkdir(mode=0o700, exist_ok=False)
        (out/"results_PRIVATE.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        (out/"summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
