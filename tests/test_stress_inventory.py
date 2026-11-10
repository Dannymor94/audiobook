"""Layer-1 tests for stress_inventory — no models, no network, tmp_path only.

Base from port-validated-settings + 14 (second review) = 33 tests now,
iteration-3 additions = 42, iteration-4 additions bring the total to 52,
iteration-5 additions bring the total to 57; T15-6A adds 3 more (60).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from unittest.mock import patch


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_env(tmp_path: Path, norm_texts: dict[str, str],
              omographs: dict | None = None,
              pronounce: str = "{}",
              watch: str = "{}",
              verified: str | None = None,
              with_omograph_dict: bool = True,
              manifests: dict[str, list[dict]] | None = None,
              ) -> tuple[Path, dict]:
    """Set up a minimal TEXT/MODELS/OUT tree under tmp_path, return (root, config).

    ``manifests`` maps section_name → list of manifest row dicts.
    If not given, a single-chunk manifest is auto-created for every norm_text.
    """
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

    # Build manifest(s)
    if manifests is not None:
        for sec, rows in manifests.items():
            sec_dir = out_dir / "sections" / sec
            sec_dir.mkdir(parents=True, exist_ok=True)
            with open(sec_dir / "manifest.jsonl", "w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
    else:
        # Auto-create manifests: one chunk per non-empty paragraph (line) in norm_text.
        # This preserves paragraph structure so example/sentence detection works correctly.
        for name, content in norm_texts.items():
            sec = name.replace(".norm.txt", "")
            sec_dir = out_dir / "sections" / sec
            sec_dir.mkdir(parents=True, exist_ok=True)
            paras = [p.strip() for p in content.splitlines() if p.strip()]
            with open(sec_dir / "manifest.jsonl", "w", encoding="utf-8") as f:
                for i, para in enumerate(paras):
                    row = {"id": f"{i+1:04d}", "n": i + 1, "text": para, "hash": "x",
                           "seed": 1, "pause_after_ms": 900, "status": "done",
                           "locked": False, "duration_ms": None}
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

    config = {"stress": {"top_n": 5}}
    return tmp_path, config


def _run(tmp_path, norm_texts, **kwargs):
    """Patch paths and run stress_inventory.run; return (rc, risk_lines, occ_lines).

    _try_accentizer is patched to return None (no model weights in CI).
    Tests that need RUAccent behaviour mock it themselves via patch(...).
    """
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, norm_texts, **kwargs)
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        from audiobook.stress_inventory import run
        with patch("audiobook.stress_inventory._try_accentizer", return_value=None):
            rc = run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    inventory = root / "out" / "stress" / "inventory"
    risk_path = inventory / "risk.tsv"
    occ_path = inventory / "omographs.tsv"
    risk_lines = risk_path.read_text(encoding="utf-8").splitlines() if risk_path.exists() else []
    occ_lines = occ_path.read_text(encoding="utf-8").splitlines() if occ_path.exists() else []
    return rc, risk_lines, occ_lines


# ── STOP-GATE 0: manifest structure and token match ───────────────────────────

def test_stopgate0_field_names():
    """manifest.jsonl auto-created by _make_env has the required fields."""
    import tempfile, json as _json
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        root, _ = _make_env(tmp, {"01_ch.norm.txt": "замок стоит."})
        mpath = root / "out" / "sections" / "01_ch" / "manifest.jsonl"
        row = _json.loads(mpath.read_text(encoding="utf-8"))
        assert "id" in row and "text" in row and "hash" in row
        assert isinstance(row["text"], str)


def test_stopgate0_tokens_match():
    """Manifest text tokens == norm.txt tokens (pre-condition for all runs)."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT
    import re
    WORD = re.compile(r"[а-яёА-ЯЁ]+")
    def toks(t): return [w.lower().replace("ё","е") for w in WORD.findall(t)]
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            root, _ = _make_env(tmp, {"01_ch.norm.txt": "Замок стоит и мука готова."})
            norm = (root / "text" / "01_ch.norm.txt").read_text(encoding="utf-8")
            import json as _json
            mpath = root / "out" / "sections" / "01_ch" / "manifest.jsonl"
            row = _json.loads(mpath.read_text(encoding="utf-8"))
            assert toks(norm) == toks(row["text"])
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out


# ── chunk id via bisect ───────────────────────────────────────────────────────

def test_chunk_id_bisect_two_chunks(tmp_path):
    """Two chunks: each occurrence maps to the correct chunk_id via bisect."""
    _, _, occ = _run(tmp_path, {
        "01_ch.norm.txt": "Старый замок стоял там. Новый замок блестел здесь.",
    }, manifests={
        "01_ch": [
            {"id": "0001", "n": 1, "text": "Старый замок стоял там.", "hash": "a",
             "seed": 1, "pause_after_ms": 900, "status": "done", "locked": False, "duration_ms": None},
            {"id": "0002", "n": 2, "text": "Новый замок блестел здесь.", "hash": "b",
             "seed": 1, "pause_after_ms": 900, "status": "done", "locked": False, "duration_ms": None},
        ],
    })
    rows = [r.split("\t") for r in occ[1:] if r.split("\t")[0] == "замок"]
    assert len(rows) == 2, f"Expected 2 zamok rows, got {len(rows)}: {occ}"
    assert rows[0][2] == "0001", f"First замок: expected 0001, got {rows[0][2]!r}"
    assert rows[1][2] == "0002", f"Second замок: expected 0002, got {rows[1][2]!r}"


def test_chunk_id_no_question_mark_with_manifest(tmp_path):
    """'?' must NOT appear in chunk column when manifest is present."""
    _, _, occ = _run(tmp_path, {"01_ch.norm.txt": "Старый замок стоит."})
    rows = [r.split("\t") for r in occ[1:] if r.split("\t")[0] == "замок"]
    assert rows, "No замок rows"
    for r in rows:
        assert r[2] != "?", f"Got '?' in chunk column: {r}"
    assert rows[0][2] == "0001"


