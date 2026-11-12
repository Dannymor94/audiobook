"""Shared parameters and generation management for stress analysis (T15 / T17).

Public API consumed by T17 (stress-sheet):
  INVENTORY_ALGO_VERSION  — bump when output format or classification logic changes
  stress_params(cfg)      — extract typed stress config from full config dict
  load_current(stress_dir) — read current.json, verify SHA, return summary dict

T15-7.3 additions (re-exported from wordprov):
  source_fp   — §5 SHA-256 of canonical source units representation
  manifest_fp — §5 SHA-256 of canonical analytic manifest fields
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

# Bump when: paragraph separator logic changes, scoring changes, new risk
# categories added, TSV columns added/removed, summary.json schema changes.
# See CLAUDE.md → "INVENTORY_ALGO_VERSION bump rules".
# v4: exact atom provenance; multi-unit joins use adjoining source atoms.
INVENTORY_ALGO_VERSION: int = 5


def stress_params(cfg: dict) -> dict:
    """Return full stress config subtree plus derived pauses parameters.

    All keys under cfg['stress'] are included automatically; new nested keys
    are picked up without code changes.  paragraph_ms is always derived from
    cfg['pauses_ms']['paragraph'], not from the stress subtree.
    """
    s = dict((cfg or {}).get("stress") or {})
    pauses = (cfg or {}).get("pauses_ms") or {}
    s.setdefault("top_n", 300)
    s["paragraph_ms"] = int(pauses.get("paragraph", 900))
    return s


def load_current(stress_dir: Path) -> dict | None:
    """Return current inventory summary dict, or None if none published.

    Reads stress_dir/inventory/current.json, finds gen/<gen_id>/summary.json,
    verifies its SHA-256 against stored value.  Raises RuntimeError on mismatch.
    """
    cur = stress_dir / "inventory" / "current.json"
    if not cur.exists():
        return None
    meta = json.loads(cur.read_text(encoding="utf-8"))
    gen_id = meta.get("gen_id", "")
    gen_dir = stress_dir / "gen" / gen_id
    summary_path = gen_dir / "summary.json"
    if not summary_path.exists():
        return None
    actual_sha = hashlib.sha256(summary_path.read_bytes()).hexdigest()
    expected_sha = meta.get("summary_sha256", "")
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"stress inventory: summary.json SHA mismatch for gen {gen_id!r}\n"
            f"  expected: {expected_sha}\n"
            f"  actual:   {actual_sha}"
        )
    return json.loads(summary_path.read_text(encoding="utf-8"))


# T15-7.3: fingerprint functions — implemented in wordprov, re-exported here.
from audiobook.wordprov import source_fp, manifest_fp  # noqa: E402, F401


HISTORICAL_TSV_NAMES = ("risk.tsv", "omographs.tsv")


def historical_tsv_digest(files: dict[str, bytes]) -> str:
    """Hash ordered filenames, length-prefixed byte contents and a format tag."""
    from audiobook.unitmap import AnnotationError
    if set(files) != set(HISTORICAL_TSV_NAMES) or any(type(v) is not bytes for v in files.values()):
        raise AnnotationError("HISTORICAL_TSV_INVALID")
    digest = hashlib.sha256(b"historical-tsv/1\0")
    for name in HISTORICAL_TSV_NAMES:
        data = files[name]
        digest.update(name.encode("utf-8") + b"\0" + len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


def check_historical_tsv(directory: Path, files: dict[str, bytes], input_identity: str) -> str:
    """Read-only comparison against immutable local v4 bytes and input identity."""
    from audiobook.unitmap import AnnotationError
    try:
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        stored = {name: (directory / name).read_bytes() for name in HISTORICAL_TSV_NAMES}
        equal = (metadata["input_identity"] == input_identity and stored == files
                 and metadata["D_tsv"] == historical_tsv_digest(stored) == historical_tsv_digest(files))
    except (OSError, ValueError, KeyError, TypeError):
        raise AnnotationError("HISTORICAL_TSV_UNAVAILABLE") from None
    if not equal:
        raise AnnotationError("HISTORICAL_TSV_MISMATCH")
    return metadata["D_tsv"]


# The eight observed SU leaves, plus the two actual inventory analysis reads
# (stress_inventory.run -> stress_params: top_n and paragraph_ms).
CONFIG_FP_KEYS = (
    "text_prep.yo_restore", "text_prep.strip_quotes", "text_prep.open_end", "text_prep.ensure_terminal",
    "render.leadin.phrase", "render.leadin.max_chars", "pauses_ms.enum_pause_ms", "pauses_ms.sentence",
    "stress.top_n", "pauses_ms.paragraph",
)


def analysis_fp(source: str, manifest: str, ruaccent: dict, config: dict, *,
                yo_dict_sha256, pronounce_sha256, verified_sha256, watch_sha256, exclude_sha256) -> str:
    """ADR §5 content identity for the advisory algorithm, independent of audio."""
    from audiobook.sutrace import _DeepRecordingConfig, DECLARED_CONFIG_PATHS
    from audiobook.unitmap import AnnotationError
    cfg = _DeepRecordingConfig(config)
    subset = {}
    for path in CONFIG_FP_KEYS:
        node = cfg
        for part in path.split("."):
            node = node.get(part) if hasattr(node, "get") else None
        subset[path] = node
    if cfg._accessed - (DECLARED_CONFIG_PATHS | {"stress", "stress.top_n", "pauses_ms.paragraph"}):
        raise AnnotationError("CONFIG_ACCESS_UNDECLARED")
    payload = {"algo": "analysis/1", "inventory_algo_version": 5, "source_fp": source,
               "manifest_fp": manifest, "ruaccent": ruaccent, "config_subset": subset,
               "yo_dict_sha256": yo_dict_sha256, "pronounce_sha256": pronounce_sha256,
               "verified_sha256": verified_sha256, "watch_sha256": watch_sha256,
               "exclude_sha256": exclude_sha256, "trace_algo": "sutrace/1"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def private_output_guard(path: Path) -> None:
    """P1: refuse writes unless the actual target is ignored and untracked."""
    from audiobook import paths
    from audiobook.unitmap import AnnotationError
    ignored = subprocess.run(["git", "check-ignore", "-q", "--", str(path)], cwd=paths.ROOT,
                             capture_output=True).returncode == 0
    tracked = subprocess.run(["git", "ls-files", "--", str(path)], cwd=paths.ROOT, capture_output=True)
    if not ignored or tracked.returncode != 0 or tracked.stdout:
        raise AnnotationError("PRIVATE_OUTPUT_REQUIRED")


def historical_input_identity() -> str:
    """Reproduce the exact v4 input identity archived with its byte baseline."""
    from audiobook import paths
    from audiobook.ruaccent_adv import ruaccent_content_identity, B1_RUNTIME_PIN, _file_sha, _canonical
    ruaccent_content_identity()  # Revalidate contents, not merely a stored pin.
    inputs = [("config.yaml", paths.ROOT / "config.yaml")]
    for label, base, pattern in (("text", paths.TEXT, "*.norm.txt"),
                                  ("text/blocks", paths.TEXT / "blocks", "*.blocks.json"),
                                  ("out/sections", paths.OUT / "sections", "*/manifest.jsonl")):
        inputs.extend((f"{label}/{p.relative_to(base).as_posix()}", p) for p in base.glob(pattern))
    inputs.extend((f"text/{n}", paths.TEXT / n) for n in
                  ("pronounce.yaml", "stress_verified.yaml", "stress_watch.yaml", "stress_inventory_exclude.yaml"))
    inputs.extend((f"src/audiobook/{n}", paths.ROOT / "src" / "audiobook" / n)
                  for n in ("unitmap.py", "chunker.py", "joins.py", "accent.py"))
    payload = {"runtime_pin": B1_RUNTIME_PIN, "inputs": [[label, _file_sha(p)] for label, p in sorted(inputs)]}
    return hashlib.sha256(_canonical(payload)).hexdigest()


RISK_HEADER = "форма\tчастота\tпричина\tпример"
OMOGRAPHS_HEADER = "форма\tсекция\tчанк\tконтекст\tварианты\truaccent\truaccent_status"


def _generation_error():
    from audiobook.unitmap import AnnotationError
    raise AnnotationError("INVENTORY_INVALID") from None


def _check_generation_file(data: bytes, metadata: dict, header: str, schema: str):
    if (not isinstance(metadata, dict) or metadata.get("schema") != schema
            or type(metadata.get("bytes")) is not int or metadata["bytes"] != len(data)
            or type(metadata.get("rows")) is not int or metadata["rows"] < 0
            or metadata.get("sha256") != hashlib.sha256(data).hexdigest()):
        _generation_error()
    text = data.decode("utf-8")
    # v4's unchanged text writer uses native newlines. Preserve its bytes on
    # Windows too; the new occurrences contract alone requires canonical LF.
    if schema != "occurrences/1":
        text = text.replace("\r\n", "\n")
    if not text.endswith("\n") or "\r" in text:
        _generation_error()
    lines = text[:-1].split("\n")
    if lines[0] != header or len(lines) - 1 != metadata["rows"]:
        _generation_error()
    if schema == "occurrences/1":
        from audiobook.wordprov import parse_tsv
        return parse_tsv(text)
    columns = len(header.split("\t"))
    for line in lines[1:]:
        values = line.split("\t")
        if len(values) != columns or not values[0]:
            _generation_error()
        if schema == "risk/1" and (not re.fullmatch(r"[1-9][0-9]*", values[1])
                                   or any(reason not in {"top", "homograph", "name", "dict", "other"}
                                          for reason in values[2].split("+"))):
            _generation_error()
        if schema == "omographs/1":
            from audiobook.unitmap import _section_violation
            if (_section_violation(values[1]) is not None or not values[2]
                    or values[6] not in ("", "resolved", "unresolved/no_stress", "unresolved/tokenization_mismatch")):
                _generation_error()
    return None


def read_occurrences(config: dict, stress_dir: Path | None = None):
    """Read a complete, current v5 generation; never repair or write anything."""
    from collections import Counter
    from audiobook import paths
    from audiobook.unitmap import AnnotationError
    from audiobook.wordprov import tsv_header
    from audiobook.ruaccent_adv import current_fingerprints
    stress_dir = stress_dir if stress_dir is not None else paths.OUT / "stress"
    try:
        inventory = stress_dir / "inventory"
        pointer = json.loads((inventory / "current.json").read_text(encoding="utf-8"))
        gen_id = pointer["gen_id"]
        if type(gen_id) is not str or re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", gen_id) is None:
            _generation_error()
        summary = load_current(stress_dir)
        if (not isinstance(summary, dict) or type(summary.get("algo_version")) is not int
                or summary.get("algo_version") != 5 or type(summary.get("schema_version")) is not int
                or summary.get("schema_version") != 1 or summary.get("gen_id") != gen_id):
            _generation_error()
        archive = stress_dir / "gen" / gen_id
        if ((archive / "current.json").read_bytes() != (inventory / "current.json").read_bytes()
                or (archive / "summary.json").read_bytes() != (inventory / "summary.json").read_bytes()):
            _generation_error()
        contracts = {"risk.tsv": (RISK_HEADER, "risk/1"), "omographs.tsv": (OMOGRAPHS_HEADER, "omographs/1"),
                     "occurrences.tsv": (tsv_header(), "occurrences/1")}
        if set(summary["files"]) != set(contracts):
            _generation_error()
        occurrences = None
        for name, (header, schema) in contracts.items():
            live = (inventory / name).read_bytes()
            if (archive / name).read_bytes() != live:
                _generation_error()
            parsed = _check_generation_file(live, summary["files"][name], header, schema)
            if parsed is not None:
                occurrences = parsed
        if occurrences is None:
            _generation_error()
        expected_counts = {"occurrences": len(occurrences),
                           "aligned": sum(o.alignment_status == "aligned" for o in occurrences),
                           "unresolved_by_reason": dict(Counter(o.reason for o in occurrences if o.status == "unresolved"))}
        counts = summary["counts"]
        if (not isinstance(counts, dict) or type(counts.get("occurrences")) is not int
                or type(counts.get("aligned")) is not int
                or not isinstance(counts.get("unresolved_by_reason"), dict)
                or any(type(value) is not int or value < 1 for value in counts["unresolved_by_reason"].values())
                or counts != expected_counts):
            _generation_error()
        published = {key: summary[key] for key in ("source_fp", "manifest_fp", "analysis_fp")}
        if any(type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None for value in published.values()):
            _generation_error()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, AnnotationError):
        _generation_error()
    try:
        current = current_fingerprints(config)
    except Exception:
        raise AnnotationError("INVENTORY_STALE") from None
    if current != published:
        raise AnnotationError("INVENTORY_STALE")
    return occurrences
