from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml
from num2words import num2words

from audiobook import paths

_custom_dict: dict[str, str] | None = None

# Chars that must NOT appear in .norm.txt
_FORBIDDEN_NORM = re.compile(r'[%–−→↓·]')  # % – − → ↓ ·

# Genitive forms of Russian cardinal numerals (for range expansion)
_GEN_TABLE: dict[str, str] = {
    'ноль': 'нуля', 'один': 'одного', 'одна': 'одного', 'два': 'двух', 'две': 'двух',
    'три': 'трёх', 'четыре': 'четырёх', 'пять': 'пяти', 'шесть': 'шести',
    'семь': 'семи', 'восемь': 'восьми', 'девять': 'девяти', 'десять': 'десяти',
    'одиннадцать': 'одиннадцати', 'двенадцать': 'двенадцати',
    'тринадцать': 'тринадцати', 'четырнадцать': 'четырнадцати',
    'пятнадцать': 'пятнадцати', 'шестнадцать': 'шестнадцати',
    'семнадцать': 'семнадцати', 'восемнадцать': 'восемнадцати',
    'девятнадцать': 'девятнадцати', 'двадцать': 'двадцати',
    'тридцать': 'тридцати', 'сорок': 'сорока',
    'пятьдесят': 'пятидесяти', 'шестьдесят': 'шестидесяти',
    'семьдесят': 'семидесяти', 'восемьдесят': 'восьмидесяти',
    'девяносто': 'девяноста', 'сто': 'ста',
}

# Pattern for "dash between numeral words" — must not appear after normalization
_NUM_GEN_WORDS = '|'.join(sorted(_GEN_TABLE.values(), key=len, reverse=True))
_DASH_BETWEEN_NUMS = re.compile(
    rf'\b({_NUM_GEN_WORDS})\s*—\s*({_NUM_GEN_WORDS})\b'
)

# Prepositions that govern a range; split by required case
_PREPS_GEN = frozenset(['до', 'около', 'от', 'с'])
_PREPS_ACC = frozenset(['на', 'через', 'за', 'в', 'по'])
_ALL_PREPS = '|'.join(_PREPS_GEN | _PREPS_ACC)

# "PREP от …" — preposition directly before "от" produced by range expansion
_PREP_BEFORE_OT = re.compile(rf'(?<!\w)(?:{_ALL_PREPS})\s+от\b')


def _load_custom_dict() -> dict[str, str]:
    global _custom_dict
    if _custom_dict is None:
        p = paths.TEXT / 'custom_dict.yaml'
        if p.exists():
            with open(p, encoding='utf-8') as f:
                _custom_dict = yaml.safe_load(f) or {}
        else:
            _custom_dict = {}
    return _custom_dict


def _num_to_words(n: int) -> str:
    try:
        return num2words(n, lang='ru')
    except Exception:
        return str(n)


def _ordinal_fem(n: int, case: str) -> str:
    """Feminine ordinal. case: nom | gen | dat | acc | prep | instr."""
    base = num2words(n, lang='ru', to='ordinal')
    words = base.split()
    last = words[-1]

    if last.endswith('ый'):
        stem = last[:-2]
        suffix = {'nom': 'ая', 'gen': 'ой', 'dat': 'ой',
                  'prep': 'ой', 'instr': 'ой', 'acc': 'ую'}[case]
    elif last.endswith('ий'):
        # "третий" is the only ordinal ending in -ий; feminine needs soft sign
        stem = last[:-2] + 'ь'  # "трет" → "треть"
        suffix = {'nom': 'я', 'gen': 'ей', 'dat': 'ей',
                  'prep': 'ей', 'instr': 'ей', 'acc': 'ью'}[case]
    elif last.endswith('ой'):
        if case in ('gen', 'dat', 'prep', 'instr'):
            return base  # already the right form (e.g. "второй")
        stem = last[:-2].rstrip('о')  # "второй" → "второо" stripped → "втор"
        suffix = {'nom': 'ая', 'acc': 'ую'}.get(case, 'ой')
    else:
        return base  # fallback

    words[-1] = stem + suffix
    return ' '.join(words)


