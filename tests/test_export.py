"""Слой 1: export (mp3/m4b deliverable), sample, credits — no models; ffmpeg only
in the RUN_SLOW-gated test at the end. All texts are placeholders."""
from __future__ import annotations

import json
import os
import subprocess

import numpy as np
import pytest
import soundfile as sf

from audiobook import export, paths


# ── fixtures ────────────────────────────────────────────────────────────────

def _book(tmp_path, monkeypatch, sections=(("01", "a", "Вступ"), ("02", "b", "Глава 1. Тест"))):
    """Fake text/ + out/ tree; returns the section names."""
    text, out = tmp_path / "text", tmp_path / "out"
    (text / "blocks").mkdir(parents=True)
    names = []
    for nn, slug, head in sections:
        (text / "blocks" / f"{nn}_{slug}.blocks.json").write_text(
            json.dumps({"nn": nn, "slug": slug, "heading": head}), encoding="utf-8")
        (text / f"{nn}_{slug}.norm.txt").write_text("слово " * 20, encoding="utf-8")
        names.append(f"{nn}_{slug}")
    monkeypatch.setattr(paths, "TEXT", text)
    monkeypatch.setattr(paths, "OUT", out)
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    return names


def _render(section: str, mp3: bytes | None = b"ID3fake", stale: bool = False):
    sec = paths.OUT / "sections" / section
    sec.mkdir(parents=True, exist_ok=True)
    man = sec / "manifest.jsonl"
    man.write_text('{"id": "0001"}\n', encoding="utf-8")
    if mp3 is not None:
        p = sec / "section.mp3"
        p.write_bytes(mp3)
        t = man.stat().st_mtime
        os.utime(p, (t - 10, t - 10) if stale else (t + 10, t + 10))
    return sec


CFG = {"book": {"title": "Книга", "author": "Автор", "narrator": "", "cover": ""},
       "render": {"skip_sections": []},
       "master": {"sample_rate": 44100, "lufs": -19}}


# ── naming ──────────────────────────────────────────────────────────────────

def test_translit_and_ascii_name():
    assert export.translit("Щука жёлтая") == "Shchuka zheltaya"
    assert export.ascii_name("Глава 1. Тест") == "Glava_1_Test"
    assert export.ascii_name("ЖЁЛТЫЙ «дом»") == "ZhELTYY_dom"
    assert export.ascii_name("Café — №5") == "Cafe_No5"
    assert export.ascii_name("«»!!!") == "track"
    assert export.ascii_name("", "audiobook") == "audiobook"
    long = export.ascii_name("слово " * 30)
    assert len(long) <= export.NAME_MAX and not long.endswith("_")
    assert all(c.isascii() for c in long)


def test_track_file_names_numbering():
    assert export.track_file_names(["Вступление", "Глава 1. Тест"]) == [
        "01_Vstuplenie.mp3", "02_Glava_1_Test.mp3"]
    names = export.track_file_names(["x"] * 100)
    assert names[0] == "001_x.mp3" and names[-1] == "100_x.mp3"


def test_hms():
    assert export.hms(3725.4) == "1:02:05" and export.hms(59.6) == "0:01:00"


# ── text builders ───────────────────────────────────────────────────────────

def test_ffmeta_escape():
    assert export.ffmeta_escape("a=b;c#d\\e\nf") == "a\\=b\\;c\\#d\\\\e\\\nf"
    assert export.ffmeta_escape("Глава 1. Тест") == "Глава 1. Тест"


def test_chapter_times_no_drift():
    assert export.chapter_times([1.0004, 1.0004, 1.0004]) == [(0, 1000), (1000, 2001), (2001, 3001)]
    assert export.chapter_times([]) == []


def test_ffmetadata_text():
    txt = export.ffmetadata_text({"title": "Кни=га", "artist": "Автор", "comment": ""},
                                 [("Глава; 1", 0, 1500), ("Вторая", 1500, 4000)])
    lines = txt.splitlines()
    assert lines[0] == ";FFMETADATA1"
    assert "title=Кни\\=га" in lines and "artist=Автор" in lines
    assert not any(ln.startswith("comment=") for ln in lines)
    assert lines.count("[CHAPTER]") == 2 and lines.count("TIMEBASE=1/1000") == 2
    i = lines.index("[CHAPTER]")
    assert lines[i + 1:i + 5] == ["TIMEBASE=1/1000", "START=0", "END=1500", "title=Глава\\; 1"]
    assert txt.endswith("\n")


