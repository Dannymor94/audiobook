from __future__ import annotations

import os

from audiobook import paths

_accentizer = None

_MIN_SECTION_BYTES = 50


def _get_accentizer():
    global _accentizer
    if _accentizer is not None:
        return _accentizer
    nn_path = paths.MODELS / 'nn'
    dict_path = paths.MODELS / 'dictionary'
    missing = [p for p in (nn_path, dict_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"RUAccent weights missing: {', '.join(str(p) for p in missing)}\n"
            "Copy models/ from the project drive before running the accent stage."
        )
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
    from ruaccent import RUAccent  # type: ignore
    a = RUAccent()
    a.load(omograph_model_size='turbo', use_dictionary=True, workdir=str(paths.MODELS))
    _accentizer = a
    return a


def accent_lines(lines: list[str]) -> list[str]:
    """Apply ruaccent. Raises FileNotFoundError if weights are missing."""
    acc = _get_accentizer()
    return [acc.process_all(line) for line in lines]


def main() -> None:
    text_dir = paths.TEXT
    skipped = []
    for norm_file in sorted(text_dir.glob('[0-9][0-9]_*.norm.txt')):
        if norm_file.stat().st_size < _MIN_SECTION_BYTES:
            skipped.append(norm_file.name)
            print(f"SKIP (empty section): {norm_file.name}")
            continue
        lines = norm_file.read_text(encoding='utf-8').splitlines()
        accented = accent_lines(lines)
        stem = norm_file.name.replace('.norm.txt', '')
        acc_path = text_dir / f"{stem}.acc.txt"
        with open(acc_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(accented))
        print(f"Written: {acc_path.name}")
    if skipped:
        print(f"\nSkipped {len(skipped)} empty sections: {', '.join(skipped)}")


if __name__ == '__main__':
    main()
