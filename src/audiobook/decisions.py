"""One page for all pending by-ear decisions, and one command to apply them.

    gamebox:  ./run.sh decisions build      → out/decisions/index.html + media/
    Mac:      open the page, choose, «Скачать решения» → decisions.json
    dev:      ./run.sh decisions apply decisions.json [--dry-run]
              → edits config.yaml / text/pronounce.yaml (then commit; gamebox git pull)

Decisions (each shown only if its listening material exists):
  temperature   newest out/golden/compare_*: pairs A/B, options = the two tags' temperatures
  pron          every out/pron_test/<sec>_<id>_<word>/ (meta.tsv): variants of the word
  takes         out/sections/*/takes/*/: all takes, the chosen one marked — keep auto-choice?
  by_end        sections/*/section_before_by_end.mp3 vs section.mp3 — pauses by final mark
  context       out/passage/<tag>/ with context off vs previous

``build`` only COPIES media into out/decisions/media/ (never moves or deletes),
so `fetch_results.sh --with-wav decisions` brings everything to the Mac.
``apply`` edits text line by line, keeping comments; it refuses anything it
cannot place exactly. Nothing here renders audio.
"""
from __future__ import annotations

import csv
import html
import json
import re
import shutil
from pathlib import Path

from audiobook import paths

BY_END_LONGER = 150
BY_END_SHORTER = -100

# ── discovery (build side) ─────────────────────────────────────────────────────


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists() or dst.stat().st_size != src.stat().st_size:
        tmp = dst.with_name(dst.name + ".part")
        shutil.copyfile(src, tmp)
        tmp.replace(dst)


def _read_tsv(p: Path) -> list[dict]:
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def find_temperature(out: Path) -> dict | None:
    comps = sorted((d for d in (out / "golden").glob("compare_*") if d.is_dir()),
                   key=lambda d: d.stat().st_mtime)
    if not comps:
        return None
    d = comps[-1]
    a_tag, _, b_tag = d.name[len("compare_"):].partition("_")
    temps = {}
    for tag in (a_tag, b_tag):
        sj = out / "golden" / tag / "settings.json"
        if sj.exists():
            temps[tag] = json.loads(sj.read_text(encoding="utf-8")).get("temperature")
    pairs = []
    for a in sorted(d.glob("*_A.wav")):
        b = a.with_name(a.name.replace("_A.wav", "_B.wav"))
        if b.exists():
            pairs.append((a, b))
    if not pairs:
        return None
    opts = [str(temps.get(t)) for t in (a_tag, b_tag) if temps.get(t) is not None]
    return {"dir": d, "tags": (a_tag, b_tag), "temps": temps, "pairs": pairs, "options": opts}


def find_pron(out: Path) -> list[dict]:
    items = []
    for d in sorted((out / "pron_test").glob("*")):
        meta = d / "meta.tsv"
        if not d.is_dir() or d.name.startswith("_") or not meta.exists():
            continue
        word = d.name.rsplit("_", 1)[-1]
        rows = [r for r in _read_tsv(meta) if (d / f"{r['n']}.wav").exists()]
        variants: list[str] = []
        for r in rows:
            if r["variant"] not in variants:
                variants.append(r["variant"])
        if rows:
            items.append({"dir": d, "word": word, "rows": rows, "variants": variants})
    return items


def find_takes(out: Path) -> list[dict]:
    from audiobook.synth import _read_manifest
    items = []
    for sec in sorted((out / "sections").glob("*")):
        tdir = sec / "takes"
        if not tdir.is_dir():
            continue
        rows = {str(r["id"]): r for r in _read_manifest(sec / "manifest.jsonl")} \
            if (sec / "manifest.jsonl").exists() else {}
        for d in sorted(tdir.glob("*__*")):
            cid = d.name.split("__")[0]
            wavs = sorted(d.glob("*.wav"))
            if len(wavs) < 2:
                continue
            row = rows.get(cid, {})
            items.append({"section": sec.name, "id": cid, "wavs": wavs,
                          "chosen": str(row.get("seed", "")), "text": row.get("text", "")})
    return items


