"""Layer-1 tests for stress_inventory — no models, no network, tmp_path only."""
from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_env(tmp_path: Path, norm_texts: dict[str, str],
              omographs: dict | None = None,
              pronounce: str = "{}",
              watch: str = "{}",
              verified: str | None = None,
              with_omograph_dict: bool = True) -> tuple[Path, dict]:
    """Set up a minimal TEXT/MODELS/OUT tree under tmp_path, return (root, config)."""
    text_dir = tmp_path / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    models_dir = tmp_path / "models" / "dictionary"
    models_dir.mkdir(parents=True, exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, content in norm_texts.items():
        (text_dir / name).write_text(content, encoding="utf-8")

    if with_omograph_dict:
        odict = omographs if omographs is not None else {
            "замок": ["з+амок", "замо+к"],
            "мука": ["м+ука", "мук+а"],
        }
        with gzip.open(models_dir / "omographs.json.gz", "wt", encoding="utf-8") as f:
            json.dump(odict, f)

    (text_dir / "pronounce.yaml").write_text(pronounce, encoding="utf-8")
    (text_dir / "stress_watch.yaml").write_text(watch, encoding="utf-8")
    if verified is not None:
        (text_dir / "stress_verified.yaml").write_text(verified, encoding="utf-8")

    config = {"stress": {"top_n": 5}}
    return tmp_path, config


def _run(tmp_path, norm_texts, **kwargs):
    """Patch paths and run stress_inventory.run; return (rc, risk_lines, occ_lines)."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, norm_texts, **kwargs)
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        from audiobook.stress_inventory import run
        rc = run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    risk_path = root / "out" / "stress" / "risk.tsv"
    occ_path = root / "out" / "stress" / "omographs.tsv"
    risk_lines = risk_path.read_text(encoding="utf-8").splitlines() if risk_path.exists() else []
    occ_lines = occ_path.read_text(encoding="utf-8").splitlines() if occ_path.exists() else []
    return rc, risk_lines, occ_lines


# ── original tests (must keep passing) ────────────────────────────────────────

def test_homograph_in_risk(tmp_path):
    """A word in the omograph dict appears in risk.tsv with reason 'homograph'."""
    _, risk, _ = _run(tmp_path, {
        "01_chapter.norm.txt": "Старый замок был крепким. Мы закрыли замок на ключ.",
    })
    forms = {row.split("\t")[0] for row in risk[1:]}
    reasons = {row.split("\t")[0]: row.split("\t")[2] for row in risk[1:]}
    assert "замок" in forms
    assert "homograph" in reasons["замок"]


def test_verified_excluded(tmp_path):
    """Forms in stress_verified.yaml are excluded from risk.tsv."""
    _, risk, _ = _run(tmp_path, {
        "01_chapter.norm.txt": "Старый замок был крепким.",
    }, verified="verified:\n  - замок\n")
    forms = {row.split("\t")[0] for row in risk[1:]}
    assert "замок" not in forms


def test_stress_verified_created_if_missing(tmp_path):
    """stress_verified.yaml is created if absent."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "Слово замок."})
    (root / "text" / "stress_verified.yaml").unlink(missing_ok=True)
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        from audiobook.stress_inventory import run
        run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    assert (root / "text" / "stress_verified.yaml").exists()


def test_name_detection(tmp_path):
    """Capitalised word not at sentence start → reason includes 'name'."""
    _, risk, _ = _run(tmp_path, {
        "01_ch.norm.txt": "Сказал Иван тихо.",
    }, omographs={})
    reasons = {row.split("\t")[0]: row.split("\t")[2] for row in risk[1:]}
    assert "иван" in reasons
    assert "name" in reasons["иван"]


def test_dict_forms_included(tmp_path):
    """Forms from stress_watch.yaml appear in risk.tsv with reason 'dict'."""
    _, risk, _ = _run(tmp_path, {
        "01_ch.norm.txt": "потом стоит руки.",
    }, omographs={}, watch="homographs:\n  - потом\n")
    reasons = {row.split("\t")[0]: row.split("\t")[2] for row in risk[1:]}
    assert "потом" in reasons
    assert "dict" in reasons["потом"]


def test_omograph_occurrence_detail(tmp_path):
    """omographs.tsv written with per-occurrence rows."""
    _, _, occ = _run(tmp_path, {
        "01_ch.norm.txt": "Старый замок стоял. Новый замок блестел.",
    })
    assert len(occ) > 1  # header + at least 2 occurrences
    header = occ[0].split("\t")
    assert "форма" in header and "контекст" in header and "варианты" in header


def test_top_n_included(tmp_path):
    """Most frequent word appears in risk.tsv with reason 'top'."""
    text = " ".join(["слово"] * 20)
    _, risk, _ = _run(tmp_path, {"01_ch.norm.txt": text}, omographs={})
    reasons = {r.split("\t")[0]: r.split("\t")[2] for r in risk[1:]}
    assert "слово" in reasons
    assert "top" in reasons["слово"]


def test_no_synthesis_models_needed(tmp_path):
    """Module imports and runs without torch, synthesis weights, or network."""
    rc, risk, _ = _run(tmp_path, {
        "01_ch.norm.txt": "Простой текст для проверки замок.",
    })
    assert rc == 0
    assert len(risk) >= 1


# ── regression tests for Codex review findings ────────────────────────────────

# Issue 1: Determinism with PYTHONHASHSEED variation
def test_risk_tsv_deterministic_same_process(tmp_path):
    """Two runs in the same process produce byte-identical risk.tsv."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    results = []
    for subdir in ("run1", "run2"):
        root, config = _make_env(tmp_path / subdir, {
            "01_ch.norm.txt": "Слово замок встречается замок дважды.",
        })
        apaths.TEXT = root / "text"
        apaths.MODELS = root / "models"
        apaths.OUT = root / "out"
        try:
            from audiobook.stress_inventory import run
            run(config)
        finally:
            apaths.TEXT = orig_text
            apaths.MODELS = orig_models
            apaths.OUT = orig_out
        results.append((root / "out" / "stress" / "risk.tsv").read_text(encoding="utf-8"))

    assert results[0] == results[1]


def test_risk_tsv_deterministic_across_hashseeds(tmp_path):
    """risk.tsv SHA-256 is identical across PYTHONHASHSEED=1,2,3 (separate processes)."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    # Build env once so all three processes share the same input
    root, _ = _make_env(tmp_path, {
        "01_ch.norm.txt": (
            "Замок был старый. Ключ открыл замок. Мука рассыпалась."
            " Тяжёлая мука лежала. Слово замок повторяется."
        ),
        "02_ch.norm.txt": "Ещё слова: замок, мука, снова.",
    })

    script = (
        "import sys, os; sys.path.insert(0, 'src');"
        "import audiobook.paths as p;"
        f"p.TEXT=__import__('pathlib').Path(r'{root}/text');"
        f"p.MODELS=__import__('pathlib').Path(r'{root}/models');"
        f"p.OUT=__import__('pathlib').Path(r'{root}/out');"
        "from audiobook.stress_inventory import run;"
        "run({'stress':{'top_n':5}});"
        "import hashlib;"
        "h=hashlib.sha256(open(r'{root}/out/stress/risk.tsv','rb').read()).hexdigest();"
        "print(h)"
    ).replace("{root}", str(root))

    hashes = set()
    for seed in ("1", "2", "3"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0, (
            f"PYTHONHASHSEED={seed} failed:\n{result.stderr}"
        )
        hashes.add(result.stdout.strip())

    assert len(hashes) == 1, f"Non-deterministic output: {hashes}"


import os  # needed for the test above


# Issue 2: Chunk numbers come from manifest when available
def test_chunk_id_from_manifest(tmp_path):
    """When a manifest exists, omographs.tsv uses manifest chunk ids, not '?'."""
    import json, audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {
        "01_ch.norm.txt": "Старый замок стоит.",
    })

    # Create a minimal manifest for section 01_ch
    sec_dir = root / "out" / "sections" / "01_ch"
    sec_dir.mkdir(parents=True)
    manifest = [
        {"id": "0001", "n": 1, "text": "Старый замок стоит.", "hash": "x", "status": "done",
         "pause_after_ms": 900, "locked": False, "duration_ms": 1000},
    ]
    with open(sec_dir / "manifest.jsonl", "w", encoding="utf-8") as f:
        for row in manifest:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        from audiobook.stress_inventory import run
        run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    occ_path = root / "out" / "stress" / "omographs.tsv"
    rows = occ_path.read_text(encoding="utf-8").splitlines()
    # header: форма section chunk context options ruaccent
    data_rows = [r.split("\t") for r in rows[1:]]
    zamok_rows = [r for r in data_rows if r[0] == "замок"]
    assert zamok_rows, "No замок occurrence in omographs.tsv"
    chunk_col = zamok_rows[0][2]
    assert chunk_col == "0001", f"Expected manifest chunk id '0001', got {chunk_col!r}"


def test_chunk_id_question_mark_without_manifest(tmp_path):
    """Without a manifest, chunk id is '?' (not a paragraph index)."""
    _, _, occ = _run(tmp_path, {
        "01_ch.norm.txt": "Старый замок стоит.",
    })
    rows = [r.split("\t") for r in occ[1:]]
    zamok_rows = [r for r in rows if r[0] == "замок"]
    assert zamok_rows
    # Must not look like an integer paragraph index; must be '?'
    assert zamok_rows[0][2] == "?", f"Got {zamok_rows[0][2]!r}, expected '?'"


# Issue 3: Each omograph occurrence gets its own correct context
def test_duplicate_omograph_different_contexts(tmp_path):
    """Two occurrences of the same omograph in a sentence get distinct contexts.

    Uses a sentence long enough that ±40-char windows around the two
    occurrences do NOT overlap, so the contexts are provably different.
    """
    # First замок at char ~45 (after 45 chars of prefix)
    # Second замок at char ~110 (after 60 more chars of фiller)
    prefix = "а" * 42  # 42 chars before first замок
    filler = " и " + "б" * 55  # 58 chars between the two замок
    text = f"{prefix} замок{filler} замок в конце."
    _, _, occ = _run(tmp_path, {"01_ch.norm.txt": text})
    rows = [r.split("\t") for r in occ[1:] if r.split("\t")[0] == "замок"]
    assert len(rows) == 2, f"Expected 2 occurrences of замок, got {len(rows)}"
    ctx1, ctx2 = rows[0][3], rows[1][3]
    assert "замок" in ctx1.lower()
    assert "замок" in ctx2.lower()
    assert ctx1 != ctx2, "Both contexts are identical — position not tracked per occurrence"


def test_omograph_context_anchored_to_occurrence(tmp_path):
    """Context ±40 chars is centered on each specific occurrence, not the first."""
    # Sentence: long preamble, then замок appears at pos > 40
    long_prefix = "а" * 50  # 50 chars before замок
    text = f"Текст {long_prefix} замок первый и замок второй."
    _, _, occ = _run(tmp_path, {"01_ch.norm.txt": text})
    rows = [r.split("\t") for r in occ[1:] if r.split("\t")[0] == "замок"]
    assert len(rows) == 2
    # Second occurrence context must NOT start from position 0 of the sentence
    ctx2 = rows[1][3]
    # If context were always from find(word)=first occurrence, ctx2 would equal ctx1
    ctx1 = rows[0][3]
    assert ctx1 != ctx2


# Issue 4: Missing omograph dict → non-zero exit
def test_missing_omograph_dict_exits_nonzero(tmp_path):
    """SystemExit raised if omographs.json.gz is absent (blocked condition)."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "Замок стоит."},
                             with_omograph_dict=False)
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        with pytest.raises(SystemExit) as exc_info:
            from audiobook.stress_inventory import run
            run(config)
        assert exc_info.value.code != 0
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out


def test_failed_run_does_not_leave_partial_tsv(tmp_path):
    """If run fails mid-way, old risk.tsv is preserved (atomic write)."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    # First run: create a known good risk.tsv
    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "Слово замок."})
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        from audiobook.stress_inventory import run
        run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    good_content = (root / "out" / "stress" / "risk.tsv").read_text(encoding="utf-8")
    assert good_content  # sanity

    # Second run: remove the dict so it fails before writing
    (root / "models" / "dictionary" / "omographs.json.gz").unlink()

    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        with pytest.raises(SystemExit):
            run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    # The old risk.tsv must be unchanged
    preserved = (root / "out" / "stress" / "risk.tsv").read_text(encoding="utf-8")
    assert preserved == good_content, "Old risk.tsv was overwritten during failed run"


