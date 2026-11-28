"""Private, bounded QWEN-VOICE-CAST-01 operator; not a production command."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import gc
import hashlib
import html
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import time

PRODUCTION_HEAD = "03677041d4fbd06e072529092deaa0e37dc2560f"
SECTION = "08_glava_1_zver_vnutri_nas_instinkty_eto_ne"
CUSTOM = ["Ryan", "Aiden", "Uncle_Fu", "Eric", "Dylan"]
STYLE = "Read in Russian as a neutral, warm audiobook narrator, naturally and clearly, with measured calm pacing."
DESIGNS = {
    "Design_A": "A warm trustworthy adult male voice, native Russian, natural clear articulation, neutral warm audiobook narration, measured calm pacing.",
    "Design_B": "A mature mellow deep reflective male voice, native Russian, natural clear articulation, neutral warm audiobook narration, measured calm pacing.",
    "Design_C": "A natural native Russian conversational male narrator with no foreign accent, clear articulation, measured calm pacing.",
}
PARAMS = dict(temperature=1.0, do_sample=True, top_k=50, top_p=1.0,
              repetition_penalty=1.05, subtalker_dosample=True,
              subtalker_temperature=0.9, subtalker_top_k=50, subtalker_top_p=1.0)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024**2), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@contextmanager
def admission(a):
    # This is called before every model import/load, including direct invocation.
    from audiobook.gamebox import require_gamebox
    from audiobook.rhythm_pilot import preflight
    require_gamebox()
    preflight(a.out.parent)
    if (a.out.resolve().is_relative_to(a.production.resolve())
            or git(a.production, "rev-parse", "HEAD") != PRODUCTION_HEAD):
        raise RuntimeError("GAMEBOX_REQUIRED: isolation or production HEAD mismatch")
    if any(os.environ.get(k) != "1" for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")):
        raise RuntimeError("OFFLINE_REQUIRED")
    from audiobook import jobqueue
    if os.environ.get(jobqueue.LOCK_HELD_ENV):
        raise RuntimeError("NO_LOCK_BYPASS_ALLOWED")
    # Use the actual canonical production lock; no per-worktree queue.
    from unittest.mock import patch
    with patch.object(jobqueue, "queue_root", return_value=a.production / "out" / "queue"):
        with jobqueue.heavy_command_lock("qwen-voice-cast-01"):
            jobs = jobqueue.list_jobs()
            if any(j.get("status") in ("pending", "running", "unreadable") for j in jobs):
                raise RuntimeError("GAMEBOX_REQUIRED: canonical queue not idle")
            processes = subprocess.check_output(["ps", "-eo", "pid,args"], text=True)
            for line in processes.splitlines():
                if any(s in line for s in ("audiobook synth", "audiobook qc", "audiobook.worker", "qwen_cast_operator.py --stage")):
                    if line.strip().split()[0] != str(os.getpid()) and not any(s in line for s in ("sshd:", "sh -c", "bash -c", "grep")):
                        raise RuntimeError("GAMEBOX_REQUIRED: competing process: " + line)
            yield


def configure(a):
    from audiobook import paths
    paths.MODELS = a.production / "models"
    paths.BIN = a.production / "bin"
    paths.TEXT = a.production / "text"
    paths.REF = a.production / "ref"
    paths.OUT = a.out / "work"
    paths.apply_env_defaults()


def inputs(a):
    p = a.production
    files = [p / "config.yaml", p / "text" / "pronounce.yaml",
             p / "ref" / "ref_ch1.wav", p / "ref" / "ref_ch1.txt",
             p / "ref" / "ref_ch1.latents_1.7b.pt",
             p / "out" / "sections" / SECTION / "manifest.jsonl"]
    # Text preparation uses the existing book-derived ё map, without changing it.
    files.extend(sorted((p / "text").glob("*.norm.txt")))
    return {str(f.relative_to(p)): sha(f) for f in files}


def verify_assets(a, plan):
    for kind in ("CustomVoice", "VoiceDesign"):
        mf = a.out / "models" / (kind + ".json")
        if sha(mf) != plan["model_manifests"][kind]:
            raise RuntimeError("MODEL_MANIFEST_CHANGED")
        for r in read(mf)["files"]:
            f = a.out / "models" / kind / r["path"]
            if f.stat().st_size != r["size"] or sha(f) != r["sha256"]:
                raise RuntimeError("MODEL_FILE_CHANGED")


def plan_stage(a):
    import soundfile as sf
    import yaml
    from audiobook import synth
    from audiobook.pronounce import load_table
    from audiobook.assemble import _trim_bounds
    if (a.out / "plan_PRIVATE.json").exists():
        raise RuntimeError("PLAN_EXISTS")
    src = a.production / "out" / "sections" / SECTION
    rows = [json.loads(l) for l in (src / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    selected = rows[2:10]
    assert [r["id"] for r in selected] == [f"{i:04}" for i in range(3, 11)]
    assert all(r["status"] == "done" and r["text"].rstrip().endswith((".", "!", "?", "»")) for r in selected)
    config = yaml.safe_load((a.production / "config.yaml").read_text(encoding="utf-8"))
    table = load_table(a.production / "text" / "pronounce.yaml")
    frozen = []
    chars = 0
    durations = []
    for r in selected:
        wav = src / "chunks" / (r["id"] + ".wav")
        audio, sr = sf.read(wav, dtype="float32")
        assert sr == 24000 and audio.ndim == 1
        start, end = _trim_bounds(audio)
        durations.append((end-start)/sr)
        text, phrase = synth.prepare_synth_text(r["text"], config, table,
            config["model"].get("sentinel", " ."), phrase=r.get("leadin"), open_end=r.get("open_end", False))
        cap = synth.max_tokens_for_text(text, **synth.cap_params(config))
        frozen.append(dict(row=r, wav_sha256=sha(wav), synth_text=text, phrase=phrase,
                           max_new_tokens=cap, span=[chars, chars+len(r["text"])]))
        chars += len(r["text"])+1
    duration = sum(durations) + sum(r["pause_after_ms"] for r in selected[:-1])/1000
    assert 80 <= duration <= 100
    base = synth._local_snapshot("1.7B")
    model_manifest = {kind:sha(a.out / "models" / (kind+".json")) for kind in ("CustomVoice", "VoiceDesign")}
    versions = {}
    from importlib.metadata import version
    for name in ("qwen-tts", "torch", "transformers", "faster-whisper"):
        versions[name] = version(name)
    data = dict(task="QWEN-VOICE-CAST-01", created_at=now(), host=socket.gethostname(),
        production_head=PRODUCTION_HEAD, operator_head=git(Path(__file__).resolve().parents[1], "rev-parse", "HEAD"),
        operator_sha256=sha(Path(__file__)), inputs=inputs(a), rows=frozen, config=config,
        model_manifests=model_manifest, base_snapshot=str(base),
        base_files={str(f.relative_to(base)):sha(f) for f in sorted(base.rglob("*")) if f.is_file()},
        versions=versions, seed=42, params=PARAMS, custom_speakers=CUSTOM, custom_instruction=STYLE,
        designs=DESIGNS, reference_text=selected[0]["text"], reference_max_new_tokens=360,
        language="russian", original_speech_s=sum(durations), original_assembled_s=duration,
        source_text_sha256=hashlib.sha256("\n".join(r["text"] for r in selected).encode()).hexdigest(),
        comparison="CustomVoice direct vs VoiceDesign reference -> Base clone; end-to-end, not speaker-only")
    verify_assets(a, data)
    write(a.out / "plan_PRIVATE.json", data)
    (a.out / "plan.sha256").write_text(sha(a.out / "plan_PRIVATE.json")+"\n", encoding="utf-8")
    print("FROZEN_PLAN", sha(a.out / "plan_PRIVATE.json"), "CONTROL_SECONDS", duration, flush=True)


def validate_audio(wav, sr, cap):
    import numpy as np
    if sr != 24000 or wav.ndim != 1 or not len(wav) or not np.isfinite(wav).all() or not np.any(wav):
        raise RuntimeError("INVALID_AUDIO")
    if len(wav)/sr >= cap/12*0.95:
        raise RuntimeError("TOKEN_CAP_REACHED_NO_RETRY")


def generate_once(a, dest, model, mode, text, cap, **kwargs):
    import numpy as np
    import soundfile as sf
    import torch
    receipt = dest.with_suffix(".receipt.json")
    attempt = dest.with_suffix(".attempt.json")
    if receipt.exists():
        rec = read(receipt)
        if rec["sha256"] != sha(dest):
            raise RuntimeError("COMPLETED_AUDIO_CHANGED")
        return
    if attempt.exists() or dest.exists():
        raise RuntimeError("PRIOR_ATTEMPT_NO_REPEAT_ALLOWED:" + str(dest))
    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    started = now()
    write(attempt, dict(started_at=started, seed=42, text_sha256=hashlib.sha256(text.encode()).hexdigest()))
    torch.manual_seed(42)
    t = time.perf_counter()
    def timed_out(signum, frame):
        raise TimeoutError("CHUNK_TIMEOUT_NO_RETRY")
    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(600)
    try:
        fn = getattr(model, "generate_" + mode)
        waves, sr = fn(text=text, language="russian", max_new_tokens=cap, **PARAMS, **kwargs)
    finally:
        signal.alarm(0)
    wav = np.asarray(waves[0], dtype=np.float32)
    validate_audio(wav, sr, cap)
    tmp = dest.with_name(dest.stem + ".part.wav")
    sf.write(tmp, wav, sr, subtype="FLOAT")
    tmp.replace(dest)
    elapsed = time.perf_counter()-t
    write(receipt, dict(started_at=started, finished_at=now(), host=socket.gethostname(), pid=os.getpid(),
                        elapsed_s=elapsed, duration_s=len(wav)/sr, rtf=elapsed/(len(wav)/sr),
                        sha256=sha(dest), seed=42, mode=mode, max_new_tokens=cap))
    print("GENERATED", dest.parent.name, dest.name, round(len(wav)/sr, 3), round(elapsed, 3), flush=True)


def render_stage(a, plan):
    from audiobook import synth
    import torch
    from qwen_tts import Qwen3TTSModel
    torch.set_num_threads(8)
    stage = a.stage
    model_path = Path(plan["base_snapshot"]) if stage == "base" else a.out / "models" / ("CustomVoice" if stage == "custom" else "VoiceDesign")
    model = Qwen3TTSModel.from_pretrained(str(model_path), dtype=torch.float32,
                                         device_map="cpu", attn_implementation="eager")
    langs = model.get_supported_languages()
    if "russian" not in langs:
        raise RuntimeError("RUSSIAN_UNSUPPORTED")
    write(a.out / (stage + ".runtime.json"), dict(languages=langs, speakers=model.get_supported_speakers(),
        model_path=str(model_path), host=socket.gethostname(), pid=os.getpid(), started_at=now()))
    speakers = CUSTOM if stage == "custom" else list(DESIGNS)
    for voice in speakers:
        try:
            if stage == "custom" and voice.lower() not in model.get_supported_speakers():
                raise RuntimeError("SPEAKER_UNSUPPORTED:" + voice)
            if stage == "design":
                generate_once(a, a.out / "references" / (voice+".wav"), model,
                    "voice_design", plan["reference_text"], plan["reference_max_new_tokens"], instruct=DESIGNS[voice])
                transcript = a.out / "references" / (voice+".txt")
                if transcript.exists() and transcript.read_text(encoding="utf-8") != plan["reference_text"]:
                    raise RuntimeError("REFERENCE_TRANSCRIPT_CHANGED")
                if not transcript.exists():
                    transcript.write_text(plan["reference_text"], encoding="utf-8")
                continue
            extra = dict(speaker=voice, instruct=STYLE) if stage == "custom" else {}
            if stage == "base":
                ref = a.out / "references" / (voice+".wav")
                rec = read(ref.with_suffix(".receipt.json"))
                if sha(ref) != rec["sha256"]:
                    raise RuntimeError("REFERENCE_CHANGED")
                lat = a.out / "references" / (voice+".latents.pt")
                if not lat.exists():
                    synth.save_latents(synth.compute_latents(model, ref, plan["reference_text"]), lat)
                extra = dict(voice_clone_prompt=synth._dict_to_items(synth.load_latents(lat)))
                write(a.out / "references" / (voice+".identity.json"),
                      dict(reference_sha256=sha(ref), latents_sha256=sha(lat), transcript=plan["reference_text"]))
            for r in plan["rows"]:
                generate_once(a, a.out / "voices" / voice / "raw" / (r["row"]["id"]+".wav"),
                    model, "custom_voice" if stage == "custom" else "voice_clone",
                    r["synth_text"], r["max_new_tokens"], **extra)
        except Exception as exc:
            write(a.out / (voice+"."+stage+".blocked.json"), dict(error=str(exc), at=now()))
            print("VOICE_BLOCKED", voice, str(exc), flush=True)
    del model
    gc.collect()


def finish_stage(a, plan):
    import numpy as np
    import soundfile as sf
    from audiobook import assemble, leadin, master, paths, qc
    from faster_whisper import WhisperModel
    whisper = WhisperModel(str(a.production / "models" / "whisper" / "small"),
                           device="cpu", compute_type="int8", cpu_threads=8)
    leadin._whisper = whisper
    completed = []
    for voice in ["Author"] + CUSTOM + list(DESIGNS):
        try:
            folder = a.out / "voices" / voice
            folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            chunks = folder / "chunks"
            chunks.mkdir(exist_ok=True)
            rows = []
            measurements = []
            for item in plan["rows"]:
                row = dict(item["row"])
                cid = row["id"]
                dest = chunks / (cid+".wav")
                if voice == "Author":
                    src = a.production / "out" / "sections" / SECTION / "chunks" / (cid+".wav")
                    if sha(src) != item["wav_sha256"]:
                        raise RuntimeError("AUTHOR_WAV_CHANGED")
                    if not dest.exists():
                        shutil.copyfile(src, dest)
                else:
                    src = folder / "raw" / (cid+".wav")
                    rec = read(src.with_suffix(".receipt.json"))
                    if sha(src) != rec["sha256"]:
                        raise RuntimeError("RAW_WAV_CHANGED")
                    # Candidate index provenance must never inherit the cached
                    # author's seed/hash/acceptance metadata.
                    row.update(seed=42, seed_override=None, locked=False,
                        hash=hashlib.sha256((voice+cid+sha(a.out / "plan_PRIVATE.json")+rec["sha256"]).encode()).hexdigest())
                    if not dest.exists():
                        wav, sr = sf.read(src, dtype="float32")
                        if item["phrase"]:
                            wav = leadin.trim_carrier(wav, item["synth_text"], item["phrase"])
                        tmp = dest.with_name(dest.stem+".part.wav")
                        sf.write(tmp, wav, 24000, subtype="FLOAT")
                        tmp.replace(dest)
                wav, sr = sf.read(dest, dtype="float32")
                validate_audio(wav, sr, 100000)
                transcript = qc.transcribe(whisper, dest)
                row.update(status="done", transcript=transcript, cer=qc.cer(row["text"], transcript))
                measurements.append(dict(id=cid, duration_s=len(wav)/sr, sha256=sha(dest),
                    transcript=transcript, cer=row["cer"], diffs=qc.word_diff(qc.normalize_for_cer(row["text"]), qc.normalize_for_cer(transcript))))
                rows.append(row)
            assert [r["id"] for r in rows] == [r["row"]["id"] for r in plan["rows"]]
            mf = folder / "manifest.jsonl"
            mf.write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in rows), encoding="utf-8")
            if not (folder / "section.wav").exists():
                assemble.assemble_section(folder, plan["config"])
            mp3 = folder / "section.mp3"
            if not mp3.exists():
                measure = master.master_wav(folder / "section.wav", mp3, plan["config"], pad=True)
                write(folder / "master.json", measure)
            # Fully decode the final MP3; do not alter its speech or playback rate.
            proc = subprocess.run([str(paths.ffmpeg()), "-v", "error", "-i", str(mp3),
                "-f", "f32le", "-acodec", "pcm_f32le", "-"], capture_output=True, check=True)
            audio = np.frombuffer(proc.stdout, dtype=np.float32)
            assert len(audio) and np.isfinite(audio).all()
            duration = len(audio)/plan["config"]["master"]["sample_rate"]
            result = dict(voice=voice, duration_s=duration, sha256=sha(mp3), chunks=measurements,
                synthesis_calls=0 if voice == "Author" else len(rows),
                pronunciation_risk="Whisper lexical differences require human review; stress/accent and speaker stability are unjudged.")
            write(folder / "qc_PRIVATE.json", result)
            completed.append(result)
            print("COMPLETED", voice, round(duration, 3), sha(mp3), flush=True)
        except Exception as exc:
            write(a.out / (voice+".finish.blocked.json"), dict(error=str(exc), at=now()))
            print("FINISH_BLOCKED", voice, str(exc), flush=True)
    review = a.out / "blind-listening"
    review.mkdir(mode=0o700, exist_ok=True)
    keyfile = a.out / "blind-key_PRIVATE.json"
    if keyfile.exists():
        order = read(keyfile)
    else:
        voices = [r["voice"] for r in completed]
        secrets.SystemRandom().shuffle(voices)
        order = {f"{i+1:02}":v for i,v in enumerate(voices)}
        write(keyfile, order)
    fields = ["Русское произношение / акцент", "Ударения", "Точность слов", "Естественность", "Приятность голоса", "Стабильность тембра", "Темп", "Пригодность для аудиокниги"]
    cards = []
    for neutral, voice in order.items():
        name = "sample-"+neutral+".mp3"
        target = review / name
        source = a.out / "voices" / voice / "section.mp3"
        if not target.exists():
            shutil.copyfile(source, target)
        assert sha(source) == sha(target)
        cards.append('<section><h2>Образец '+neutral+'</h2><audio controls preload="metadata" src="'+name+'"></audio><div class="fields">'+
            ''.join('<label>'+html.escape(f)+'<select data-field="'+str(i)+'"><option value="">Не оценено</option>'+''.join('<option>'+str(n)+'</option>' for n in range(1,6))+'</select></label>' for i,f in enumerate(fields))+
            '</div><label>Заметки и таймкоды<textarea rows="3" placeholder="Что вы услышали"></textarea></label></section>')
    text = '\n\n'.join(r["row"]["text"] for r in plan["rows"])
    page = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Слепое прослушивание</title><style>body{font:17px system-ui;max-width:1000px;margin:36px auto;padding:0 22px;background:#f5f3ee;color:#242424}section{background:white;padding:24px;margin:22px 0;border-radius:14px}audio{width:100%}.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin:20px 0}label{display:block}select,textarea{display:block;width:100%;padding:8px;box-sizing:border-box;margin-top:6px}button{padding:12px 18px;margin:10px 0}pre{white-space:pre-wrap;font:inherit}h1{font-size:30px}</style><h1>Слепое прослушивание · '''+str(len(completed))+''' голосов</h1><p>Один отрывок, одинаковые границы и настройки сборки. Оцените каждый голос от 1 (плохо) до 5 (отлично). Для темпа: 5 — наиболее подходящий. Длительность зависит от речи: скорость не изменялась. Один образец — исходный авторский голос. Названия скрыты; ключ хранится отдельно.</p><p>Прослушивание не подтверждает качество автоматически. Оценки сохраняются в этом браузере; экспортируйте их для передачи.</p><details><summary>Общий текст отрывка</summary><pre>'''+html.escape(text)+'''</pre></details><button id="export">Скачать оценки JSON</button>'''+''.join(cards)+'''<script>const fields=[...document.querySelectorAll('select,textarea')];const k='qwen-cast-01-'+location.pathname;let saved={};try{saved=JSON.parse(localStorage.getItem(k)||'{}')}catch{}fields.forEach((e,i)=>{e.value=saved[i]||'';e.addEventListener('input',()=>{saved[i]=e.value;localStorage.setItem(k,JSON.stringify(saved))})});document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>document.querySelectorAll('audio').forEach(b=>{if(a!==b)b.pause()})));document.getElementById('export').onclick=()=>{const result=[...document.querySelectorAll('section')].map(s=>({sample:s.querySelector('h2').textContent,ratings:[...s.querySelectorAll('select')].map(e=>({criterion:e.parentElement.firstChild.textContent,score:e.value?Number(e.value):null})),notes:s.querySelector('textarea').value}));const u=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='listening-ratings.json';a.click();URL.revokeObjectURL(u)};</script></html>'''
    (review / "index.html").write_text(page, encoding="utf-8")
    write(a.out / "delivery_PRIVATE.json", dict(status="READY" if len(completed)==9 else "PARTIAL",
        finished_at=now(), host=socket.gethostname(), plan_sha256=sha(a.out / "plan_PRIVATE.json"),
        completed=completed, page_sha256=sha(review / "index.html"), subjective_ratings=None))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["plan", "custom", "design", "base", "finish"], required=True)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    a = parser.parse_args()
    configure(a)
    with admission(a):
        if a.stage == "plan":
            plan_stage(a)
            return
        plan = read(a.out / "plan_PRIVATE.json")
        if sha(a.out / "plan_PRIVATE.json") != (a.out / "plan.sha256").read_text(encoding="utf-8").strip():
            raise RuntimeError("PLAN_CHANGED")
        if sha(Path(__file__)) != plan["operator_sha256"] or inputs(a) != plan["inputs"]:
            raise RuntimeError("FROZEN_INPUT_CHANGED")
        verify_assets(a, plan)
        for name, expected in plan["base_files"].items():
            if sha(Path(plan["base_snapshot"]) / name) != expected:
                raise RuntimeError("BASE_MODEL_CHANGED")
        print("STAGE_START", a.stage, now(), socket.gethostname(), os.getpid(), flush=True)
        started = time.perf_counter()
        if a.stage == "finish":
            finish_stage(a, plan)
        else:
            render_stage(a, plan)
        write(a.out / (a.stage+".exit.json"), dict(exit_code=0, finished_at=now(), elapsed_s=time.perf_counter()-started,
              host=socket.gethostname(), pid=os.getpid(), inputs_unchanged=inputs(a)==plan["inputs"]))
        print("STAGE_FINISH", a.stage, now(), flush=True)


if __name__ == "__main__":
    main()
