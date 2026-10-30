"""Listening marks → fix plan → redo candidates → one page to pick from.

    ./run.sh fix plan [labels_*.json ...] [--journal] [--since ГГГГ-ММ-ДД]
    ./run.sh fix queue [--candidates N]
    ./run.sh fix review

plan    reads exported labels JSON (review page) and/or the journal
        text/labels.yaml; every «плохо» that maps to a chunk of the CURRENT
        manifest goes into out/fix/plan.json (per section, deduped, manifest
        order). A mark carries a hash prefix when the page knew it: it must
        match the manifest row, otherwise the text changed after listening —
        reported as «устарело», never planned. Marks that are not about book
        chunks are reported, not planned: pron-test takes (the decision goes to
        pronounce.yaml), redo candidates (pick with accept), ref-compare. Golden
        compare marks count only when their hash is the current manifest's.
        Locked chunks are planned and flagged: redo + accept again.
queue   re-checks the plan against the manifests and queues one redo job per
        chunk, all or nothing (jobqueue.add_many). Candidates already rendered
        for the same chunk text are kept; --candidates N new ones are added on
        top (redo skips existing variant files).
review  one page out/fix/review.html with the candidates of every planned
        chunk (out/redo/<section>/<id>/, _old_* folders ignored) and the accept
        command for each chunk.

Nothing here renders, deletes audio or changes manifests; the plan is a text
file under out/ and may be rebuilt at any time.
"""
from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from audiobook import jobqueue, labels, paths, review

DEFAULT_CANDIDATES = 3
TEXT_PREVIEW = 60
_VARIANT_RE = re.compile(r"variant_(\d+)__seed\+\d+\.wav")
_HASH_MIN = 6  # shorter hash prefixes are ignored (not a reliable identity)

# reasons (printed and stored in plan.json)
R_PRON = "проба произношения — решение в pronounce.yaml"
R_REDO = "оценка кандидата redo — выбор через ./run.sh accept"
R_REFCMP = "сравнение референсов — не чанк книги"
R_GOLDEN = "golden: хеш не из текущего манифеста (другие настройки или текст)"
R_STALE = "устарело: текст чанка изменился после прослушки"
R_LOCKED = "заблокирован — нужно redo+accept заново"


def fix_dir(out_root: Path | None = None) -> Path:
    return (out_root or paths.OUT) / "fix"


def plan_path(out_root: Path | None = None) -> Path:
    return fix_dir(out_root) / "plan.json"


def _natural(s: str) -> list:
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", s)]


def _cut(s: str, n: int) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


# ── manifests ─────────────────────────────────────────────────────────────────