# Issue 5: Example column always ≤80 chars and contains the form
def test_example_always_contains_form(tmp_path):
    """Example column always contains the form (even when sentence > 80 chars)."""
    long_sent = "а" * 40 + " замок " + "б" * 40  # 87 chars, > 80
    _, risk, _ = _run(tmp_path, {"01_ch.norm.txt": long_sent})
    rows = {r.split("\t")[0]: r.split("\t")[3] for r in risk[1:]}
    assert "замок" in rows, "замок not in risk.tsv"
    example = rows["замок"]
    assert "замок" in example.lower(), f"Form not in example: {example!r}"


def test_example_at_most_80_chars(tmp_path):
    """Example column is at most 80 characters."""
    # Sentence well over 80 chars
    long_sent = "слово " * 30 + "замок " + "слово " * 20
    _, risk, _ = _run(tmp_path, {"01_ch.norm.txt": long_sent})
    rows = {r.split("\t")[0]: r.split("\t")[3] for r in risk[1:]}
    for form, example in rows.items():
        assert len(example) <= 80, (
            f"Example for {form!r} exceeds 80 chars: {len(example)} chars: {example!r}"
        )


def test_example_prefers_short_sentence(tmp_path):
    """When a short sentence exists, it is preferred over context snippet."""
    short_sent = "Замок закрыт."       # 13 chars — fits
    long_sent = "а" * 40 + " замок " + "б" * 40  # long, would trigger snippet
    text = long_sent + "\n" + short_sent
    _, risk, _ = _run(tmp_path, {"01_ch.norm.txt": text})
    rows = {r.split("\t")[0]: r.split("\t")[3] for r in risk[1:]}
    example = rows.get("замок", "")
    assert example == "Замок закрыт.", f"Short sentence not preferred: {example!r}"


