"""Read-only private evidence consolidation after the casting batch finishes."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import subprocess

from qwen_cast_operator import admission, configure, now, read, sha, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    a = parser.parse_args()
    configure(a)
    if not (a.out / "batch.finished.txt").exists():
        raise RuntimeError("BATCH_NOT_FINISHED")
    plan = read(a.out / "plan_PRIVATE.json")
    delivery = read(a.out / "delivery_PRIVATE.json")
    with admission(a):
        from audiobook import qc
        from faster_whisper import WhisperModel
        whisper = WhisperModel(str(a.production / "models" / "whisper" / "small"),
                               device="cpu", compute_type="int8", cpu_threads=8)
        refs = []
        for ref in sorted((a.out / "references").glob("*.wav")):
            transcript = qc.transcribe(whisper, ref)
            refs.append(dict(profile=ref.stem, sha256=sha(ref),
                generation=read(ref.with_suffix(".receipt.json")),
                expected_transcript=plan["reference_text"], whisper_transcript=transcript,
                cer=qc.cer(plan["reference_text"], transcript),
                identity=read(ref.with_suffix(".identity.json")) if ref.with_suffix(".identity.json").exists() else None))
        preserved = {}
        for inventory in ("production-wavs-before.sha256", "baselines-before.sha256"):
            proc = subprocess.run(["sha256sum", "-c", str(a.out / inventory)],
                                  text=True, capture_output=True)
            (a.out / (inventory+".verification.txt")).write_text(proc.stdout+proc.stderr, encoding="utf-8")
            preserved[inventory] = dict(exit_code=proc.returncode, inventory_sha256=sha(a.out / inventory),
                                       lines=len(proc.stdout.splitlines()))
            if proc.returncode:
                raise RuntimeError("PRESERVATION_MISMATCH")
        voices = []
        for result in delivery["completed"]:
            voice = result["voice"]
            receipts = [read(f) for f in sorted((a.out / "voices" / voice / "raw").glob("*.receipt.json"))]
            elapsed = sum(r["elapsed_s"] for r in receipts)
            raw_s = sum(r["duration_s"] for r in receipts)
            voices.append(dict(voice=voice, duration_s=result["duration_s"], mp3_sha256=result["sha256"],
                synthesized_chunks=len(receipts), reused_chunks=len(result["chunks"]) if voice == "Author" else 0,
                synthesis_elapsed_s=elapsed, generated_raw_audio_s=raw_s,
                raw_synth_rtf=elapsed/raw_s if raw_s else None,
                synth_wall_per_mastered_second=elapsed/result["duration_s"] if receipts else None,
                per_chunk_cer={r["id"]:r["cer"] for r in result["chunks"]},
                max_chunk_cer=max(r["cer"] for r in result["chunks"]),
                raw_receipts=receipts))
        models = {}
        for kind in ("CustomVoice", "VoiceDesign"):
            mf = a.out / "models" / (kind+".json")
            inv = read(mf)
            models[kind] = dict(repo=inv["repo"], revision=inv["revision"], license=inv["license"],
                manifest_sha256=sha(mf), newly_downloaded=True,
                files=inv["files"])
        models["Base"] = dict(reused=True, snapshot=plan["base_snapshot"], files=plan["base_files"])
        start = (a.out / "batch.started.txt").read_text(encoding="utf-8").strip()
        end = (a.out / "batch.finished.txt").read_text(encoding="utf-8").strip()
        stages = {name:read(a.out / (name+".exit.json")) if (a.out / (name+".exit.json")).exists()
                  else dict(exit_code=int((a.out / (name+".exit-code.txt")).read_text(encoding="utf-8")))
                  for name in ("custom", "design", "base", "finish")}
        result = dict(task="QWEN-VOICE-CAST-01", status=delivery["status"], report_at=now(),
            host="danny-serv", production_head=plan["production_head"], operator_head=plan["operator_head"],
            operator_sha256=plan["operator_sha256"], report_operator_sha256=sha(Path(__file__)),
            plan_sha256=sha(a.out / "plan_PRIVATE.json"), inputs=plan["inputs"],
            source_section="CH1", source_chunk_ids=[r["row"]["id"] for r in plan["rows"]],
            text_sha256=plan["source_text_sha256"], ordered_source_coverage_exact=True,
            source_original_assembled_s=plan["original_assembled_s"], language=plan["language"],
            versions=plan["versions"], requested_runtime=dict(device="cpu", dtype="float32", cpu_threads=8),
            api_non_streaming_mode=dict(custom_voice=True, voice_design=True, voice_clone=False),
            custom_instruction=plan["custom_instruction"], design_instructions=plan["designs"],
            params=plan["params"], seeds=dict(new_candidates=42, author="cached original per-chunk seeds; see frozen plan"),
            comparison=plan["comparison"], models=models, references=refs, voices=voices,
            batch_started_at=start, batch_finished_at=end,
            batch_elapsed_s=(datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds(),
            stages=stages, preservation=preserved,
            blocked={f.name:read(f) for f in sorted(a.out.glob("*.blocked.json"))},
            review_page_sha256=delivery["page_sha256"],
            listening_ratings=None, pronunciation_and_timbre="Await owner listening; ASR does not judge stress, accent, appeal or speaker stability.",
            rtf_note="Raw synth RTF includes generated context carriers. Wall per mastered second excludes reference setup, model loading, verification, QC and mastering. Batch elapsed includes all stages.")
        write(a.out / "report_PRIVATE.json", result)
        print("REPORT", result["status"], "VOICES", len(voices), "PRESERVATION", preserved, flush=True)


if __name__ == "__main__":
    main()
