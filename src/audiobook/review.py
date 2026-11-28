"""Listening page: one self-contained review.html next to the wavs.

    ./run.sh review --dir out/pron_test/<...> [--title T] [--meta file.tsv]

Every wav gets a player, buttons хорошо / плохо / ?, an issue select and a
comment box; marks live in the browser (localStorage) and leave it as
labels_<title>_<page_id>.json ("Скачать разметку" or "Копировать JSON"), which
``./run.sh labels import`` appends to the text journal text/labels.yaml.

Page identity: ``page_id`` = short hash of the folder name chain (relative to
out/, else the last three names) + the sorted wav list with size and mtime.
It keys the browser storage (title + page_id) and goes into the exported JSON,
so two pages with the same title (or a re-run with the same file names) never
share marks and the journal does not drop them as duplicates.

The page has no external URLs (opens from file://), wav paths are relative to
the page. Folder kinds are detected from file names:

  pron-test   n.wav + meta.tsv (n, chunk, variant, take, start, synth_text)
  redo        variant_XX__seed+N.wav  (out/redo/<section>/<chunk>/)
  probe       chunks/<hash16>.wav listed in index.tsv (hash column, or via
              manifests for an old index); wavs not in the index are ignored
  golden      NN_A.wav / NN_B.wav pairs side by side, captions from index.tsv
              (n, file_a, file_b, section, chunk, why, text, tag_a, tag_b)
  ref-compare <candidate>/<hash16>.wav (or legacy <chunk id>.wav) subfolders,
              one row per chunk
  generic     any other *.wav

``build_combined`` puts several folders on one page (``./run.sh fix review``:
the redo candidates of every planned chunk, one row per chunk).

Nothing here touches models, manifests or the chunk cache.
"""
from __future__ import annotations

import csv
import datetime
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from audiobook import paths

ISSUES = ["ударение", "акцент", "каша", "темп", "артефакт", "другое"]
KIND_NAMES = {
    "pron-test": "pron-test: дубли написаний",
    "redo": "redo: кандидаты чанка",
    "probe": "probe: подборка ловушек",
    "golden": "golden: пары A/B",
    "ref-compare": "ref-compare: кандидаты референса",
    "generic": "wav-файлы",
}
# meta keys shown as small chips under the file name, in this order
CHIP_KEYS = ["tag", "section", "chunk", "variant", "take", "seed_offset", "start", "tags", "why"]
OLD_PREFIX = "_old_"  # archived runs (see archive_stale); never listed on a page


# ── reading the folder ────────────────────────────────────────────────────────

def _natural(s: str) -> list:
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", s)]


def read_tsv(path: Path) -> list[dict]:
    """Header row + data rows; no quoting (our index/meta files never escape)."""
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    if not rows:
        return []
    head = [h.strip() for h in rows[0]]
    return [dict(zip(head, r)) for r in rows[1:] if any(c.strip() for c in r)]


def _archived(p: Path, base: Path) -> bool:
    return any(part.startswith(OLD_PREFIX) for part in p.relative_to(base).parts[:-1])


def _wavs(folder: Path, recursive: bool = False) -> list[Path]:
    it = folder.rglob("*.wav") if recursive else folder.glob("*.wav")
    return sorted((p for p in it if p.is_file() and not _archived(p, folder)),
                  key=lambda p: _natural(p.name))


def _subdirs(folder: Path) -> list[Path]:
    return [d for d in folder.iterdir() if d.is_dir() and not d.name.startswith(OLD_PREFIX)]


def archive_stale(folder: Path, files: list[Path],
                  say: Callable[[str], None] = print) -> Path | None:
    """Move the files of a previous run into folder/_old_<timestamp>/ — moved,
    never deleted. Returns the archive folder, or None if there was nothing."""
    files = [f for f in files if f.is_file()]
    if not files:
        return None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = folder / f"{OLD_PREFIX}{stamp}"
    k = 2
    while dest.exists():
        dest = folder / f"{OLD_PREFIX}{stamp}_{k}"
        k += 1
    dest.mkdir(parents=True)
    for f in files:
        f.rename(dest / f.name)
    say(f"файлы прошлого прогона ({len(files)} шт.) перенесены в {dest}")
    return dest