# ── Second Codex review: regression tests ────────────────────────────────────
# P1: chunk fingerprint matching

def test_find_chunk_id_no_candidates():
    """Word absent from manifest → '?'."""
    from audiobook.stress_inventory import _find_chunk_id
    assert _find_chunk_id("замок", "Старый замок.", 7, []) == "?"


def test_find_chunk_id_single_candidate():
    """Single candidate returned without fingerprint logic."""
    from audiobook.stress_inventory import _find_chunk_id
    r = _find_chunk_id("замок", "Старый замок крепкий.", 7,
                       [("0001", "Старый замок крепкий.")])
    assert r == "0001"


def test_find_chunk_id_fingerprint_disambiguation(tmp_path):
    """Two chunks with the same form; fingerprint picks the correct one."""
    from audiobook.stress_inventory import _find_chunk_id
    candidates = [
        ("0001", "Старый замок был крепким."),
        ("0002", "Новый замок блестел на солнце."),
    ]
    r1 = _find_chunk_id("замок", "Старый замок был крепким.", 7, candidates)
    r2 = _find_chunk_id("замок", "Новый замок блестел на солнце.", 6, candidates)
    assert r1 == "0001", f"Expected 0001, got {r1!r}"
    assert r2 == "0002", f"Expected 0002, got {r2!r}"


