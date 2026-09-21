from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ARROW = "→"
DOWN_ARROW = "↓"

_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
    'з': 'z', 'и': 'i', 'й': 'j', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
    'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def cyrillic_slug(text: str) -> str:
    out = []
    for ch in text.lower():
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif ch.isascii() and (ch.isalnum() or ch == ' '):
            out.append(ch)
    slug = '_'.join(''.join(out).split())[:40]
    return slug or 'section'


def normalize_text_key(text: str) -> str:
    t = text.replace('·', '').strip()
    t = re.sub(r'\s+', ' ', t)
    return t


def block_sha1(text: str) -> str:
    return hashlib.sha1(normalize_text_key(text).encode('utf-8')).hexdigest()


def _is_down_arrow_only(text: str) -> bool:
    return text.strip() in ('↓', '↑')


def normalize_paragraphs(paras: list[tuple[str, str]]) -> list[dict]:
    """paras = list of (style, text). Returns list of classified block dicts."""
    # Expand embedded \n↓\n chains into virtual separate paragraphs
    expanded: list[tuple[str, str]] = []
    for style, text in paras:
        if '\n↓\n' in text:
            parts = text.split('\n↓\n')
            for k, part in enumerate(parts):
                expanded.append((style, part))
                if k < len(parts) - 1:
                    expanded.append((style, '↓'))
        else:
            expanded.append((style, text))

    # Merge content-para, ↓-only-para, content-para sequences into chain blocks
    result: list[dict] = []
    i = 0
    while i < len(expanded):
        style, text = expanded[i]
        stripped = text.strip()
        if not stripped:
            i += 1
            continue

        # Look ahead: is this the start of a multi-para chain?
        if not _is_down_arrow_only(stripped) and not style.startswith('Heading'):
            chain_parts = [stripped]
            j = i + 1
            while j < len(expanded):
                ns, nt = expanded[j]
                nstripped = nt.strip()
                if not nstripped:
                    j += 1
                    continue
                if _is_down_arrow_only(nstripped):
                    # peek further for next content para
                    k = j + 1
                    while k < len(expanded) and not expanded[k][1].strip():
                        k += 1
                    if k < len(expanded) and not _is_down_arrow_only(expanded[k][1].strip()) and not expanded[k][0].startswith('Heading'):
                        chain_parts.append(expanded[k][1].strip())
                        j = k + 1
                    else:
                        break
                else:
                    break

            if len(chain_parts) > 1:
                chain_text = '\n'.join(chain_parts)
                result.append({
                    'type': 'chain',
                    'text': chain_text,
                    'sha1': block_sha1(chain_text),
                    'pause_ms': None,
                })
                i = j
                continue

        # Single paragraph classification
        blk = _classify_single(style, stripped)
        if blk is not None:
            result.append(blk)
        i += 1

    return result


def _classify_single(style: str, text: str) -> dict | None:
    if not text:
        return None
    if style.startswith('Heading'):
        try:
            level = int(style.split()[-1])
        except ValueError:
            level = 1
        pause_after = {1: 1500, 2: 900}.get(level, 600)
        return {
            'type': 'heading', 'text': text, 'sha1': block_sha1(text),
            'pause_ms': None, 'heading_level': level, 'pause_after_ms': pause_after,
        }
    if '\n' in text and re.match(r'^\d+\.', text):
        return {'type': 'stack', 'text': text, 'sha1': block_sha1(text), 'pause_ms': 500}
    if re.match(r'^Рисунок\s+\d+', text):
        return {'type': 'figure_caption', 'text': text, 'sha1': block_sha1(text), 'pause_ms': None}
    if ARROW in text:
        btype = 'prose_with_arrow' if len(text) > 200 else 'flow'
        return {'type': btype, 'text': text, 'sha1': block_sha1(text), 'pause_ms': None}
    return {'type': 'paragraph', 'text': text, 'sha1': block_sha1(text), 'pause_ms': None}


def extract_sections(docx_path: Path) -> list[dict]:
    from docx import Document  # type: ignore

    doc = Document(str(docx_path))
    paras = doc.paragraphs

    # Split by Heading 1
    sections_raw: list[tuple[int, str, list[tuple[str, str]]]] = []
    current_heading = ""
    current_paras: list[tuple[str, str]] = []
    h1_pos = -1

    for p in paras:
        style = p.style.name
        text = p.text  # keep raw for extraction
        if style == 'Heading 1':
            if current_heading or current_paras:
                sections_raw.append((h1_pos, current_heading, current_paras))
            current_heading = text.strip()
            current_paras = [(style, text.strip())]
            h1_pos = len(sections_raw)
        else:
            if current_heading is not None:
                current_paras.append((style, text))

    if current_heading or current_paras:
        sections_raw.append((h1_pos, current_heading, current_paras))

    # Build sections with block IDs
    sections = []
    global_schema_id = 1  # only for flow/chain/stack/prose_with_arrow

    for nn, (_, heading, paras_raw) in enumerate(sections_raw):
        nn_str = f"{nn:02d}"
        slug = cyrillic_slug(heading)
        blocks_raw = normalize_paragraphs(paras_raw)

        blocks = []
        local_id = 1
        for blk in blocks_raw:
            is_schema = blk['type'] in ('flow', 'chain', 'stack', 'prose_with_arrow')
            entry = {
                'id': local_id,
                'global_id': global_schema_id if is_schema else None,
                'type': blk['type'],
                'text': blk['text'],
                'sha1': blk['sha1'],
                'pause_ms': blk['pause_ms'],
            }
            if blk['type'] == 'heading':
                entry['heading_level'] = blk['heading_level']
                entry['pause_after_ms'] = blk['pause_after_ms']
            blocks.append(entry)
            local_id += 1
            if is_schema:
                global_schema_id += 1

        sections.append({
            'nn': nn_str,
            'slug': slug,
            'heading': heading,
            'blocks': blocks,
        })

    return sections