def find_by_end(out: Path) -> dict | None:
    for sec in sorted((out / "sections").glob("*")):
        before, after = sec / "section_before_by_end.mp3", sec / "section.mp3"
        if before.exists() and after.exists():
            return {"section": sec.name, "before": before, "after": after}
    return None


def find_context(out: Path) -> dict | None:
    found: dict[str, Path] = {}
    for d in sorted((out / "passage").glob("*")):
        sj, mp3 = d / "settings.json", d / "passage.mp3"
        if not (sj.exists() and mp3.exists()):
            continue
        s = json.loads(sj.read_text(encoding="utf-8"))
        mode = str((((s.get("leadin") or {}).get("context")) or {}).get("mode", "off"))
        found.setdefault(mode, mp3)
    if "off" in found and "previous" in found:
        return {"off": found["off"], "previous": found["previous"]}
    return None


# ── page ──────────────────────────────────────────────────────────────────────

_CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--mut:#6b6a66;--line:#e4e1da;--acc:#2f6f5e;--card:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe7;--mut:#a3a19b;--line:#2c2b29;--acc:#7fc3ae;--card:#1c1c1a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px 120px}h1{font-size:24px;margin:0 0 4px}
.mut{color:var(--mut);font-size:14px}section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:16px 0}
h2{font-size:18px;margin:0 0 8px}.row{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin:6px 0}
audio{height:32px;max-width:100%}label.opt{display:inline-flex;gap:6px;align-items:center;padding:6px 10px;border:1px solid var(--line);border-radius:8px;cursor:pointer}
label.opt:has(input:checked){border-color:var(--acc);outline:1px solid var(--acc)}.chosen{color:var(--acc);font-weight:600}
details{margin-top:8px}footer{position:fixed;left:0;right:0;bottom:0;background:var(--card);border-top:1px solid var(--line);padding:12px 16px;display:flex;gap:12px;justify-content:center;align-items:center}
button{font:inherit;padding:10px 18px;border-radius:10px;border:0;background:var(--acc);color:#fff;cursor:pointer}
"""

_JS = """
const KEY='audiobook-decisions';
function collect(){const d={version:1};document.querySelectorAll('[data-key]').forEach(g=>{
 const c=g.querySelector('input:checked');if(!c)return;const k=g.dataset.key;
 if(k.startsWith('pron:')){d.pron=d.pron||{};d.pron[k.slice(5)]=c.value}else d[k]=c.value});return d}
function save(){try{localStorage.setItem(KEY,JSON.stringify(collect()))}catch(e){}upd()}
function upd(){const d=collect();const n=Object.keys(d).length-1+(d.pron?Object.keys(d.pron).length-1:0);
 document.getElementById('cnt').textContent='выбрано: '+n}
function restore(){let d=null;try{d=JSON.parse(localStorage.getItem(KEY)||'null')}catch(e){}if(!d)return;
 for(const [k,v] of Object.entries(d)){if(k==='pron'){for(const [w,x] of Object.entries(v))pick('pron:'+w,x)}else pick(k,v)}}
function pick(k,v){const g=document.querySelector('[data-key="'+CSS.escape(k)+'"]');if(!g)return;
 g.querySelectorAll('input').forEach(i=>{if(i.value===v)i.checked=true})}
function dl(){const b=new Blob([JSON.stringify(collect(),null,1)],{type:'application/json'});
 const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='decisions.json';a.click()}
document.addEventListener('change',save);restore();upd();
"""


def _audio(rel: str, caption: str) -> str:
    return (f'<div class="row"><span class="mut">{html.escape(caption)}</span>'
            f'<audio controls preload="none" src="{html.escape(rel)}"></audio></div>')


def _options(key: str, opts: list[tuple[str, str]], current: str | None) -> str:
    out = [f'<div class="row" data-key="{html.escape(key)}">']
    for val, label in opts:
        cur = " (сейчас)" if current is not None and val == current else ""
        out.append(f'<label class="opt"><input type="radio" name="{html.escape(key)}" '
                   f'value="{html.escape(val)}">{html.escape(label)}{cur}</label>')
    out.append("</div>")
    return "".join(out)


def current_values(config: dict, table: dict[str, str]) -> dict:
    lc = ((config.get("render") or {}).get("leadin") or {}).get("context") or {}
    return {"temperature": str((config.get("model") or {}).get("temperature")),
            "context": str(lc.get("mode", "off")),
            "takes": "on" if int(((config.get("qc") or {}).get("takes") or {}).get("count", 1)) > 1 else "off",
            "pron": table}


def build(config: dict, out: Path | None = None) -> Path:
    from audiobook.pronounce import load_table
    out = Path(out or paths.OUT)
    dest = out / "decisions"
    media = dest / "media"
    cur = current_values(config, load_table())
    parts: list[str] = []

    t = find_temperature(out)
    if t:
        rows = []
        for a, b in t["pairs"]:
            n = a.name.split("_")[0]
            ra, rb = f"media/temperature/{a.name}", f"media/temperature/{b.name}"
            _copy(a, media / "temperature" / a.name)
            _copy(b, media / "temperature" / b.name)
            rows.append(_audio(ra, f"{n} A") + _audio(rb, f"{n} B"))
        a_tag, b_tag = t["tags"]
        opts = [(str(t["temps"].get(x)), f"{x}: temperature {t['temps'].get(x)}")
                for x in (a_tag, b_tag) if t["temps"].get(x) is not None]
        parts.append("<section><h2>1. Temperature</h2>"
                     f"<p class='mut'>A = {a_tag}, B = {b_tag}. Слушайте ударения, «кашу», живость.</p>"
                     + _options("temperature", opts, cur["temperature"])
                     + f"<details><summary>{len(t['pairs'])} пар</summary>{''.join(rows)}</details></section>")

    for it in find_pron(out):
        w = it["word"]
        rows = []
        for r in it["rows"]:
            rel = f"media/pron/{it['dir'].name}/{r['n']}.wav"
            _copy(it["dir"] / f"{r['n']}.wav", media / "pron" / it["dir"].name / f"{r['n']}.wav")
            label = "без правки" if r["variant"] == "-" else r["variant"]
            rows.append(_audio(rel, f"{label} · дубль {r['take']}"))
        current = cur["pron"].get(w, "-")
        opts = [(v, "без правки" if v == "-" else v) for v in it["variants"]]
        parts.append(f"<section><h2>2. Ударение: {html.escape(w)}</h2>"
                     "<p class='mut'>Берите вариант, верный в обоих дублях. Решение применится и к формам слова.</p>"
                     + "".join(rows) + _options(f"pron:{w}", opts, current) + "</section>")

    tk = find_takes(out)
    if tk:
        rows = []
        for it in tk:
            rows.append(f"<p><b>{html.escape(it['section'][:30])} · {it['id']}</b> "
                        f"<span class='mut'>{html.escape(it['text'][:80])}</span></p>")
            for w in it["wavs"]:
                rel = f"media/takes/{it['section']}/{it['id']}/{w.name}"
                _copy(w, media / "takes" / it["section"] / it["id"] / w.name)
                mark = " ← выбран" if w.stem == it["chosen"] else ""
                rows.append(_audio(rel, f"seed {w.stem}{mark}"))
        parts.append("<section><h2>3. Автовыбор дублей</h2>"
                     "<p class='mut'>Совпадает ли выбор qc («← выбран») с вашим ухом?</p>"
                     + _options("takes", [("on", "доверяем автовыбору"), ("off", "выключить дубли")], cur["takes"])
                     + f"<details><summary>{len(tk)} чанков</summary>{''.join(rows)}</details></section>")

    be = find_by_end(out)
    if be:
        _copy(be["before"], media / "by_end" / "before.mp3")
        _copy(be["after"], media / "by_end" / "after.mp3")
        parts.append("<section><h2>4. Паузы по знаку в конце фразы</h2>"
                     "<p class='mut'>Разница — после «?», «!», «…», «:» внутри абзаца.</p>"
                     + _audio("media/by_end/before.mp3", "было") + _audio("media/by_end/after.mp3", "стало")
                     + _options("by_end", [("keep", "оставить"), ("longer", "ещё длиннее"),
                                           ("shorter", "чуть короче"), ("off", "вернуть как было")], None)
                     + "</section>")

    cx = find_context(out)
    if cx:
        _copy(cx["off"], media / "context" / "A_base.mp3")
        _copy(cx["previous"], media / "context" / "B_context.mp3")
        parts.append("<section><h2>5. Контекст из предыдущей фразы</h2>"
                     "<p class='mut'>Связнее ли стыки? Нет ли обрывков слов в начале фраз? Цена ≈ +17% времени.</p>"
                     + _audio("media/context/A_base.mp3", "A без контекста")
                     + _audio("media/context/B_context.mp3", "B с контекстом")
                     + _options("context", [("off", "без контекста"), ("previous", "с контекстом")], cur["context"])
                     + "</section>")

    if not parts:
        raise SystemExit("нечего решать: не найдено ни одного сравнения в out/")
    page = ("<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Решения по звуку</title><style>{_CSS}</style></head><body><main>"
            "<h1>Решения по звуку</h1><p class='mut'>Выбор сохраняется в браузере. "
            "В конце — «Скачать решения» и прислать decisions.json.</p>"
            + "".join(parts) + "</main><footer><span id='cnt' class='mut'></span>"
            "<button onclick='dl()'>Скачать решения</button></footer>"
            f"<script>{_JS}</script></body></html>")
    dest.mkdir(parents=True, exist_ok=True)
    p = dest / "index.html"
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(page, encoding="utf-8")
    tmp.replace(p)
    return p


# ── apply (dev side) ───────────────────────────────────────────────────────────

def _sub_once(text: str, pattern: str, repl, what: str) -> str:
    new, n = re.subn(pattern, repl, text, count=1, flags=re.M)
    if n != 1:
        raise SystemExit(f"decisions apply: не нашёл в config.yaml место для «{what}»")
    return new


def stress_index(word: str, variant: str) -> int | None:
    """Index of the capitalised stressed VOWEL of a same-length respelling
    (a capital consonant is a one-off trick, not a rule to copy to word forms)."""
    if len(word) != len(variant):
        return None
    diffs = [i for i, (a, b) in enumerate(zip(word, variant)) if a != b]
    if (len(diffs) == 1 and variant[diffs[0]] in "АЕЁИОУЫЭЮЯ"
            and word[diffs[0]].islower()):
        return diffs[0]
    return None


def pron_family(table: dict[str, str], word: str, idx: int | None) -> list[str]:
    """Dictionary keys that are forms of ``word``: same lowercase prefix up to
    the stressed letter (or the first 5 letters when removing)."""
    n = (idx + 1) if idx is not None else min(5, len(word))
    pre = word.lower()[:n]
    return [k for k in table if " " not in k and "." not in k and k.lower()[:n] == pre]


def _pron_line_re(key: str) -> str:
    return rf'^"?{re.escape(key)}"?\s*:.*$\n?'


def apply_pron(pron_text: str, table: dict[str, str], word: str, variant: str,
               changes: list[str]) -> str:
    idx = stress_index(word, variant) if variant != "-" else None
    family = pron_family(table, word, idx) if (variant == "-" or idx is not None) else []
    if word not in family:
        family = [word, *family]
    for key in family:
        if variant == "-":
            new_val = None
        elif key == word:
            new_val = variant
        elif idx is not None and len(key) > idx:
            new_val = key[:idx] + key[idx].upper() + key[idx + 1:]
        else:
            continue
        old_val = table.get(key)
        if new_val == old_val:
            continue
        pat = _pron_line_re(key)
        if new_val is None:
            pron_text, n = re.subn(pat, "", pron_text, count=1, flags=re.M)
            if n:
                changes.append(f"pronounce: удалено {key!r} (было {old_val!r})")
            continue
        line = f'"{key}": "{new_val}"     # decisions: выбрано на слух (1.7B)\n'
        if re.search(pat, pron_text, flags=re.M):
            pron_text = re.sub(pat, line, pron_text, count=1, flags=re.M)
        else:
            pron_text = pron_text.rstrip("\n") + "\n" + line
        changes.append(f"pronounce: {key!r}: {old_val!r} → {new_val!r}")
    return pron_text


def apply(decisions: dict, config_text: str, pron_text: str, config: dict,
          table: dict[str, str]) -> tuple[str, str, list[str]]:
    """Pure: new (config_text, pron_text) and a human list of changes."""
    changes: list[str] = []
    c = config_text
    if "temperature" in decisions:
        t = str(decisions["temperature"])
        if t != str(config["model"]["temperature"]):
            float(t)
            c = _sub_once(c, r"^(\s*temperature:\s*)[0-9.]+", rf"\g<1>{t}", "model.temperature")
            changes.append(f"config: model.temperature {config['model']['temperature']} → {t}")
    if "context" in decisions:
        mode = decisions["context"]
        if mode not in ("off", "previous"):
            raise SystemExit(f"decisions: context {mode!r}?")
        cur = (((config.get("render") or {}).get("leadin") or {}).get("context") or {}).get("mode", "off")
        if mode != cur:
            c = _sub_once(c, r'^(\s*context:\s*\{mode:\s*)"?\w+"?', rf'\g<1>"{mode}"', "leadin.context.mode")
            changes.append(f"config: render.leadin.context.mode {cur} → {mode}")
    if "takes" in decisions:
        want = 3 if decisions["takes"] == "on" else 1
        cur = int(((config.get("qc") or {}).get("takes") or {}).get("count", 1))
        if (want > 1) != (cur > 1):
            c = _sub_once(c, r"^(\s*count:\s*)\d+", rf"\g<1>{want}", "qc.takes.count")
            changes.append(f"config: qc.takes.count {cur} → {want}")
    if decisions.get("by_end", "keep") != "keep":
        cur = {str(k): int(v) for k, v in
               ((config.get("pauses_ms") or {}).get("by_end") or {}).items()}
        floor = int((config.get("pauses_ms") or {}).get("sentence", 350))
        opt = decisions["by_end"]
        if opt == "off":
            new = {}
        elif opt in ("longer", "shorter"):
            step = BY_END_LONGER if opt == "longer" else BY_END_SHORTER
            new = {k: max(floor, v + step) for k, v in cur.items()}
        else:
            raise SystemExit(f"decisions: by_end {opt!r}?")
        body = "{" + ", ".join(f'"{k}": {v}' for k, v in new.items()) + "}"
        c = _sub_once(c, r"^(\s*by_end:\s*)\{[^}\n]*\}[^\n]*", rf"\g<1>{body}   # decisions: {opt}",
                      "pauses_ms.by_end")
        changes.append(f"config: pauses_ms.by_end {cur} → {new}")
    p = pron_text
    for word, variant in (decisions.get("pron") or {}).items():
        p = apply_pron(p, table, word, str(variant), changes)
    return c, p, changes


def run_apply(config: dict, path: str, dry_run: bool = False) -> int:
    from audiobook.pronounce import load_table
    from audiobook.__main__ import config_path
    with open(path, encoding="utf-8") as f:
        decisions = json.load(f)
    cfg_p = Path(config_path())
    pron_p = paths.TEXT / "pronounce.yaml"
    c_old = cfg_p.read_text(encoding="utf-8")
    p_old = pron_p.read_text(encoding="utf-8")
    c_new, p_new, changes = apply(decisions, c_old, p_old, config, load_table())
    if not changes:
        print("решения совпадают с текущими настройками — менять нечего")
        return 0
    print("изменения:" + "".join(f"\n  {ch}" for ch in changes))
    if dry_run:
        print("(--dry-run: файлы не тронуты)")
        return 0
    for p, new in ((cfg_p, c_new), (pron_p, p_new)):
        if new != p.read_text(encoding="utf-8"):
            tmp = p.with_name(p.name + ".part")
            tmp.write_text(new, encoding="utf-8")
            tmp.replace(p)
    print("записано. Дальше: uv run pytest -q → commit → на gamebox git pull и ./run.sh impact")
    return 0


def run_build(config: dict) -> int:
    p = build(config)
    print(f"страница решений: {p}\n  на Mac: scripts/mac/fetch_results.sh gamebox --with-wav decisions")
    return 0