def test_chunk_id_same_form_in_one_chunk(tmp_path):
    """Form repeated multiple times in one chunk → all get same chunk_id."""
    _, _, occ = _run(tmp_path, {"01_ch.norm.txt": "Замок замок замок."})
    rows = [r.split("\t") for r in occ[1:] if r.split("\t")[0] == "замок"]
    assert len(rows) == 3
    assert all(r[2] == "0001" for r in rows)


# ── token mismatch → SystemExit ───────────────────────────────────────────────

def test_token_mismatch_exits(tmp_path):
    """If manifest text tokens differ from norm.txt, run raises SystemExit."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT
    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "замок стоит."},
                             manifests={"01_ch": [
                                 {"id": "0001", "n": 1, "text": "другое слово.",
                                  "hash": "x", "seed": 1, "pause_after_ms": 900,
                                  "status": "done", "locked": False, "duration_ms": None}
                             ]})
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


# ── RUAccent per-occurrence (positional) ──────────────────────────────────────

def test_ruaccent_nth_occurrence_not_first(tmp_path):
    """Each occurrence of a repeated form gets its own RUAccent result via positional match."""
    from unittest.mock import patch
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "замок замок."})
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"

    # First occurrence gets ударение на А, second на О
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

    inventory = root / "out" / "stress" / "inventory"
    rows = [r.split("\t") for r in (inventory / "omographs.tsv").read_text(encoding="utf-8").splitlines()[1:]]
    zamok_rows = [r for r in rows if r[0] == "замок"]
    assert len(zamok_rows) == 2
    r1, r2 = zamok_rows[0][5], zamok_rows[1][5]
    assert r1 != r2, f"Both got same ruaccent: {r1!r}"


def test_ruaccent_difflib_fallback(tmp_path):
    """When tokens diverge, SequenceMatcher aligns equal blocks correctly."""
    from audiobook.stress_inventory import _ruaccent_resolve
    # Perfect match case
    stressed, status = _ruaccent_resolve("замок", 0, "старый замок стоит", "ст+арый зам+ок сто+ит")
    assert status == "resolved"
    assert "+" in stressed

    # Second occurrence
    stressed2, status2 = _ruaccent_resolve("замок", 1, "замок замок", "зам+ок замо+к")
    assert status2 == "resolved"
    assert stressed2 != stressed  # different stress position


def test_ruaccent_no_stress_status(tmp_path):
    """When RUAccent output has no '+', status is unresolved/no_stress."""
    from audiobook.stress_inventory import _ruaccent_resolve
    stressed, status = _ruaccent_resolve("замок", 0, "старый замок", "старый замок")
    assert status == "unresolved/no_stress"


# ── RUAccent errors → SystemExit (not silenced) ───────────────────────────────

def test_ruaccent_inference_exception_is_fatal(tmp_path):
    """Exception from RUAccent inference raises SystemExit (not silenced to stderr)."""
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
        with pytest.raises(SystemExit):
            with patch("audiobook.stress_inventory._try_accentizer", return_value=bad_process):
                from audiobook.stress_inventory import run
                run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out


# ── summary.json ──────────────────────────────────────────────────────────────

def test_summary_json_written(tmp_path):
    """inventory/ contains summary.json with sha256 of risk.tsv and omographs.tsv."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT
    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "Замок стоит."})
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        from audiobook.stress_inventory import run
        with patch("audiobook.stress_inventory._try_accentizer", return_value=None):
            run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    summary_path = root / "out" / "stress" / "inventory" / "summary.json"
    assert summary_path.exists(), "summary.json not written"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["schema_version"] == 1
    assert "files" in summary
    assert "risk.tsv" in summary["files"]
    assert "omographs.tsv" in summary["files"]
    # Verify SHA-256 matches actual files
    inv = summary_path.parent
    for fname, info in summary["files"].items():
        actual = hashlib.sha256((inv / fname).read_bytes()).hexdigest()
        assert actual == info["sha256"], f"SHA mismatch for {fname}"


def test_summary_json_counters(tmp_path):
    """summary.json counters match the actual number of risk rows."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT
    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "Замок стоит."})
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        from audiobook.stress_inventory import run
        with patch("audiobook.stress_inventory._try_accentizer", return_value=None):
            run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    inv = root / "out" / "stress" / "inventory"
    summary = json.loads((inv / "summary.json").read_text(encoding="utf-8"))
    risk_lines = (inv / "risk.tsv").read_text(encoding="utf-8").splitlines()
    assert summary["files"]["risk.tsv"]["rows"] == len(risk_lines) - 1


# ── atomic publish: inventory/ location and structure ─────────────────────────

def test_output_in_inventory_subdir(tmp_path):
    """Results land in out/stress/inventory/, not directly in out/stress/."""
    _, risk, occ = _run(tmp_path, {"01_ch.norm.txt": "Замок стоит."})
    # _run reads from inventory/ — if files are there, this passes
    assert len(risk) >= 1
    assert risk[0] == "форма\tчастота\tпричина\tпример"


def test_failed_run_preserves_previous_inventory(tmp_path):
    """If run fails (missing dict), previous inventory/ is not destroyed."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    # First successful run
    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "Слово замок."})
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        from audiobook.stress_inventory import run
        with patch("audiobook.stress_inventory._try_accentizer", return_value=None):
            run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    inv = root / "out" / "stress" / "inventory"
    good = (inv / "risk.tsv").read_text(encoding="utf-8")
    good_summary = (inv / "summary.json").read_text(encoding="utf-8")

    # Second run: remove dict → SystemExit before publish
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

    # Previous inventory/ must be untouched
    assert (inv / "risk.tsv").read_text(encoding="utf-8") == good
    assert (inv / "summary.json").read_text(encoding="utf-8") == good_summary