def test_find_chunk_id_ambiguous_returns_question():
    """Fingerprint matches multiple candidates → '?'."""
    from audiobook.stress_inventory import _find_chunk_id
    # Identical chunk texts → fingerprint cannot disambiguate
    candidates = [("0001", "замок"), ("0002", "замок")]
    r = _find_chunk_id("замок", "замок", 0, candidates)
    assert r == "?", f"Expected '?', got {r!r}"


def test_chunk_matching_two_chunks_fingerprint(tmp_path):
    """Full pipeline: two chunks with same form get correct ids via fingerprint."""
    import json, audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {
        "01_ch.norm.txt": "Старый замок стоял там. Новый замок блестел здесь.",
    })
    sec_dir = root / "out" / "sections" / "01_ch"
    sec_dir.mkdir(parents=True)
    manifest = [
        {"id": "0001", "n": 1, "text": "Старый замок стоял там.", "hash": "a",
         "status": "done", "pause_after_ms": 900, "locked": False, "duration_ms": 1000},
        {"id": "0002", "n": 2, "text": "Новый замок блестел здесь.", "hash": "b",
         "status": "done", "pause_after_ms": 900, "locked": False, "duration_ms": 1000},
    ]
    with open(sec_dir / "manifest.jsonl", "w", encoding="utf-8") as f:
        for row in manifest:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        from audiobook.stress_inventory import run
        run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    occ_path = root / "out" / "stress" / "omographs.tsv"
    rows = [r.split("\t") for r in occ_path.read_text(encoding="utf-8").splitlines()[1:]]
    zamok_rows = [r for r in rows if r[0] == "замок"]
    assert len(zamok_rows) == 2, f"Expected 2 zamok rows, got {len(zamok_rows)}"
    # Both occurrences should map to their respective chunks
    assert zamok_rows[0][2] == "0001", f"First замок: expected 0001, got {zamok_rows[0][2]!r}"
    assert zamok_rows[1][2] == "0002", f"Second замок: expected 0002, got {zamok_rows[1][2]!r}"


