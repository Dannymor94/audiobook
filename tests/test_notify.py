"""Layer 1: Telegram notifications — opt-in env, never raises, token masked,
message builders, and the queue worker's notification points (fake notifier)."""
from __future__ import annotations

import io
import json
import logging
import threading
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

from audiobook import jobqueue as jq, notify

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "123456:SECRET-token_value"
ENV = {notify.TOKEN_ENV: TOKEN, notify.CHAT_ENV: "-100500"}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _fake_urlopen(calls, body=b'{"ok": true}'):
    def urlopen(req, timeout=None):
        calls.append((req, timeout))
        return _Resp(body)
    return urlopen


# ------------------------------------------------------------------- opt-in

def test_missing_env_is_silent_noop(monkeypatch, caplog):
    calls = []
    monkeypatch.delenv(notify.TOKEN_ENV, raising=False)
    monkeypatch.delenv(notify.CHAT_ENV, raising=False)
    with caplog.at_level(logging.WARNING):
        assert notify.send("x", urlopen=_fake_urlopen(calls)) is False
        assert notify.send("x", env={notify.TOKEN_ENV: TOKEN}, urlopen=_fake_urlopen(calls)) is False
        assert notify.send("x", env={notify.CHAT_ENV: "1", notify.TOKEN_ENV: "  "},
                           urlopen=_fake_urlopen(calls)) is False
    assert calls == [] and caplog.records == []
    assert notify.CHAT_ENV in notify.why_disabled({notify.TOKEN_ENV: TOKEN})
    assert notify.why_disabled(ENV) is None


def test_send_posts_to_bot_api():
    calls = []
    assert notify.send("привет", env=ENV, urlopen=_fake_urlopen(calls)) is True
    (req, timeout), = calls
    assert req.full_url == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert req.get_method() == "POST" and timeout == 10
    form = urllib.parse.parse_qs(req.data.decode("utf-8"))
    assert form["chat_id"] == ["-100500"] and form["text"] == ["привет"]


def test_long_text_is_clipped():
    calls = []
    notify.send("я" * 10000, env=ENV, urlopen=_fake_urlopen(calls))
    text = urllib.parse.parse_qs(calls[0][0].data.decode("utf-8"))["text"][0]
    assert len(text) <= 4096


@pytest.mark.parametrize("exc", [
    urllib.error.URLError(f"cannot reach https://api.telegram.org/bot{TOKEN}/sendMessage"),
    TimeoutError("timed out"),
    RuntimeError(f"weird {TOKEN}"),
    urllib.error.HTTPError("u", 401, "Unauthorized", {},
                           io.BytesIO(b'{"ok":false,"description":"Unauthorized"}')),
])
def test_send_never_raises_and_masks_token(exc, caplog):
    def urlopen(req, timeout=None):
        raise exc
    with caplog.at_level(logging.WARNING, logger="audiobook.notify"):
        assert notify.send("x", env=ENV, urlopen=urlopen) is False
    assert caplog.records, "a failed send logs a warning"
    assert all(TOKEN not in r.getMessage() for r in caplog.records)
    assert all("SECRET" not in r.getMessage() for r in caplog.records)


def test_http_error_reason_is_reported():
    def urlopen(req, timeout=None):
        raise urllib.error.HTTPError("u", 400, "Bad", {},
                                     io.BytesIO(b'{"ok":false,"description":"chat not found"}'))
    ok, why = notify.deliver("x", env=ENV, urlopen=urlopen)
    assert not ok and "400" in why and "chat not found" in why


def test_not_ok_body_is_failure():
    calls = []
    ok, why = notify.deliver("x", env=ENV,
                             urlopen=_fake_urlopen(calls, b'{"ok":false,"description":"nope"}'))
    assert not ok and why == "nope"


def test_send_is_bounded_when_network_hangs():
    release = threading.Event()

    def urlopen(req, timeout=None):
        release.wait(5)
        raise TimeoutError
    try:
        ok, why = notify.deliver("x", env=ENV, urlopen=urlopen, deadline=0.05)
    finally:
        release.set()
    assert not ok and "нет ответа" in why


def test_mask():
    assert notify.mask(f"a {TOKEN} b", TOKEN) == "a <token> b"
    assert TOKEN not in notify.mask(urllib.parse.quote(TOKEN, safe=""), TOKEN)
    assert notify.mask("abc", None) == "abc"


def test_cli_test_reports(capsys):
    assert notify.cli_test(env={}) == 1
    out = capsys.readouterr().out
    assert "RED" in out and notify.TOKEN_ENV in out
    calls = []
    assert notify.cli_test(env=ENV, urlopen=_fake_urlopen(calls)) == 0
    assert "GREEN" in capsys.readouterr().out
    text = urllib.parse.parse_qs(calls[0][0].data.decode("utf-8"))["text"][0]
    assert "проверка связи" in text


