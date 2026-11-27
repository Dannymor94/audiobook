"""Offline contract tests for the manually admitted Colab CPU notebook."""
import ast
import json
from pathlib import Path

import pytest


def notebook():
    path = Path(__file__).resolve().parents[1] / "cloud" / "colab" / "public_cpu_pilot.ipynb"
    return json.loads(path.read_text(encoding="utf-8"))


def test_colab_cpu_notebook_is_unexecuted_and_compiles():
    nb = notebook()
    assert nb["nbformat"] == 4
    cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert len(cells) == 3
    for cell in cells:
        assert cell["execution_count"] is None
        assert cell["outputs"] == []
        source = "".join(cell["source"])
        compile(source, "colab-cell", "exec")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                if any(isinstance(t, ast.Name) and t.id in {"download", "pilot"} for t in node.targets):
                    compile(node.value.value, "colab-child", "exec")


def test_default_admission_fails_before_download_or_model_import():
    source = "".join(notebook()["cells"][1]["source"])
    scope = {}
    with pytest.raises(RuntimeError, match="MANUAL_CPU_ADMISSION_REQUIRED"):
        exec(compile(source, "colab-admission", "exec"), scope)
    assert "ROOT" not in scope
    assert "torch" not in scope


def test_cpu_download_and_inference_are_separate_and_bounded():
    nb = notebook()
    download = "".join(nb["cells"][2]["source"])
    pilot = "".join(nb["cells"][3]["source"])
    assert "PackageImporter" not in download
    assert "urlopen" not in pilot
    assert "timeout=min(180, remaining)" in download
    assert "timeout=min(360, remaining)" in pilot
    assert 'torch.device("cpu")' in pilot
    assert 'CUDA_VISIBLE_DEVICES=""' in pilot
    assert "MODEL_HASH_MISMATCH" in download and "MODEL_HASH_MISMATCH" in pilot
    assert "provider_shutdown_verified=False" in pilot
    assert "release_ready=False" in pilot