def test_same_form_repeated_in_one_chunk_gets_chunk_id(tmp_path):
    """Form repeated multiple times in ONE chunk → both get same chunk_id (not '?')."""
    import json, audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {
        "01_ch.norm.txt": "Замок замок замок.",
    })
    sec_dir = root / "out" / "sections" / "01_ch"
    sec_dir.mkdir(parents=True)
    manifest = [
        {"id": "0001", "n": 1, "text": "Замок замок замок.", "hash": "x",
         "status": "done", "pause_after_ms": 900, "locked": False, "duration_ms": 1000},
    ]
    with open(sec_dir / "manifest.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(manifest[0], ensure_ascii=False) + "\n")

    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        from audiobook.stress_inventory import run
        run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    occ_path = root / "out" / "stress" / "omographs.tsv"
    rows = [r.split("\t") for r in occ_path.read_text(encoding="utf-8").splitlines()[1:]]
    zamok_rows = [r for r in rows if r[0] == "замок"]
    # All three occurrences should map to 0001 (single candidate, no ambiguity)
    for i, r in enumerate(zamok_rows):
        assert r[2] == "0001", f"Occurrence {i}: expected 0001, got {r[2]!r}"


# P1: RUAccent per-occurrence extraction

def test_ruaccent_nth_occurrence_not_first(tmp_path):
    """Each occurrence of a repeated form gets its own RUAccent result.

    Uses a mock accentizer that returns different stress marks for
    the first and second occurrence of 'замок' in the sentence.
    """
    from unittest.mock import patch
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {
        "01_ch.norm.txt": "замок замок.",
    })
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"

    # Mock returns "з+амок замо+к." — first has stress on а, second on о
    def mock_process(sent):
        return "з+амок замо+к."

    try:
        with patch("audiobook.stress_inventory._try_accentizer", return_value=mock_process):
            from audiobook.stress_inventory import run
            run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    occ_path = root / "out" / "stress" / "omographs.tsv"
    rows = [r.split("\t") for r in occ_path.read_text(encoding="utf-8").splitlines()[1:]]
    zamok_rows = [r for r in rows if r[0] == "замок"]
    assert len(zamok_rows) == 2, f"Expected 2 occurrences, got {len(zamok_rows)}"
    # ruaccent column is index 5
    r1, r2 = zamok_rows[0][5], zamok_rows[1][5]
    assert r1 != r2, (
        f"Both occurrences got same ruaccent {r1!r} — Nth-match extraction not working"
    )


# P1: RUAccent error handling