def test_concat_list_quotes(tmp_path):
    p = tmp_path / "it's.mp3"
    txt = export.concat_list_text([p])
    assert txt.splitlines()[0] == "ffconcat version 1.0"
    assert txt.splitlines()[1] == "file '" + p.resolve().as_posix().replace("'", "'\\''") + "'"


def test_m3u8_and_contents():
    m = export.m3u8_text(["01_a.mp3", "02_b.mp3"], ["Один", "Два"], [61.4, 3600.0], "Автор")
    assert m.splitlines() == ["#EXTM3U", "#EXTINF:61,Автор - Один", "01_a.mp3",
                              "#EXTINF:3600,Автор - Два", "02_b.mp3"]
    c = export.contents_tsv(["01_a.mp3"], ["Один\tтаб"], [61.4]).splitlines()
    assert c == ["track\tfile\ttitle\tduration", "1\t01_a.mp3\tОдин таб\t0:01:01"]


def test_m4b_args(tmp_path):
    lst, meta, out, cov = (tmp_path / n for n in ("l.txt", "m.txt", "b.m4b.part", "c.jpg"))
    cmd = export.m4b_args("ff", lst, meta, out, "64k", 1, 44100)
    assert cmd[:8] == ["ff", "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i"]
    assert cmd[cmd.index("-map_metadata") + 1] == "1" and cmd[cmd.index("-map_chapters") + 1] == "1"
    assert cmd[cmd.index("-c:a") + 1] == "aac" and cmd[cmd.index("-b:a") + 1] == "64k"
    assert cmd[cmd.index("-ac") + 1] == "1" and cmd[-3:] == ["-f", "mp4", str(out)]
    assert "attached_pic" not in cmd and "2:v" not in cmd
    cc = export.m4b_args("ff", lst, meta, out, "96k", 2, 44100, cov)
    assert str(cov) in cc and "2:v" in cc and "attached_pic" in cc
    assert export.aac_bitrate(1) == "64k" and export.aac_bitrate(2) == "96k"


def test_global_tags():
    t = export.global_tags({"book": {"title": "Книга", "author": "Автор", "narrator": "Чтец"}})
    assert t == {"title": "Книга", "album": "Книга", "artist": "Автор", "album_artist": "Автор",
                 "genre": "Audiobook", "comment": "Читает: Чтец"}
    assert export.global_tags({}) == {"genre": "Audiobook"}


def test_ffprobe_next_to_bin_ffmpeg(tmp_path, monkeypatch):
    import sys
    monkeypatch.setattr(paths, "BIN", tmp_path)
    sfx = ".exe" if sys.platform == "win32" else ""
    (tmp_path / f"ffmpeg{sfx}").touch()
    (tmp_path / f"ffprobe{sfx}").touch()
    assert export.ffprobe() == tmp_path / f"ffprobe{sfx}"


def test_parse_float():
    assert export.parse_float("N/A\n12.5\n", "x") == 12.5
    with pytest.raises(SystemExit):
        export.parse_float("", "x")


# ── pre-flight + mp3 export ─────────────────────────────────────────────────

def test_preflight_refuses_missing_and_stale(tmp_path, monkeypatch):
    names = _book(tmp_path, monkeypatch, (("01", "a", "А"), ("02", "b", "Б"),
                                          ("03", "c", "В"), ("04", "d", "Г")))
    _render(names[0])
    _render(names[1], stale=True)
    _render(names[2], mp3=None)           # chunked, never mastered
    # names[3]: not even chunked
    with pytest.raises(SystemExit) as e:
        export.export(CFG, "mp3", duration_fn=lambda p: 1.0)
    msg = str(e.value)
    assert "02_b: section.mp3 старше manifest.jsonl" in msg
    assert "03_c: нет section.mp3" in msg and "04_d: не нарезано" in msg
    assert "01_a" not in msg
    assert not (paths.OUT / "export" / "mp3").exists()      # no partial book


