"""Read-only stress/intonation plan. No model load, no book/cache writes.

The existing chunker remains the authority for segmentation and hashes. A plan
is a diagnostic, NOT an application/approval command or a TTS prosody control.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from audiobook import chunker, leadin, paths, pronounce, voicecfg

_WORD = re.compile(r"[А-Яа-яЁё]+(?: [А-Яа-яЁё]+)*")
_VOWELS = frozenset("АЕЁИОУЫЭЮЯ")
_FIELDS = ("id", "n", "text", "hash", "seed", "leadin", "open_end", "cont", "pause_after_ms")


def digest(value) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def validate_rules(rules: dict) -> dict[str, str]:
    """Restrict candidates to stress case, е→ё and exact phrase-final comma.

    Existing legacy dictionary entries are not rewritten or restricted. These
    rules are explicit candidates, not proof of human approval or TTS accuracy.
    No inferred word-family or homograph expansion, no raw RUAccent '+'.
    """
    if not isinstance(rules, dict):
        raise ValueError("rules: expected a JSON object")
    for key, value in rules.items():
        # A narrowly scoped rhythm cue: an unchanged multiword Cyrillic
        # phrase followed by exactly one comma. Not general punctuation edits.
        if (isinstance(key, str) and isinstance(value, str)
                and " " in key and _WORD.fullmatch(key) and value == key + ","):
            continue
        if (not isinstance(key, str) or not isinstance(value, str)
                or not _WORD.fullmatch(key) or not _WORD.fullmatch(value)
                or len(key) != len(value) or key == value):
            raise ValueError("rules: expected nontrivial Cyrillic word/phrase respelling")
        for a, b in zip(key, value):
            if a == b:
                continue
            if a == "е" and b in ("ё", "Ё") or a == "Е" and b == "Ё":
                continue
            if a.islower() and b in _VOWELS and a.upper() == b:
                continue
            raise ValueError("rules: unsupported letter, case or spacing change")
    return dict(rules)


def pause_config(config: dict, sentence: int | None = None,
                 paragraph: int | None = None, heading: int | None = None) -> dict:
    """Only assembly-pause knobs, not segmentation, voice or text settings."""
    result = deepcopy(config)
    pauses = result.setdefault("pauses_ms", {})
    for key, value in (("sentence", sentence), ("paragraph", paragraph), ("heading", heading)):
        if value is None:
            continue
        if type(value) is not int or not 0 <= value <= 5000:
            raise ValueError("pause: expected integer milliseconds in 0..5000")
        if key == "heading":
            levels = {int(k): v for k, v in (pauses.get("heading_level") or {}).items()}
            levels[1] = value
            pauses["heading_level"] = levels
        else:
            pauses[key] = value
    return result


def source_anchors(units: list[dict], rows: list[dict], config: dict) -> list[dict]:
    """Exact ordinal + offsets into a verified normalized unit.

    Reproduce segmentation separately per source unit. Consume its non-space
    tokens in order; only whitespace differences are allowed. Never search
    the whole section for a text match or infer a unique duplicate occurrence.
    On this base the normalized line ordinal is the available source identity,
    bound to unit/section digests, not an invented persistent SectionMap UID.
    """
    anchors = []
    position = 0
    for index, unit in enumerate(units):
        pieces = chunker.build_chunks([unit], config)
        source = unit["text"]
        tokens = list(re.finditer(r"\S+", source))
        cursor = 0
        number, label, title = (chunker.split_heading(source)
                                if unit["type"] == "heading" else (None, None, None))
        for i, piece in enumerate(pieces):
            parts = piece["text"].split()
            matched = tokens[cursor:cursor + len(parts)]
            if not parts or [m.group() for m in matched] != parts:
                raise ValueError("SOURCE_SPAN_MISMATCH")
            if position >= len(rows) or rows[position]["text"] != piece["text"]:
                raise ValueError("SOURCE_CHUNK_MISMATCH")
            last = i == len(pieces) - 1
            kind = piece.get("kind", "text")
            mark = chunker.end_mark(piece["text"])
            if kind == "heading":
                if not last and number and piece["text"] == number:
                    role = "chapter_number"
                elif not last and label and piece["text"] == label:
                    role = "heading_label"
                elif last and number and piece["text"] == title:
                    role = "chapter_title"
                elif last and number:
                    role = "chapter_heading_combined"
                else:
                    role = "heading"
                boundary = "heading_end" if last else "heading_part"
            elif kind == "step":
                role, boundary = "step_label", "step"
            elif kind == "stack":
                role = "list_item"
                boundary = "paragraph" if unit.get("last_in_stack") else "stack_line"
            else:
                role = "question" if mark == "?" else "narration"
                boundary = ("paragraph" if last else
                            "sentence" if mark in (".", "?", "!", "…") else
                            "clause" if mark in (":", ";") else "continuation")
            if position == len(rows) - 1:
                boundary = "section_end"
            anchors.append({
                "unit_ordinal": index + 1,
                "unit_sha256": digest(unit),
                "start": matched[0].start(),
                "end": matched[-1].end(),
                "role": role,
                "boundary_kind": boundary,
                "terminal_mark": mark,
                "rule_id": "structure_v1:" + role + ":" + boundary,
                "review_intonation": kind == "heading" or role == "question",
                "opening_after_heading": (
                    index > 0 and i == 0 and kind == "text"
                    and units[index - 1]["type"] == "heading"),
            })
            cursor += len(parts)
            position += 1
        if cursor != len(tokens):
            raise ValueError("SOURCE_UNIT_NOT_EXHAUSTED")
    if position != len(rows):
        raise ValueError("SOURCE_SECTION_NOT_EXHAUSTED")
    return anchors


def prepared_input(row: dict, config: dict, table: dict) -> str:
    """Exact pre-sentinel string (same fixed sentinel on both sides).

    Compare the actual padded input, not only the hash's own-text component.
    Existing hash does not independently cover carrier-only respelling changes.
    """
    prepared = voicecfg.prepare_text(row["text"], config, row["open_end"])
    base = leadin.pad(prepared, row["leadin"]) if row["leadin"] else prepared
    return pronounce.respell(base, table)


def plan_section(units: list[dict], old: list[dict], config: dict, table: dict,
                 rules: dict | None = None, sentence: int | None = None,
                 paragraph: int | None = None, heading: int | None = None,
                 chapter_title_carrier: bool = False) -> dict:
    """Plan a section against a current, exactly validated manifest snapshot."""
    candidates = validate_rules({} if rules is None else rules)
    if (config.get("pauses_ms") or {}).get("enum_pause_ms"):
        raise ValueError("ENUM_SYNTH_UNSUPPORTED: per-fragment synth input requires review")
    baseline = chunker.build_manifest(units, config, pronounce_table=table)
    if (not old or len(old) != len(baseline)
            or any(any(k not in a or a[k] != b[k] for k in _FIELDS)
                   for a, b in zip(old, baseline))):
        raise ValueError("STALE_MANIFEST: rebuild evidence, not production")
    anchors = source_anchors(units, baseline, config)
    candidate_config = pause_config(config, sentence, paragraph, heading)
    if chapter_title_carrier:
        candidate_config.setdefault("render", {}).setdefault("leadin", {})["chapter_title_carrier"] = True
    candidate_table = {**table, **candidates}
    future = chunker.build_manifest(units, candidate_config, pronounce_table=candidate_table)
    if len(future) != len(baseline):
        raise ValueError("UNEXPECTED_SEGMENTATION_CHANGE")

    items = []
    counts: Counter = Counter()
    rule_hits: Counter = Counter()
    pattern = pronounce.build_pattern(candidate_table)
    for live, a, b, anchor in zip(old, baseline, future, anchors):
        if (a["id"], a["text"], a["open_end"]) != (
                b["id"], b["text"], b["open_end"]):
            raise ValueError("UNEXPECTED_SEGMENTATION_CHANGE")
        if a["leadin"] != b["leadin"] and not (chapter_title_carrier and
                anchor["role"] in ("chapter_title", "chapter_heading_combined")):
            raise ValueError("UNEXPECTED_SEGMENTATION_CHANGE")
        before = prepared_input(a, config, table)
        after = prepared_input(b, candidate_config, candidate_table)
        if pattern is not None:
            prepared = voicecfg.prepare_text(b["text"], candidate_config, b["open_end"])
            padded = leadin.pad(prepared, b["leadin"]) if b["leadin"] else prepared
            rule_hits.update(m.group(0) for m in pattern.finditer(padded)
                             if m.group(0) in candidates)
        changed_input = before != after
        changed_hash = a["hash"] != b["hash"]
        changed_pause = a["pause_after_ms"] != b["pause_after_ms"]
        if changed_input and not changed_hash:
            action = "blocked_hash_gap"
        elif changed_hash:
            action = "needs_synth"
        elif changed_pause:
            action = "pause_only"
        else:
            action = "review_only"
        counts[action] += 1
        items.append({
            "id": a["id"], "old_hash": a["hash"], "candidate_hash": b["hash"],
            "source_anchor": anchor, "action": action,
            "pause_before_ms": a["pause_after_ms"], "pause_after_ms": b["pause_after_ms"],
            "model_input_changed": changed_input, "hash_changed": changed_hash,
            "pause_changed": changed_pause, "locked": bool(live.get("locked")),
            "old_status": live.get("status"),
        })
    return {
        "schema_version": 1,
        "source_section_sha256": digest(units),
        "baseline_manifest_sha256": digest(old),
        "baseline_config_sha256": digest(config),
        "baseline_dictionary_sha256": digest(table),
        "candidate_config_sha256": digest(candidate_config),
        "candidate_dictionary_sha256": digest(candidate_table),
        "counts": dict(sorted(counts.items())),
        "blocked": bool(counts["blocked_hash_gap"]),
        "rendered_hash_changes": sum(r["hash_changed"] and r["old_status"] in ("done", "manual")
                                     for r in items),
        "locked_hash_changes": sum(r["hash_changed"] and r["locked"] for r in items),
        "candidate_rule_hits": [{"key": k, "hits_including_carrier": rule_hits[k]}
                                for k in sorted(candidates)],
        "scope": "one section; global dictionary changes require whole-book impact",
        "rows": items,
    }


def _unique_object(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError("rules: duplicate JSON key")
        result[k] = v
    return result


def run(config: dict, section: str, rules_file: str | None = None,
        sentence: int | None = None, paragraph: int | None = None,
        heading: int | None = None, tag: str = "plan", chapter_title_carrier: bool = False) -> int:
    if not re.fullmatch(r"[0-9]{2}_[A-Za-z0-9_-]+", section) or not re.fullmatch(r"[A-Za-z0-9_-]+", tag):
        raise SystemExit("voice-plan: недопустимое имя секции или тега")
    try:
        rules = (validate_rules(json.loads(Path(rules_file).read_text(encoding="utf-8"),
                                           object_pairs_hook=_unique_object)) if rules_file else {})
        nn, slug = section.split("_", 1)
        units = chunker.load_units(nn, slug)
        old = chunker._read_manifest(paths.OUT / "sections" / section / "manifest.jsonl")
        config = chunker.section_config(config, section)
        result = plan_section(units, old, config, pronounce.load_table(),
                              rules, sentence, paragraph, heading, chapter_title_carrier)
    except (ValueError, OSError, KeyError, TypeError, IndexError) as exc:
        # Only allow fixed diagnostic codes, never private source/error strings.
        codes = {"SOURCE_SPAN_MISMATCH", "SOURCE_CHUNK_MISMATCH",
                 "SOURCE_UNIT_NOT_EXHAUSTED", "SOURCE_SECTION_NOT_EXHAUSTED",
                 "STALE_MANIFEST: rebuild evidence, not production",
                 "ENUM_SYNTH_UNSUPPORTED: per-fragment synth input requires review",
                 "UNEXPECTED_SEGMENTATION_CHANGE"}
        reason = str(exc) if str(exc) in codes else type(exc).__name__
        raise SystemExit(f"voice-plan: BLOCKED ({reason}); проверьте входные данные локально") from None
    result["section"] = section
    dest = paths.OUT / "voice_plan" / section
    dest.mkdir(parents=True, exist_ok=True, mode=0o700)
    report = dest / (tag + ".json")
    with report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    print("voice-plan: " + json.dumps(result["counts"], sort_keys=True))
    print("BLOCKED_HASH_GAP" if result["blocked"] else "PLAN_ONLY — изменений нет")
    print(f"локальный приватный отчёт: {report}")
    return 2 if result["blocked"] else 0