def _rel(base: Path, p: Path) -> str:
    return p.relative_to(base).as_posix()


def _clean(meta: dict) -> dict:
    return {k: str(v) for k, v in meta.items() if v is not None and str(v) != ""}


def _manifest_rows(out_root: Path, section: str) -> dict[str, dict]:
    """id -> manifest row of out/sections/<section>; {} if there is none."""
    mp = out_root / "sections" / section / "manifest.jsonl"
    try:
        lines = mp.read_text(encoding="utf-8").splitlines()
        rows = [json.loads(ln) for ln in lines if ln.strip()]
        return {str(r["id"]): r for r in rows}
    except (OSError, ValueError, KeyError):
        return {}


def _manifest_hashes(out_root: Path) -> dict[str, tuple[str, str]]:
    """hash16 -> (section, chunk id) over all section manifests."""
    out: dict[str, tuple[str, str]] = {}
    sections = out_root / "sections"
    if not sections.is_dir():
        return out
    for d in sorted(p for p in sections.iterdir() if p.is_dir()):
        for cid, row in _manifest_rows(out_root, d.name).items():
            if row.get("hash"):
                out[str(row["hash"])[:16]] = (d.name, cid)
    return out


def _item(file: str, name: str, meta: dict, item: str = "") -> dict:
    meta = _clean(meta)
    if item:
        meta["item"] = item
    return {"file": file, "name": name, "meta": meta}


def _kind_pron(folder: Path, meta_rows: list[dict]) -> list[list[dict]]:
    by_n = {r.get("n", ""): r for r in meta_rows}
    groups = []
    for w in _wavs(folder):
        r = by_n.get(w.stem, {})
        name = f"{w.stem}. {r['variant']} · дубль {r.get('take', '')}" if r.get("variant") else w.name
        item = f"{r['variant']} / дубль {r.get('take', '')}" if r.get("variant") else w.stem
        groups.append([_item(w.name, name, r, item)])
    return groups


def _kind_redo(folder: Path, wavs: list[Path]) -> list[list[dict]]:
    f = folder.resolve()
    ctx: dict = {}
    rows: dict[str, dict] = {}
    if f.parent.parent.name == "redo":  # out/redo/<section>/<chunk>/
        ctx = {"section": f.parent.name, "chunk": f.name}
        rows = _manifest_rows(f.parent.parent.parent, f.parent.name)
    row = rows.get(f.name, {})
    groups = []
    for w in wavs:
        m = re.fullmatch(r"variant_(\d+)__seed\+(\d+)\.wav", w.name)
        meta = dict(ctx, variant=m.group(1) if m else "", seed_offset=m.group(2) if m else "",
                    text=row.get("text", ""), hash=str(row.get("hash", ""))[:16])
        groups.append([_item(w.name, f"variant {m.group(1)}" if m else w.name, meta,
                             f"variant {m.group(1)}" if m else w.stem)])
    return groups


def _kind_probe(folder: Path, wav_dir: Path, index_path: Path | None) -> list[list[dict]]:
    """Only wavs named by the index are listed, in index (listening) order;
    other wavs in chunks/ (older picks, other configs) are ignored. An old
    index without a hash column is mapped via the section manifests."""
    index = read_tsv(index_path) if index_path and index_path.exists() else []
    present = {w.stem: w for w in _wavs(wav_dir)}
    strict = any(r.get("hash") for r in index)
    by_key: dict[tuple[str, str], str] = {}
    if not strict:
        base = folder.resolve()
        out_root = base.parent.parent if base.name == "chunks" else base.parent
        by_key = {key: h for h, key in _manifest_hashes(out_root).items()}
    groups, seen = [], set()
    for r in index:
        h = r.get("hash", "") if strict else by_key.get((r.get("section", ""), r.get("chunk", "")), "")
        if not h or h in seen or h not in present:
            continue
        seen.add(h)
        w = present[h]
        meta = {"section": r.get("section", ""), "chunk": r.get("chunk", ""),
                "start": r.get("start", ""), "tags": r.get("tags", ""),
                "text": r.get("text", ""), "hash": h}
        name = f"{r.get('start', '')} · {r.get('section', '')} {r.get('chunk', '')}".strip(" ·")
        groups.append([_item(_rel(folder, w), name, meta,
                             f"{r.get('section', '')}/{r.get('chunk', '')}")])
    return groups