def test_preflight_allow_missing_skips_loudly(tmp_path, monkeypatch, capsys):
    names = _book(tmp_path, monkeypatch)
    _render(names[1])
    out = export.export(CFG, "mp3", allow_missing=True, duration_fn=lambda p: 2.0)
    assert "НЕПОЛНАЯ" in capsys.readouterr().out
    assert sorted(p.name for p in out.glob("*.mp3")) == ["01_Glava_1_Test.mp3"]


def test_preflight_nothing_ready(tmp_path, monkeypatch):
    _book(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match="нет ни одной"):
        export.export(CFG, "mp3", allow_missing=True, duration_fn=lambda p: 1.0)


def test_skip_sections_left_out(tmp_path, monkeypatch):
    names = _book(tmp_path, monkeypatch)
    _render(names[1])          # 01_a skipped by config, not rendered → not a problem
    cfg = dict(CFG, render={"skip_sections": [names[0]]})
    out = export.export(cfg, "mp3", duration_fn=lambda p: 1.0)
    assert [p.name for p in sorted(out.glob("*.mp3"))] == ["01_Glava_1_Test.mp3"]


def test_export_mp3_copies_and_writes_lists(tmp_path, monkeypatch, capsys):
    names = _book(tmp_path, monkeypatch)
    for n in names:
        _render(n, mp3=f"ID3-{n}".encode())
    out = export.export(CFG, "mp3", duration_fn=lambda p: 90.0)
    assert out == paths.OUT / "export" / "mp3"
    assert sorted(p.name for p in out.iterdir()) == [
        "01_Vstup.mp3", "02_Glava_1_Test.mp3", "playlist.m3u8"]
    assert (out / "02_Glava_1_Test.mp3").read_bytes() == b"ID3-02_b"      # untouched copy
    for n in names:                                                       # copy, not move
        assert (paths.OUT / "sections" / n / "section.mp3").exists()
    pl = (out / "playlist.m3u8").read_text(encoding="utf-8").splitlines()
    assert pl == ["#EXTM3U", "#EXTINF:90,Автор - Вступ", "01_Vstup.mp3",
                  "#EXTINF:90,Автор - Глава 1. Тест", "02_Glava_1_Test.mp3"]
    tsv = (paths.OUT / "export" / "contents.tsv").read_text(encoding="utf-8").splitlines()
    assert tsv[2] == "2\t02_Glava_1_Test.mp3\tГлава 1. Тест\t0:01:30"
    assert not (paths.OUT / "export" / "mp3.part").exists()
    # second export: the previous one is moved aside, never deleted
    export.export(CFG, "mp3", duration_fn=lambda p: 90.0)
    old = list((paths.OUT / "export" / "_old").glob("*/mp3/01_Vstup.mp3"))
    assert len(old) == 1 and "перенесён" in capsys.readouterr().out


def test_long_track_warning(tmp_path, monkeypatch, capsys):
    names = _book(tmp_path, monkeypatch)
    for n in names:
        _render(n)
    export.export(CFG, "mp3", duration_fn=lambda p: 121 * 60.0 if "02_b" in str(p) else 60.0)
    o = capsys.readouterr().out
    assert "ВНИМАНИЕ: файл длиннее 120 мин" in o and "02_b: 2:01:00" in o and "01_a:" not in o


def test_bad_format():
    with pytest.raises(SystemExit, match="не поддерживается"):
        export.export(CFG, "ogg")


def test_retire_keeps_both(tmp_path):
    old = tmp_path / "_old"
    for _ in range(2):
        (tmp_path / "a.mp3").write_bytes(b"x")
        export.retire(tmp_path / "a.mp3", old)
    assert sorted(p.name for p in old.iterdir()) == ["a.1.mp3", "a.mp3"]
    assert export.retire(tmp_path / "none.mp3", old) is None


# ── sample ──────────────────────────────────────────────────────────────────

