"""Layer 1: loudness report — ebur128 parsing, flags, atomic tsv, wiring with a
fake meter. Real measurement needs ffmpeg and is not run here."""
from __future__ import annotations

import pytest

from audiobook import loudness as ld, paths

# Shape of `ffmpeg -nostats -i x.mp3 -af ebur128=peak=true -f null -` stderr
# (ffmpeg 6.x): per-frame lines carry I:/LRA: mid-line, the Summary is last.
SAMPLE = """\
Input #0, mp3, from 'section.mp3':
  Duration: 00:41:12.35, start: 0.025057, bitrate: 192 kb/s
  Stream #0:0: Audio: mp3, 44100 Hz, mono, fltp, 192 kb/s
[Parsed_ebur128_0 @ 0x55d0c1a2b2c0] t: 2471.9       TARGET:-23 LUFS    M: -18.7 S: -19.4     I: -19.1 LUFS       LRA:   6.3 LU  FTPK: -4.2 dBFS  TPK: -3.4 dBFS
[Parsed_ebur128_0 @ 0x55d0c1a2b2c0] t: 2472         TARGET:-23 LUFS    M: -19.0 S: -19.4     I: -19.1 LUFS       LRA:   6.3 LU  FTPK: -4.6 dBFS  TPK: -3.4 dBFS
[out#0/null @ 0x55d0c1a0eac0] video:0kB audio:425870kB subtitle:0kB other streams:0kB global headers:0kB muxing overhead: unknown
size=N/A time=00:41:12.33 bitrate=N/A speed= 212x
[Parsed_ebur128_0 @ 0x55d0c1a2b2c0] Summary:

  Integrated loudness:
    I:         -19.1 LUFS
    Threshold: -29.4 LUFS

  Loudness range:
    LRA:         6.3 LU
    Threshold: -39.6 LUFS
    LRA low:   -23.0 LUFS
    LRA high:  -16.7 LUFS

  True peak:
    Peak:       -3.4 dBFS
"""

SILENT = """\
[Parsed_ebur128_0 @ 0x5600] Summary:

  Integrated loudness:
    I:         -70.0 LUFS
    Threshold:   0.0 LUFS

  Loudness range:
    LRA:         0.0 LU
    Threshold:   0.0 LUFS
    LRA low:     0.0 LUFS
    LRA high:    0.0 LUFS

  True peak:
    Peak:       -inf dBFS
"""


def test_parse_summary_not_progress_lines():
    assert ld.parse_ebur128(SAMPLE) == {"lufs": -19.1, "lra": 6.3, "true_peak": -3.4}


def test_parse_takes_last_summary():
    first = SAMPLE.replace("-19.1 LUFS\n    Threshold: -29.4", "-25.0 LUFS\n    Threshold: -35.0")
    assert ld.parse_ebur128(first + SAMPLE)["lufs"] == -19.1


def test_parse_silent_file():
    got = ld.parse_ebur128(SILENT)
    assert got["lufs"] == -70.0 and got["true_peak"] == float("-inf")


@pytest.mark.parametrize("text", ["", "Error opening input file x.mp3",
                                  SAMPLE.replace("    Peak:       -3.4 dBFS\n", "")])
def test_parse_errors(text):
    with pytest.raises(ValueError):
        ld.parse_ebur128(text)


def _row(name, lufs, tp, lra, kind="section"):
    return {"kind": kind, "name": name, "file": name, "lufs": lufs,
            "true_peak": tp, "lra": lra, "error": None}


def test_evaluate_flags():
    rows = [_row("01", -19.0, -3.5, 5.0),
            _row("02", -20.2, -3.5, 6.0),         # 1.2 LU quiet
            _row("03", -18.5, -2.9, 9.0),         # peak above -3
            _row("live", -14.0, -0.5, 15.0, kind="ref")]
    spread = ld.evaluate(rows, -19.0, -3.0)
    assert spread == pytest.approx(4.0)
    assert rows[0]["flags"] == [ld.FLAG_LRA_MIN]
    assert rows[1]["flags"] == [ld.FLAG_LOUD]
    assert rows[2]["flags"] == [ld.FLAG_PEAK, ld.FLAG_LRA_MAX]
    assert rows[3]["flags"] == []                 # reference is never judged