def test_stale_tmp_cleaned_on_start(tmp_path):
    """Stale inventory.tmp/ from a previous interrupted run is removed at start."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT
    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "Замок стоит."})
    # Pre-create stale tmp
    stale = root / "out" / "stress" / "inventory.tmp"
    stale.mkdir(parents=True)
    (stale / "stale_file.txt").write_text("stale", encoding="utf-8")

    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        from audiobook.stress_inventory import run
        with patch("audiobook.stress_inventory._try_accentizer", return_value=None):
            run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    assert not stale.exists(), "Stale inventory.tmp/ not cleaned"
    assert (root / "out" / "stress" / "inventory" / "risk.tsv").exists()


# ── _char_context guarantees ──────────────────────────────────────────────────

def test_char_context_form_always_in_window():
    """_char_context always contains the full form (≤80 chars)."""
    from audiobook.stress_inventory import _char_context
    text = "а" * 70 + "замок" + "б" * 70
    ctx = _char_context(text, 70, 5)
    assert len(ctx) <= 80
    assert "замок" in ctx


def test_char_context_form_near_right_edge():
    """When form_end > start+80, start is shifted to include full form."""
    from audiobook.stress_inventory import _char_context
    # word at char_pos=50, word_len=45 → form_end=95, start=10 → 10+80=90 < 95
    text = "а" * 50 + "б" * 45 + "в" * 50
    ctx = _char_context(text, 50, 45)
    assert len(ctx) <= 80
    form_in_ctx = "б" * 45 in ctx or ctx.endswith("б" * (95 - len(text) + len(ctx)))
    # The form starts at 50 and ends at 95; ctx must cover [50..95]
    abs_start = text.index(ctx)
    assert abs_start <= 50
    assert abs_start + len(ctx) >= 95


# ── name detection (sentence-level, initials-aware) ───────────────────────────

def test_name_sentence_start_not_name(tmp_path):
    """First word of SECOND sentence is NOT classified as name."""
    _, risk, _ = _run(tmp_path, {
        "01_ch.norm.txt": "Слово раз два. Второй пункт списка.",
    }, omographs={})
    reasons = {r.split("\t")[0]: r.split("\t")[2] for r in risk[1:]}
    assert "name" not in reasons.get("второй", ""), (
        f"'второй' falsely classified as name: {reasons.get('второй')!r}"
    )


def test_name_mid_sentence_detected(tmp_path):
    """Capitalised word at wi>0 within a sentence IS classified as name."""
    _, risk, _ = _run(tmp_path, {
        "01_ch.norm.txt": "Сказал Иван тихо. Следующее предложение.",
    }, omographs={})
    reasons = {r.split("\t")[0]: r.split("\t")[2] for r in risk[1:]}
    assert "name" in reasons.get("иван", ""), (
        f"'иван' not classified as name: {reasons.get('иван')!r}"
    )


def test_name_initials_no_false_boundary(tmp_path):
    """Initials (А.) don't split the sentence — word after initial not at wi=0."""
    _, risk, _ = _run(tmp_path, {
        "01_ch.norm.txt": "Встретил А. Иванова вчера.",
    }, omographs={})
    reasons = {r.split("\t")[0]: r.split("\t")[2] for r in risk[1:]}
    # 'иванова' is after the initial — must be classified as name
    assert "name" in reasons.get("иванова", ""), (
        f"'иванова' not classified as name after initial: {reasons.get('иванова')!r}"
    )


# ── dict error handling ───────────────────────────────────────────────────────