def test_sample_window():
    assert export.sample_window(10, 300, 1000) == (10, 300)
    assert export.sample_window(900, 300, 1000) == (900, 100)
    for args in ((0, 301, 1000), (-1, 60, 1000), (0, 1.5, 1000), (1000, 60, 1000), (999, 60, 1000)):
        with pytest.raises(SystemExit):
            export.sample_window(*args)


def test_sample_refuses_over_limit_before_anything(tmp_path, monkeypatch):
    _book(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match="лимита 300"):
        export.sample(CFG, "02_b", 0, 301)
    with pytest.raises(SystemExit, match="нет"):
        export.sample(CFG, "02_b", 0, 60)
    assert not (paths.OUT / "export").exists()


def test_sample_args_and_tags(tmp_path, monkeypatch):
    _book(tmp_path, monkeypatch)
    tags = export.sample_tags(CFG, "02_b")
    assert tags["title"] == "Книга — отрывок" and tags["album"] == "Книга" and "track" not in tags
    assert export.fade_filter(60) == "afade=t=in:st=0:d=0.5,afade=t=out:st=58.5:d=1.5"
    cmd = export.sample_args("ff", tmp_path / "s.mp3", tmp_path / "o.part", 12.5, 60, 44100, tags)
    assert cmd.index("-ss") < cmd.index("-i") and cmd[cmd.index("-ss") + 1] == "12.5"
    assert cmd[cmd.index("-t") + 1] == "60" and cmd[cmd.index("-map_metadata") + 1] == "-1"
    assert cmd[cmd.index("-b:a") + 1] == "192k" and "title=Книга — отрывок" in cmd
    assert cmd[-3:] == ["-f", "mp3", str(tmp_path / "o.part")]


# ── credits ─────────────────────────────────────────────────────────────────

def test_music_bed_args(tmp_path):
    cmd = export.music_bed_args("ff", tmp_path / "v.wav", tmp_path / "m.mp3", tmp_path / "o.wav",
                                -24, 10.0)
    assert cmd[cmd.index("-stream_loop") + 1] == "-1"
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "volume=-24dB" in fc and "atrim=0:10.000" in fc and "afade=t=out:st=7.000:d=3.000" in fc
    assert "amix=inputs=2:duration=first" in fc and cmd[-1] == str(tmp_path / "o.wav")
    short = export.music_bed_args("ff", tmp_path / "v", tmp_path / "m", tmp_path / "o", -20, 4.0)
    assert "afade=t=out:st=2.000:d=2.000" in short[short.index("-filter_complex") + 1]


def test_plan_credit():
    P = export.CreditPlan
    assert export.plan_credit({}, "k", "m", False, False) == P(True, True, "", "")
    assert export.plan_credit({"key": "old" * 5}, "k", "m", True, True) == \
        P(True, True, ("old" * 5)[:12], "")
    assert export.plan_credit({"key": "k", "mix_key": "m"}, "k", "m", True, True) == \
        P(False, False, "", "")
    assert export.plan_credit({"key": "k", "mix_key": "m0" * 8}, "k", "m", True, True) == \
        P(False, True, "", ("m0" * 8)[:12])
    assert export.plan_credit({"key": "k", "mix_key": "m"}, "k", "m", True, False) == \
        P(False, True, "", "")
    # wav lost but mp3 there: re-synth, and the old mp3 is moved aside, not overwritten
    assert export.plan_credit({"key": "k", "mix_key": "m"}, "k", "m", False, True) == \
        P(True, True, "", "m")


CREDITS_CFG = dict(CFG, model={"name": "fake", "seed": 42, "temperature": 1.0, "language": "ru",
                               "sentinel": ""},
                   reference={"path": "ref/none.wav"}, render={"timeout_retries": 1},
                   chunking={"target": 180, "cap": 180, "min_len": 40},
                   credits={"opening": "Плейсхолдер вступления. Строка два.",
                            "closing": "", "music": "", "music_db": -24})


class _FakeEngine:
    calls: list = []
    fail = False

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def synth(self, text, seed, **kw):
        _FakeEngine.calls.append((text, seed))
        return None if _FakeEngine.fail else np.full(2400, 0.1, dtype=np.float32)