_PAIR_RE = re.compile(r"(.+)_([AB])\.wav")


def _kind_golden(folder: Path, wavs: list[Path]) -> list[list[dict]]:
    """Pairs in index.tsv order (golden compare: n, file_a, file_b, section,
    chunk, why, text, tag_a, tag_b); captions name the tags. Wavs not in the
    index (or no index at all) are paired by name."""
    idx = folder / "index.tsv"
    index = [r for r in (read_tsv(idx) if idx.exists() else [])
             if r.get("file_a") or r.get("file_b")]
    names = {w.name for w in wavs}
    groups: list[list[dict]] = []
    used: set[str] = set()
    for r in index:
        grp = []
        for side in ("A", "B"):
            f = r.get(f"file_{side.lower()}", "")
            m = _PAIR_RE.fullmatch(f)
            if f not in names or f in used or not m:
                continue
            used.add(f)
            pair, tag = m.group(1), r.get(f"tag_{side.lower()}", "")
            meta = {"pair": pair, "side": side, "tag": tag, "section": r.get("section", ""),
                    "chunk": r.get("chunk", ""), "why": r.get("why", ""),
                    "text": r.get("text", ""), "start": r.get("start", ""),
                    "hash": r.get(f"hash_{side.lower()}", "")}
            caption = f"{pair} · {side}" + (f" · {tag}" if tag else "")
            item = f"{pair}_{side}" + (f" ({tag})" if tag else "")
            grp.append(_item(f, caption, meta, item))
        if grp:
            groups.append(grp)
    pairs: dict[str, list[Path]] = {}
    for w in wavs:
        if w.name not in used:
            pairs.setdefault(_PAIR_RE.fullmatch(w.name).group(1), []).append(w)
    for key in sorted(pairs, key=_natural):
        grp = []
        for w in sorted(pairs[key], key=lambda p: p.name):
            side = w.stem[-1]
            grp.append(_item(w.name, f"{key} · {side}", {"pair": key, "side": side},
                             f"{key}_{side}"))
        groups.append(grp)
    return groups


def _kind_refcmp(folder: Path, subdirs: list[Path]) -> list[list[dict]]:
    """Candidate wavs are named <hash16>.wav (legacy: <chunk id>.wav); the
    manifest maps a hash16 back to the chunk id and text."""
    f = folder.resolve()
    section, rows = "", {}
    if f.parent.name == "ref_compare":  # out/ref_compare/<section>/
        section = f.name
        rows = _manifest_rows(f.parent.parent, section)
    by_hash = {str(r.get("hash", ""))[:16]: r for r in rows.values() if r.get("hash")}
    order = {cid: i for i, cid in enumerate(rows)}
    by_chunk: dict[str, list[tuple[Path, str]]] = {}
    for d in subdirs:
        for w in _wavs(d):
            if w.stem in by_hash:
                cid, h = str(by_hash[w.stem]["id"]), w.stem
            else:
                cid, h = w.stem, ""
            by_chunk.setdefault(cid, []).append((w, h))
    groups = []
    for cid in sorted(by_chunk, key=lambda c: (order.get(c, len(order)), _natural(c))):
        grp = []
        for w, h in by_chunk[cid]:
            meta = {"section": section, "chunk": cid, "candidate": w.parent.name,
                    "text": rows.get(cid, {}).get("text", ""), "hash": h}
            grp.append(_item(_rel(folder, w), w.parent.name, meta, f"{w.parent.name}/{cid}"))
        groups.append(grp)
    return groups


