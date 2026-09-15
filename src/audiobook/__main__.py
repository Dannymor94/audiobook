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
    for name in ("synth", "qc", "assemble", "master"):
        s = sub.add_parser(name)
        s.add_argument("--chapter", type=int, default=None)
    a = p.parse_args(argv)

    if a.cmd == "doctor":
        from .doctor import run as doctor
        return 0 if doctor(a.no_models, load_config()) else 1
    if a.cmd == "bench":
        from .bench import run as bench
        return bench(load_config())
    print(f"{a.cmd}: не реализовано в каркасе", file=sys.stderr)
    return 2


if __name__ == "__main__":
    import multiprocessing as mp
    mp.set_start_method("spawn", force=True)   # как на Windows, всегда
    sys.exit(main())
