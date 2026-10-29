"""Lint the whole manuscript (text/*.norm.txt) BEFORE rendering it.

Finds things a human should fix in the text, never fixes anything itself:
a missed «ё» (the model reads «слезы» with the stress on the wrong syllable),
typos that survive spell-checking, and tokens the TTS has to be told how to read.
Output: out/lint/text_lint.md + a short console summary.

Sections of the report:
  1. «Вероятно пропущена ё»  — word is written both with ё and without (ё→е folding
     makes them equal); every occurrence WITHOUT ё is listed with context.
  2. «Неоднозначные е/ё»     — small explicit list (все/всё, ее/её, еще/ещё …); shown
     only if the book has the ё-variant somewhere.
  3. «Подозрительные формы»  — hints, not corrections: rare word next to a frequent
     near-twin, repeated word, Latin letters inside a Cyrillic word, «…ётся и»
     (maybe past tense «-ёгся»), tripled letters.
  4. «Для озвучки»          — abbreviations, digits, Latin tokens, hyphenated caps.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

from audiobook import paths

CONTEXT_RADIUS = 40
EXAMPLES_CAP = 5            # contexts shown per word outside section 1
RARE_MAX_FREQ = 2           # «rare» word: occurs at most this many times
FREQUENT_MIN_FREQ = 5       # «frequent» neighbour: occurs at least this many times
RARE_MIN_LEN = 5
MAX_EDIT = 2
DIST2_MIN_LEN = 8          # distance 2 on a short word matches too many real words

# Pairs where the ё-spelling is a different word or a frequent source of noise.
# no-ё form → (ё form, note). Excluded from section 1, reported in section 2.
AMBIGUOUS: dict[str, tuple[str, str]] = {
    "все": ("всё", "омограф, проверить по смыслу"),
    "небо": ("нёбо", "омограф, проверить по смыслу"),
    "полет": ("полёт", "омограф, проверить по смыслу"),
    "берет": ("берёт", "омограф, проверить по смыслу"),
    "осел": ("осёл", "омограф, проверить по смыслу"),
    "узнает": ("узнаёт", "омограф, проверить по смыслу"),
    "чем": ("чём", "почти всегда «чем» — проверить только «о чём», «при чём»"),
    "ее": ("её", "то же слово: ё нужна всегда"),
    "нее": ("неё", "то же слово: ё нужна всегда"),
    "еще": ("ещё", "то же слово: ё нужна всегда"),
}

_CYR = "А-Яа-яЁё"
_WORD = re.compile(rf"[{_CYR}]+")
_ANY_WORD = re.compile(rf"[A-Za-z{_CYR}]+")
_HYPHEN_WORD = re.compile(rf"[{_CYR}]+(?:-[{_CYR}]+)+")
_LATIN = re.compile(
    rf"(?<![A-Za-z{_CYR}])[A-Za-z]+(?:[-.'][A-Za-z]+)*(?![A-Za-z{_CYR}])")
_DIGITS = re.compile(rf"\d+(?:[.,:/\-–]\d+)*(?:-?[{_CYR}]+)?")
_REPEAT = re.compile(
    rf"(?<![\w-])([{_CYR}]+)[ \t ]+\1(?![\w-])", re.IGNORECASE)
_YOTSYA_I = re.compile(
    rf"(?<![\w-])([{_CYR}]*ётся)[ \t ]+и(?![\w-])", re.IGNORECASE)
_TRIPLE = re.compile(r"(.)\1\1")

# (stem, context) — one place in the text.
Hit = tuple[str, str]


# ── primitives ───────────────────────────────────────────────────────────────

def fold(word: str) -> str:
    """Lowercase and ё→е: the key under which ё/е spellings of one word meet."""
    return word.lower().replace("ё", "е")


def context(text: str, start: int, end: int, radius: int = CONTEXT_RADIUS) -> str:
    """±radius chars around [start:end], the word itself in **bold**, one line."""
    left = " ".join(text[max(0, start - radius):start].split())
    right = " ".join(text[end:end + radius].split())
    sep_l = " " if text[max(0, start - 1):start].isspace() and left else ""
    sep_r = " " if text[end:end + 1].isspace() and right else ""
    return f"{left}{sep_l}**{text[start:end]}**{sep_r}{right}".strip()


def read_sections(text_dir: Path | None = None) -> dict[str, str]:
    """{file stem: text} for every *.norm.txt, in file-name order."""
    base = text_dir if text_dir is not None else paths.TEXT
    out: dict[str, str] = {}
    for f in sorted(base.glob("*.norm.txt")):
        out[f.name[: -len(".norm.txt")]] = f.read_text(encoding="utf-8")
    return out


def _words(text: str):
    """Yield (surface, start, end) for each Cyrillic word."""
    for m in _WORD.finditer(text):
        yield m.group(), m.start(), m.end()


def word_count(sections: dict[str, str]) -> int:
    return sum(1 for t in sections.values() for _ in _words(t))


def surface_freq(sections: dict[str, str]) -> Counter:
    """Counter of lowercase surface forms (ё kept)."""
    c: Counter = Counter()
    for t in sections.values():
        for w, _s, _e in _words(t):
            c[w.lower()] += 1
    return c


# ── 1. missed ё ──────────────────────────────────────────────────────────────

def find_missing_yo(sections: dict[str, str]) -> list[dict]:
    """Words spelled both with and without ё. One dict per folded word:
    {"plain": str, "yo": {form: count}, "hits": [(stem, ctx)]} — hits are the
    occurrences WITHOUT ё. Sorted by number of hits, descending."""
    forms = surface_freq(sections)
    groups: dict[str, dict[str, int]] = defaultdict(dict)
    for form, n in forms.items():
        groups[fold(form)][form] = n
    wanted: dict[str, dict[str, int]] = {}
    for key, fs in groups.items():
        if key in AMBIGUOUS:
            continue
        yo = {f: n for f, n in fs.items() if f != key}
        if key in fs and yo:
            wanted[key] = yo
    hits: dict[str, list[Hit]] = {k: [] for k in wanted}
    for stem, text in sections.items():
        for w, s, e in _words(text):
            lw = w.lower()
            if lw in wanted and lw == fold(lw):
                hits[lw].append((stem, context(text, s, e)))
    res = [{"plain": k, "yo": wanted[k], "hits": hits[k]} for k in wanted]
    res.sort(key=lambda d: (-len(d["hits"]), d["plain"]))
    return res


def find_ambiguous_yo(sections: dict[str, str]) -> list[dict]:
    """For each AMBIGUOUS pair whose ё-form occurs in the book:
    {"plain", "yo", "note", "n_plain", "n_yo", "hits": first EXAMPLES_CAP no-ё contexts}."""
    forms = surface_freq(sections)
    res = []
    for plain, (yo, note) in AMBIGUOUS.items():
        n_yo = forms.get(yo, 0)
        if not n_yo:
            continue
        res.append({"plain": plain, "yo": yo, "note": note,
                    "n_plain": forms.get(plain, 0), "n_yo": n_yo, "hits": []})
    by_plain = {d["plain"]: d for d in res}
    for stem, text in sections.items():
        for w, s, e in _words(text):
            d = by_plain.get(w.lower())
            if d is not None and len(d["hits"]) < EXAMPLES_CAP:
                d["hits"].append((stem, context(text, s, e)))
    return res


# ── 2. suspicious forms ──────────────────────────────────────────────────────

def edit_distance_le(a: str, b: str, limit: int) -> int:
    """Levenshtein distance, or limit+1 as soon as it is known to exceed limit."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def _only_tail_differs(a: str, b: str, tail: int = 3) -> bool:
    """True if the words differ only in their last `tail` letters — that is a
    plain inflection (дорога/дорогу), not a typo; skipped to keep the noise down."""
    p = 0
    for x, y in zip(a, b):
        if x != y:
            break
        p += 1
    return p >= min(len(a), len(b)) - tail