# Suffix → (gender, case) for ordinal+suffix patterns like "51-я", "1-й"
_ORDINAL_SUFFIX: dict[str, tuple[str, str]] = {
    'й': ('m', 'nom'), 'ый': ('m', 'nom'), 'ий': ('m', 'nom'),
    'ой': ('m', 'gen'),
    'я': ('f', 'nom'), 'ая': ('f', 'nom'),
    'е': ('n', 'nom'),
    'го': ('m', 'gen'), 'ого': ('m', 'gen'),
    'ую': ('f', 'acc'),
    'ей': ('f', 'gen'),
    'ём': ('m', 'prep'), 'ем': ('m', 'prep'),
    'ым': ('m', 'instr'),
}

_CHAPTER_CASE: dict[str, str] = {
    'е': 'prep', 'Е': 'prep',
    'ы': 'gen',  'Ы': 'gen',
    'у': 'acc',  'У': 'acc',
    'а': 'nom',  'А': 'nom',
}
_CHAPTER_NOUN: dict[str, str] = {
    'prep': 'главе', 'gen': 'главы', 'acc': 'главу', 'nom': 'глава',
}


def _expand_percent(text: str, changes: list[str]) -> str:
    def _sub(m: re.Match) -> str:
        repl = m.group(1) + ' процентов'
        changes.append(f"percent: {m.group()!r} → {repl!r}")
        return repl
    return re.sub(r'(\d+)\s*%', _sub, text)


def _cardinal_gen(n: int) -> str:
    """Genitive form of Russian cardinal numeral."""
    words = num2words(n, lang='ru').split()
    gen_words = [_GEN_TABLE.get(w, w) for w in words]
    return ' '.join(gen_words)


def _normalize_dashes(text: str, changes: list[str]) -> str:
    # Step 1: PREP N–M → "PREP num1-num2" (hyphenated; case governed by preposition)
    def _prep_range_sub(m: re.Match) -> str:
        prep = m.group(1)
        n1, n2 = int(m.group(2)), int(m.group(3))
        if prep.lower() in _PREPS_GEN:
            w1, w2 = _cardinal_gen(n1), _cardinal_gen(n2)
        else:  # accusative ≈ nominative for cardinal numbers
            w1, w2 = _num_to_words(n1), _num_to_words(n2)
        repl = f"{prep} {w1}-{w2}"
        changes.append(f"range: {m.group()!r} → {repl!r}")
        return repl

    text = re.sub(
        r'(?<!\w)(до|на|через|за|около|с|в|по|от)\s+(\d+)\s*[–−]\s*(\d+)',
        _prep_range_sub, text, flags=re.IGNORECASE,
    )

    # Step 2: bare N–M (no preposition) → "от num1 до num2"
    def _range_sub(m: re.Match) -> str:
        n1, n2 = int(m.group(1)), int(m.group(2))
        repl = f"от {_cardinal_gen(n1)} до {_cardinal_gen(n2)}"
        changes.append(f"range: {m.group()!r} → {repl!r}")
        return repl

    text = re.sub(r'(\d+)\s*[–−]\s*(\d+)', _range_sub, text)

    # Step 3: remaining –/− between words → em-dash
    if '–' in text or '−' in text:
        text = text.replace('–', '—').replace('−', '—')
        changes.append("dash: en-dash/minus → em-dash")
    return text


def _expand_chapter_refs(text: str, changes: list[str]) -> str:
    def _sub(m: re.Match) -> str:
        ending = m.group(1)
        n = int(m.group(2))
        case = _CHAPTER_CASE.get(ending, 'nom')
        ordinal = _ordinal_fem(n, case)
        noun = _CHAPTER_NOUN[case]
        repl = f"{ordinal} {noun}"
        changes.append(f"chapter_ref: Глав{ending} {n} → {repl}")
        return repl
    return re.sub(r'[Гг]лав([еЕыЫуУаА])\s+(\d+)', _sub, text)


