from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from audiobook import paths
from audiobook.text_norm import normalize_line
from audiobook.accent import accent_lines


def _load_ruleset() -> dict:
    with open(paths.TEXT / 'read_rules.yaml', encoding='utf-8') as f:
        return yaml.safe_load(f)


def run_all() -> None:
    ruleset = _load_ruleset()
    defaults = ruleset['defaults']
    rules = ruleset.get('rules', {})
    prose_fragments = ruleset.get('prose_fragments', {})

    # Import here to avoid circular
    from audiobook.apply_rules import apply_section

    proofread: list[dict] = []
    blocks_dir = paths.TEXT / 'blocks'

    for blocks_file in sorted(blocks_dir.glob('*.blocks.json')):
        sec = json.loads(blocks_file.read_text(encoding='utf-8'))
        raw_lines = apply_section(sec, defaults, rules, prose_fragments)

        # .txt
        txt_path = paths.TEXT / f"{sec['nn']}_{sec['slug']}.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(raw_lines))

        # .norm.txt
        norm_lines = []
        for line in raw_lines:
            normed, changes = normalize_line(line)
            norm_lines.append(normed)
            if changes:
                proofread.append({
                    'section': sec['heading'][:60],
                    'original': line[:120],
                    'normalized': normed[:120],
                    'changes': changes,
                })

        norm_path = paths.TEXT / f"{sec['nn']}_{sec['slug']}.norm.txt"
        with open(norm_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(norm_lines))

        # .acc.txt
        acc_lines = accent_lines(norm_lines)
        acc_path = paths.TEXT / f"{sec['nn']}_{sec['slug']}.acc.txt"
        with open(acc_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(acc_lines))

        print(f"[{sec['nn']}] {sec['heading'][:50]}: {len(raw_lines)} lines")

    # proofread_queue.md
    pq_path = paths.TEXT / 'proofread_queue.md'
    with open(pq_path, 'w', encoding='utf-8') as f:
        f.write(f"# Очередь корректуры ({len(proofread)} записей)\n\n")
        for item in proofread:
            f.write(f"## {item['section']}\n")
            f.write(f"- **Оригинал:** {item['original']}\n")
            f.write(f"- **Нормализовано:** {item['normalized']}\n")
            f.write(f"- **Изменения:** {', '.join(item['changes'])}\n\n")

    print(f"\nproofread_queue.md: {len(proofread)} записей → {pq_path}")


if __name__ == '__main__':
    run_all()
