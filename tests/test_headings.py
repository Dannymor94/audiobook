"""Layer-1 tests for headings module: logic only, no models."""
from __future__ import annotations

from audiobook.headings import _fmt_ts


def test_fmt_ts_basic():
    assert _fmt_ts(0) == "00:00"
    assert _fmt_ts(60) == "01:00"
    assert _fmt_ts(90) == "01:30"
    assert _fmt_ts(3661) == "61:01"


def test_fmt_ts_sub_minute():
    assert _fmt_ts(5) == "00:05"
    assert _fmt_ts(59) == "00:59"