def find_rare_neighbors(sections: dict[str, str]) -> list[dict]:
    """Rare words (≤2 occurrences, ≥5 letters) that have a frequent (≥5) word with
    the same first letter at edit distance 1–2 (ё folded). One dict per rare word:
    {"word", "freq", "neighbors": [(form, freq, dist)], "hits"}; sorted by
    best distance, then by neighbour frequency (desc)."""
    folded: Counter = Counter()
    surface: dict[str, Counter] = defaultdict(Counter)
    for form, n in surface_freq(sections).items():
        k = fold(form)
        folded[k] += n
        surface[k][form] += n
    frequent: dict[str, list[str]] = defaultdict(list)
    for k, n in folded.items():
        if n >= FREQUENT_MIN_FREQ:
            frequent[k[:1]].append(k)
    found: dict[str, list[tuple[str, int, int]]] = {}
    for k, n in folded.items():
        if n > RARE_MAX_FREQ or len(k) < RARE_MIN_LEN:
            continue
        nb = []
        for cand in frequent.get(k[:1], ()):
            if abs(len(cand) - len(k)) > MAX_EDIT or _only_tail_differs(k, cand):
                continue
            d = edit_distance_le(k, cand, MAX_EDIT)
            if d == MAX_EDIT and len(k) < DIST2_MIN_LEN:
                continue
            if d <= MAX_EDIT:
                nb.append((surface[cand].most_common(1)[0][0], folded[cand], d))
        if nb:
            nb.sort(key=lambda t: (t[2], -t[1], t[0]))
            found[k] = nb[:3]
    hits: dict[str, list[Hit]] = {k: [] for k in found}
    for stem, text in sections.items():
        for w, s, e in _words(text):
            k = fold(w)
            if k in hits:
                hits[k].append((stem, context(text, s, e)))
    res = [{"word": surface[k].most_common(1)[0][0], "freq": folded[k],
            "neighbors": nb, "hits": hits[k]} for k, nb in found.items()]
    res.sort(key=lambda d: (d["neighbors"][0][2], -d["neighbors"][0][1], d["word"]))
    return res


