"""Optional local spaCy adapter for ALG-03. Read-only; no download or TTS."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from audiobook.rhythm_syntax import coordination_boundaries, protected_commas


def model_digest(root: Path) -> str:
    """Digest relative paths and contents, not machine-specific locations."""
    h = hashlib.sha256()
    files = sorted(root.rglob("*"))
    if not root.is_dir() or not files:
        raise ValueError("LOCAL_MODEL_REQUIRED")
    for p in files:
        if p.is_symlink():
            raise ValueError("MODEL_SYMLINK_FORBIDDEN")
        if p.is_file():
            record = [p.relative_to(root).as_posix(),
                      hashlib.sha256(p.read_bytes()).hexdigest()]
            h.update(json.dumps(record, ensure_ascii=False).encode("utf-8") + b"\n")
    return h.hexdigest()


def propose(text: str, doc) -> dict:
    """Convert local parser output, preserving exact source offsets."""
    if doc.text != text:
        raise ValueError("PARSER_TEXT_MISMATCH")
    proposals = set()
    protected = protected_commas(text)
    cursor = 0
    for sent in doc.sents:
        start, end = sent.start_char, sent.end_char
        if not cursor <= start < end <= len(text) or text[cursor:start].strip():
            raise ValueError("PARSER_SENTENCE_ALIGNMENT_MISMATCH")
        cursor = end
        tokens = [t for t in sent if not t.is_space]
        ids = {t.i: i for i, t in enumerate(tokens, 1)}
        tree = []
        for t in tokens:
            head = 0 if t.head.i == t.i else ids.get(t.head.i)
            if head is None:
                raise ValueError("PARSER_HEAD_OUTSIDE_SENTENCE")
            tree.append({"id": ids[t.i], "start": t.idx-start,
                         "end": t.idx-start+len(t.text), "text": t.text,
                         "head": head, "deprel": t.dep_.lower(), "upos": t.pos_})
        result = coordination_boundaries(text[start:end], tree)
        proposals.update(start+i for i in result["candidate_offsets"])
    if text[cursor:].strip():
        raise ValueError("PARSER_SOURCE_NOT_EXHAUSTED")
    return {"candidate_offsets": sorted(proposals-protected),
            "protected_offsets": sorted(protected)}


def audit(manifest: Path, nlp) -> dict:
    data = manifest.read_bytes()
    rows = [json.loads(l) for l in data.decode("utf-8").splitlines() if l.strip()]
    if not rows or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("INVALID_MANIFEST_INVENTORY")
    results = []
    for row in rows:
        try:
            r = propose(row["text"], nlp(row["text"]))
        except ValueError as exc:
            results.append({"id": row["id"], "hash": row["hash"],
                            "status": "unresolved", "reason": str(exc)})
        else:
            results.append({"id": row["id"], "hash": row["hash"],
                            "status": "parsed", **r})
    return {"manifest_sha256": hashlib.sha256(data).hexdigest(),
            "chunk_count": len(rows),
            "parsed_chunks": sum(r["status"] == "parsed" for r in results),
            "candidate_chunks": sum(bool(r.get("candidate_offsets")) for r in results),
            "candidate_count": sum(len(r.get("candidate_offsets", [])) for r in results),
            "rows": results}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest", type=Path)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--model-sha256", required=True)
    p.add_argument("--spacy-version", required=True)
    p.add_argument("--model-version", required=True)
    a = p.parse_args()
    if a.model.is_symlink():
        raise ValueError("MODEL_SYMLINK_FORBIDDEN")
    root = a.model.resolve(strict=True)
    if model_digest(root) != a.model_sha256:
        raise ValueError("MODEL_DIGEST_MISMATCH")
    import spacy

    if spacy.__version__ != a.spacy_version:
        raise ValueError("SPACY_VERSION_MISMATCH")
    spacy.require_cpu()
    nlp = spacy.load(root, exclude=["ner", "lemmatizer"])
    if (nlp.meta.get("lang") != "ru" or nlp.meta.get("version") != a.model_version
            or not nlp.has_pipe("parser")):
        raise ValueError("RUSSIAN_PARSER_IDENTITY_MISMATCH")
    result = audit(a.manifest, nlp)
    if model_digest(root) != a.model_sha256:
        raise ValueError("MODEL_CHANGED")
    result["parser"] = {"spacy": a.spacy_version, "model": nlp.meta.get("name"),
                        "version": a.model_version, "sha256": a.model_sha256}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
