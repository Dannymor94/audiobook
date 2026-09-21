from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from audiobook import paths
from audiobook.text_blocks import block_sha1, normalize_text_key

ARROW = '→'
REQUIRES_SPOKEN = {'flow', 'chain', 'prose_with_arrow'}


def _norm(text: str) -> str:
    return normalize_text_key(text)


def _prefix_before_ellipsis(text: str) -> str:
    for marker in ('…', '...'):
        idx = text.find(marker)
        if idx != -1:
            return text[:idx].strip()
    return text.strip()


def _has_ellipsis(text: str) -> bool:
    return '…' in text or '...' in text


def parse_rewrite_draft(path: Path) -> dict:
    # sha1_entries: list of (sha1, spoken, original_text) for fuzzy fallback
    sha1_entries: list[tuple[str, str, str]] = []
    prefix_entries: list[tuple[str, str]] = []   # (prefix_text, spoken)
    fragment_entries: list[tuple[str, str]] = []  # (find_fragment, replace_with)
    section_positional: dict[str, list[str]] = {}  # section_heading -> [spoken, ...]

    lines = path.read_text(encoding='utf-8').splitlines()

    current_section = ''
    in_fragment_table = False
    in_table = False
    in_numbered_table = False  # | № | Оригинал | Озвучка |
    current_block_original: str | None = None
    current_block_spoken_lines: list[str] = []
    pending_block_header = False

    def _add_orig(orig: str, spoken: str) -> None:
        if not orig or not spoken:
            return
        if _has_ellipsis(orig):
            prefix = _prefix_before_ellipsis(orig)
            if prefix:
                prefix_entries.append((prefix, spoken))
        else:
            sha1_entries.append((block_sha1(orig), spoken, orig))

    def flush_block() -> None:
        nonlocal current_block_original, current_block_spoken_lines, pending_block_header
        if not current_block_spoken_lines:
            current_block_original = None
            pending_block_header = False
            return
        spoken = ' '.join(current_block_spoken_lines).strip()
        if current_block_original is not None:
            _add_orig(current_block_original, spoken)
        else:
            section_positional.setdefault(current_section, []).append(spoken)
        current_block_original = None
        current_block_spoken_lines = []
        pending_block_header = False

    for raw_line in lines:
        line = raw_line.rstrip()

        if line.startswith('## '):
            flush_block()
            current_section = line[3:].strip()
            in_table = in_fragment_table = in_numbered_table = False
            continue

        if '|' in line:
            cols = [c.strip() for c in line.strip().strip('|').split('|')]
            if not cols:
                continue
            # Separator row
            if all(not c or set(c) <= set('-: ') for c in cols):
                continue

            col0_low = cols[0].lower()
            col1_low = cols[1].lower() if len(cols) > 1 else ''

            is_header = (
                any(h in col0_low for h in ('оригинал', 'озвучка', '№')) or
                any(h in col1_low for h in ('оригинал', 'фрагмент'))
            )
            if is_header:
                flush_block()
                in_table = in_fragment_table = in_numbered_table = False
                if '№' in col0_low and len(cols) >= 3:
                    if 'фрагмент' in col1_low:
                        in_fragment_table = True
                    else:
                        in_numbered_table = True  # | № | Оригинал | Озвучка |
                else:
                    in_table = True
                continue

            if in_fragment_table and len(cols) >= 3:
                find_frag, replace = cols[1], cols[2]
                if find_frag and replace:
                    fragment_entries.append((find_frag, replace))
                continue

            if in_numbered_table and len(cols) >= 3:
                # cols: [num, original, spoken]
                _add_orig(cols[1], cols[2])
                continue

            if in_table and len(cols) >= 2:
                orig, spoken = cols[0], cols[1]
                if orig.lower() not in ('оригинал', 'озвучка', 'original', 'озвучка фрагмента'):
                    _add_orig(orig, spoken)
                continue

            # Outside table mode — try 2-col match
            if not in_fragment_table and not in_numbered_table and len(cols) >= 2:
                orig, spoken = cols[0], cols[1]
                if orig.lower() not in ('оригинал', 'озвучка'):
                    _add_orig(orig, spoken)
            continue

        m = re.match(r'^\*\*(\d[\d–\-]*\.?)\s*(.*?)\*\*\s*$', line)
        if m:
            flush_block()
            in_table = in_fragment_table = in_numbered_table = False
            pending_block_header = True
            desc = m.group(2).strip()
            if ARROW in desc and not _has_ellipsis(desc):
                current_block_original = desc
            else:
                current_block_original = None
            continue

        if line.startswith('>'):
            chunk = line[1:].strip()
            if chunk:
                current_block_spoken_lines.append(chunk)
            continue

        if pending_block_header and line.strip() and not line.startswith('#') and '|' not in line:
            text = line.strip()
            IGNORE_STARTS = ('Оригинал', 'Стрелка', 'Семь', 'Переписывать', 'Абзац', 'Если',
                             'Какой', 'Мы ', 'Это ', 'Лови', 'Учись')
            if ARROW in text and not any(text.startswith(s) for s in IGNORE_STARTS):
                if current_block_original is None:
                    current_block_original = text
            continue

        if not line.strip():
            in_table = in_fragment_table = in_numbered_table = False

    flush_block()

    return {
        'sha1_entries': sha1_entries,
        'prefix_entries': prefix_entries,
        'fragment_entries': fragment_entries,
        'section_positional': section_positional,
    }


