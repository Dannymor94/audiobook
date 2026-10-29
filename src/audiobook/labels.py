"""Journal of listening decisions: text/labels.yaml (text only, lives in git).

    ./run.sh labels import labels_<title>.json [--section S]
    ./run.sh labels show [--section S]

The JSON comes from the review page (``./run.sh review``). Each marked item
becomes one journal entry; re-importing the same file adds nothing (dedupe on
page_id — or the title for an old JSON without it — + file + hash prefix), while
the same file name on another page or another run is a new entry. Unmarked
items are skipped; a comment without a mark counts as
«?». The journal says what was heard — it never changes audio, hashes or the
chunk cache; fixes still go to pronounce.yaml / read_rules / redo+accept.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from audiobook import paths

LABELS = ("ok", "bad", "unsure")
ISSUES = ("ударение", "акцент", "каша", "темп", "артефакт", "другое")
_ALIASES = {"хорошо": "ok", "плохо": "bad", "?": "unsure"}
FIELDS = ("date", "title", "page_id", "file", "section", "chunk", "hash_prefix", "item",
          "label", "issue", "note")

HEADER = """\
# Журнал решений «на слух». Дописывается командой `./run.sh labels import`,
# читается `./run.sh labels show`. Только текст — в git. Аудио и хеши не трогает.
#
# Поля записи:
#   date         дата импорта (ГГГГ-ММ-ДД)
#   title        название страницы прослушки (папка, из которой слушали)
#   page_id      хеш страницы (папка + список wav); у старых записей пуст
#   file         wav относительно папки страницы; (page_id или title, file,
#                hash_prefix) уникальны
#   section      секция книги (из разметки или --section)
#   chunk        id чанка, если известен
#   hash_prefix  первые 8 символов хеша чанка, если известен
#   item         что именно слушали (вариант/дубль/пара), для человека
#   label        ok | bad | unsure
#   issue        ударение | акцент | каша | темп | артефакт | другое (если bad)
#   note         комментарий
"""


def labels_path() -> Path:
    return paths.TEXT / "labels.yaml"


def load(path: Path | None = None) -> list[dict]:
    import yaml
    path = path or labels_path()
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [e for e in (data or []) if isinstance(e, dict)]


def _write(entries: list[dict], path: Path) -> None:
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(entries, allow_unicode=True, sort_keys=False,
                          default_flow_style=False, width=1000) if entries else "[]\n"
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(HEADER + "\n" + body)
    tmp.replace(path)


def _hash_prefix(meta: dict, file: str, item_hash: str = "") -> str:
    h = str(item_hash or meta.get("hash") or "")
    if not h:
        stem = Path(file).stem
        if len(stem) == 16 and all(c in "0123456789abcdef" for c in stem):
            h = stem
    return h[:8]


def entries_from_json(data: dict, section: str | None, today: str) -> tuple[list[dict], int]:
    """(journal entries for marked items, number of unmarked items skipped)."""
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise SystemExit("это не разметка прослушки: нет списка items")
    title = str(data.get("title") or "")
    pid = str(data.get("page_id") or "")
    out, skipped = [], 0
    for it in data["items"]:
        if not isinstance(it, dict) or not it.get("file"):
            continue
        label = str(it.get("label") or "").strip().lower()
        label = _ALIASES.get(label, label)
        comment = str(it.get("comment") or "").strip()
        if label not in LABELS:
            if label or not comment:
                skipped += 1
                continue
            label = "unsure"
        meta = it.get("meta") if isinstance(it.get("meta"), dict) else {}
        file = str(it["file"])
        issue = str(it.get("issue") or "").strip()
        if issue and issue not in ISSUES:
            issue = "другое"
        out.append({
            "date": today,
            "title": title,
            "page_id": pid,
            "file": file,
            "section": section or str(it.get("section") or meta.get("section")
                                      or data.get("section") or ""),
            "chunk": str(it.get("chunk") or meta.get("chunk") or ""),
            "hash_prefix": _hash_prefix(meta, file, str(it.get("hash") or "")),
            "item": str(meta.get("item") or Path(file).stem),
            "label": label,
            "issue": issue,
            "note": comment,
        })
    return out, skipped


def dedupe_key(e: dict) -> tuple[str, str, str, str]:
    """(namespace, page, file, hash prefix): page_id when the page had one,
    else the title (journal entries and JSON from before page_id)."""
    pid = str(e.get("page_id") or "")
    page = ("page", pid) if pid else ("title", str(e.get("title") or ""))
    return (*page, str(e.get("file") or ""), str(e.get("hash_prefix") or ""))


def import_json(path: Path, section: str | None = None, journal: Path | None = None,
                today: str | None = None) -> tuple[int, int, int]:
    """Append the marked items of a labels_*.json to the journal.
    Returns (added, duplicates, unmarked)."""
    path = Path(path)
    if not path.is_file():
        raise SystemExit(f"нет файла: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:
        raise SystemExit(f"не читается JSON {path.name}: {e}")
    journal = journal or labels_path()
    today = today or datetime.date.today().isoformat()
    new, unmarked = entries_from_json(data, section, today)
    entries = load(journal)
    seen = {dedupe_key(e) for e in entries}
    added = 0
    for e in new:
        key = dedupe_key(e)
        if key in seen:
            continue
        seen.add(key)
        entries.append(e)
        added += 1
    if added or not journal.exists():
        _write(entries, journal)
    return added, len(new) - added, unmarked


def run_import(path: str, section: str | None) -> int:
    added, dup, unmarked = import_json(Path(path), section)
    print(f"в журнал {labels_path()}: добавлено {added}, уже были {dup}, без оценки {unmarked}")
    return 0


def _cut(s: str, n: int) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "…"


def format_table(entries: list[dict]) -> list[str]:
    cols = [("date", "дата", 10), ("section", "секция", 16), ("chunk", "чанк", 6),
            ("hash_prefix", "хеш", 8), ("item", "что", 22), ("label", "оценка", 6),
            ("issue", "что не так", 10), ("note", "комментарий", 40)]
    lines = ["  ".join(h.ljust(w) for _k, h, w in cols).rstrip()]
    for e in entries:
        lines.append("  ".join(_cut(e.get(k, ""), w).ljust(w) for k, _h, w in cols).rstrip())
    return lines


def show(section: str | None = None, journal: Path | None = None) -> list[dict]:
    entries = load(journal)
    if section:
        entries = [e for e in entries if e.get("section") == section]
    if not entries:
        print("журнал пуст" + (f" для секции {section}" if section else ""))
        return entries
    for line in format_table(entries):
        print(line)
    counts = {k: sum(1 for e in entries if e.get("label") == k) for k in LABELS}
    print(f"\nвсего {len(entries)}: ok {counts['ok']}, bad {counts['bad']}, "
          f"unsure {counts['unsure']}")
    return entries


def run_show(section: str | None) -> int:
    show(section)
    return 0