def test_evaluate_boundaries_and_small_spread():
    rows = [_row("01", -20.0, -3.0, 5.0), _row("02", -18.0, -3.0, 8.0)]
    assert ld.evaluate(rows, -19.0, -3.0) == pytest.approx(3.0)
    assert rows[0]["flags"] == [] and rows[1]["flags"] == []   # exactly 1.0 LU / at peak / 3 LU
    one = [_row("01", -19.0, -3.5, 5.0)]
    assert ld.evaluate(one, -19.0, -3.0) is None


def test_report_with_fake_meter(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    for s in ("01_a", "02_b"):
        d = out / "sections" / s
        d.mkdir(parents=True)
        (d / "section.mp3").write_bytes(b"")
    (out / "sections" / "03_c").mkdir()          # no section.mp3 → not listed
    live = tmp_path / "live"
    live.mkdir()
    (live / "rec1.m4a").write_bytes(b"")
    (live / "notes.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(paths, "OUT", out)

    values = {"01_a": (-19.2, -3.6, 5.0), "02_b": (-21.0, -3.4, 9.5), "rec1.m4a": (-15.0, -1.0, 12.0)}

    def fake(p):
        key = p.parent.name if p.name == "section.mp3" else p.name
        lufs, tp, lra = values[key]
        return {"lufs": lufs, "true_peak": tp, "lra": lra}

    config = {"master": {"lufs": -19, "true_peak": -3, "lra": 11}}
    assert ld.report(config, extra_dirs=[live], measure_fn=fake) == 0
    printed = capsys.readouterr().out
    assert "эталон" in printed and "ПРЕВЫШЕН" in printed and "громкость" in printed
    lines = (out / "loudness" / "report.tsv").read_text(encoding="utf-8").splitlines()
    assert [ln.split("\t")[1] for ln in lines[1:]] == ["01_a", "02_b", "rec1.m4a"]
    assert lines[2].split("\t")[6] == "громкость; LRA макс"
    assert lines[3].split("\t")[0] == "ref" and lines[3].split("\t")[6] == ""
    assert sorted(p.name for p in (out / "loudness").iterdir()) == ["report.tsv"]


def test_report_named_section_missing_and_meter_error(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    (out / "sections" / "01_a").mkdir(parents=True)
    (out / "sections" / "01_a" / "section.mp3").write_bytes(b"")
    monkeypatch.setattr(paths, "OUT", out)

    def broken(p):
        raise ValueError("в выводе ffmpeg нет Summary ebur128")

    config = {"master": {"lufs": -19, "true_peak": -3}}
    assert ld.report(config, sections=["01_a", "09_x"], measure_fn=broken) == 0
    text = capsys.readouterr().out
    assert "нет section.mp3" in text and "нет Summary" in text


def test_report_nothing_to_measure(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    assert ld.report({"master": {"lufs": -19, "true_peak": -3}}, measure_fn=lambda p: {}) == 1


def test_report_missing_ref_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "OUT", tmp_path / "out")
    assert ld.report({"master": {"lufs": -19, "true_peak": -3}},
                     extra_dirs=[tmp_path / "nope"], measure_fn=lambda p: {}) == 2


def test_report_without_ffmpeg_is_clear(tmp_path, monkeypatch):
    out = tmp_path / "out"
    (out / "sections" / "01_a").mkdir(parents=True)
    (out / "sections" / "01_a" / "section.mp3").write_bytes(b"")
    monkeypatch.setattr(paths, "OUT", out)
    monkeypatch.setattr(paths, "ffmpeg", lambda: None)
    with pytest.raises(SystemExit, match="ffmpeg не найден"):
        ld.report({"master": {"lufs": -19, "true_peak": -3}})