def test_missing_omograph_dict_exits(tmp_path):
    """SystemExit raised if omographs.json.gz is absent."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT
    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "Замок стоит."},
                             with_omograph_dict=False)
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


def test_corrupt_gzip_dict_exits(tmp_path):
    """Corrupt gzip file raises SystemExit."""
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


# ── original tests (preserved) ────────────────────────────────────────────────

def test_homograph_in_risk(tmp_path):
    """A word in the omograph dict appears in risk.tsv with reason 'homograph'."""
    _, risk, _ = _run(tmp_path, {
        "01_chapter.norm.txt": "Старый замок был крепким. Мы закрыли замок на ключ.",
    })
    reasons = {row.split("\t")[0]: row.split("\t")[2] for row in risk[1:]}
    assert "замок" in reasons
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
        with patch("audiobook.stress_inventory._try_accentizer", return_value=None):
            run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out
    assert (root / "text" / "stress_verified.yaml").exists()


def test_name_detection(tmp_path):
    """Capitalised word not at sentence start → reason includes 'name'."""
    _, risk, _ = _run(tmp_path, {"01_ch.norm.txt": "Сказал Иван тихо."}, omographs={})
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
    assert len(occ) > 1
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
    rc, risk, _ = _run(tmp_path, {"01_ch.norm.txt": "Простой текст для проверки замок."})
    assert rc == 0
    assert len(risk) >= 1


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
            with patch("audiobook.stress_inventory._try_accentizer", return_value=None):
                run(config)
        finally:
            apaths.TEXT = orig_text
            apaths.MODELS = orig_models
            apaths.OUT = orig_out
        results.append(
            (root / "out" / "stress" / "inventory" / "risk.tsv")
            .read_text(encoding="utf-8")
        )
    assert results[0] == results[1]


def test_risk_tsv_deterministic_across_hashseeds(tmp_path):
    """risk.tsv SHA-256 is identical across PYTHONHASHSEED=1,2,3."""
    root, _ = _make_env(tmp_path, {
        "01_ch.norm.txt": (
            "Замок был старый. Ключ открыл замок. Мука рассыпалась."
            " Тяжёлая мука лежала. Слово замок повторяется."
        ),
        "02_ch.norm.txt": "Ещё слова: замок, мука, снова.",
    })
    script = (
        "import sys; sys.path.insert(0, 'src');"
        "import audiobook.paths as p;"
        f"p.TEXT=__import__('pathlib').Path(r'{root}/text');"
        f"p.MODELS=__import__('pathlib').Path(r'{root}/models');"
        f"p.OUT=__import__('pathlib').Path(r'{root}/out');"
        "from unittest.mock import patch;"
        "from audiobook.stress_inventory import run;"
        "_p=patch('audiobook.stress_inventory._try_accentizer',return_value=None);_p.start();"
        "run({'stress':{'top_n':5}});_p.stop();"
        "import hashlib;"
        f"h=hashlib.sha256(open(r'{root}/out/stress/inventory/risk.tsv','rb').read()).hexdigest();"
        "print(h)"
    )
    hashes = set()
    for seed in ("1", "2", "3"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
            cwd=str(Path(__file__).parent.parent),
        )
        assert result.returncode == 0, f"PYTHONHASHSEED={seed}:\n{result.stderr}"
        # Last line is the sha256; earlier lines are inventory stats (gen_id differs by timestamp)
        hashes.add(result.stdout.strip().splitlines()[-1])
    assert len(hashes) == 1, f"Non-deterministic: {hashes}"


import os  # noqa: E402


def test_example_at_most_80_chars(tmp_path):
    """Example column is at most 80 characters."""
    long_sent = "слово " * 30 + "замок " + "слово " * 20
    _, risk, _ = _run(tmp_path, {"01_ch.norm.txt": long_sent})
    for r in risk[1:]:
        example = r.split("\t")[3]
        assert len(example) <= 80, f"Example >80: {len(example)}: {example!r}"


def test_example_prefers_short_sentence(tmp_path):
    """When a short sentence exists, it is preferred over context snippet."""
    short_sent = "Замок закрыт."
    long_sent = "а" * 40 + " замок " + "б" * 40
    # \n\n — different paragraphs, so the short sentence is its own sentence unit
    text = long_sent + "\n\n" + short_sent
    _, risk, _ = _run(tmp_path, {"01_ch.norm.txt": text})
    rows = {r.split("\t")[0]: r.split("\t")[3] for r in risk[1:]}
    assert rows.get("замок") == "Замок закрыт.", f"Short sentence not preferred: {rows.get('замок')!r}"


def test_duplicate_omograph_different_contexts(tmp_path):
    """Two occurrences of same omograph in a paragraph get distinct contexts."""
    prefix = "а" * 42
    filler = " и " + "б" * 55
    text = f"{prefix} замок{filler} замок в конце."
    _, _, occ = _run(tmp_path, {"01_ch.norm.txt": text})
    rows = [r.split("\t") for r in occ[1:] if r.split("\t")[0] == "замок"]
    assert len(rows) == 2
    assert "замок" in rows[0][3].lower()
    assert "замок" in rows[1][3].lower()
    assert rows[0][3] != rows[1][3]


def test_omograph_occurrence_detail_header(tmp_path):
    """omographs.tsv has the expected header including ruaccent_status column."""
    _, _, occ = _run(tmp_path, {"01_ch.norm.txt": "замок стоит."})
    header = occ[0].split("\t")
    assert header[-1] == "ruaccent_status", f"Last column: {header[-1]!r}"


# ── iteration-4 regression tests ──────────────────────────────────────────────

def test_identical_sentences_in_different_chunks(tmp_path):
    """Same sentence text in two different chunks → distinct chunk_ids (not both 0001)."""
    _, _, occ = _run(tmp_path, {
        "01_ch.norm.txt": "замок стоит.\n\nзамок стоит.",
    }, manifests={
        "01_ch": [
            {"id": "0001", "n": 1, "text": "замок стоит.", "hash": "a",
             "seed": 1, "pause_after_ms": 900, "status": "done", "locked": False, "duration_ms": None},
            {"id": "0002", "n": 2, "text": "замок стоит.", "hash": "b",
             "seed": 1, "pause_after_ms": 900, "status": "done", "locked": False, "duration_ms": None},
        ],
    })
    rows = [r.split("\t") for r in occ[1:] if r.split("\t")[0] == "замок"]
    assert len(rows) == 2, f"Expected 2 замок rows, got {len(rows)}"
    assert rows[0][2] == "0001", f"First: expected 0001, got {rows[0][2]!r}"
    assert rows[1][2] == "0002", f"Second: expected 0002, got {rows[1][2]!r}"


def test_late_paragraph_correct_chunk_id(tmp_path):
    """Form in a late paragraph (after long first paragraph) gets correct chunk_id."""
    first = "текст без омографов. " * 10  # ~210 chars
    second = "старый замок стоит."
    text = first.rstrip() + "\n\n" + second
    _, _, occ = _run(tmp_path, {"01_ch.norm.txt": text}, manifests={
        "01_ch": [
            {"id": "0001", "n": 1, "text": first.rstrip(), "hash": "a",
             "seed": 1, "pause_after_ms": 900, "status": "done", "locked": False, "duration_ms": None},
            {"id": "0002", "n": 2, "text": second, "hash": "b",
             "seed": 1, "pause_after_ms": 900, "status": "done", "locked": False, "duration_ms": None},
        ],
    })
    rows = [r.split("\t") for r in occ[1:] if r.split("\t")[0] == "замок"]
    assert rows, "No замок rows"
    assert rows[0][2] == "0002", f"Expected 0002, got {rows[0][2]!r}"
    assert "замок" in rows[0][3].lower(), f"Context missing form: {rows[0][3]!r}"


def test_intra_paragraph_chunks_joined_with_space(tmp_path):
    """Two chunks from the same paragraph are joined with space, not \\n\\n."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {
        "01_ch.norm.txt": "замок стоял. мука рассыпалась.",
    }, manifests={
        "01_ch": [
            # pause_after_ms=350 < 900 → same paragraph, space separator before next chunk
            {"id": "0001", "n": 1, "text": "замок стоял.", "hash": "a",
             "seed": 1, "pause_after_ms": 350, "status": "done", "locked": False, "duration_ms": None},
            {"id": "0002", "n": 2, "text": "мука рассыпалась.", "hash": "b",
             "seed": 1, "pause_after_ms": 900, "status": "done", "locked": False, "duration_ms": None},
        ],
    })
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        from audiobook.stress_inventory import _build_section_data
        full_text, starts, chunk_ids = _build_section_data("01_ch", paragraph_ms=900)
        assert "\n\n" not in full_text, f"Found \\n\\n in same-paragraph chunks: {full_text!r}"
        assert " " in full_text, f"No space between same-paragraph chunks: {full_text!r}"
        assert len(starts) == 2
        # Second chunk starts right after the space
        assert starts[1] == len("замок стоял.") + 1
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out


