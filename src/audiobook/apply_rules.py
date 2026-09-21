from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from audiobook import paths

_ARROW_CHARS = frozenset('→↓·')


def assert_no_arrows(text: str) -> None:
    for ch in _ARROW_CHARS:
        if ch in text:
            sys.exit(f"ERROR: forbidden character '{ch}' in output line:\n  {text[:200]}")


def check_coverage(blocks: list[dict], rules: dict, prose_fragments: dict) -> None:
    NEEDS_SPOKEN = {'flow', 'chain', 'prose_with_arrow'}
    for b in blocks:
        if b['type'] in NEEDS_SPOKEN and b['sha1'] not in rules and b['sha1'] not in prose_fragments:
            sys.exit(
                f"ERROR: no spoken form for block type={b['type']}\n"
                f"  text: {b['text'][:200]}"
            )


def apply_section(
    sec: dict,
    defaults: dict,
    rules: dict,
    prose_fragments: dict,
) -> tuple[list[str], int, int]:
    """Returns (lines, heading_count, figure_caption_count)."""
    lines: list[str] = []
    heading_count = 0
    figure_count = 0
    check_coverage(sec['blocks'], rules, prose_fragments)

    for blk in sec['blocks']:
        btype = blk['type']
        sha1 = blk['sha1']

        action = defaults.get(btype, 'read')

        if action == 'skip':
            if btype == 'figure_caption':
                figure_count += 1
            continue

        if btype == 'prose_with_arrow':
            if sha1 in rules:
                # Full rewrite
                text = rules[sha1]['spoken']
            elif sha1 in prose_fragments:
                entry = prose_fragments[sha1]
                text = blk['text'].replace(entry['find'], entry['replace'])
                text = text.replace('·', '').strip()
            else:
                sys.exit(f"ERROR: no rule for prose_with_arrow block:\n  {blk['text'][:200]}")
            assert_no_arrows(text)
            lines.append(text)
            continue

        if btype == 'heading':
            heading_count += 1
            lines.append(blk['text'])
            continue

        if btype in ('flow', 'chain'):
            if sha1 not in rules:
                sys.exit(f"ERROR: no spoken form for {btype}:\n  {blk['text'][:200]}")
            text = rules[sha1]['spoken']
            assert_no_arrows(text)
            lines.append(text)
            continue

        # paragraph, stack: read as-is
        text = blk['text'].replace('·', '').replace('✓', '').strip()
        if text:
            if btype == 'stack':
                for part in text.split('\n'):
                    part = part.strip()
                    if part:
                        assert_no_arrows(part)
                        lines.append(part)
            else:
                assert_no_arrows(text)
                lines.append(text)

    return lines, heading_count, figure_count


def main() -> None:
    rules_path = paths.TEXT / 'read_rules.yaml'
    blocks_dir = paths.TEXT / 'blocks'

    with open(rules_path, encoding='utf-8') as f:
        ruleset = yaml.safe_load(f)

    defaults = ruleset['defaults']
    rules = ruleset.get('rules', {})
    prose_fragments = ruleset.get('prose_fragments', {})

    skip_sections = set(ruleset.get('skip_sections', []))
    total_headings = 0
    total_figures = 0
    skipped = []
    for blocks_file in sorted(blocks_dir.glob('*.blocks.json')):
        sec = json.loads(blocks_file.read_text(encoding='utf-8'))
        if sec['nn'] in skip_sections:
            skipped.append(sec['nn'])
            print(f"SKIP (skip_sections): {sec['nn']}_{sec['slug']}")
            continue
        output_lines, h_count, fig_count = apply_section(sec, defaults, rules, prose_fragments)
        out_path = paths.TEXT / f"{sec['nn']}_{sec['slug']}.txt"
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(output_lines))
        parts = [f"{len(output_lines)} lines"]
        if h_count:
            parts.append(f"headings: {h_count}")
        if fig_count:
            parts.append(f"figures skipped: {fig_count}")
        print(f"Written: {out_path.name} ({', '.join(parts)})")
        total_headings += h_count
        total_figures += fig_count
    print(f"\nTotal headings emitted: {total_headings}")
    print(f"Total figure captions skipped: {total_figures}")
    if skipped:
        print(f"Sections skipped (skip_sections): {', '.join(skipped)}")


if __name__ == '__main__':
    main()
