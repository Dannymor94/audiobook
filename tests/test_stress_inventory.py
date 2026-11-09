"""Layer-1 tests for stress_inventory — no models, no network, tmp_path only."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_env(tmp_path: Path, norm_texts: dict[str, str],
              omographs: dict | None = None,
              pronounce: str = "{}",
              watch: str = "{}",
              verified: str | None = None) -> tuple[Path, dict]:
    """Set up a minimal TEXT/MODELS/OUT tree under tmp_path, return (root, config)."""
    text_dir = tmp_path / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    models_dir = tmp_path / "models" / "dictionary"
    models_dir.mkdir(parents=True, exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, content in norm_texts.items():
        (text_dir / name).write_text(content, encoding="utf-8")

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
    """Patch paths and run stress_inventory.run; return (risk_lines, occ_lines)."""
    import audiobook.paths as apaths
    orig_text = apaths.TEXT
    orig_models = apaths.MODELS
    orig_out = apaths.OUT

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


# ── tests ─────────────────────────────────────────────────────────────────────

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
    # don't create stress_verified.yaml
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
    # "Иван" at position wi>0 in sentence
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
    # This test passes if _run completes without FileNotFoundError for synthesis weights.
    rc, risk, _ = _run(tmp_path, {
        "01_ch.norm.txt": "Простой текст для проверки замок.",
    })
    assert rc == 0
    assert len(risk) >= 1  # at least header


def test_risk_tsv_deterministic(tmp_path):
    """Two identical runs produce byte-identical risk.tsv."""
    import audiobook.paths as apaths
    orig_text, orig_models, orig_out = apaths.TEXT, apaths.MODELS, apaths.OUT

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

    r1 = (tmp_path / "run1" / "out" / "stress" / "risk.tsv").read_text(encoding="utf-8")
    r2 = (tmp_path / "run2" / "out" / "stress" / "risk.tsv").read_text(encoding="utf-8")
    assert r1 == r2