# ------------------------------------------------------------------ builders

def test_builders_are_short_russian_with_host_and_args():
    job = {"id": "0001-ab", "args": ["synth", "--section", "01_x"], "exit_code": 3}
    m = notify.job_failed(job, "line1\nline2", host="box")
    assert "box" in m and "synth --section 01_x" in m and "код 3" in m and "line2" in m
    m = notify.chapter_ready("01_x", "за 5 мин", host="box")
    assert "box" in m and "01_x" in m and "за 5 мин" in m and "master --section 01_x" in m
    m = notify.queue_drained(4, 1, host="box")
    assert "box" in m and "4" in m and "1" in m and "очередь пуста" in m.lower()
    m = notify.job_interrupted({"id": "z", "args": ["qc", "--section", "02"]}, 3, host="box")
    assert "box" in m and "qc --section 02" in m and "3" in m
    assert notify.job_failed(job, "") .startswith("ОШИБКА ")      # default host works
    huge = notify.job_failed(job, "x" * 20000, host="box")
    assert len(huge) <= notify.MAX_LEN and huge.endswith("x")    # keeps the end of the log


@pytest.mark.parametrize("args, section", [
    (["master", "--section", "03_a"], "03_a"),
    (["master", "--section=03_a"], "03_a"),
    (["master", "--sec", "03_a"], "03_a"),
    (["master", "--section", "03_a", "--first", "5"], None),
    (["master", "--section", "03_a", "--first=5"], None),
    (["master"], None),
    (["master", "--section", ""], None),
    (["assemble", "--section", "03_a"], None),
    ([], None),
])
def test_master_section(args, section):
    assert notify.master_section(args) == section


def test_log_tail(tmp_path):
    p = tmp_path / "j.log"
    lines = [f"строка {i}" for i in range(40)]
    p.write_text("\n".join(lines) + "\nprogress 10%\rprogress 100%\n\n", encoding="utf-8")
    tail = notify.log_tail(p).splitlines()
    assert len(tail) == 15 and tail[-1] == "progress 100%" and tail[-2] == "строка 39"
    assert notify.log_tail(tmp_path / "missing.log") == ""
    crlf = tmp_path / "crlf.log"
    crlf.write_bytes("один\r\nдва 5%\rдва 100%\r\n".encode("utf-8"))
    assert notify.log_tail(crlf) == "один\nдва 100%"


def test_elapsed_and_extra():
    assert notify.elapsed("2026-01-01T00:00:00+00:00", "2026-01-01T01:05:00+00:00") == "за 1 ч 05 мин"
    assert notify.elapsed("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:07+00:00") == "за 7 с"
    assert notify.elapsed(None, None) == ""
    job = {"started": "2026-01-01T00:00:00+00:00", "finished": "2026-01-01T00:03:00+00:00"}
    extra = notify.chapter_extra(job, "x\nfinal mp3: -18.00 LUFS (target -18)\ny")
    assert extra == "за 3 мин\nfinal mp3: -18.00 LUFS (target -18)"


# ------------------------------------------------------------- queue hooks

def _runner(codes: dict, log_text: str = ""):
    def runner(job, log_path):
        if log_text:
            log_path.write_text(log_text, encoding="utf-8")
        return codes.get(job["args"][0], 0)
    return runner


def test_worker_notifies_failed_master_and_drain(tmp_path):
    q = tmp_path / "q"
    jq.add_job(["doctor"], q)
    jq.add_job(["qc", "--section", "01"], q)
    jq.add_job(["master", "--section", "01"], q)
    jq.add_job(["master", "--section", "01", "--first", "3"], q)
    sent = []
    log = "\n".join(f"l{i}" for i in range(30)) + "\nfinal mp3: -18.0 LUFS\n"
    code = jq.run_worker(q, _runner({"qc": 2}, log), poll=0.01, say=lambda s: None,
                         notifier=sent.append)
    assert code == 1
    assert len(sent) == 3, sent
    failed, ready, drained = sent
    assert failed.startswith("ОШИБКА") and "qc --section 01" in failed and "код 2" in failed
    assert "l29" in failed and "l14" not in failed.split("хвост лога:")[1].split()  # ~15 lines
    assert ready.startswith("ГОТОВО") and "01" in ready and "final mp3" in ready
    assert drained.startswith("ОЧЕРЕДЬ ПУСТА") and "выполнено 3" in drained and "ошибкой 1" in drained


def test_runner_exception_notifies_with_error(tmp_path):
    q = tmp_path / "q"
    jq.add_job(["doctor"], q)
    sent = []

    def boom(job, lp):
        raise RuntimeError("kaboom")
    jq.run_worker(q, boom, poll=0.01, say=lambda s: None, notifier=sent.append)
    assert "kaboom" in sent[0] and "код -1" in sent[0]


