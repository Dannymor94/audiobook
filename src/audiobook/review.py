"""Listening page: one self-contained review.html next to the wavs.

    ./run.sh review --dir out/pron_test/<...> [--title T] [--meta file.tsv]

Every wav gets a player, buttons хорошо / плохо / ?, an issue select and a
comment box; marks live in the browser (localStorage) and leave it as
labels_<title>.json ("Скачать разметку" or "Копировать JSON"), which
``./run.sh labels import`` appends to the text journal text/labels.yaml.

The page has no external URLs (opens from file://), wav paths are relative to
the page. Folder kinds are detected from file names:

  pron-test   n.wav + meta.tsv (n, chunk, variant, take, start, synth_text)
  redo        variant_XX__seed+N.wav  (out/redo/<section>/<chunk>/)
  probe       chunks/<hash16>.wav + index.tsv (hash16 column, or via manifests)
  golden      NN_A.wav / NN_B.wav pairs, shown side by side
  ref-compare <candidate>/<chunk>.wav subfolders, one row per chunk
  generic     any other *.wav

Nothing here touches models, manifests or the chunk cache.
"""
from __future__ import annotations

import csv
import html
import json
import re
from pathlib import Path
from urllib.parse import quote

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
CHIP_KEYS = ["section", "chunk", "variant", "take", "seed_offset", "start", "tags"]


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


def _wavs(folder: Path, recursive: bool = False) -> list[Path]:
    it = folder.rglob("*.wav") if recursive else folder.glob("*.wav")
    return sorted((p for p in it if p.is_file()), key=lambda p: _natural(p.name))


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
    index = read_tsv(index_path) if index_path and index_path.exists() else []
    base = folder.resolve()
    hashes = _manifest_hashes(base.parent) if base.name != "chunks" else \
        _manifest_hashes(base.parent.parent)
    by_key = {(r.get("section", ""), r.get("chunk", "")): r for r in index}
    placed: dict[str, dict] = {}  # hash16 -> index row
    for r in index:
        if r.get("hash"):
            placed[r["hash"]] = r
    by_hash: dict[str, dict] = {}
    for w in _wavs(wav_dir):
        row = placed.get(w.stem)
        if row is None and w.stem in hashes:
            row = by_key.get(hashes[w.stem])
        by_hash[w.stem] = row or {}
    order = {id(r): i for i, r in enumerate(index)}
    wavs = sorted(_wavs(wav_dir), key=lambda w: (
        order.get(id(by_hash[w.stem]), len(index)), _natural(w.name)))
    groups = []
    for w in wavs:
        r = by_hash[w.stem]
        meta = {"section": r.get("section", ""), "chunk": r.get("chunk", ""),
                "start": r.get("start", ""), "tags": r.get("tags", ""),
                "text": r.get("text", ""), "hash": w.stem}
        if r:
            name = f"{r.get('start', '')} · {r.get('section', '')} {r.get('chunk', '')}".strip(" ·")
            item = f"{r.get('section', '')}/{r.get('chunk', '')}"
        else:
            name, item = w.name, w.stem
        groups.append([_item(_rel(folder, w), name, meta, item)])
    return groups


def _kind_golden(folder: Path, wavs: list[Path]) -> list[list[dict]]:
    pairs: dict[str, list[Path]] = {}
    for w in wavs:
        pairs.setdefault(re.fullmatch(r"(.+)_[AB]\.wav", w.name).group(1), []).append(w)
    groups = []
    for key in sorted(pairs, key=_natural):
        grp = []
        for w in sorted(pairs[key], key=lambda p: p.name):
            side = w.stem[-1]
            grp.append(_item(w.name, f"{key} · {side}", {"pair": key, "side": side},
                             f"{key}_{side}"))
        groups.append(grp)
    return groups


def _kind_refcmp(folder: Path, subdirs: list[Path]) -> list[list[dict]]:
    f = folder.resolve()
    section, rows = "", {}
    if f.parent.name == "ref_compare":  # out/ref_compare/<section>/
        section = f.name
        rows = _manifest_rows(f.parent.parent, section)
    by_chunk: dict[str, list[Path]] = {}
    for d in subdirs:
        for w in _wavs(d):
            by_chunk.setdefault(w.stem, []).append(w)
    groups = []
    for cid in sorted(by_chunk, key=_natural):
        grp = []
        for w in by_chunk[cid]:
            meta = {"section": section, "chunk": cid, "candidate": w.parent.name,
                    "text": rows.get(cid, {}).get("text", "")}
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
    elif (folder / "chunks").is_dir() and _wavs(folder / "chunks"):
        kind, groups = "probe", _kind_probe(folder, folder / "chunks", folder / "index.tsv")
    elif folder.name == "chunks" and top and (folder.parent / "index.tsv").exists():
        kind, groups = "probe", _kind_probe(folder, folder, folder.parent / "index.tsv")
    elif top and all(re.fullmatch(r".+_[AB]\.wav", w.name) for w in top):
        kind, groups = "golden", _kind_golden(folder, top)
    elif not top and any(_wavs(d) for d in folder.iterdir() if d.is_dir()):
        subdirs = sorted((d for d in folder.iterdir() if d.is_dir() and _wavs(d)),
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
        '<textarea class="note" rows="2" placeholder="комментарий"></textarea>'
        '</article>'
    )


def _safe_name(title: str) -> str:
    s = re.sub(r"[^\w.\-]+", "_", title, flags=re.UNICODE).strip("_")
    return s or "review"


def render(title: str, kind: str, groups: list[list[dict]]) -> str:
    flat = [it for g in groups for it in g]
    body, i = [], 0
    for g in groups:
        cells = []
        for it in g:
            cells.append(_render_item(i, it))
            i += 1
        cls = "grp pair" if len(g) > 1 else "grp"
        body.append(f'<section class="{cls}">{"".join(cells)}</section>')
    data = {"title": title, "safe": _safe_name(title), "kind": kind,
            "items": [{"file": it["file"], "meta": it["meta"]} for it in flat]}
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
        f.write(render(title, kind, groups))
    tmp.replace(out)
    return out


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
  var KEY = "audiobook-review:" + DATA.title;
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
    var note = card.querySelector(".note");
    if (note.value !== (s.comment || "")) { note.value = s.comment || ""; }
  }
  function count() {
    var n = 0;
    DATA.items.forEach(function (it) { if ((state[it.file] || {}).label) { n++; } });
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
      return {file: it.file, label: s.label || "", issue: s.issue || "",
              comment: s.comment || "", meta: it.meta};
    });
    return JSON.stringify({title: DATA.title, items: items}, null, 2);
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
      a.download = "labels_" + DATA.safe + ".json";
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