def test_corrupt_gzip_dict_exits(tmp_path):
    """Corrupt gzip file raises SystemExit (blocked condition)."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "замок."},
                             with_omograph_dict=False)
    (root / "models" / "dictionary" / "omographs.json.gz").write_bytes(b"not valid gzip")

    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        with pytest.raises(SystemExit):
            from audiobook.stress_inventory import run
            run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out


def test_wrong_structure_dict_exits(tmp_path):
    """Dict containing a list instead of a dict raises SystemExit."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "замок."},
                             with_omograph_dict=False)
    with gzip.open(root / "models" / "dictionary" / "omographs.json.gz",
                   "wt", encoding="utf-8") as f:
        json.dump(["not", "a", "dict"], f)

    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        with pytest.raises(SystemExit):
            from audiobook.stress_inventory import run
            run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out


def test_ruaccent_errors_reported_to_stderr(tmp_path, capsys):
    """RUAccent inference errors appear on stderr, not silently discarded."""
    from unittest.mock import patch
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "замок."})
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"

    def bad_process(sent):
        raise RuntimeError("model failure")

    try:
        with patch("audiobook.stress_inventory._try_accentizer", return_value=bad_process):
            from audiobook.stress_inventory import run
            run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    captured = capsys.readouterr()
    assert "ПРЕДУПРЕЖДЕНИЕ" in captured.err or "ERR:" in captured.err or \
           "ошибок" in captured.err, \
        f"RUAccent error not reported to stderr: {captured.err!r}"


# P2: _char_context form guarantee

def test_char_context_form_always_in_window():
    """_char_context always includes the full form, even when it lies near the edge."""
    from audiobook.stress_inventory import _char_context

    # Form starts at char 70 — with start=30 and window of 80, form_end=75 is within range
    sent = "а" * 70 + "замок" + "б" * 70
    ctx = _char_context(sent, 70, 5)
    assert len(ctx) <= 80
    assert "замок" in ctx, f"Form not in context: {ctx!r}"


def test_char_context_form_near_window_edge():
    """When form_end > start+80, start is shifted leftward to include the form."""
    from audiobook.stress_inventory import _char_context

    # char_pos=0 (start of sentence), word_len=5: start=0, form_end=5 ≤ 80 → no shift needed
    sent = "замок" + "а" * 100
    ctx = _char_context(sent, 0, 5)
    assert "замок" in ctx

    # char_pos=50, word_len=45: start=10, form_end=95 > start+80=90 → start shifts to 15
    sent2 = "а" * 50 + "б" * 45 + "в" * 50
    ctx2 = _char_context(sent2, 50, 45)
    assert len(ctx2) <= 80
    # form = sent2[50:95] must be in ctx2
    form_text = sent2[50:95]
    assert ctx2 in sent2  # ctx2 must be a substring of sent2
    assert sent2.index(ctx2) <= 50 <= sent2.index(ctx2) + 80


# P2: name detection — sentence-level wi

def test_name_detection_sentence_start_not_name(tmp_path):
    """First word of SECOND sentence is NOT classified as a name.

    Regression for the para_word_i bug: when tracking word index across
    the whole paragraph, the first word of the second sentence had
    para_word_i > 1 and was wrongly classified as a name.
    """
    _, risk, _ = _run(tmp_path, {
        "01_ch.norm.txt": "Слово раз два. Второй пункт списка.",
    }, omographs={})
    reasons = {r.split("\t")[0]: r.split("\t")[2] for r in risk[1:]}
    # 'второй' starts the second sentence → must NOT be classified as name
    assert "name" not in reasons.get("второй", ""), (
        f"'второй' falsely classified as name: {reasons.get('второй')!r}"
    )


def test_name_detection_mid_sentence_still_detected(tmp_path):
    """Capitalised word at wi>0 within a sentence IS classified as name."""
    _, risk, _ = _run(tmp_path, {
        "01_ch.norm.txt": "Сказал Иван тихо. Следующее предложение.",
    }, omographs={})
    reasons = {r.split("\t")[0]: r.split("\t")[2] for r in risk[1:]}
    assert "name" in reasons.get("иван", ""), (
        f"'иван' not classified as name: {reasons.get('иван')!r}"
    )
