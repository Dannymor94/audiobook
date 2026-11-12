"""Offline, content-pinned advisory stress analysis. Never changes TTS text."""
from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import os
import re
from collections import Counter
from importlib.metadata import version
from pathlib import Path

from audiobook import paths
from audiobook.unitmap import AnnotationError

_WORD = re.compile(r"[а-яёА-ЯЁ]+")
_MARKED = re.compile(r"[а-яёА-ЯЁ+]+")
_VOWELS = frozenset("аеёиоуыэюя")
B1_RUNTIME_PIN = "2f670f53b1fcdcea328a63388ac76ccfdbff11cc593011795d1fd3dc6c70ccbd"
INIT_PARAMS = {"omograph_model_size": "turbo", "use_dictionary": True,
               "device": "CPU", "tiny_mode": False, "custom_dict": {}, "custom_homographs": {}}
RUNTIME_VERSIONS = {"ruaccent": "1.5.8.3", "transformers": "4.57.3",
                    "torch": "2.14.0", "onnxruntime": "1.30.0"}


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ruaccent_content_identity(*, models=None, package=None, loader=None,
                             versions=None, require_pin=True) -> dict:
    """Hash the accepted runtime file closure; never use mtimes as identity.

    The B1 aggregate uses its original labels/order/size framing. The returned
    ADR identity uses sorted relative paths and content hashes, including the
    unchanged loader. Explicit roots allow synthetic, model-free mutation tests.
    """
    try:
        models = models if models is not None else paths.MODELS
        package = package if package is not None else Path(importlib.util.find_spec("ruaccent").origin).parent
        loader = loader if loader is not None else paths.ROOT / "src" / "audiobook" / "accent.py"
        versions = versions if versions is not None else {name: version(name) for name in RUNTIME_VERSIONS}
        entries = []
        for label, base in (("nn", models / "nn"), ("dictionary", models / "dictionary"), ("ruaccent", package)):
            if not base.is_dir():
                raise AnnotationError("RUACCENT_RUNTIME_UNAVAILABLE")
            for file in sorted(base.rglob("*")):
                if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
                    entries.append([label, file.relative_to(base).as_posix(), file.stat().st_size, _file_sha(file)])
        loader_sha = _file_sha(loader)
    except (OSError, ImportError, AttributeError, ValueError):
        raise AnnotationError("RUACCENT_RUNTIME_UNAVAILABLE") from None
    b1 = {"files": entries, "init": INIT_PARAMS, "loader_sha256": loader_sha}
    if require_pin and (hashlib.sha256(_canonical(b1)).hexdigest() != B1_RUNTIME_PIN
                        or versions != RUNTIME_VERSIONS):
        raise AnnotationError("RUACCENT_RUNTIME_PIN_MISMATCH")
    files = [[f"{label}/{name}", sha] for label, name, _, sha in entries]
    files.append(["loader/accent.py", loader_sha])
    return {"version": dict(sorted(versions.items())), "init_params": INIT_PARAMS,
            "files": sorted(files)}


