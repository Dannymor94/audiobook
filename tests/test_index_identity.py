"""assemble index.tsv carries hash16+seed; suspects checks audio identity by them."""
from audiobook import assemble, suspects


def _rows():
    return [{"id": "0001", "hash": "a" * 40, "seed": 11, "text": "x"},
            {"id": "0002", "hash": "b" * 40, "seed": 22, "seed_override": 99, "text": "y"}]


def _stats():
    return [{"id": "0001", "start_ms": 0, "lead_ms": 10},
            {"id": "0002", "start_ms": 1500, "lead_ms": 20}]


def test_write_index_columns_and_atomic(tmp_path):
    p = tmp_path / "section.index.tsv"
    assemble.write_index(p, _rows(), _stats())
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "id\tstart_ms\tlead_ms\thash16\tseed"
    assert lines[1] == "0001\t0\t10\t" + "a" * 16 + "\t11"
    assert lines[2] == "0002\t1500\t20\t" + "b" * 16 + "\t99"   # seed_override wins
    assert not list(tmp_path.glob("*.part"))
    assert suspects.read_index(p) == {"0001": (0, 10), "0002": (1500, 20)}


def test_identity_ok_even_if_manifest_newer(tmp_path):
    p = tmp_path / "section.index.tsv"
    rows = _rows()
    assemble.write_index(p, rows, _stats())
    rows[0]["flag_words"] = [["w", 0.1, 0.2, "conf"]]          # qc only added flags
    assert suspects.check_identity(suspects.read_index_identity(p), rows, None) is None


def test_identity_detects_retake_and_changed_text(tmp_path):
    p = tmp_path / "section.index.tsv"
    assemble.write_index(p, _rows(), _stats())
    ident = suspects.read_index_identity(p)
    rows = _rows()
    rows[0]["seed"] = 12                                       # qc re-take
    assert "0001" in suspects.check_identity(ident, rows, None)
    rows = _rows()
    rows[1]["hash"] = "c" * 40                                  # text changed
    rows[1].pop("seed_override")
    rows[1]["seed"] = 22
    assert "0002" in suspects.check_identity(ident, rows, None)
    assert "не совпадают" in suspects.check_identity(ident, _rows()[:1], None)


def test_old_three_column_index_has_no_identity(tmp_path):
    p = tmp_path / "section.index.tsv"
    p.write_text("id\tstart_ms\tlead_ms\n0001\t0\t5\n", encoding="utf-8")
    assert suspects.read_index_identity(p) is None
    assert suspects.read_index(p) == {"0001": (0, 5)}