def _apply_meta(groups: list[list[dict]], meta_rows: list[dict]) -> None:
    """Merge rows of an explicit --meta file into items: by file (path or base
    name), else by n / id / chunk equal to the wav stem."""
    for g in groups:
        for it in g:
            p = Path(it["file"])
            for r in meta_rows:
                if r.get("file") in (it["file"], p.name) or (
                        not r.get("file") and any(r.get(k) == p.stem for k in ("n", "id", "chunk"))):
                    it["meta"].update(_clean({k: v for k, v in r.items() if k != "file"}))
                    break


def collect(folder: Path, meta_rows: list[dict] | None = None) -> tuple[str, list[list[dict]]]:
    """(kind, groups of items). A group is a row on the page: one item, or the
    A/B pair / the candidates of one chunk."""
    explicit = meta_rows is not None
    if meta_rows is None and (folder / "meta.tsv").exists():
        meta_rows = read_tsv(folder / "meta.tsv")
    meta_rows = meta_rows or []
    top = _wavs(folder)

    if top and any(r.get("n") for r in meta_rows) and not any(
            re.fullmatch(r"variant_\d+__seed\+\d+\.wav", w.name) for w in top):
        return "pron-test", _kind_pron(folder, meta_rows)
    if top and all(re.fullmatch(r"variant_\d+__seed\+\d+\.wav", w.name) for w in top):
        kind, groups = "redo", _kind_redo(folder, top)
    elif ((folder / "chunks").is_dir() and _wavs(folder / "chunks")
          and (folder / "index.tsv").exists()):
        kind, groups = "probe", _kind_probe(folder, folder / "chunks", folder / "index.tsv")
    elif folder.name == "chunks" and top and (folder.parent / "index.tsv").exists():
        kind, groups = "probe", _kind_probe(folder, folder, folder.parent / "index.tsv")
    elif top and all(re.fullmatch(r".+_[AB]\.wav", w.name) for w in top):
        kind, groups = "golden", _kind_golden(folder, top)
    elif not top and any(_wavs(d) for d in _subdirs(folder)):
        subdirs = sorted((d for d in _subdirs(folder) if _wavs(d)),
                         key=lambda d: _natural(d.name))
        kind, groups = "ref-compare", _kind_refcmp(folder, subdirs)
    else:
        found = top or _wavs(folder, recursive=True)
        kind = "generic"
        groups = [[_item(_rel(folder, w), _rel(folder, w), {}, w.stem)] for w in found]
    if explicit and meta_rows:
        _apply_meta(groups, meta_rows)
    return kind, groups


# ── rendering ─────────────────────────────────────────────────────────────────

def _chips(meta: dict) -> str:
    out = [f'<span class="chip">{html.escape(k)} {html.escape(meta[k])}</span>'
           for k in CHIP_KEYS if meta.get(k)]
    return "".join(out)