def load_pinned_runtime():
    """Initialize only the accepted local CPU loader, or fail without fallback."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    identity = ruaccent_content_identity()
    try:
        from audiobook.accent import _get_accentizer
        engine = _get_accentizer()
        if Path(engine.workdir).resolve() != paths.MODELS.resolve() or engine.tiny_mode:
            raise AnnotationError("RUACCENT_RUNTIME_PIN_MISMATCH")
        # ONNX opens model files in native code. Inspect the actual loaded model
        # paths/providers as well as the content-pinned Python/tokenizer closure.
        for name in ("omograph_model", "accent_model", "stress_usage_predictor", "yo_homograph_model"):
            session = getattr(engine, name).session
            model = Path(session._model_path).resolve()
            if not model.is_relative_to((paths.MODELS / "nn").resolve()) or session.get_providers() != ["CPUExecutionProvider"]:
                raise AnnotationError("RUACCENT_RUNTIME_PIN_MISMATCH")
        if identity != ruaccent_content_identity():
            raise AnnotationError("RUACCENT_RUNTIME_PIN_MISMATCH")
        return engine.process_all, identity
    except AnnotationError:
        raise
    except Exception:
        raise AnnotationError("RUACCENT_INIT_ERROR") from None


def parse_advice(sentence: str, accented: str) -> list[tuple[str, int | None]]:
    """Strict occurrence-index correspondence; no searches or realignment."""
    original = _WORD.findall(sentence)
    if not isinstance(accented, str):
        raise AnnotationError("RUACCENT_RUNTIME_ERROR")
    marked = _MARKED.findall(accented)
    fold = lambda text: text.replace("+", "").lower().replace("ё", "е")
    if [fold(t) for t in original] != [fold(t) for t in marked]:
        return [("tokenization_mismatch", None)] * len(original)
    result = []
    for token in marked:
        marks = [i for i, char in enumerate(token) if char == "+"]
        if any(i + 1 == len(token) or token[i + 1].lower() not in _VOWELS for i in marks):
            result.append(("invalid_mark", None))
        elif len(marks) > 1:
            result.append(("multi_stress", None))
        elif not marks:
            result.append(("no_stress", None))
        else:
            result.append(("resolved", sum(c.lower() in _VOWELS for c in token[:marks[0]])))
    return result


def apply_advisory(occs, analysis: str, process):
    """Fill F6 and §9 outcomes; preserve original spelling and fields 1–29."""
    from audiobook.stress_facts import resolve_expected, classify_status
    from audiobook.stress_inventory import _split_sentences_with_pos
    evidence = {}
    for sentence, start in _split_sentences_with_pos(analysis):
        words = list(_WORD.finditer(sentence))
        if not words:
            continue
        if process is None:
            statuses = [("not_run", None)] * len(words)
        else:
            try:
                statuses = parse_advice(sentence, process(sentence))
            except AnnotationError:
                raise
            except Exception:
                raise AnnotationError("RUACCENT_RUNTIME_ERROR") from None
        for word, outcome in zip(words, statuses, strict=True):
            evidence[(start + word.start(), start + word.end())] = outcome
    enriched = []
    for occ in occs:
        if analysis[occ.ana_start:occ.ana_end] != occ.form_analysis:
            raise AnnotationError("ANALYSIS_LINK_ERROR")
        try:
            status, vowel = evidence[occ.ana_start, occ.ana_end]
        except KeyError:
            raise AnnotationError("ANALYSIS_LINK_ERROR") from None
        source, expected = resolve_expected(occ.f2_approval, occ.f2_vowel, occ.f5_status,
                                           occ.f5_vowel, status, vowel)
        final_status, reason = classify_status(occ.alignment_status, occ.f1_flag, occ.f1_rule,
                                               source, status, vowel, expected, occ.f3_verified)
        values = dataclasses.asdict(occ)
        values.update(f6_status=status, f6_vowel=vowel, expected_source=source,
                      expected_vowel=expected, status=final_status, reason=reason)
        enriched.append(type(occ)(**values))
    return enriched


def collect_snapshot(config):
    """Read frozen inputs under the accepted row/SU dependency guard."""
    import yaml
    from audiobook.chunker import load_units
    from audiobook.wordprov import check_source_marks, validate_manifest_accesses
    exclude = paths.TEXT / "stress_inventory_exclude.yaml"
    data = yaml.safe_load(exclude.read_text(encoding="utf-8")) if exclude.exists() else {}
    excluded = sorted(str(item["section"]) for item in (data or {}).get("sections", []))
    table_path = paths.TEXT / "pronounce.yaml"
    table = yaml.safe_load(table_path.read_text(encoding="utf-8")) if table_path.exists() else {}
    from audiobook.pronounce import load_table
    table = load_table(table_path)
    units, rows = {}, {}
    sentinel = config.get("model", {}).get("sentinel", "")  # TTS parameter, not an analysis dependency.
    for norm in sorted(paths.TEXT.glob("[0-9][0-9]_*.norm.txt")):
        section = norm.name.removesuffix(".norm.txt")
        if section in excluded:
            continue
        manifest = paths.OUT / "sections" / section / "manifest.jsonl"
        units[section] = load_units(*section.split("_", 1))
        check_source_marks(units[section], section)
        rows[section] = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
        validate_manifest_accesses(rows[section], config, table, sentinel)
    if not units:
        raise AnnotationError("SOURCE_UNAVAILABLE")
    return units, rows, excluded, table


def current_fingerprints(config, identity=None, snapshot=None):
    from audiobook import stress_fp, yo
    from audiobook.wordprov import source_fp, manifest_fp
    units, rows, excluded, _ = snapshot if snapshot is not None else collect_snapshot(config)
    identity = ruaccent_content_identity() if identity is None else identity
    source = source_fp(units, excluded)
    manifest = manifest_fp(rows)
    files = {}
    for field, filename in (("pronounce", "pronounce.yaml"), ("verified", "stress_verified.yaml"),
                            ("watch", "stress_watch.yaml"), ("exclude", "stress_inventory_exclude.yaml")):
        path = paths.TEXT / filename
        files[field + "_sha256"] = _file_sha(path) if path.exists() else None
    mapping = yo.build_map([p.read_text(encoding="utf-8") for p in sorted(paths.TEXT.glob("*.norm.txt"))])
    files["yo_dict_sha256"] = hashlib.sha256(_canonical(mapping)).hexdigest()
    analysis = stress_fp.analysis_fp(source, manifest, identity, config, **files)
    return {"source_fp": source, "manifest_fp": manifest, "analysis_fp": analysis}


def build_payload(config):
    """In-memory publication payload; no model or source output is written here."""
    from audiobook.sutrace import trace_section
    from audiobook.wordprov import process_section_occs, serialize_tsv
    from audiobook.stress_facts import apply_facts, _load_verified_safe
    process, identity = load_pinned_runtime()
    snapshot = collect_snapshot(config)
    fingerprints = current_fingerprints(config, identity, snapshot)
    units, rows, _, table = snapshot
    verified = _load_verified_safe(paths.TEXT / "stress_verified.yaml")
    occurrences = []
    for section in units:
        traces = trace_section(section, config, table, config.get("model", {}).get("sentinel", ""))
        if any(trace.status != "ok" for trace in traces):
            raise AnnotationError("TRACE_FAILURE")
        by_su = {(trace.chunk_id, trace.fragment): trace for trace in traces}
        occs, analysis, _ = process_section_occs(section, units[section], rows[section], traces)
        facts = [apply_facts(occ, by_su.get((occ.su_chunk_id, occ.su_fragment)), verified) for occ in occs]
        occurrences.extend(apply_advisory(facts, analysis, process))
    if current_fingerprints(config) != fingerprints:
        raise AnnotationError("INVENTORY_STALE")
    unresolved = Counter(occ.reason for occ in occurrences if occ.status == "unresolved")
    return {**fingerprints, "tsv": serialize_tsv(occurrences),
            "counts": {"occurrences": len(occurrences),
                       "aligned": sum(occ.alignment_status == "aligned" for occ in occurrences),
                       "unresolved_by_reason": dict(sorted(unresolved.items()))},
            "f6_status_counts": dict(sorted(Counter(occ.f6_status for occ in occurrences).items()))}