def read_manifest(out_root: Path, section: str) -> list[dict] | None:
    """Rows of out/sections/<section>/manifest.jsonl, None if there is none."""
    mp = out_root / "sections" / section / "manifest.jsonl"
    if not mp.is_file():
        return None
    with open(mp, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


class _Manifests:
    """Lazy cache of section manifests under one out/ root."""

    def __init__(self, out_root: Path):
        self.out_root = out_root
        self._rows: dict[str, list[dict] | None] = {}

    def rows(self, section: str) -> list[dict] | None:
        if section not in self._rows:
            self._rows[section] = read_manifest(self.out_root, section) if section else None
        return self._rows[section]

    def all_sections(self) -> list[str]:
        d = self.out_root / "sections"
        if not d.is_dir():
            return []
        return sorted((p.name for p in d.iterdir() if (p / "manifest.jsonl").is_file()),
                      key=_natural)


# ── marks ─────────────────────────────────────────────────────────────────────

@dataclass
class Mark:
    source: str
    kind: str
    entry: dict  # journal-shaped entry (labels.FIELDS)

    def get(self, key: str) -> str:
        return str(self.entry.get(key) or "")

    def brief(self, reason: str = "") -> dict:
        out = {k: self.get(k) for k in ("section", "chunk", "hash_prefix", "title",
                                        "file", "item", "label", "issue", "note")}
        out["source"] = self.source
        out["kind"] = self.kind
        if reason:
            out["reason"] = reason
        return out


def infer_kind(file: str, item: str = "") -> str:
    """Page kind of a journal entry (the journal does not store it)."""
    p = PurePosixPath(file)
    if _VARIANT_RE.fullmatch(p.name):
        return "redo"
    if re.fullmatch(r"\d+_[AB]\.wav", p.name):
        return "golden"
    if re.fullmatch(r"\d+\.wav", p.name) and "дубль" in item:
        return "pron-test"
    if len(p.parts) == 2 and p.parts[0] == "chunks":
        return "probe"
    if len(p.parts) == 2:
        return "ref-compare"
    return "generic"


def load_marks(inputs: list[Path], since: str | None = None) -> tuple[list[Mark], list[str]]:
    """Marks from labels JSON files and/or journal files (*.yaml / *.yml),
    deduped like the journal does (page, file, hash prefix). ``since`` keeps
    journal entries dated on or after it (exported JSON has no date)."""
    today = datetime.date.today().isoformat()
    marks: list[Mark] = []
    sources: list[str] = []
    for path in inputs:
        path = Path(path)
        if not path.is_file():
            raise SystemExit(f"нет файла: {path}")
        sources.append(str(path))
        if path.suffix.lower() in (".yaml", ".yml"):
            for e in labels.load(path):
                if since and str(e.get("date") or "") < since:
                    continue
                kind = infer_kind(str(e.get("file") or ""), str(e.get("item") or ""))
                marks.append(Mark(path.name, kind, e))
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except ValueError as e:
            raise SystemExit(f"не читается JSON {path.name}: {e}")
        entries, _unmarked = labels.entries_from_json(data, None, today)
        page_kind = str(data.get("kind") or "")
        for e in entries:
            kind = page_kind or infer_kind(e["file"], e["item"])
            marks.append(Mark(path.name, kind, e))
    seen: set = set()
    out = []
    for m in marks:
        key = (*labels.dedupe_key(m.entry), m.get("label"))
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out, sources


# ── plan ──────────────────────────────────────────────────────────────────────

@dataclass
class Plan:
    sections: dict[str, list[dict]] = field(default_factory=dict)
    stale: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    unsure: list[dict] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    created: str = ""

    def chunk_count(self) -> int:
        return sum(len(v) for v in self.sections.values())

    def to_json(self) -> dict:
        return {"version": 1, "created": self.created, "sources": self.sources,
                "sections": [{"section": s, "chunks": c} for s, c in self.sections.items()],
                "stale": self.stale, "skipped": self.skipped, "unsure": self.unsure}

    @classmethod
    def from_json(cls, data: dict) -> "Plan":
        return cls(sections={str(s["section"]): list(s["chunks"])
                             for s in data.get("sections", [])},
                   stale=list(data.get("stale", [])), skipped=list(data.get("skipped", [])),
                   unsure=list(data.get("unsure", [])), sources=list(data.get("sources", [])),
                   created=str(data.get("created", "")))


def _find_by_hash(mf: _Manifests, sections: list[str], h: str) -> tuple[str, dict] | None:
    for s in sections:
        for r in mf.rows(s) or []:
            if str(r.get("hash", "")).startswith(h):
                return s, r
    return None


def resolve(mark: Mark, mf: _Manifests) -> tuple[str, str, dict | None, str]:
    """(status, section, row, reason). status: ok | unverified | stale | skip.
    The hash prefix identifies the chunk TEXT: it is looked up first (a
    re-chunk may have moved the text to another id); a known id with another
    hash is stale; without a hash the id is trusted (unverified)."""
    section, chunk = mark.get("section"), mark.get("chunk")
    h = mark.get("hash_prefix")
    h = h if len(h) >= _HASH_MIN else ""
    if h:
        found = _find_by_hash(mf, [section] if section else mf.all_sections(), h)
        if found:
            return "ok", found[0], found[1], ""
    if mark.kind == "golden":
        return "skip", section, None, R_GOLDEN
    if not section:
        return "skip", "", None, ("хеш не найден ни в одном манифесте" if h
                                  else "нет секции — импортируй с --section")
    rows = mf.rows(section)
    if rows is None:
        return "skip", section, None, f"нет манифеста секции {section}"
    by_id = {str(r["id"]): r for r in rows}
    if not chunk:
        stem = PurePosixPath(mark.get("file")).stem
        if stem in by_id and not h:
            chunk = stem
        else:
            return "skip", section, None, "нет id чанка"
    row = by_id.get(chunk)
    if row is None:
        return "skip", section, None, f"нет чанка {chunk} в секции {section}"
    if h:
        return "stale", section, row, R_STALE
    return "unverified", section, row, ""


def plan(labels_inputs: list[Path], out_root: Path | None = None,
         since: str | None = None) -> Plan:
    """Build the fix plan from labels JSON and/or journal files (pure: reads
    manifests, writes nothing)."""
    out_root = Path(out_root or paths.OUT)
    marks, sources = load_marks([Path(p) for p in labels_inputs], since)
    mf = _Manifests(out_root)
    result = Plan(sources=sources,
                  created=datetime.datetime.now().isoformat(timespec="seconds"))
    picked: dict[tuple[str, str], dict] = {}
    for m in marks:
        label = m.get("label")
        if label == "ok":
            continue
        if m.kind == "pron-test":
            result.skipped.append(m.brief(R_PRON))
            continue
        if m.kind == "redo":
            result.skipped.append(m.brief(R_REDO))
            continue
        if m.kind == "ref-compare":
            result.skipped.append(m.brief(R_REFCMP))
            continue
        if label != "bad":
            result.unsure.append(m.brief("под вопросом — не в плане, переслушать"))
            continue
        status, section, row, reason = resolve(m, mf)
        if status == "stale":
            result.stale.append(m.brief(reason))
            continue
        if status == "skip":
            result.skipped.append(m.brief(reason))
            continue
        cid = str(row["id"])
        entry = picked.setdefault((section, cid), {
            "id": cid, "hash": str(row.get("hash", "")), "text": str(row.get("text", "")),
            "locked": bool(row.get("locked")), "verified": False,
            "issues": [], "notes": [], "marked_as": [], "sources": []})
        entry["verified"] = entry["verified"] or status == "ok"
        for key, val in (("issues", m.get("issue")), ("notes", m.get("note")),
                         ("sources", m.source)):
            if val and val not in entry[key]:
                entry[key].append(val)
        if m.get("chunk") and m.get("chunk") != cid and m.get("chunk") not in entry["marked_as"]:
            entry["marked_as"].append(m.get("chunk"))  # id at listening time (re-chunked)
    for section in sorted({s for s, _ in picked}, key=_natural):
        order = {str(r["id"]): i for i, r in enumerate(mf.rows(section) or [])}
        chunks = [e for (s, _), e in picked.items() if s == section]
        result.sections[section] = sorted(chunks, key=lambda e: order.get(e["id"], 1 << 30))
    return result


def _brief_line(b: dict) -> str:
    where = " ".join(x for x in (b.get("section", ""), b.get("chunk", "")) if x)
    what = " · ".join(x for x in (b.get("title", ""), b.get("file", "")) if x)
    note = " — " + _cut(b["note"], 50) if b.get("note") else ""
    return f"  {where or '—'}  {what}{note}"


def print_plan(p: Plan) -> None:
    n = p.chunk_count()
    print(f"план исправлений: {n} чанк(ов) в {len(p.sections)} секц.")
    for section, chunks in p.sections.items():
        print(f"\n{section}")
        for c in chunks:
            extra = []
            if c["issues"]:
                extra.append(", ".join(c["issues"]))
            if c["notes"]:
                extra.append(" ".join(f"«{_cut(x, 50)}»" for x in c["notes"]))
            if c["locked"]:
                extra.append(f"[{R_LOCKED}]")
            if not c["verified"]:
                extra.append("[без хеша в разметке — не проверено на устаревание]")
            if c["marked_as"]:
                extra.append(f"[при прослушке был id {', '.join(c['marked_as'])}]")
            tail = ("  — " + "  ".join(extra)) if extra else ""
            print(f"  {c['id']}  «{_cut(c['text'], TEXT_PREVIEW)}»{tail}")
    if p.stale:
        print(f"\nустарело (текст изменился после прослушки, в план не вошло): {len(p.stale)}")
        for b in p.stale:
            print(_brief_line(b))
    if p.skipped:
        print(f"\nпропущено: {len(p.skipped)}")
        by_reason: dict[str, list[dict]] = {}
        for b in p.skipped:
            by_reason.setdefault(b["reason"], []).append(b)
        for reason, items in by_reason.items():
            print(f"  {reason}: {len(items)}")
            for b in items:
                print("  " + _brief_line(b))
    if p.unsure:
        print(f"\nпод вопросом (?) — не в плане, переслушать: {len(p.unsure)}")
        for b in p.unsure:
            print(_brief_line(b))


def cmd_plan(inputs: list[str] | None = None, use_journal: bool = False,
             since: str | None = None, out_root: Path | None = None,
             journal: Path | None = None) -> int:
    """Print the plan and write out/fix/plan.json. No inputs → the journal."""
    files = [Path(x) for x in (inputs or [])]
    if use_journal or not files:
        jp = Path(journal or labels.labels_path())
        if not jp.is_file():
            raise SystemExit(f"нет журнала {jp}: передай labels_*.json или сделай labels import")
        files.append(jp)
    p = plan(files, out_root, since)
    print_plan(p)
    out = plan_path(out_root)
    _write_json(out, p.to_json())
    print(f"\nплан: {out}")
    if p.chunk_count():
        print("дальше: ./run.sh fix queue")
    return 0


# ── queue ─────────────────────────────────────────────────────────────────────

def load_plan(out_root: Path | None = None) -> Plan:
    pp = plan_path(out_root)
    if not pp.is_file():
        raise SystemExit(f"нет плана {pp}: сначала ./run.sh fix plan")
    with open(pp, encoding="utf-8") as f:
        return Plan.from_json(json.load(f))


def redo_dir(section: str, chunk_id: str, out_root: Path | None = None) -> Path:
    return (out_root or paths.OUT) / "redo" / section / chunk_id


def _candidate_hash(d: Path) -> str | None:
    meta = d / "meta.json"
    if not meta.is_file():
        return None
    try:
        with open(meta, encoding="utf-8") as f:
            return json.load(f).get("hash")
    except (OSError, ValueError):
        return None


def existing_variants(d: Path, chunk_hash: str) -> list[int]:
    """Variant numbers already rendered in ``d`` for this chunk text (redo
    moves candidates of another text aside, so those do not count)."""
    if not d.is_dir() or _candidate_hash(d) != chunk_hash:
        return []
    nums = []
    for w in d.glob("variant_*.wav"):
        m = _VARIANT_RE.fullmatch(w.name)
        if m and w.is_file():
            nums.append(int(m.group(1)))
    return sorted(nums)


def check_plan(p: Plan, out_root: Path | None = None) -> list[str]:
    """Problems that make the plan outdated against the current manifests."""
    mf = _Manifests(Path(out_root or paths.OUT))
    problems = []
    for section, chunks in p.sections.items():
        rows = mf.rows(section)
        if rows is None:
            problems.append(f"{section}: нет манифеста")
            continue
        by_id = {str(r["id"]): r for r in rows}
        for c in chunks:
            row = by_id.get(c["id"])
            if row is None:
                problems.append(f"{section} {c['id']}: чанка больше нет")
            elif str(row.get("hash", "")) != c["hash"]:
                problems.append(f"{section} {c['id']}: текст чанка изменился")
    return problems


def queue_jobs(p: Plan, candidates: int = DEFAULT_CANDIDATES,
               out_root: Path | None = None) -> list[tuple[str, str, list[int], list[str]]]:
    """(section, id, variants already there, redo job args) per planned chunk.
    The job asks for existing max + ``candidates`` so it renders new ones."""
    out = []
    for section, chunks in p.sections.items():
        for c in chunks:
            have = existing_variants(redo_dir(section, c["id"], out_root), c["hash"])
            n = (max(have) if have else 0) + candidates
            out.append((section, c["id"], have, jobqueue.redo_jobs(section, [c["id"]], n)[0]))
    return out


def cmd_queue(candidates: int = DEFAULT_CANDIDATES, out_root: Path | None = None,
              queue_root: Path | None = None) -> int:
    """Queue one redo per planned chunk — all sections in one all-or-nothing call."""
    if candidates < 1:
        raise SystemExit("--candidates должно быть ≥ 1")
    p = load_plan(out_root)
    if not p.chunk_count():
        print("план пуст — ставить в очередь нечего")
        return 0
    problems = check_plan(p, out_root)
    if problems:
        print("план устарел (манифесты изменились) — ничего не поставлено:")
        for x in problems:
            print(f"  {x}")
        print("пересобери: ./run.sh fix plan …")
        return 2
    planned = queue_jobs(p, candidates, out_root)
    try:
        added = jobqueue.add_many([job for *_rest, job in planned], queue_root)
    except ValueError as e:
        print(f"отклонено, ничего не поставлено: {e}")
        return 2
    for (section, cid, have, job), j in zip(planned, added):
        cfg = "" if j["config"] == jobqueue.DEFAULT_CONFIG else \
            f"  [{jobqueue.CONFIG_ENV}={j['config']}]"
        print(f"в очереди: {j['id']}  {' '.join(job)}{cfg}")
        if have:
            print(f"  {section} {cid}: уже есть кандидаты {', '.join(map(str, have))} "
                  f"для этого текста — они останутся, добавятся новые")
    print("дальше: ./run.sh queue run, затем ./run.sh fix review")
    return 0


# ── review ────────────────────────────────────────────────────────────────────

def section_short(section: str, width: int = 20) -> str:
    return section if len(section) <= width else section[:width - 1] + "…"


def cmd_review(out_root: Path | None = None) -> int:
    """One page over the redo candidates of every planned chunk + accept hints."""
    p = load_plan(out_root)
    if not p.chunk_count():
        print("план пуст — слушать нечего")
        return 0
    sources: list[tuple[Path, str]] = []
    ready: list[tuple[str, str, list[int]]] = []
    missing: list[str] = []
    other_text: list[str] = []
    for section, chunks in p.sections.items():
        for c in chunks:
            d = redo_dir(section, c["id"], out_root)
            have = existing_variants(d, c["hash"])
            if have:
                sources.append((d, f"{section_short(section)} · {c['id']}"))
                ready.append((section, c["id"], have))
            elif d.is_dir() and any(d.glob("variant_*.wav")):
                other_text.append(f"{section} {c['id']}")
            else:
                missing.append(f"{section} {c['id']}")
    page = None
    if sources:
        page, _empty = review.build_combined(sources, fix_dir(out_root) / "review.html",
                                             "fix: кандидаты redo")
    if page:
        n = sum(len(v) for *_x, v in ready)
        print(f"страница прослушки: {page}  ({len(ready)} чанк(ов), {n} кандидат(ов))")
        print("выбрать вариант N и установить:")
        for section, cid, have in ready:
            print(f"  ./run.sh accept {section} {cid} <N>    варианты: "
                  f"{', '.join(map(str, have))}")
    if other_text:
        print(f"\nкандидаты от другого текста чанка (не показаны) — нужен новый redo: "
              f"{len(other_text)}")
        for x in other_text:
            print(f"  {x}")
    if missing:
        print(f"\nещё не отрендерено: {len(missing)}")
        for x in missing:
            print(f"  {x}")
        print("дальше: ./run.sh queue run (если задачи в очереди), иначе ./run.sh fix queue")
    return 0 if page else 1