def _expand_ordinal_suffixes(text: str, changes: list[str]) -> str:
    """Expand N-suffix patterns like 51-я, 1-й, 2-й."""
    def _sub(m: re.Match) -> str:
        n = int(m.group(1))
        suffix = m.group(2).lower()
        original = m.group()
        gender_case = _ORDINAL_SUFFIX.get(suffix)
        if gender_case is None:
            return original  # unknown suffix; protect number from later expansion
        gender, case = gender_case
        if gender == 'f':
            result = _ordinal_fem(n, case)
        elif gender == 'n':
            result = num2words(n, lang='ru', to='ordinal')  # neut ≈ masc for now
        else:  # masc
            base = num2words(n, lang='ru', to='ordinal')
            if case == 'nom':
                result = base
            elif case == 'gen':
                words = base.split()
                last = words[-1]
                if last.endswith('ый'):
                    last = last[:-2] + 'ого'
                elif last.endswith('ий'):
                    last = last[:-2] + 'его'
                elif last.endswith('ой'):
                    last = last[:-2].rstrip('о') + 'ого'
                words[-1] = last
                result = ' '.join(words)
            else:
                result = base
        changes.append(f"ordinal: {original!r} → {result!r}")
        return result

    # Match N-suffix; suffix is Cyrillic letters only
    return re.sub(r'(\d+)-([а-яёА-ЯЁ]+)', _sub, text)


def _expand_numbers(text: str, changes: list[str]) -> str:
    """Expand standalone integers not followed by -Cyrillic (already handled above)."""
    def _sub(m: re.Match) -> str:
        w = _num_to_words(int(m.group()))
        changes.append(f"num: {m.group()!r} → {w!r}")
        return w
    # Negative lookahead: don't touch numbers followed by hyphen+Cyrillic (compound words
    # like "50-летний" that weren't caught by ordinal expander)
    return re.sub(r'\b(\d+)\b(?!-[а-яёА-ЯЁ])', _sub, text)


def normalize_line(line: str) -> tuple[str, list[str]]:
    """Return (normalized_line, list_of_change_descriptions)."""
    changes: list[str] = []
    result = line

    # 1. Custom dictionary (whole-word)
    for orig, repl in _load_custom_dict().items():
        if orig in result:
            result = result.replace(orig, repl)
            changes.append(f"dict: {orig!r} → {repl!r}")

    # 2. Dashes: en-dash and minus → em-dash
    result = _normalize_dashes(result, changes)

    # 3. Percent expansion (before number expansion)
    result = _expand_percent(result, changes)

    # 4. Chapter cross-references (before number expansion)
    result = _expand_chapter_refs(result, changes)

    # 5. Ordinals with suffix (before standalone number expansion)
    result = _expand_ordinal_suffixes(result, changes)

    # 6. Standalone integer expansion
    result = _expand_numbers(result, changes)

    return result, changes


def assert_norm_chars(line: str, section: str, line_no: int) -> None:
    m = _FORBIDDEN_NORM.search(line)
    if m:
        ch = m.group()
        pos = m.start()
        sys.exit(
            f"NORM CODEPOINT ERROR: U+{ord(ch):04X} '{ch}' "
            f"in section '{section}', line {line_no}\n"
            f"  context: {line[max(0, pos-30):pos+30]!r}"
        )
    m2 = _DASH_BETWEEN_NUMS.search(line)
    if m2:
        sys.exit(
            f"NORM ERROR: dash between spelled-out numerals "
            f"in section '{section}', line {line_no}\n"
            f"  context: {line[max(0, m2.start()-20):m2.end()+20]!r}"
        )
    m3 = _PREP_BEFORE_OT.search(line)
    if m3:
        sys.exit(
            f"NORM ERROR: preposition before 'от' (range collision) "
            f"in section '{section}', line {line_no}\n"
            f"  context: {line[max(0, m3.start()-20):m3.end()+20]!r}"
        )


_MIN_SECTION_BYTES = 50


def main() -> None:
    text_dir = paths.TEXT
    skipped = []
    for txt_file in sorted(text_dir.glob('[0-9][0-9]_*.txt')):
        if '.norm.' in txt_file.name or '.acc.' in txt_file.name:
            continue
        if txt_file.stat().st_size < _MIN_SECTION_BYTES:
            skipped.append(txt_file.name)
            print(f"SKIP (empty section): {txt_file.name}")
            continue
        lines = txt_file.read_text(encoding='utf-8').splitlines()
        out_lines = []
        for i, line in enumerate(lines, 1):
            normed, _ = normalize_line(line)
            assert_norm_chars(normed, txt_file.stem, i)
            out_lines.append(normed)
        stem = txt_file.stem
        norm_path = txt_file.parent / f"{stem}.norm.txt"
        with open(norm_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(out_lines))
        print(f"Written: {norm_path.name}")


if __name__ == '__main__':
    main()