def test_ruaccent_init_error_is_fatal():
    """_try_accentizer: RuntimeError from _get_accentizer() → SystemExit."""
    import sys
    from types import ModuleType

    fake_accent = ModuleType("audiobook.accent")

    def bad_get_accentizer():
        raise RuntimeError("model corrupt")

    fake_accent._get_accentizer = bad_get_accentizer

    orig = sys.modules.get("audiobook.accent")
    sys.modules["audiobook.accent"] = fake_accent
    try:
        from audiobook.stress_inventory import _try_accentizer
        with pytest.raises(SystemExit):
            _try_accentizer()
    finally:
        if orig is None:
            sys.modules.pop("audiobook.accent", None)
        else:
            sys.modules["audiobook.accent"] = orig


def test_ruaccent_init_importerror_is_fatal():
    """_try_accentizer: ImportError from accent module → SystemExit."""
    import sys
    from types import ModuleType
    orig = sys.modules.get("audiobook.accent", "MISSING")
    sys.modules["audiobook.accent"] = None  # causes ImportError on import
    try:
        from audiobook.stress_inventory import _try_accentizer
        with pytest.raises(SystemExit):
            _try_accentizer()
    finally:
        if orig == "MISSING":
            sys.modules.pop("audiobook.accent", None)
        else:
            sys.modules["audiobook.accent"] = orig


def test_ruaccent_init_oserror_is_fatal():
    """_try_accentizer: OSError from _get_accentizer() → SystemExit."""
    import sys
    from types import ModuleType

    fake_accent = ModuleType("audiobook.accent")

    def bad_get_accentizer():
        raise OSError("device not found")

    fake_accent._get_accentizer = bad_get_accentizer
    orig = sys.modules.get("audiobook.accent")
    sys.modules["audiobook.accent"] = fake_accent
    try:
        from audiobook.stress_inventory import _try_accentizer
        with pytest.raises(SystemExit):
            _try_accentizer()
    finally:
        if orig is None:
            sys.modules.pop("audiobook.accent", None)
        else:
            sys.modules["audiobook.accent"] = orig


def test_ruaccent_init_filenotfound_is_fatal():
    """_try_accentizer: FileNotFoundError from _get_accentizer() → SystemExit."""
    import sys
    from types import ModuleType

    fake_accent = ModuleType("audiobook.accent")

    def bad_get_accentizer():
        raise FileNotFoundError("weights missing")

    fake_accent._get_accentizer = bad_get_accentizer
    orig = sys.modules.get("audiobook.accent")
    sys.modules["audiobook.accent"] = fake_accent
    try:
        from audiobook.stress_inventory import _try_accentizer
        with pytest.raises(SystemExit):
            _try_accentizer()
    finally:
        if orig is None:
            sys.modules.pop("audiobook.accent", None)
        else:
            sys.modules["audiobook.accent"] = orig


def test_ruaccent_init_failure_does_not_publish(tmp_path):
    """When RUAccent init fails, existing inventory is not overwritten."""
    import audiobook.paths as apaths
    from types import ModuleType
    from unittest.mock import patch

    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT
    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "Замок стоит."})
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"

    # Write a sentinel file into existing inventory/
    inventory_dir = root / "out" / "stress" / "inventory"
    inventory_dir.mkdir(parents=True)
    sentinel = inventory_dir / "risk.tsv"
    sentinel.write_text("sentinel", encoding="utf-8")

    fake_accent = ModuleType("audiobook.accent")

    def _bad_init():
        raise OSError("boom")

    fake_accent._get_accentizer = _bad_init

    orig_accent = sys.modules.get("audiobook.accent")
    sys.modules["audiobook.accent"] = fake_accent
    try:
        from audiobook.stress_inventory import run
        with pytest.raises(SystemExit):
            run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out
        if orig_accent is None:
            sys.modules.pop("audiobook.accent", None)
        else:
            sys.modules["audiobook.accent"] = orig_accent

    assert sentinel.read_text(encoding="utf-8") == "sentinel"