def _render_item(i: int, it: dict) -> str:
    meta = it["meta"]
    src = quote(it["file"], safe="/+")
    text = ""
    if meta.get("text"):
        text += f'<p class="text">{html.escape(meta["text"])}</p>'
    if meta.get("synth_text") and meta.get("synth_text") != meta.get("text"):
        text += f'<p class="text synth"><b>модели:</b> {html.escape(meta["synth_text"])}</p>'
    ratings = ""
    if meta.get("control_ratings"):
        fields = (
            ("heard_stress", "Ударение в слове " + str(meta["target_word"]), (("1", "Первый слог"), ("2", "Второй слог"), ("unclear", "Не разобрать"))),
            ("lexical", "Все слова разборчивы?", (("yes", "Да"), ("no", "Нет"), ("unclear", "Не уверен"))),
            ("voice", "Похож на голос автора?", (("yes", "Да"), ("no", "Нет"), ("unclear", "Не уверен"))),
            ("rhythm", "Естественность ритма", (("ok", "Хорошо"), ("bad", "Плохо"), ("unclear", "Не уверен"))),
        )
        for key, label, opts in fields:
            choices = "".join(f'<option value="{v}">{html.escape(t)}</option>' for v, t in opts)
            ratings += (f'<label>{html.escape(label)}<select data-rating="{key}">'
                        f'<option value="">—</option>{choices}</select></label>')
    options = "".join(f'<option value="{o}">{o}</option>' for o in ISSUES)
    return (
        f'<article class="item" data-i="{i}">'
        f'<div class="head"><span class="name">{html.escape(it["name"])}</span>'
        f'<span class="mark" aria-live="polite"></span></div>'
        f'<div class="chips">{_chips(meta)}</div>{text}'
        f'<audio controls preload="none" src="{html.escape(src, quote=True)}"></audio>'
        '<div class="btns" role="group" aria-label="оценка">'
        '<button type="button" data-l="ok">хорошо</button>'
        '<button type="button" data-l="bad">плохо</button>'
        '<button type="button" data-l="unsure">?</button></div>'
        f'<select class="issue" aria-label="что не так"><option value="">что не так: —</option>'
        f'{options}</select>'
        f'{ratings}'
        '<textarea class="note" rows="2" placeholder="комментарий"></textarea>'
        '</article>'
    )


def _safe_name(title: str) -> str:
    s = re.sub(r"[^\w.\-]+", "_", title, flags=re.UNICODE).strip("_")
    return s or "review"


def page_id(folder: Path, files: list[str]) -> str:
    """Short hash of the folder name chain + the sorted wav list (size, mtime in
    whole seconds — survives rsync -a). Same folder and same audio → same id
    (marks in the browser survive a rebuilt page); another folder with the
    same title, or a re-run with the same file names → another id."""
    base = Path(folder).resolve()
    try:
        chain = base.relative_to(paths.OUT.resolve()).parts
    except ValueError:
        chain = base.parts[-3:]
    h = hashlib.sha1("\x1f".join(chain).encode("utf-8"))
    for f in sorted(files):
        try:
            st = (Path(folder) / f).stat()
            size, mtime = st.st_size, int(st.st_mtime)
        except OSError:
            size, mtime = -1, -1
        h.update(f"\x00{f}\x00{size}\x00{mtime}".encode("utf-8"))
    return h.hexdigest()[:10]


def render(title: str, kind: str, groups: list[list[dict]], pid: str = "") -> str:
    flat = [it for g in groups for it in g]
    body, i = [], 0
    for g in groups:
        cells = []
        for it in g:
            cells.append(_render_item(i, it))
            i += 1
        cls = "grp pair" if len(g) > 1 else "grp"
        body.append(f'<section class="{cls}">{"".join(cells)}</section>')
    data = {"title": title, "safe": _safe_name(title), "kind": kind, "page_id": pid,
            "items": [{"file": it["file"], "meta": it["meta"],
                       **{k: it["meta"][k] for k in ("section", "chunk", "hash")
                          if it["meta"].get(k)}}
                      for it in flat]}
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    return (TEMPLATE.replace("__TITLE__", html.escape(title))
            .replace("__KIND__", html.escape(KIND_NAMES.get(kind, kind)))
            .replace("__ITEMS__", "\n".join(body))
            .replace("__DATA__", blob))


def build_review(folder: Path, title: str | None = None,
                 meta_rows: list[dict] | None = None) -> Path:
    """Write <folder>/review.html and return its path."""
    folder = Path(folder)
    if not folder.is_dir():
        raise SystemExit(f"нет папки: {folder}")
    kind, groups = collect(folder, meta_rows)
    if not groups:
        raise SystemExit(f"в {folder} нет *.wav")
    if not title:
        base = folder.resolve()
        title = (base.parent if base.name == "chunks" else base).name
    out = folder / "review.html"
    tmp = folder / "review.html.part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(render(title, kind, groups,
                       page_id(folder, [it["file"] for g in groups for it in g])))
    tmp.replace(out)
    return out


