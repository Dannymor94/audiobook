"""T15-7: READ-ONLY owner-authorized S4 C3 compatibility census.

Run in an isolated offline worktree with existing .venv:
  PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  UV_NO_SYNC=1 UV_PROJECT_ENVIRONMENT=<existing local .venv> \
  PYTHONPATH="$PWD/src" uv run python -B tests/stress_s4_c3_readonly.py

Print ONLY aggregate JSON. Never print source keys, book text, gold rows,
individual hashes or paths. No sample/merge/score/renderer is invoked.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


class AuditBlocked(Exception):
    """Only safe reason codes may escape into aggregate JSON."""


_WORD = re.compile(r"[А-Яа-яЁё]+")


def _read_gold_table(path: Path, fields: tuple[str, ...]):
    """Read TSV bytes without normalizing on disk, skipping rows or writing."""
    if path.is_symlink():
        raise AuditBlocked("S4_SYMLINK_UNSUPPORTED")
    if not path.exists():
        return {"exists": False, "rows": []}, None
    if not path.is_file():
        raise AuditBlocked("S4_NONREGULAR_FILE")
    raw = path.read_bytes()
    try:
        decoded = raw.decode("utf-8").replace("\r\n", "\n")
    except UnicodeError:
        raise AuditBlocked("S4_ENCODING_INVALID") from None
    if not decoded.endswith("\n"):
        raise AuditBlocked("S4_FINAL_NEWLINE_MISSING")
    lines = decoded[:-1].split("\n")
    if lines[0] != "\t".join(fields):
        raise AuditBlocked("S4_HEADER_INVALID")
    rows = []
    for line in lines[1:]:
        cells = line.split("\t")
        if len(cells) != len(fields):
            raise AuditBlocked("S4_ROW_WIDTH_INVALID")
        rows.append(dict(zip(fields, cells)))
    return {"exists": True, "rows": rows}, hashlib.sha256(raw).digest()


def _ledger_numbers(rows, context, ev):
    """Distinguish repeated keys, differing source identities and stale rows."""
    count_by_key = Counter(r["source_key"] for r in rows)
    versions = defaultdict(set)
    active = defaultdict(set)
    valid_current = stale_rows = invalid = 0
    for r in rows:
        try:
            ev.validate_gold(r, historical=True)
            version = tuple(r[k] for k in ev.IDENTITY_FIELDS)
            current = context.sources.resolve(r["source_key"])
        except Exception:
            invalid += 1
            continue
        versions[r["source_key"]].add(version)
        if current is None or version != tuple(current[0][k] for k in ev.IDENTITY_FIELDS):
            stale_rows += 1
        else:
            valid_current += 1
            active[r["source_key"]].add((r["gold_vowel"], r["yo_correct"]))
    return {
        "rows": len(rows),
        "unique_source_keys": len(count_by_key),
        "source_keys_repeated": sum(n > 1 for n in count_by_key.values()),
        "repeated_key_rows_extra": sum(n - 1 for n in count_by_key.values()),
        "keys_with_multiple_source_identities": sum(len(v) > 1 for v in versions.values()),
        "extra_historical_identities": sum(max(0, len(v) - 1) for v in versions.values()),
        "currently_stale_rows": stale_rows,
        "current_identity_rows": valid_current,
        "active_distinct_keys": len(active),
        "active_conflicting_keys": sum(len(v) > 1 for v in active.values()),
        "invalid_ledger_rows": invalid,
        "human_labeled_rows": sum(bool(r["gold_vowel"]) for r in rows),
    }


def _todo_numbers(todo, gold, ev, selected_keys):
    """Filled unmerged human edits are not equivalent to blank owner todo."""
    known = {
        tuple(r[k] for k in ev.IDENTITY_FIELDS) + (r["gold_vowel"], r["yo_correct"])
        for r in gold
    }
    counts = Counter()
    for r in todo:
        filled = [bool(r[k]) for k in ev.LABEL_FIELDS]
        if not any(filled):
            counts["blank_rows"] += 1
        elif not all(filled):
            counts["partially_filled_rows"] += 1
        else:
            counts["filled_rows"] += 1
            try:
                ev.validate_gold(r, historical=True)
                counts["filled_structurally_valid"] += 1
            except Exception:
                counts["filled_invalid"] += 1
            signature = tuple(r[k] for k in ev.IDENTITY_FIELDS) + (
                r["gold_vowel"], r["yo_correct"])
            if signature not in known:
                counts["filled_not_merged"] += 1
        if r["source_key"] not in selected_keys:
            counts["unexpected_current_sample_key"] += 1
    return {
        "rows": len(todo),
        **{key: counts[key] for key in (
            "blank_rows", "partially_filled_rows", "filled_rows",
            "filled_structurally_valid", "filled_invalid", "filled_not_merged",
            "unexpected_current_sample_key",
        )},
    }


def _selected_yo_exclusions(config, context, selection, mapping):
    """For selected words, count verified pre-respell RESTORED with F1 exclusions."""
    from audiobook import paths, synth, voicecfg, yo
    from test_stress_yo_fragment_witness import witness
    from test_stress_yo_prerespell_proof import probe_pre_respell

    selected = set(selection.record["keys"])
    by_key = {row.source_key: row for row in context.rows}
    if not selected.issubset(by_key):
        raise AuditBlocked("SELECTED_SOURCE_KEY_MISSING")
    chunks = defaultdict(list)
    for row in context.rows:
        if row.source_key in selected:
            chunks[(row.section, row.chunk_id)].append(row)
    by_section = defaultdict(set)
    for section, chunk_id in chunks:
        by_section[section].add(chunk_id)
    counts = Counter()
    for section in sorted(by_section):
        manifest = paths.OUT / "sections" / section / "manifest.jsonl"
        try:
            records = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()
                       if line.strip()]
        except (OSError, UnicodeError, ValueError):
            raise AuditBlocked("MANIFEST_UNREADABLE") from None
        by_id = {}
        for manifest_row in records:
            cid = manifest_row.get("id")
            if not isinstance(cid, str) or cid in by_id:
                raise AuditBlocked("MANIFEST_DUPLICATE_ID")
            by_id[cid] = manifest_row
        for chunk_id in sorted(by_section[section]):
            manifest_row = by_id.get(chunk_id)
            if manifest_row is None or not isinstance(manifest_row.get("text"), str):
                raise AuditBlocked("MANIFEST_CHUNK_MISSING")
            raw = manifest_row["text"]
            source_words = _WORD.findall(raw)
            fragments = synth.chunk_fragments(raw, config)
            if not fragments:
                raise AuditBlocked("FRAGMENTS_EMPTY")
            if len(fragments) == 1:
                raw_fragments = [raw]
                open_end_values = [bool(manifest_row.get("open_end", False))]
            else:
                raw_fragments = [text.rstrip("?") if is_enum and text.endswith("?") else text
                                 for text, _, is_enum in fragments]
                open_end_values = [False] * len(raw_fragments)
            if [word for frag in raw_fragments for word in _WORD.findall(frag)] != source_words:
                raise AuditBlocked("FRAGMENT_SOURCE_STREAM_MISMATCH")
            prepared = [voicecfg.prepare_text(frag, config, open_end)
                        for frag, open_end in zip(raw_fragments, open_end_values, strict=True)]
            direct = [yo.restore(frag, mapping) if (config.get("text_prep") or {}).get("yo_restore")
                      else frag for frag in raw_fragments]
            for occurrence in chunks[(section, chunk_id)]:
                current = context.sources.resolve(occurrence.source_key)
                if current is None or current[0]["form_source"] != occurrence.form_source:
                    raise AuditBlocked("SELECTED_SOURCE_IDENTITY_CHANGED")
                if (current[2].start(), current[2].end()) != (
                    occurrence.norm_start, occurrence.norm_end
                ):
                    raise AuditBlocked("SELECTED_SOURCE_OFFSET_CHANGED")
                idx = occurrence.chunk_word_index
                if type(idx) is not int or idx < 0 or idx >= len(source_words):
                    raise AuditBlocked("SOURCE_ORDINAL_INVALID")
                if source_words[idx] != occurrence.form_source:
                    raise AuditBlocked("SOURCE_ORDINAL_MISMATCH")
                try:
                    w = witness(source_words, raw_fragments, idx, occurrence.form_source)
                    obs = probe_pre_respell(
                        raw_fragments[w.fragment], occurrence.form_source,
                        w.fragment_word_index,
                        prepared[w.fragment], direct[w.fragment],
                    )
                except (ValueError, TypeError):
                    raise AuditBlocked("PRE_RESPELL_OBSERVATION_UNSUPPORTED") from None
                counts["selected_checked"] += 1
                if obs.restored_vowel_indices:
                    counts["selected_restored"] += 1
                    has_rule = occurrence.f1_rule is not None
                    has_flag = occurrence.f1_flag != "none"
                    if has_rule or has_flag:
                        counts["excluded_union"] += 1
                        counts["excluded_f1_rule"] += int(has_rule)
                        counts["excluded_f1_flag"] += int(has_flag)
                        counts["excluded_both"] += int(has_rule and has_flag)
                    else:
                        counts["yo_evaluable"] += 1
    if counts["selected_checked"] != len(selected):
        raise AuditBlocked("SELECTED_ACCOUNTING_MISMATCH")
    return {key: counts[key] for key in (
        "selected_checked", "selected_restored", "excluded_union",
        "excluded_f1_rule", "excluded_f1_flag", "excluded_both", "yo_evaluable",
    )}


def audit_local(config):
    from audiobook import paths, stress_eval as ev, yo
    from audiobook.__main__ import load_config
    from stress_yo_g0_readonly import audit_local as audit_g0, content_snapshot, prep_config_digest

    files = {name: paths.TEXT / name for name in (
        "stress_gold.tsv", "stress_gold.archive.tsv", "stress_gold.todo.tsv"
    )}
    initial = {name: _read_gold_table(path, ev.GOLD_FIELDS) for name, path in files.items()}
    # Fail closed if an isolated worktree has no owner-local S4 mounted.
    # Missing files are NOT evidence that the owner has no historical labels.
    if not initial["stress_gold.tsv"][0]["exists"]:
        raise AuditBlocked("AUTHORITATIVE_GOLD_NOT_MOUNTED")
    if not initial["stress_gold.todo.tsv"][0]["exists"]:
        raise AuditBlocked("OWNER_TODO_NOT_MOUNTED")
    data = {name: item[0]["rows"] for name, item in initial.items()}
    context = ev._load_context(config)
    selection = ev._selection(context)
    # Verify the persisted sample WITHOUT calling sample(), which writes S4.
    try:
        ev._verify_sample(selection.record, ev._sample_path(selection.record))
    except Exception:
        raise AuditBlocked("CURRENT_SAMPLE_NOT_VERIFIED") from None
    gold = _ledger_numbers(data["stress_gold.tsv"], context, ev)
    todo = _todo_numbers(
        data["stress_gold.todo.tsv"], data["stress_gold.tsv"], ev,
        set(selection.record["keys"]),
    )
    archive_rows = data["stress_gold.archive.tsv"]
    ledger_signatures = Counter(tuple(row[k] for k in ev.GOLD_FIELDS)
                                for row in data["stress_gold.tsv"])
    archived_signatures = Counter(tuple(row[k] for k in ev.GOLD_FIELDS)
                                  for row in archive_rows)
    archive_unmatched = sum(max(0, n - ledger_signatures[record])
                            for record, n in archived_signatures.items())
    archive_invalid = 0
    for archived in archive_rows:
        try:
            ev.validate_gold(archived, historical=True)
        except Exception:
            archive_invalid += 1

    mapping, norm_digest, map_digest = content_snapshot(paths.TEXT)
    if yo.book_map() != mapping:
        raise AuditBlocked("YO_MTIME_CACHE_STALE")
    g0 = audit_g0(config)
    if (g0["status"] != "G0_COVERAGE_MEASURED"
            or g0["counts"]["selected_verified"] != len(selection.record["keys"])):
        raise AuditBlocked("G0_COVERAGE_NOT_PROVEN")
    excluded = _selected_yo_exclusions(config, context, selection, mapping)
    if excluded["selected_restored"] != g0["counts"]["selected_pre_restored"]:
        raise AuditBlocked("RESTORATION_COUNT_DISAGREEMENT")
    if (selection.record["sample_fp"], context.source_fp, context.analysis_fp) != (
        g0["sample_fp"], g0["source_fp"], g0["analysis_fp"]
    ):
        raise AuditBlocked("INVENTORY_OR_SAMPLE_CHANGED")
    _, norm_after, map_after = content_snapshot(paths.TEXT)
    if (norm_digest, map_digest) != (norm_after, map_after) or yo.book_map() != mapping:
        raise AuditBlocked("YO_CONTENT_CHANGED")
    if prep_config_digest(load_config(), map_after) != g0["prep_config_sha256"]:
        raise AuditBlocked("TEXT_PREP_CONFIG_CHANGED")
    fresh = ev._load_context(config)
    if (context.source_fp, context.analysis_fp, context.generation) != (
        fresh.source_fp, fresh.analysis_fp, fresh.generation
    ):
        raise AuditBlocked("INVENTORY_CHANGED")
    for name, path in files.items():
        follow_up, digest = _read_gold_table(path, ev.GOLD_FIELDS)
        if digest != initial[name][1] or follow_up["exists"] != initial[name][0]["exists"]:
            raise AuditBlocked("S4_CHANGED_DURING_AUDIT")

    reason_codes = []
    if gold["invalid_ledger_rows"]:
        reason_codes.append("GOLD_INVALID_ROWS")
    if gold["active_conflicting_keys"]:
        reason_codes.append("GOLD_ACTIVE_CONFLICTS")
    if todo["partially_filled_rows"] or todo["filled_invalid"]:
        reason_codes.append("TODO_LABELS_INVALID_OR_PARTIAL")
    if todo["filled_not_merged"]:
        reason_codes.append("TODO_UNMERGED_LABELS")
    if todo["unexpected_current_sample_key"]:
        reason_codes.append("TODO_SAMPLE_MISMATCH")
    if archive_unmatched:
        reason_codes.append("ARCHIVE_ORPHAN_ROWS")
    if archive_invalid:
        reason_codes.append("ARCHIVE_INVALID_ROWS")
    # Any human edits, even only in todo, merit the history-first recommendation.
    # "No historical versions" is not the same as "no owner data to preserve".
    history_exists = (
        gold["human_labeled_rows"] > 0 or todo["filled_rows"] > 0 or
        todo["partially_filled_rows"] > 0 or
        gold["extra_historical_identities"] > 0 or
        gold["currently_stale_rows"] > 0 or len(archive_rows) > 0 or
        gold["source_keys_repeated"] > 0
    )
    recommendation = (
        "PREFER_KEEP_EXISTING_C3_VERSION_LEDGER_AND_PRESERVE_HISTORY"
        if history_exists else "PREFER_MINIMAL_C3_KEEP_CURRENT_LEDGER_NO_MIGRATION"
    )
    return {
        "status": "BLOCKED" if reason_codes else "PASS",
        "reason_codes": reason_codes,
        "owner_A": "APPROVED_IN_PRINCIPLE",
        "owner_B": "DEFERRED_NOT_APPROVED",
        "gold": {"present": initial["stress_gold.tsv"][0]["exists"], **gold},
        "archive": {
            "present": initial["stress_gold.archive.tsv"][0]["exists"],
            "rows": len(archive_rows),
            "unmatched_to_current_gold": archive_unmatched,
            "invalid_rows": archive_invalid,
        },
        "todo": {"present": initial["stress_gold.todo.tsv"][0]["exists"], **todo},
        "restoration_selected": excluded,
        "sample_current_keys": len(selection.record["keys"]),
        "g0_eligible_verified": g0["counts"]["eligible_verified"],
        "g0_unsupported_selected": sum(
            number for key, number in g0["counts"].items()
            if key.startswith("selected_unsupported_")
        ),
        "recommendation": recommendation,
        "authorized_migration": False,
        "production_modified": False,
        "s4_modified": False,
    }


def main():
    try:
        from audiobook.__main__ import load_config
        result = audit_local(load_config())
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] == "PASS" else 2
    except AuditBlocked as err:
        print(json.dumps({
            "status": "BLOCKED", "reason_codes": [str(err)],
            "owner_B": "DEFERRED_NOT_APPROVED", "authorized_migration": False,
        }, sort_keys=True))
        return 2
    except Exception:
        # Exception messages and tracebacks may contain private paths or text.
        print(json.dumps({
            "status": "BLOCKED", "reason_codes": ["LOCAL_AUDIT_ERROR"],
            "owner_B": "DEFERRED_NOT_APPROVED", "authorized_migration": False,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