def _regex_hits(sections: dict[str, str], rx: re.Pattern, group: int = 0) -> list[Hit]:
    out: list[Hit] = []
    for stem, text in sections.items():
        for m in rx.finditer(text):
            out.append((stem, context(text, m.start(group), m.end(group))))
    return out


def find_repeats(sections: dict[str, str]) -> list[Hit]:
    """The same word twice in a row on one line («и и»)."""
    out: list[Hit] = []
    for stem, text in sections.items():
        for m in _REPEAT.finditer(text):
            out.append((stem, context(text, m.start(), m.end())))
    return out


def find_mixed_script(sections: dict[str, str]) -> list[Hit]:
    """Latin letters inside a Cyrillic word (or the reverse)."""
    out: list[Hit] = []
    for stem, text in sections.items():
        for m in _ANY_WORD.finditer(text):
            w = m.group()
            if re.search("[A-Za-z]", w) and re.search(rf"[{_CYR}]", w):
                out.append((stem, context(text, m.start(), m.end())))
    return out


def find_yotsya_i(sections: dict[str, str]) -> list[Hit]:
    """«…ётся и» — maybe a typo for past tense «…ёгся» («обжёгся и»)."""
    out: list[Hit] = []
    for stem, text in sections.items():
        for m in _YOTSYA_I.finditer(text):
            out.append((stem, context(text, m.start(), m.end())))
    return out


def find_triple_letters(sections: dict[str, str]) -> list[Hit]:
    """Three identical letters in a row inside a word (not «ааа»-style interjections)."""
    out: list[Hit] = []
    for stem, text in sections.items():
        for w, s, e in _words(text):
            lw = w.lower()
            if len(set(lw)) > 1 and _TRIPLE.search(lw):
                out.append((stem, context(text, s, e)))
    return out


# ── 3. for TTS ───────────────────────────────────────────────────────────────

def find_abbreviations(sections: dict[str, str]) -> list[dict]:
    """All-caps words (≥2 letters) the book never writes in lowercase.
    [{"word", "count", "hits": first examples}] sorted by count desc."""
    lower_seen: set[str] = set()
    for t in sections.values():
        for w, _s, _e in _words(t):
            if not w.isupper():
                lower_seen.add(w.lower())
    acc: dict[str, dict] = {}
    for stem, text in sections.items():
        for w, s, e in _words(text):
            if len(w) < 2 or not w.isupper() or w.lower() in lower_seen:
                continue
            d = acc.setdefault(w, {"word": w, "count": 0, "hits": []})
            d["count"] += 1
            if len(d["hits"]) < EXAMPLES_CAP:
                d["hits"].append((stem, context(text, s, e)))
    return sorted(acc.values(), key=lambda d: (-d["count"], d["word"]))