def rel_url(base_dir: Path, target: Path) -> str:
    """Relative path from ``base_dir`` to ``target`` in URL form, walking up with
    '..' when needed (pathlib.relative_to cannot walk up before Python 3.12)."""
    b = Path(base_dir).resolve().parts
    t = Path(target).resolve().parts
    k = 0
    while k < min(len(b), len(t)) and b[k] == t[k]:
        k += 1
    return Path(*([".."] * (len(b) - k)), *t[k:]).as_posix()


def collect_many(sources: list[tuple[Path, str]],
                 base: Path) -> tuple[str, list[list[dict]], list[Path]]:
    """Several folders on one page. Each source folder becomes one row (group)
    with all its items; captions get the source's prefix; files are relative to
    ``base`` (the folder of the page). Returns (kind, groups, folders without
    wavs). Redo candidates are captioned "вариант N" (N = the accept number)."""
    kinds: set[str] = set()
    groups: list[list[dict]] = []
    empty: list[Path] = []
    for folder, prefix in sources:
        folder = Path(folder)
        if not folder.is_dir():
            empty.append(folder)
            continue
        kind, found = collect(folder)
        items = [it for g in found for it in g]
        if not items:
            empty.append(folder)
            continue
        kinds.add(kind)
        row = []
        for it in items:
            name = it["name"]
            variant = it["meta"].get("variant", "")
            if kind == "redo" and variant.isdigit():
                name = f"вариант {int(variant)}"
            caption = f"{prefix} · {name}" if prefix else name
            row.append({"file": rel_url(base, folder / it["file"]), "name": caption,
                        "meta": dict(it["meta"], item=caption)})
        groups.append(row)
    kind = next(iter(kinds)) if len(kinds) == 1 else "generic"
    return kind, groups, empty


def build_combined(sources: list[tuple[Path, str]], out_html: Path,
                   title: str) -> tuple[Path | None, list[Path]]:
    """One review page over several folders (see collect_many), written
    atomically to ``out_html``. Returns (page path or None if no folder had
    wavs, folders without wavs)."""
    out_html = Path(out_html)
    base = out_html.parent
    base.mkdir(parents=True, exist_ok=True)
    kind, groups, empty = collect_many(sources, base)
    if not groups:
        return None, empty
    files = [it["file"] for g in groups for it in g]
    tmp = out_html.with_name(out_html.name + ".part")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(render(title, kind, groups, page_id(base, files)))
    tmp.replace(out_html)
    return out_html, empty


def run(folder: str, title: str | None = None, meta: str | None = None) -> int:
    rows = None
    if meta:
        mp = Path(meta)
        if not mp.is_file():
            raise SystemExit(f"нет файла разметки подписей: {mp}")
        rows = read_tsv(mp)
    out = build_review(Path(folder), title, rows)
    kind, groups = collect(Path(folder), rows)
    n = sum(len(g) for g in groups)
    print(f"страница прослушки: {out}  ({KIND_NAMES.get(kind, kind)}, {n} шт.)")
    print("открыть двойным кликом; потом «Скачать разметку» → ./run.sh labels import <labels_*.json>")
    return 0


TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  --bg: #f6f5f1; --card: #ffffff; --ink: #1d1d1b; --muted: #6a6a64; --line: #dcdad2;
  --ok: #1f7a46; --bad: #b3261e; --unsure: #8a6100; --accent: #2b5fa8; --chip: #ecebe4;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #161614; --card: #21211e; --ink: #ecebe4; --muted: #a3a29a; --line: #3a3a35;
    --ok: #5cc98a; --bad: #ff8a80; --unsure: #e8b84a; --accent: #8db4ee; --chip: #2e2e2a;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.45 -apple-system, "Segoe UI", Roboto, sans-serif; }
