"""Integration smoke with the real pinned Silero package; public synthetic text only."""
from importlib.metadata import version

from audiobook.stress_consensus import compare

def main():
    if version("silero-stress") != "1.4":
        raise SystemExit("UNEXPECTED_SILERO_VERSION")
    from silero_stress import load_accentor
    accentor = load_accentor()
    text = "Молоко и берёза."
    records = compare(text, "Молок+о +и бер+ёза.", accentor(text))
    assert len(records) == 2, records
    assert all(r["status"] == "agree" for r in records), records
    print("SILERO_REAL_SMOKE=PASS (synthetic public text; not acoustic verification)")


if __name__ == "__main__":
    main()
