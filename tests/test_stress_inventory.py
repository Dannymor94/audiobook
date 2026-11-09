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
