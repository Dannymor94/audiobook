"""READ-ONLY local G0 coverage probe. Research-only; no ADR or gold changes.

Run in audiobook's offline .venv with PYTHONPATH=src:
  python -B tests/stress_yo_g0_readonly.py

This script reads current validated v5 inventory, local source/manifest and
the live ё map. It writes NOTHING and prints ONLY aggregate counts and global
digests. No source tokens, source keys, paths, per-occurrence hashes or labels.

A source_key is verified against the source index, then mapped by an EXACT
chunk-word ordinal to raw pre-respell fragment. Fuzzy search, SUTrace token
indices and WordOcc.form_synth are not provenance or fallback evidence.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from test_stress_yo_fragment_witness import UnsupportedWitness, witness
from test_stress_yo_prerespell_proof import UnsupportedObservation, probe_pre_respell

_WORD = re.compile(r"[А-Яа-яЁё]+")


class AuditFailure(RuntimeError):
    pass


def _digest(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def content_snapshot(directory: Path) -> tuple[dict[str, str], str, str]:
    """Hash exact .norm bytes and rebuild actual YO map from decoded content.

    This bypasses the runtime mtime-only cache; no file content is printed.
    """
    from audiobook.yo import build_map
    files = sorted(directory.glob("*.norm.txt"))
    names_and_sha: list[tuple[str, str]] = []
    texts: list[str] = []
    for file in files:
        raw = file.read_bytes()
        names_and_sha.append((file.name, hashlib.sha256(raw).hexdigest()))
        texts.append(raw.decode("utf-8"))
    mapping = build_map(texts)
    if not isinstance(mapping, dict):
        raise AuditFailure("YO_MAP_INVALID")
    return mapping, _digest({"algo": "yo-norm-content/1", "files": names_and_sha}), _digest({
        "algo": "yo-map/1", "mapping": sorted(mapping.items()),
    })


def prep_config_digest(config: dict, map_digest: str) -> str:
    """Only relevant textual preprocessing inputs; not model/voice/secrets."""
    tp = config.get("text_prep") or {}
    return _digest({
        "algo": "yo-prep-config/1",
        "yo_map_sha256": map_digest,
        "yo_restore": bool(tp.get("yo_restore", False)),
        "strip_quotes": bool(tp.get("strip_quotes", False)),
        "ensure_terminal": bool(tp.get("ensure_terminal", False)),
        "open_end": tp.get("open_end", "keep"),
    })


def audit_local(config: dict) -> dict:
    from audiobook import paths, synth, voicecfg, yo, stress_eval as evaluation

    mapping, norm_fp, map_fp = content_snapshot(paths.TEXT)
    runtime_map = yo.book_map()
    if runtime_map != mapping:
        raise AuditFailure("YO_MTIME_CACHE_STALE")
    cfg_fp = prep_config_digest(config, map_fp)
    context = evaluation._load_context(config)  # Existing validated v5 reader.
    selection = evaluation._selection(context)
    selected = set(selection.record["keys"])
    eligible = [row for row in context.rows if (
        row.alignment_status == "aligned" and evaluation.vowel_count(row.form_analysis) >= 2
    )]
    chunks: dict[tuple[str, str], list] = defaultdict(list)
    for row in context.rows:
        chunks[(row.section, row.chunk_id)].append(row)
    by_section = defaultdict(set)
    for row in eligible:
        by_section[row.section].add(row.chunk_id)

    counts = Counter()
    by_stratum = {name: Counter() for name, _ in evaluation.STRATA}
    counts["inventory_rows"] = len(context.rows)
    counts["eligible"] = len(eligible)
    counts["selected"] = len(selected)
    counts["sections"] = len(by_section)
    counts["chunks_with_eligible"] = sum(map(len, by_section.values()))

    def record(row, status: str, restored: bool | None) -> None:
        counts["eligible_" + status] += 1
        if row.source_key not in selected:
            return
        counts["selected_" + status] += 1
        stratum = selection.strata_by_key[row.source_key]
        by_stratum[stratum][status] += 1
        if restored is None:
            return
        post_changed = evaluation.yo_changed(row)  # Existing post-respell, for contrast only.
        counts[
            "selected_pre_" + str(int(restored)) + "_post_" + str(int(post_changed))
        ] += 1

    # The local manifest belongs to the validated original source generation.
    # Never scan names and infer matches by spelling or edit distance.
    seen_manifest_chunks: set[tuple[str, str]] = set()
    observed_selection: set[str] = set()
    for section in sorted(by_section):
        manifest = paths.OUT / "sections" / section / "manifest.jsonl"
        try:
            records = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, UnicodeError, ValueError):
            raise AuditFailure("MANIFEST_UNREADABLE") from None
        by_id: dict[str, dict] = {}
        for manifest_row in records:
            chunk_id = manifest_row.get("id")
            if not isinstance(chunk_id, str) or chunk_id in by_id:
                raise AuditFailure("MANIFEST_ID_INVALID")
            by_id[chunk_id] = manifest_row

        for chunk_id in sorted(by_section[section]):
            key = (section, chunk_id)
            if key in seen_manifest_chunks:
                raise AuditFailure("DUPLICATE_MANIFEST_CHUNK")
            seen_manifest_chunks.add(key)
            all_rows = sorted(chunks[key], key=lambda occ: occ.chunk_word_index)
            checked = [r for r in all_rows if (
                r.alignment_status == "aligned" and evaluation.vowel_count(r.form_analysis) >= 2
            )]
            chunk = by_id.get(chunk_id)
            if chunk is None or not isinstance(chunk.get("text"), str):
                for row in checked:
                    record(row, "unsupported_manifest", None)
                continue
            raw = chunk["text"]
            source_words = _WORD.findall(raw)
            valid_chunk = (
                len(source_words) == len(all_rows)
                and [r.chunk_word_index for r in all_rows] == list(range(len(all_rows)))
                and [r.form_source for r in all_rows] == source_words
            )
            if not valid_chunk:
                for row in checked:
                    record(row, "unsupported_source_stream", None)
                continue
            try:
                frags = synth.chunk_fragments(raw, config)
                if not frags:
                    raise UnsupportedWitness("NO_FRAGMENTS")
                if len(frags) == 1:
                    raw_fragments = [raw]
                    opens = [bool(chunk.get("open_end", False))]
                else:
                    raw_fragments = [
                        item.rstrip("?") if is_enum and item.endswith("?") else item
                        for item, _, is_enum in frags
                    ]
                    opens = [False] * len(raw_fragments)
                if [word for frag in raw_fragments for word in _WORD.findall(frag)] != source_words:
                    raise UnsupportedWitness("FRAGMENT_STREAM_NOT_EXACT_SOURCE")
            except (UnsupportedWitness, ValueError, TypeError):
                for row in checked:
                    record(row, "unsupported_fragments", None)
                continue

            prepared = [voicecfg.prepare_text(fragment, config, opened)
                        for fragment, opened in zip(raw_fragments, opens, strict=True)]
            direct = [(yo.restore(fragment, mapping) if config.get("text_prep", {}).get("yo_restore") else fragment)
                      for fragment in raw_fragments]
            for row in checked:
                # SourceIndex.resolve is the independent source_key/identity witness
                # for selected rows; unit/token coordinates must agree exactly.
                if row.source_key in selected:
                    observed_selection.add(row.source_key)
                    try:
                        src = context.sources.resolve(row.source_key)
                        if src is None:
                            raise UnsupportedWitness("SOURCE_NOT_FOUND")
                        identity, _, match = src
                        if (identity["form_source"] != row.form_source
                                or (match.start(), match.end()) != (row.norm_start, row.norm_end)):
                            raise UnsupportedWitness("SOURCE_KEY_NOT_CURRENT")
                    except (UnsupportedWitness, ValueError, TypeError):
                        record(row, "unsupported_source_key", None)
                        continue
                try:
                    proof = witness(source_words, raw_fragments,
                                    row.chunk_word_index, row.form_source)
                    result = probe_pre_respell(
                        raw_fragments[proof.fragment], row.form_source,
                        proof.fragment_word_index,
                        prepared[proof.fragment], direct[proof.fragment],
                    )
                    record(row, "verified", bool(result.restored_vowel_indices))
                    if result.restored_vowel_indices:
                        counts["eligible_pre_restored"] += 1
                        if row.source_key in selected:
                            counts["selected_pre_restored"] += 1
                except (UnsupportedWitness, UnsupportedObservation, ValueError, TypeError):
                    record(row, "unsupported_prep", None)

    if observed_selection != selected:
        # A selected row that is no longer eligible or has no counted chunk is not
        # evidence of absence of a restoration; stop rather than omit its identity.
        raise AuditFailure("SELECTED_COVERAGE_INCOMPLETE")

    # Recheck actual bytes and runtime map rather than trusting file mtimes.
    _, norm_fp_after, map_fp_after = content_snapshot(paths.TEXT)
    if norm_fp_after != norm_fp or map_fp_after != map_fp:
        raise AuditFailure("YO_SOURCE_CHANGED_DURING_AUDIT")
    if yo.book_map() != mapping:
        raise AuditFailure("YO_CACHED_MAP_CHANGED_DURING_AUDIT")
    config_after = __import__("audiobook.__main__", fromlist=["load_config"]).load_config()
    if prep_config_digest(config_after, map_fp_after) != cfg_fp:
        raise AuditFailure("PREP_CONFIG_CHANGED_DURING_AUDIT")
    refreshed = evaluation._load_context(config_after)
    if (context.source_fp, context.analysis_fp, context.generation) != (
        refreshed.source_fp, refreshed.analysis_fp, refreshed.generation
    ):
        raise AuditFailure("INVENTORY_CHANGED_DURING_AUDIT")

    n_sel_verified = counts["selected_verified"]
    n_sel_unsupported = sum(
        n for key, n in counts.items() if key.startswith("selected_unsupported_")
    )
    if n_sel_verified + n_sel_unsupported != counts["selected"]:
        raise AuditFailure("SELECTED_ACCOUNTING_MISMATCH")
    return {
        "status": "G0_COVERAGE_MEASURED" if n_sel_unsupported == 0 else "G0_UNSUPPORTED_PRESENT",
        "policy": "g0-observation-audit/1", "source_fp": context.source_fp,
        "analysis_fp": context.analysis_fp, "sample_fp": selection.record["sample_fp"],
        "yo_map_sha256": map_fp, "norm_content_sha256": norm_fp,
        "prep_config_sha256": cfg_fp,
        "counts": {name: counts[name] for name in sorted(counts)},
        "selected_by_stratum": {
            name: {k: value[k] for k in sorted(value)}
            for name, value in sorted(by_stratum.items())
        },
        "g0_closed": False, "no_data_written": True,
    }


def main() -> int:
    try:
        from audiobook.__main__ import load_config
        data = audit_local(load_config())
        print(json.dumps(data, sort_keys=True, ensure_ascii=False))
        return 0 if data["status"] == "G0_COVERAGE_MEASURED" else 2
    except Exception as err:
        # Never print raw exceptions: they may include private filenames or text.
        code = err.args[0] if isinstance(err, AuditFailure) else "PRIVATE_LOCAL_AUDIT_ERROR"
        print(json.dumps({"status": "ERROR", "code": code, "g0_closed": False}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