header { position: sticky; top: 0; z-index: 5; background: var(--bg);
  border-bottom: 1px solid var(--line); padding: 10px 16px; }
h1 { font-size: 1.1rem; margin: 0; overflow-wrap: anywhere; }
.sub { color: var(--muted); font-size: .85rem; margin: 2px 0 8px; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.actions button { min-height: 40px; padding: 0 14px; border-radius: 8px; cursor: pointer;
  border: 1px solid var(--accent); background: var(--accent); color: var(--bg); font: inherit; }
.actions button.ghost { background: transparent; color: var(--accent); }
#box { width: 100%; height: 8rem; margin-top: 8px; font: 12px/1.3 ui-monospace, monospace;
  background: var(--card); color: var(--ink); border: 1px solid var(--line); border-radius: 8px; }
main { max-width: 960px; margin: 0 auto; padding: 12px 16px 48px; }
.grp { margin-bottom: 14px; display: grid; gap: 10px; }
.grp.pair { grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); }
.item { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 12px;
  border-left-width: 6px; min-width: 0; }
.item[data-label="ok"] { border-left-color: var(--ok); }
.item[data-label="bad"] { border-left-color: var(--bad); }
.item[data-label="unsure"] { border-left-color: var(--unsure); }
.head { display: flex; justify-content: space-between; gap: 8px; font-weight: 600; }
.name { overflow-wrap: anywhere; }
.mark { font-weight: 600; font-size: .85rem; white-space: nowrap; }
[data-label="ok"] .mark { color: var(--ok); }
[data-label="bad"] .mark { color: var(--bad); }
[data-label="unsure"] .mark { color: var(--unsure); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
.chip { background: var(--chip); color: var(--muted); border-radius: 999px; padding: 1px 9px;
  font-size: .78rem; overflow-wrap: anywhere; }
.text { margin: 6px 0; overflow-wrap: anywhere; }
.text.synth { color: var(--muted); font-size: .92rem; }
audio { width: 100%; margin: 8px 0; }
.btns { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.btns button { min-height: 44px; border-radius: 8px; border: 2px solid var(--line);
  background: transparent; color: var(--ink); font: inherit; cursor: pointer; }
.btns button[aria-pressed="true"][data-l="ok"] { border-color: var(--ok); color: var(--ok); font-weight: 700; }
.btns button[aria-pressed="true"][data-l="bad"] { border-color: var(--bad); color: var(--bad); font-weight: 700; }
.btns button[aria-pressed="true"][data-l="unsure"] { border-color: var(--unsure); color: var(--unsure); font-weight: 700; }
.issue, .note { width: 100%; margin-top: 8px; font: inherit; padding: 8px; border-radius: 8px;
  border: 1px solid var(--line); background: var(--bg); color: var(--ink); }
.note { resize: vertical; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <div class="sub">__KIND__ · размечено <span id="count">0</span></div>
  <div class="actions">
    <button type="button" id="dl">Скачать разметку</button>
    <button type="button" id="cp">Копировать JSON</button>
    <button type="button" id="clr" class="ghost">Очистить</button>
  </div>
  <textarea id="box" readonly hidden></textarea>
</header>
<main>
__ITEMS__
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
(function () {
  var DATA = JSON.parse(document.getElementById("data").textContent);
  var KEY = "audiobook-review:" + DATA.title + ":" + (DATA.page_id || "");
  var NAMES = {ok: "хорошо", bad: "плохо", unsure: "?"};
  var state = {};

  function load() {
    try { var s = localStorage.getItem(KEY); return s ? JSON.parse(s) : {}; }
    catch (e) { return {}; }
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
  }
  state = load();

  var cards = Array.prototype.slice.call(document.querySelectorAll(".item"));

  function paint(card) {
    var f = DATA.items[+card.getAttribute("data-i")].file;
    var s = state[f] || {};
    card.setAttribute("data-label", s.label || "");
    card.querySelector(".mark").textContent = s.label ? NAMES[s.label] : "";
    Array.prototype.forEach.call(card.querySelectorAll(".btns button"), function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-l") === s.label ? "true" : "false");
    });
    card.querySelector(".issue").value = s.issue || "";
    Array.prototype.forEach.call(card.querySelectorAll("[data-rating]"), function (el) {
      el.value = s[el.getAttribute("data-rating")] || "";
    });
    var note = card.querySelector(".note");
    if (note.value !== (s.comment || "")) { note.value = s.comment || ""; }
  }
  function count() {
    var n = 0;
    DATA.items.forEach(function (it) {
      var s = state[it.file] || {};
      if (s.label && (!it.meta.control_ratings || (s.heard_stress && s.lexical && s.voice && s.rhythm))) { n++; }
    });
    document.getElementById("count").textContent = n + " из " + DATA.items.length;
  }
  function patch(card, key, val) {
    var f = DATA.items[+card.getAttribute("data-i")].file;
    var s = state[f] || {};
    s[key] = val;
    state[f] = s;
    save();
    paint(card);
    count();
  }

  cards.forEach(function (card) {
    paint(card);
    Array.prototype.forEach.call(card.querySelectorAll(".btns button"), function (b) {
      b.addEventListener("click", function () {
        var f = DATA.items[+card.getAttribute("data-i")].file;
        var cur = (state[f] || {}).label;
        patch(card, "label", cur === b.getAttribute("data-l") ? "" : b.getAttribute("data-l"));
      });
    });
    Array.prototype.forEach.call(card.querySelectorAll("[data-rating]"), function (el) {
      el.addEventListener("change", function () { patch(card, el.getAttribute("data-rating"), el.value); });
    });
    card.querySelector(".issue").addEventListener("change", function (e) {
      patch(card, "issue", e.target.value);
    });
    card.querySelector(".note").addEventListener("input", function (e) {
      var f = DATA.items[+card.getAttribute("data-i")].file;
      var s = state[f] || {};
      s.comment = e.target.value;
      state[f] = s;
      save();
    });
  });
  count();

  // one player at a time
  document.addEventListener("play", function (e) {
    Array.prototype.forEach.call(document.querySelectorAll("audio"), function (a) {
      if (a !== e.target) { a.pause(); }
    });
  }, true);

  function build() {
    var items = DATA.items.map(function (it) {
      var s = state[it.file] || {};
      var item = {file: it.file, section: it.section || "", chunk: it.chunk || "",
              hash: it.hash || "", label: s.label || "", issue: s.issue || "",
              comment: s.comment || "", meta: it.meta};
      if (it.meta.control_ratings) {
        ["heard_stress", "lexical", "voice", "rhythm"].forEach(function (k) { item[k] = s[k] || ""; });
      }
      return item;
    });
    return JSON.stringify({title: DATA.title, page_id: DATA.page_id || "", kind: DATA.kind,
                           items: items}, null, 2);
  }
  function showBox() {
    var box = document.getElementById("box");
    box.hidden = false;
    box.value = build();
    box.focus();
    box.select();
    return box;
  }

  document.getElementById("dl").addEventListener("click", function () {
    try {
      var blob = new Blob([build()], {type: "application/json"});
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = "labels_" + DATA.safe + (DATA.page_id ? "_" + DATA.page_id : "") + ".json";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(url); }, 3000);
    } catch (e) {
      showBox();
    }
  });
  document.getElementById("cp").addEventListener("click", function () {
    var box = showBox();
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(box.value).catch(function () {});
      } else {
        document.execCommand("copy");
      }
    } catch (e) {}
  });
  document.getElementById("clr").addEventListener("click", function () {
    if (!window.confirm("Стереть всю разметку на этой странице?")) { return; }
    state = {};
    save();
    cards.forEach(paint);
    count();
  });
})();
</script>
</body>
</html>
"""