def find_hyphen_caps(sections: dict[str, str]) -> list[dict]:
    """Hyphenated words with an all-caps part (ПТСР-синдром)."""
    acc: dict[str, dict] = {}
    for stem, text in sections.items():
        for m in _HYPHEN_WORD.finditer(text):
            parts = m.group().split("-")
            if not any(len(p) >= 2 and p.isupper() for p in parts):
                continue
            d = acc.setdefault(m.group(), {"word": m.group(), "count": 0, "hits": []})
            d["count"] += 1
            if len(d["hits"]) < EXAMPLES_CAP:
                d["hits"].append((stem, context(text, m.start(), m.end())))
    return sorted(acc.values(), key=lambda d: (-d["count"], d["word"]))


def _token_groups(sections: dict[str, str], rx: re.Pattern) -> list[dict]:
    acc: dict[str, dict] = {}
    for stem, text in sections.items():
        for m in rx.finditer(text):
            d = acc.setdefault(m.group(), {"word": m.group(), "count": 0, "hits": []})
            d["count"] += 1
            if len(d["hits"]) < EXAMPLES_CAP:
                d["hits"].append((stem, context(text, m.start(), m.end())))
    return sorted(acc.values(), key=lambda d: (-d["count"], d["word"]))


def find_digits(sections: dict[str, str]) -> list[dict]:
    return _token_groups(sections, _DIGITS)


def find_latin(sections: dict[str, str]) -> list[dict]:
    """Standalone Latin-script tokens (URLs, PDF, Roman numerals)."""
    return _token_groups(sections, _LATIN)


# ── report ───────────────────────────────────────────────────────────────────

def _hit_lines(hits: list[Hit], cap: int | None = None) -> list[str]:
    shown = hits if cap is None else hits[:cap]
    lines = [f"  - `{stem}`: {ctx}" for stem, ctx in shown]
    if cap is not None and len(hits) > cap:
        lines.append(f"  - … и ещё {len(hits) - cap}")
    return lines


def _group_lines(groups: list[dict]) -> list[str]:
    lines: list[str] = []
    for d in groups:
        lines.append(f"- **{d['word']}** ×{d['count']}")
        lines += _hit_lines(d["hits"], EXAMPLES_CAP)
    return lines


def lint(sections: dict[str, str]) -> dict:
    """Run every check; the result feeds render_report()/summary()."""
    return {
        "n_sections": len(sections),
        "n_words": word_count(sections),
        "missing_yo": find_missing_yo(sections),
        "ambiguous": find_ambiguous_yo(sections),
        "rare": find_rare_neighbors(sections),
        "repeats": find_repeats(sections),
        "mixed": find_mixed_script(sections),
        "yotsya": find_yotsya_i(sections),
        "triple": find_triple_letters(sections),
        "abbrev": find_abbreviations(sections),
        "hyphen_caps": find_hyphen_caps(sections),
        "digits": find_digits(sections),
        "latin": find_latin(sections),
    }


def summary(res: dict) -> list[tuple[str, int]]:
    """[(section title, number of items)] — what the console prints."""
    return [
        ("Вероятно пропущена ё (слов)", len(res["missing_yo"])),
        ("Вероятно пропущена ё (мест)", sum(len(d["hits"]) for d in res["missing_yo"])),
        ("Неоднозначные е/ё (пар)", len(res["ambiguous"])),
        ("Подозрительные: редкое слово рядом с частым", len(res["rare"])),
        ("Подозрительные: повтор слова подряд", len(res["repeats"])),
        ("Подозрительные: латиница в кириллическом слове", len(res["mixed"])),
        ("Подозрительные: «-ётся и»", len(res["yotsya"])),
        ("Подозрительные: тройная буква", len(res["triple"])),
        ("Для озвучки: аббревиатуры", len(res["abbrev"])),
        ("Для озвучки: слова через дефис с капсом", len(res["hyphen_caps"])),
        ("Для озвучки: числа цифрами", len(res["digits"])),
        ("Для озвучки: латиница", len(res["latin"])),
    ]