def test_wrong_dict_value_type_exits(tmp_path):
    """Dict entry where value is a string (not list[str]) raises SystemExit."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "замок."},
                             with_omograph_dict=False)
    with gzip.open(root / "models" / "dictionary" / "omographs.json.gz",
                   "wt", encoding="utf-8") as f:
        json.dump({"замок": "not_a_list"}, f)

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


def test_two_omographs_one_sentence_process_once(tmp_path):
    """Two different omographs in one sentence → process() called exactly once."""
    from unittest.mock import patch
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "замок и мука здесь."},
                             omographs={"замок": ["з+амок", "замо+к"],
                                        "мука": ["м+ука", "мук+а"]})
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"

    call_log: list[str] = []

    def counting_process(sent):
        call_log.append(sent)
        return "зам+ок и мук+а здесь."

    try:
        with patch("audiobook.stress_inventory._try_accentizer", return_value=counting_process):
            from audiobook.stress_inventory import run
            run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    assert len(call_log) == 1, f"process() called {len(call_log)} times, expected 1"


def test_yoye_conflict_distinct_stress(tmp_path):
    """'все' and 'всё' get different stress marks — no ё/е position confusion."""
    from unittest.mock import patch
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "знает все всё."},
                             omographs={"все": ["вс+е", "в+сё"],
                                        "всё": ["вс+ё", "в+сё"]})
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"

    def mock_process(sent):
        return "зна+ет вс+е вс+ё."

    try:
        with patch("audiobook.stress_inventory._try_accentizer", return_value=mock_process):
            from audiobook.stress_inventory import run
            run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    rows = [(r.split("\t")[0], r.split("\t")[5])
            for r in (root / "out" / "stress" / "inventory" / "omographs.tsv")
            .read_text(encoding="utf-8").splitlines()[1:]]
    vse = [stress for form, stress in rows if form == "все"]
    vsyo = [stress for form, stress in rows if form == "всё"]
    assert vse, "No rows for 'все'"
    assert vsyo, "No rows for 'всё'"
    assert vse[0] != vsyo[0], f"'все' and 'всё' got same stress: {vse[0]!r}"


def test_second_rename_failure_recovery(tmp_path):
    """After interrupted atomic publish (inventory/ missing, .old/ present), next run recovers."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "замок стоит."})
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"

    try:
        from audiobook.stress_inventory import run
        with patch("audiobook.stress_inventory._try_accentizer", return_value=None):
            # First successful run
            run(config)
            inv = root / "out" / "stress" / "inventory"
            good = (inv / "risk.tsv").read_text(encoding="utf-8")

            # Simulate interrupted atomic: inventory/ renamed to .old/, second rename failed
            inv.rename(inv.parent / "inventory.old")
            assert not inv.exists()
            assert (inv.parent / "inventory.old").exists()

            # Next run must recover .old/ and produce a valid report
            run(config)

        assert inv.exists(), "inventory/ not restored"
        assert (inv / "risk.tsv").exists()
        assert not (inv.parent / "inventory.old").exists(), ".old/ not cleaned up"
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out


def test_top_n_change_in_fingerprint(tmp_path):
    """Different top_n values are recorded in summary.json inputs."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, _ = _make_env(tmp_path, {"01_ch.norm.txt": "замок стоит."})
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"

    top_n_values = []
    try:
        from audiobook.stress_inventory import run
        with patch("audiobook.stress_inventory._try_accentizer", return_value=None):
            for n in (5, 10):
                run({"stress": {"top_n": n}})
                s = json.loads((root / "out" / "stress" / "inventory" / "summary.json")
                               .read_text(encoding="utf-8"))
                top_n_values.append(s["inputs"]["top_n"])
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    assert top_n_values[0] == 5
    assert top_n_values[1] == 10


def test_all_manifests_missing_exits(tmp_path):
    """If no section has a manifest, run raises SystemExit."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "замок стоит."},
                             manifests={})  # explicitly no manifests
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


# ── iteration-5 integration tests ─────────────────────────────────────────────