def _fake_master(log):
    def m(src, out, config, pad=False, tags=None, cover=None):
        log.append((src.name, tags["title"], pad))
        out.write_bytes(b"ID3" + src.read_bytes()[:8])
        return {}
    return m


def test_credit_rows_hash_like_book(tmp_path, monkeypatch):
    _book(tmp_path, monkeypatch)
    text = "Плейсхолдер один.\n\nПлейсхолдер два."
    assert export.credit_chunks(text, CREDITS_CFG) == ["Плейсхолдер один.", "Плейсхолдер два."]
    r1 = export.credit_rows(text, CREDITS_CFG, {}, "lat")
    assert [r["id"] for r in r1] == ["0001", "0002"] and len(r1[0]["hash"]) == 40
    assert export.credit_rows(text, CREDITS_CFG, {}, "lat") == r1          # deterministic
    assert export.credit_rows(text, CREDITS_CFG, {}, "lat2")[0]["hash"] != r1[0]["hash"]
    seed2 = dict(CREDITS_CFG, model=dict(CREDITS_CFG["model"], seed=7))
    assert export.credit_rows(text, seed2, {}, "lat")[0]["hash"] != r1[0]["hash"]
    k = export.credit_key(text, r1)
    assert k != export.credit_key(text + " ", export.credit_rows(text + " ", CREDITS_CFG, {}, "lat"))


def test_render_credits_cache_and_retire(tmp_path, monkeypatch):
    from audiobook import synth
    names = _book(tmp_path, monkeypatch)
    monkeypatch.setattr(synth, "prepare_synth_text", lambda t, c, tb, s: (t, None))
    _FakeEngine.calls, _FakeEngine.fail = [], False
    log: list = []
    cfg = json.loads(json.dumps(CREDITS_CFG))
    d = paths.OUT / "credits"

    out = export.render_credits(cfg, engine_factory=_FakeEngine, master_fn=_fake_master(log))
    assert out == [d / "opening.mp3"] and not (d / "closing.mp3").exists()   # empty → nothing
    assert len(_FakeEngine.calls) == 1                     # one chunk ≤ 180 chars
    data, sr = sf.read(str(d / "opening.wav"), dtype="float32")
    assert sr == 24000 and len(data) == 2400 and sf.info(str(d / "opening.wav")).subtype == "FLOAT"
    assert log == [("opening.wav", "Вступление", True)]
    st = json.loads((d / "opening.json").read_text(encoding="utf-8"))
    assert st["key"] and st["mix_key"]
    assert export.credit_state(cfg, "opening")[0] == "ok"
    assert export.credit_state(cfg, "closing")[0] == "empty"

    # unchanged → nothing re-rendered, nothing re-mastered
    _FakeEngine.calls.clear()
    export.render_credits(cfg, engine_factory=_FakeEngine, master_fn=_fake_master(log))
    assert _FakeEngine.calls == [] and len(log) == 1

    # master setting changed → re-master only, the old mp3 moved aside
    cfg["master"]["lufs"] = -18
    assert export.credit_state(cfg, "opening")[0] == "stale"
    export.render_credits(cfg, engine_factory=_FakeEngine, master_fn=_fake_master(log))
    assert _FakeEngine.calls == [] and len(log) == 2
    assert len(list(d.glob(f"_old_{st['mix_key'][:12]}/opening.mp3"))) == 1

    # text changed → wav/mp3/json moved to _old_<hash12>, re-synthesised
    cfg["credits"]["opening"] = "Другой плейсхолдер."
    export.render_credits(cfg, engine_factory=_FakeEngine, master_fn=_fake_master(log))
    old = d / f"_old_{st['key'][:12]}"
    assert sorted(p.name for p in old.iterdir()) == ["opening.json", "opening.mp3", "opening.wav"]
    assert len(_FakeEngine.calls) == 1 and (d / "opening.wav").exists()

    # export picks the credits up as the first track
    for n in names:
        _render(n)
    exp = export.export(cfg, "mp3", duration_fn=lambda p: 5.0)
    assert sorted(p.name for p in exp.glob("*.mp3")) == [
        "01_Vstuplenie.mp3", "02_Vstup.mp3", "03_Glava_1_Test.mp3"]