def build_read_rules(blocks_dir: Path, draft_path: Path) -> dict:
    parsed = parse_rewrite_draft(draft_path)

    sections: list[dict] = []
    all_schema_blocks: list[dict] = []
    for f in sorted(blocks_dir.glob('*.blocks.json')):
        sec = json.loads(f.read_text(encoding='utf-8'))
        sections.append(sec)
        for b in sec['blocks']:
            if b['type'] in REQUIRES_SPOKEN:
                b['_section_heading'] = sec['heading']
                all_schema_blocks.append(b)

    sha1_to_block = {b['sha1']: b for b in all_schema_blocks}
    rules: dict[str, str] = {}
    matched_sha1s: set[str] = set()

    # 1. Exact SHA1 match
    for sha1, spoken, _orig in parsed['sha1_entries']:
        if sha1 in sha1_to_block:
            rules[sha1] = spoken
            matched_sha1s.add(sha1)

    # 2. Fuzzy fallback for unmatched sha1 entries
    for sha1, spoken, orig in parsed['sha1_entries']:
        if sha1 in matched_sha1s:
            continue
        norm_orig = _norm(orig)
        # Try multiple prefix candidates: before first →, before first (, 25 chars
        candidates = []
        for sep in (ARROW, '('):
            idx = norm_orig.find(sep)
            if idx > 5:
                candidates.append(norm_orig[:idx].strip())
        candidates.append(norm_orig[:25] if len(norm_orig) > 25 else norm_orig)
        matched = False
        for prefix in candidates:
            if not prefix:
                continue
            for blk in all_schema_blocks:
                if blk['sha1'] in matched_sha1s:
                    continue
                if prefix in _norm(blk['text']):
                    rules[blk['sha1']] = spoken
                    matched_sha1s.add(blk['sha1'])
                    matched = True
                    break
            if matched:
                break

    # 3. Prefix matches (originals truncated with …)
    for prefix, spoken in parsed['prefix_entries']:
        norm_prefix = _norm(prefix)
        if not norm_prefix:
            continue
        for blk in all_schema_blocks:
            if blk['sha1'] in matched_sha1s:
                continue
            if norm_prefix in _norm(blk['text']):
                rules[blk['sha1']] = spoken
                matched_sha1s.add(blk['sha1'])
                break

    # 4. Fragment entries: find prose_with_arrow blocks containing the fragment
    prose_fragments: dict[str, dict] = {}
    for find_frag, replace in parsed['fragment_entries']:
        core = find_frag.replace('…', '').replace('...', '').strip()
        if not core:
            continue
        for blk in all_schema_blocks:
            if blk['type'] == 'prose_with_arrow' and core in blk['text']:
                prose_fragments[blk['sha1']] = {'find': core, 'replace': replace}
                matched_sha1s.add(blk['sha1'])
                break

    # 5. Positional matching within sections
    def _section_heading_key(h: str) -> str:
        m = re.match(r'(Глава\s+\d+|Приложение\s+\d+)', h)
        return m.group(0) if m else h[:25]

    for draft_heading, spoken_list in parsed['section_positional'].items():
        key = _section_heading_key(draft_heading)
        matched_sec = None
        for sec in sections:
            if key and key in sec['heading']:
                matched_sec = sec
                break
        if matched_sec is None:
            # fallback: first 20 chars
            for sec in sections:
                if draft_heading[:20] in sec['heading']:
                    matched_sec = sec
                    break
        if matched_sec is None:
            continue

        unmatched = [
            b for b in matched_sec['blocks']
            if b['type'] in REQUIRES_SPOKEN and b['sha1'] not in matched_sha1s
        ]
        for i, spoken in enumerate(spoken_list):
            if i >= len(unmatched):
                break
            blk = unmatched[i]
            rules[blk['sha1']] = spoken
            matched_sha1s.add(blk['sha1'])

    unmatched_blocks = [
        b for b in all_schema_blocks
        if b['sha1'] not in matched_sha1s and b['sha1'] not in prose_fragments
    ]
    if unmatched_blocks:
        print(f"WARNING: {len(unmatched_blocks)} unmatched schema blocks:")
        for b in unmatched_blocks:
            print(f"  [{b['_section_heading'][:40]}] {b['type']}: {b['text'][:80]}")

    total = len(all_schema_blocks)
    matched = len(matched_sha1s)
    print(f"Coverage: {matched}/{total} schema blocks matched ({len(prose_fragments)} fragment-only)")

    return {
        'defaults': {
            'heading': 'skip',
            'paragraph': 'read',
            'flow': 'rewrite',
            'chain': 'rewrite',
            'stack': 'read',
            'prose_with_arrow': 'rewrite',
        },
        'rules': {sha1: {'spoken': spoken} for sha1, spoken in rules.items()},
        'prose_fragments': prose_fragments,
    }


def main() -> None:
    out = build_read_rules(paths.TEXT / 'blocks', paths.TEXT / 'rewrite_draft.md')
    out_path = paths.TEXT / 'read_rules.yaml'
    with open(out_path, 'w', encoding='utf-8') as f:
        yaml.dump(out, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"Written: {out_path}")


if __name__ == '__main__':
    main()