def test_exclude_yaml_removes_form(tmp_path):
    """Form in stress_inventory_exclude.yaml is absent from risk.tsv regardless of reason."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "замок замок замок замок замок."})
    # Write exclude yaml
    (root / "text" / "stress_inventory_exclude.yaml").write_text(
        "exclude:\n  - замок\n", encoding="utf-8"
    )
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        from audiobook.stress_inventory import run
        with patch("audiobook.stress_inventory._try_accentizer", return_value=None):
            run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    inv = root / "out" / "stress" / "inventory"
    forms = {r.split("\t")[0] for r in (inv / "risk.tsv").read_text(encoding="utf-8").splitlines()[1:]}
    assert "замок" not in forms, f"'замок' in risk.tsv despite being in exclude.yaml: {forms}"


def test_fingerprint_has_algo_version(tmp_path):
    """summary.json inputs.algo_version matches INVENTORY_ALGO_VERSION."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "Замок стоит."})
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        from audiobook.stress_inventory import run
        from audiobook.stress_fp import INVENTORY_ALGO_VERSION
        with patch("audiobook.stress_inventory._try_accentizer", return_value=None):
            run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    summary = json.loads(
        (root / "out" / "stress" / "inventory" / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["inputs"]["algo_version"] == INVENTORY_ALGO_VERSION
    assert summary["algo_version"] == INVENTORY_ALGO_VERSION


def test_gen_dir_created_with_current_json(tmp_path):
    """After publish, gen/<gen_id>/ exists and inventory/current.json points to it."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "Замок стоит."})
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        from audiobook.stress_inventory import run
        with patch("audiobook.stress_inventory._try_accentizer", return_value=None):
            run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    stress_dir = root / "out" / "stress"
    cur_path = stress_dir / "inventory" / "current.json"
    assert cur_path.exists(), "inventory/current.json not written"
    cur = json.loads(cur_path.read_text(encoding="utf-8"))
    gen_id = cur["gen_id"]
    gen_dir = stress_dir / "gen" / gen_id
    assert gen_dir.exists(), f"gen/{gen_id}/ not created"
    assert (gen_dir / "risk.tsv").exists()
    assert (gen_dir / "summary.json").exists()
    # SHA must match
    actual_sha = hashlib.sha256((gen_dir / "summary.json").read_bytes()).hexdigest()
    assert actual_sha == cur["summary_sha256"], "current.json SHA mismatch"

    # load_current must succeed without error
    from audiobook.stress_fp import load_current
    result = load_current(stress_dir)
    assert result is not None
    assert result["algo_version"] == 2

# ── T15-6B1: section exclusion allowlist ─────────────────────────────────────

def _make_env_with_skip(tmp_path, norm_texts, sections_yaml=None, manifests=None, **kwargs):
    """Like _make_env but writes custom sections: block into exclude.yaml."""
    root, config = _make_env(tmp_path, norm_texts, manifests=manifests, **kwargs)
    if sections_yaml is not None:
        exclude_p = root / "text" / "stress_inventory_exclude.yaml"
        # File may not exist yet (created lazily by _load_exclude_forms); write it
        base = "exclude: []\n"
        if exclude_p.exists():
            base = exclude_p.read_text(encoding="utf-8")
        exclude_p.write_text(base + sections_yaml, encoding="utf-8")
    return root, config


def _run_with_paths(root, config):
    """Call run() with patched paths and _try_accentizer; return rc."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    try:
        from audiobook.stress_inventory import run
        with patch("audiobook.stress_inventory._try_accentizer", return_value=None):
            return run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out


def test_section_allowlist_valid_skip(tmp_path):
    """Missing manifest + matching allowlist entry and token count → skip (rc=0)."""
    # 01_ch has manifest; 02_extra has no manifest but is allowlisted with tokens=1
    root, config = _make_env_with_skip(
        tmp_path,
        {"01_ch.norm.txt": "замок стоит.", "02_extra.norm.txt": "слово"},
        manifests={"01_ch": [
            {"id": "0001", "n": 1, "text": "замок стоит.", "hash": "x",
             "seed": 1, "pause_after_ms": 900, "status": "done",
             "locked": False, "duration_ms": None}
        ]},
        sections_yaml=(
            "\nsections:\n"
            "  - section: 02_extra\n"
            "    tokens: 1\n"
            "    reason: test\n"
        ),
        with_omograph_dict=True,
    )
    rc = _run_with_paths(root, config)
    assert rc == 0


def test_section_missing_manifest_no_allowlist_exits(tmp_path):
    """Missing manifest for a section not in allowlist → SystemExit."""
    root, config = _make_env(
        tmp_path,
        {"01_ch.norm.txt": "замок стоит.", "02_extra.norm.txt": "слово"},
        manifests={"01_ch": [
            {"id": "0001", "n": 1, "text": "замок стоит.", "hash": "x",
             "seed": 1, "pause_after_ms": 900, "status": "done",
             "locked": False, "duration_ms": None}
        ]},
    )
    with pytest.raises(SystemExit):
        _run_with_paths(root, config)


def test_section_allowlist_wrong_token_count_exits(tmp_path):
    """Allowlisted section with wrong token count → SystemExit."""
    root, config = _make_env_with_skip(
        tmp_path,
        {"01_ch.norm.txt": "замок стоит.", "02_extra.norm.txt": "слово"},
        manifests={"01_ch": [
            {"id": "0001", "n": 1, "text": "замок стоит.", "hash": "x",
             "seed": 1, "pause_after_ms": 900, "status": "done",
             "locked": False, "duration_ms": None}
        ]},
        sections_yaml=(
            "\nsections:\n"
            "  - section: 02_extra\n"
            "    tokens: 99\n"  # wrong — actual is 1
            "    reason: test\n"
        ),
    )
    with pytest.raises(SystemExit):
        _run_with_paths(root, config)


def test_section_allowlist_stale_has_manifest_exits(tmp_path):
    """Allowlisted section that now has a manifest → SystemExit (stale exclusion)."""
    # 02_extra is in allowlist but we also create a manifest for it
    root, config = _make_env_with_skip(
        tmp_path,
        {"01_ch.norm.txt": "замок стоит.", "02_extra.norm.txt": "слово"},
        manifests={
            "01_ch": [
                {"id": "0001", "n": 1, "text": "замок стоит.", "hash": "x",
                 "seed": 1, "pause_after_ms": 900, "status": "done",
                 "locked": False, "duration_ms": None}
            ],
            "02_extra": [
                {"id": "0001", "n": 1, "text": "слово", "hash": "x",
                 "seed": 1, "pause_after_ms": 900, "status": "done",
                 "locked": False, "duration_ms": None}
            ],
        },
        sections_yaml=(
            "\nsections:\n"
            "  - section: 02_extra\n"
            "    tokens: 1\n"
            "    reason: test\n"
        ),
    )
    with pytest.raises(SystemExit):
        _run_with_paths(root, config)


def test_zero_occurrences_exits(tmp_path):
    """Sections with manifests but no Cyrillic text → SystemExit."""
    root, config = _make_env(
        tmp_path,
        {"01_ch.norm.txt": "..."},  # no Cyrillic
        manifests={"01_ch": [
            {"id": "0001", "n": 1, "text": "...", "hash": "x",
             "seed": 1, "pause_after_ms": 900, "status": "done",
             "locked": False, "duration_ms": None}
        ]},
    )
    with pytest.raises(SystemExit):
        _run_with_paths(root, config)


def test_section_allowlist_failure_does_not_publish(tmp_path):
    """When section allowlist check fails, existing inventory is not overwritten."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

    # First: successful run with only 01_ch
    root, config = _make_env(tmp_path, {"01_ch.norm.txt": "замок стоит."})
    apaths.TEXT = root / "text"
    apaths.MODELS = root / "models"
    apaths.OUT = root / "out"
    inventory_dir = root / "out" / "stress" / "inventory"
    try:
        from audiobook.stress_inventory import run
        with patch("audiobook.stress_inventory._try_accentizer", return_value=None):
            run(config)
        sentinel = (inventory_dir / "risk.tsv").read_text(encoding="utf-8")

        # Add a second norm file without manifest or allowlist → fail
        (root / "text" / "03_new.norm.txt").write_text("слово", encoding="utf-8")
        with pytest.raises(SystemExit):
            with patch("audiobook.stress_inventory._try_accentizer", return_value=None):
                run(config)
    finally:
        apaths.TEXT = orig_text
        apaths.MODELS = orig_models
        apaths.OUT = orig_out

    assert (inventory_dir / "risk.tsv").read_text(encoding="utf-8") == sentinel

# ── T15-6B2: section counters and coverage ────────────────────────────────────

def _summary_for(root):
    """Read summary.json from out/stress/inventory/."""
    return json.loads(
        (root / "out" / "stress" / "inventory" / "summary.json")
        .read_text(encoding="utf-8")
    )


def test_section_counters_two_processed_one_excluded(tmp_path):
    """2 processed + 1 excluded → total=3, processed=2, excluded=1."""
    root, config = _make_env_with_skip(
        tmp_path,
        {
            "01_ch.norm.txt": "замок стоит.",
            "02_ch.norm.txt": "мука лежала.",
            "03_extra.norm.txt": "слово слово слово слово слово",  # 5 tokens, excluded
        },
        manifests={
            "01_ch": [{"id": "0001", "n": 1, "text": "замок стоит.", "hash": "x",
                        "seed": 1, "pause_after_ms": 900, "status": "done",
                        "locked": False, "duration_ms": None}],
            "02_ch": [{"id": "0001", "n": 1, "text": "мука лежала.", "hash": "x",
                        "seed": 1, "pause_after_ms": 900, "status": "done",
                        "locked": False, "duration_ms": None}],
        },
        sections_yaml=(
            "\nsections:\n"
            "  - section: 03_extra\n"
            "    tokens: 5\n"
            "    reason: test\n"
        ),
    )
    _run_with_paths(root, config)
    d = _summary_for(root)["diagnostics"]
    assert d["sections_total"] == 3
    assert d["sections_processed"] == 2
    assert d["sections_excluded"] == 1


def test_excluded_tokens_counted(tmp_path):
    """Excluded section with 5 tokens → excluded_tokens=5 in summary."""
    root, config = _make_env_with_skip(
        tmp_path,
        {
            "01_ch.norm.txt": "замок стоит.",
            "02_extra.norm.txt": "слово слово слово слово слово",
        },
        manifests={
            "01_ch": [{"id": "0001", "n": 1, "text": "замок стоит.", "hash": "x",
                        "seed": 1, "pause_after_ms": 900, "status": "done",
                        "locked": False, "duration_ms": None}],
        },
        sections_yaml=(
            "\nsections:\n"
            "  - section: 02_extra\n"
            "    tokens: 5\n"
            "    reason: test\n"
        ),
    )
    _run_with_paths(root, config)
    d = _summary_for(root)["diagnostics"]
    assert d["excluded_tokens"] == 5


def test_total_tokens_includes_excluded(tmp_path):
    """Coverage denominator (total_tokens) includes excluded section tokens."""
    # 01_ch: 2 tokens ("замок стоит"); 02_extra: 5 tokens (excluded)
    # total_tokens must be 2 + 5 = 7
    root, config = _make_env_with_skip(
        tmp_path,
        {
            "01_ch.norm.txt": "замок стоит.",
            "02_extra.norm.txt": "слово слово слово слово слово",
        },
        manifests={
            "01_ch": [{"id": "0001", "n": 1, "text": "замок стоит.", "hash": "x",
                        "seed": 1, "pause_after_ms": 900, "status": "done",
                        "locked": False, "duration_ms": None}],
        },
        sections_yaml=(
            "\nsections:\n"
            "  - section: 02_extra\n"
            "    tokens: 5\n"
            "    reason: test\n"
        ),
        omographs={},
    )
    _run_with_paths(root, config)
    s = _summary_for(root)
    assert s["counters"]["total_tokens"] == 7, s["counters"]["total_tokens"]


def test_excluded_section_no_risk_occurrences(tmp_path):
    """Excluded section's words do not appear in risk.tsv."""
    # 01_ch has "замок" (omograph). 02_extra has "замок замок" but is excluded.
    # Risk rows must come only from 01_ch; excluded words must not inflate freq.
    root, config = _make_env_with_skip(
        tmp_path,
        {
            "01_ch.norm.txt": "замок стоит.",
            "02_extra.norm.txt": "замок замок замок замок замок",
        },
        manifests={
            "01_ch": [{"id": "0001", "n": 1, "text": "замок стоит.", "hash": "x",
                        "seed": 1, "pause_after_ms": 900, "status": "done",
                        "locked": False, "duration_ms": None}],
        },
        sections_yaml=(
            "\nsections:\n"
            "  - section: 02_extra\n"
            "    tokens: 5\n"
            "    reason: test\n"
        ),
    )
    _run_with_paths(root, config)
    inv = root / "out" / "stress" / "inventory"
    risk = {r.split("\t")[0]: int(r.split("\t")[1])
            for r in (inv / "risk.tsv").read_text(encoding="utf-8").splitlines()[1:]}
    # "замок" frequency must be 1 (only from 01_ch), not 6
    assert risk.get("замок", 0) == 1


def test_zero_excluded_sections_unchanged(tmp_path):
    """When no sections are excluded, sections_excluded=0 and excluded_tokens=0."""
    _, risk, _ = _run(tmp_path, {"01_ch.norm.txt": "замок стоит."})
    # Can't get summary from _run directly; use _run_with_paths
    root, config = _make_env(tmp_path / "s2", {"01_ch.norm.txt": "замок стоит."})
    _run_with_paths(root, config)
    d = _summary_for(root)["diagnostics"]
    assert d["sections_excluded"] == 0
    assert d["excluded_tokens"] == 0
    assert d["sections_processed"] == d["sections_total"]