def test_render_credits_failed_synth_writes_nothing(tmp_path, monkeypatch):
    from audiobook import synth
    _book(tmp_path, monkeypatch)
    monkeypatch.setattr(synth, "prepare_synth_text", lambda t, c, tb, s: (t, None))
    _FakeEngine.calls, _FakeEngine.fail = [], True
    try:
        with pytest.raises(SystemExit, match="не синтезировался"):
            export.render_credits(CREDITS_CFG, engine_factory=_FakeEngine,
                                  master_fn=_fake_master([]))
    finally:
        _FakeEngine.fail = False
    assert len(_FakeEngine.calls) == 2                     # retries + 1 seeds tried
    d = paths.OUT / "credits"
    assert not (d / "opening.wav").exists() and not (d / "opening.json").exists()


def test_credits_missing_blocks_export(tmp_path, monkeypatch):
    names = _book(tmp_path, monkeypatch)
    for n in names:
        _render(n)
    with pytest.raises(SystemExit, match="вступление \\(credits.opening\\): нет mp3"):
        export.export(CREDITS_CFG, "mp3", duration_fn=lambda p: 1.0)


def test_credits_missing_music_refused(tmp_path, monkeypatch):
    _book(tmp_path, monkeypatch)
    cfg = dict(CREDITS_CFG, credits=dict(CREDITS_CFG["credits"], music="nope.mp3"))
    with pytest.raises(SystemExit, match="credits.music"):
        export.music_path(cfg)


# ── real ffmpeg (RUN_SLOW only) ─────────────────────────────────────────────

@pytest.mark.slow
@pytest.mark.skipif(paths.ffmpeg() is None or export.ffprobe() is None, reason="нет ffmpeg/ffprobe")
def test_real_ffmpeg_export_m4b_mp3_sample(tmp_path, monkeypatch, slow):
    names = _book(tmp_path, monkeypatch)
    ff = str(paths.ffmpeg())
    for i, n in enumerate(names):
        sec = _render(n, mp3=None)
        wav = tmp_path / f"{n}.wav"
        t = np.arange(int((3 + i) * 24000)) / 24000
        sf.write(str(wav), (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), 24000)
        subprocess.run([ff, "-y", "-i", str(wav), "-ar", "44100", "-c:a", "libmp3lame",
                        "-b:a", "192k", "-metadata", "title=X", str(sec / "section.mp3")],
                       check=True, capture_output=True)
    mp3dir = export.export(CFG, "mp3")
    assert len(list(mp3dir.glob("*.mp3"))) == 2
    m4b = export.export(CFG, "m4b")
    assert m4b.name == "Kniga.m4b" and m4b.exists()
    p = subprocess.run([str(export.ffprobe()), "-v", "error", "-show_chapters",
                        "-show_format", "-of", "json", str(m4b)],
                       capture_output=True, text=True, check=True)
    info = json.loads(p.stdout)
    assert [c["tags"]["title"] for c in info["chapters"]] == ["Вступ", "Глава 1. Тест"]
    assert abs(float(info["chapters"][1]["start_time"]) - 3.0) < 0.1
    assert abs(float(info["format"]["duration"]) - 7.0) < 0.2
    assert info["format"]["tags"]["title"] == "Книга"
    assert info["format"]["tags"]["genre"] == "Audiobook"
    s = export.sample(CFG, names[1], 0.5, 3.0)
    assert abs(export.probe_duration(s) - 3.0) < 0.1


def test_cli_wires_export_commands():
    from audiobook.__main__ import _HEAVY, _MAIN_CONFIG_ONLY, build_parser
    p = build_parser()
    assert p.parse_args(["export", "--format", "m4b"]).format == "m4b"
    assert p.parse_args(["export-sample", "--section", "x"]).length == 300.0
    assert p.parse_args(["credits"]).cmd == "credits"
    assert "credits" in _HEAVY and "credits" in _MAIN_CONFIG_ONLY and "export" in _MAIN_CONFIG_ONLY