def test_empty_queue_sends_nothing(tmp_path):
    sent = []
    assert jq.run_worker(tmp_path / "q", _runner({}), poll=0.01, say=lambda s: None,
                         notifier=sent.append) == 0
    assert sent == []


def test_broken_notifier_never_breaks_the_queue(tmp_path):
    q = tmp_path / "q"
    jq.add_job(["doctor"], q)
    jq.add_job(["qc", "--section", "01"], q)

    def bad(text):
        raise RuntimeError("telegram down")
    assert jq.run_worker(q, _runner({"qc": 1}), poll=0.01, say=lambda s: None,
                         notifier=bad) == 1
    assert [j["status"] for j in jq.list_jobs(q)] == ["done", "failed"]


def test_default_notifier_is_noop_without_env(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(notify.urllib.request, "urlopen", _fake_urlopen(calls))
    q = tmp_path / "q"
    jq.add_job(["qc", "--section", "01"], q)
    jq.run_worker(q, _runner({"qc": 1}), poll=0.01, say=lambda s: None)
    assert calls == []


def test_watch_drain_message_once_per_drain_and_idle_is_silent(tmp_path):
    q = tmp_path / "q"
    sent, sleeps = [], []

    def sleep(s):
        sleeps.append(s)
        if len(sleeps) == 3:
            jq.add_job(["doctor"], q)
            jq.add_job(["probe", "--max", "1"], q)

    jq.add_job(["doctor"], q)
    jq.run_worker(q, _runner({}), poll=0.01, say=lambda s: None, watch=1, max_cycles=8,
                  sleep=sleep, notifier=sent.append)
    drains = [m for m in sent if m.startswith("ОЧЕРЕДЬ ПУСТА")]
    assert drains == [notify.queue_drained(1, 0), notify.queue_drained(2, 0)]
    assert len(sent) == 2                    # idle cycles add nothing


def test_watch_idle_never_notifies(tmp_path):
    sent = []
    jq.run_worker(tmp_path / "q", _runner({}), poll=0.01, say=lambda s: None, watch=1,
                  max_cycles=20, sleep=lambda s: None, notifier=sent.append)
    assert sent == []


def _mark_running(q: Path, job_id: str, pid: int = 999) -> None:
    p = q / "pending" / f"{job_id}.json"
    job = json.loads(p.read_text(encoding="utf-8"))
    p.write_text(json.dumps({**job, "status": "running", "pid": pid, "attempts": 2}),
                 encoding="utf-8")


def test_requeue_exhaustion_notifies(tmp_path):
    q = tmp_path / "q"
    j = jq.add_job(["synth", "--section", "05"], q)
    _mark_running(q, j["id"])
    sent = []
    code = jq.run_worker(q, _runner({}), poll=0.01, say=lambda s: None,
                         alive=lambda pid: False, requeue_interrupted=True,
                         notifier=sent.append)
    assert code == 1
    assert sent[0].startswith("СНЯТА") and "synth --section 05" in sent[0] and "3" in sent[0]
    assert sent[-1] == notify.queue_drained(0, 1)


def test_requeue_without_exhaustion_is_silent_until_drain(tmp_path):
    q = tmp_path / "q"
    j = jq.add_job(["doctor"], q)
    p = q / "pending" / f"{j['id']}.json"
    job = json.loads(p.read_text(encoding="utf-8"))
    p.write_text(json.dumps({**job, "status": "running", "pid": 9}), encoding="utf-8")
    sent = []
    jq.run_worker(q, _runner({}), poll=0.01, say=lambda s: None, alive=lambda pid: False,
                  requeue_interrupted=True, notifier=sent.append)
    assert sent == [notify.queue_drained(1, 0)]


# --------------------------------------------------------------- ops files

def test_env_is_git_ignored_and_unit_loads_it():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in [ln.strip() for ln in ignored]
    unit = (ROOT / "scripts" / "gamebox" / "audiobook-queue.service").read_text(encoding="utf-8")
    assert "EnvironmentFile=-%h/audiobook/.env" in unit
    assert f"{notify.TOKEN_ENV}=" not in unit                  # secrets never in the unit
    readme = (ROOT / "scripts" / "gamebox" / "README.md").read_text(encoding="utf-8")
    for s in ("@BotFather", notify.TOKEN_ENV, notify.CHAT_ENV, "chmod 600", "notify-test"):
        assert s in readme


def test_no_credentials_in_config():
    cfg = (ROOT / "config.yaml").read_text(encoding="utf-8")
    assert "TG_TOKEN" not in cfg and "api.telegram.org" not in cfg
