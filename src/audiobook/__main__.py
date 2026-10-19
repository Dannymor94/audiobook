from __future__ import annotations

import argparse
import sys

from . import paths


def load_config() -> dict:
    import yaml
    with open(paths.ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main(argv: list[str] | None = None) -> int:
    paths.apply_env_defaults()
    p = argparse.ArgumentParser(prog="audiobook")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("doctor", help="проверка окружения")
    d.add_argument("--no-models", action="store_true", help="не проверять веса (CI)")
    sub.add_parser("bench", help="RTF на 5 чанках")
    sub.add_parser("pick-ref", help="синтез тестового отрывка для всех кандидатов ref/candidates/")
    sub.add_parser("calibrate", help="гриды скорости и паузы → out/ref_test2, speed_test, pause_test")
    ck = sub.add_parser("chunk", help="чанкинг разделов → out/sections/NN/manifest.jsonl")
    ck.add_argument("--section", type=str, default=None,
                    help="только эта секция (без флага — вся книга)")
    sub.add_parser("headings", help="рендер 483 заголовков → out/headings_check_v2/")
    rd = sub.add_parser("redo", help="рендер N кандидатов для чанка → out/redo/<sec>/<id>/")
    rd.add_argument("section", help="имя секции (например 01_vvedenie)")
    rd.add_argument("chunk_id", help="id чанка (например 0003)")
    rd.add_argument("--candidates", type=int, default=3, help="число кандидатов (default 3)")
    rc = sub.add_parser("ref-compare",
                        help="кандидаты ref/candidates/*.wav на одном тексте → out/ref_compare/")
    rc.add_argument("--section", type=str, default=None)
    rc.add_argument("--first", type=int, default=None, help="первые N чанков секции")
    rc.add_argument("--transcribe", action="store_true",
                    help="только черновики текста (whisper) для кандидатов без .txt")
    ac = sub.add_parser("accept", help="установить кандидат и заблокировать чанк")
    ac.add_argument("section")
    ac.add_argument("chunk_id")
    ac.add_argument("variant", type=int, help="номер варианта (1-based)")
    for name in ("synth", "qc", "assemble", "master"):
        s = sub.add_parser(name)
        s.add_argument("--chapter", type=int, default=None)
        s.add_argument("--section", type=str, default=None,
                       help="имя секции out/sections/<section> (обязательно для рендера)")
        if name == "synth":
            s.add_argument("--workers", type=int, default=1,
                           help="параллельных воркеров синтеза (Ryzen 0.6B: 4, 1.7B: 2)")
        if name in ("synth", "assemble", "master"):
            s.add_argument("--first", type=int, default=None,
                           help="только первые N чанков секции (превью → preview_firstN)")
    a = p.parse_args(argv)

    if a.cmd == "doctor":
        from .doctor import run as doctor
        return 0 if doctor(a.no_models, load_config()) else 1
    if a.cmd == "bench":
        from .bench import run as bench
        return bench(load_config())
    if a.cmd == "pick-ref":
        from .pick_ref import run as pick_ref
        return pick_ref(load_config())
    if a.cmd == "chunk":
        from .chunker import run as chunk
        return chunk(load_config(), a.section)
    if a.cmd == "headings":
        from .headings import run as headings
        return headings(load_config())
    if a.cmd == "calibrate":
        from .calibrate import run as calibrate
        return calibrate(load_config())
    if a.cmd == "redo":
        from .redo import run_redo
        return run_redo(load_config(), a.section, a.chunk_id, a.candidates)
    if a.cmd == "ref-compare":
        from .ref_compare import run as ref_compare
        return ref_compare(load_config(), a.section, a.first, a.transcribe)
    if a.cmd == "accept":
        from .redo import run_accept
        return run_accept(load_config(), a.section, a.chunk_id, a.variant)
    if a.cmd == "synth":
        from .synth import run as synth
        return synth(load_config(), a.section, a.workers, a.first)
    if a.cmd == "qc":
        from .qc import run as qc
        return qc(load_config(), a.section)
    if a.cmd == "assemble":
        from .assemble import run as assemble
        return assemble(load_config(), a.section, a.first)
    if a.cmd == "master":
        from .master import run as master
        return master(load_config(), a.section, a.first)
    print(f"{a.cmd}: не реализовано в каркасе", file=sys.stderr)
    return 2


if __name__ == "__main__":
    import multiprocessing as mp
    mp.set_start_method("spawn", force=True)   # как на Windows, всегда
    sys.exit(main())
