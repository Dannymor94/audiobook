"""Synthetic checks for the read-only Russian stress dictionary audit."""
from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_ruaccent_dictionary.py"
spec = importlib.util.spec_from_file_location("audit_ruaccent_dictionary", SCRIPT)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_lexical_categories_do_not_claim_correct_stress():
    accents = {"музыка": "м+узыка", "замок": "з+амок"}
    homographs = {"замок": ["з+амок", "зам+ок"]}
    yo = {"все": "всё"}
    assert mod.category("музыка", accents, homographs, yo) == "dictionary_exact"
    assert mod.category("замок", accents, homographs, yo) == "homograph"
    assert mod.category("все", accents, homographs, yo) == "yo_needs_context"
    assert mod.category("наследие", accents, homographs, yo) == "not_in_dictionary"


def test_word_count_and_multisyllabic_split():
    from collections import Counter
    counts = Counter(mod.words_in("МУ́ЗЫКА и МУЗЫКА, замок — замок, всё."))
    # Standalone U+0301 is not a word character; letters remain intact.
    result, private = mod.audit(counts, {"музыка": "м+узыка"}, {"замок": ["з+амок", "зам+ок"]}, {})
    assert result["total_word_tokens"] == 7
    assert result["tokens_by_category"]["dictionary_exact"] == 2
    assert result["tokens_by_category"]["homograph"] == 2
    assert result["multisyllabic_tokens"] == 4
    assert any(r["wordform"] == "музыка" and r["tokens"] == 2 for r in private)


def test_cli_is_local_and_fail_closed(tmp_path):
    d = tmp_path / "dictionary"
    d.mkdir()
    texts = tmp_path / "text"
    texts.mkdir()
    (texts / "08_test.norm.txt").write_text("Музыка звучит уверенно. " * 4, encoding="utf-8")
    for filename, data in {
        "accents.json.gz": {"музыка": "м+узыка"},
        "omographs.json.gz": {"замок": ["з+амок", "зам+ок"]},
        "yo_words.json.gz": {"все": "всё"},
    }.items():
        with gzip.open(d / filename, "wt", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    out = tmp_path / "out"
    args = [sys.executable, str(SCRIPT), "--dictionary", str(d),
            "--text-dir", str(texts), "--section", "08_test", "--out", str(out)]
    ok = subprocess.run(args, text=True, capture_output=True, check=True)
    report = json.loads((out / "counts.json").read_text(encoding="utf-8"))
    assert report["sections_scanned"] == 1
    assert report["tokens_by_category"]["dictionary_exact"] == 4
    assert "музыка" not in ok.stdout.lower()
    assert (out / "wordforms_PRIVATE.tsv").is_file()
    (d / "accents.json.gz").unlink()
    blocked = subprocess.run(args, text=True, capture_output=True)
    assert blocked.returncode != 0