def render_report(res: dict) -> str:
    L: list[str] = ["# Проверка текста перед озвучкой", "",
                    f"Секций: {res['n_sections']}, слов: {res['n_words']}. "
                    "Это подсказки для человека: в тексте ничего не исправлено.", ""]

    L += ["## Вероятно пропущена ё", "",
          "Слово есть в книге и с «ё», и без; ниже все места БЕЗ «ё».", ""]
    if not res["missing_yo"]:
        L += ["Не найдено.", ""]
    for d in res["missing_yo"]:
        yo = ", ".join(f"{f} ×{n}" for f, n in sorted(d["yo"].items(), key=lambda t: -t[1]))
        L.append(f"### {d['plain']} ×{len(d['hits'])} (с ё: {yo})")
        L += _hit_lines(d["hits"])
        L.append("")

    L += ["## Неоднозначные е/ё", "",
          "Пары из короткого списка в коде; показаны, только если в книге есть ё-написание.", ""]
    if not res["ambiguous"]:
        L += ["Не найдено.", ""]
    for d in res["ambiguous"]:
        L.append(f"### {d['plain']} ×{d['n_plain']} / {d['yo']} ×{d['n_yo']} — {d['note']}")
        L += _hit_lines(d["hits"])
        L.append("")

    L += ["## Подозрительные формы", ""]
    L += ["### Редкое слово рядом с частым", "",
          f"Слово встречается ≤{RARE_MAX_FREQ} раз(а), рядом по написанию (расстояние "
          f"Левенштейна 1–{MAX_EDIT}, та же первая буква) есть слово с частотой "
          f"≥{FREQUENT_MIN_FREQ}. Различия только в последних трёх буквах не считаются "
          f"(это обычное словоизменение); расстояние 2 — только для слов от {DIST2_MIN_LEN} букв.", ""]
    if not res["rare"]:
        L += ["Не найдено.", ""]
    for d in res["rare"]:
        nb = ", ".join(f"{f} ×{n} (р={dist})" for f, n, dist in d["neighbors"])
        L.append(f"- **{d['word']}** ×{d['freq']} — похоже на: {nb}")
        L += _hit_lines(d["hits"])
    L.append("")
    sub = [
        ("Повтор слова подряд", res["repeats"]),
        ("Латиница внутри кириллического слова", res["mixed"]),
        ("«-ётся» перед «и» — проверить: возможно прош. время «-ёгся»", res["yotsya"]),
        ("Три одинаковые буквы подряд", res["triple"]),
    ]
    for title, hits in sub:
        L += [f"### {title} ({len(hits)})", ""]
        L += _hit_lines(hits) if hits else ["Не найдено."]
        L.append("")

    L += ["## Для озвучки", ""]
    for title, groups in [("Аббревиатуры (капс, которого нет в нижнем регистре)", res["abbrev"]),
                          ("Слова через дефис с капсом", res["hyphen_caps"]),
                          ("Числа цифрами", res["digits"]),
                          ("Латиница", res["latin"])]:
        L += [f"### {title} ({len(groups)})", ""]
        L += _group_lines(groups) if groups else ["Не найдено."]
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def run(config: dict | None = None) -> int:
    """CLI entry: lint text/*.norm.txt → out/lint/text_lint.md."""
    sections = read_sections()
    if not sections:
        print(f"нет файлов *.norm.txt в {paths.TEXT}")
        return 1
    res = lint(sections)
    out_dir = paths.OUT / "lint"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "text_lint.md"
    tmp = target.with_name(target.name + ".part")
    tmp.write_text(render_report(res), encoding="utf-8")
    tmp.replace(target)
    print(f"секций: {res['n_sections']}, слов: {res['n_words']}")
    for title, n in summary(res):
        print(f"  {title}: {n}")
    print(f"отчёт: {target}")
    return 0
