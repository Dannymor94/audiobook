"""No real model loads in these host-policy tests."""
import pytest

from audiobook import gamebox


@pytest.mark.parametrize(("system", "host"), [
    ("Darwin", "danny-serv"), ("Linux", "ci-runner"),
    ("Linux", ""), ("Windows", "danny-serv"),
    ("Linux", "danny-serv.example.org"),
])
def test_unknown_host_denied(monkeypatch, system, host):
    monkeypatch.setattr(gamebox.platform, "system", lambda: system)
    monkeypatch.setattr(gamebox.socket, "gethostname", lambda: host)
    monkeypatch.setenv("HOSTNAME", "danny-serv")
    with pytest.raises(gamebox.GameboxRequired, match="GAMEBOX_REQUIRED"):
        gamebox.require_gamebox()


def test_gamebox_allowed(monkeypatch):
    monkeypatch.setattr(gamebox.platform, "system", lambda: "Linux")
    monkeypatch.setattr(gamebox.socket, "gethostname", lambda: "danny-serv")
    gamebox.require_gamebox()


def test_identity_error_denied(monkeypatch):
    def unavailable():
        raise OSError("unavailable")
    monkeypatch.setattr(gamebox.socket, "gethostname", unavailable)
    with pytest.raises(gamebox.GameboxRequired):
        gamebox.require_gamebox()


def test_direct_and_worker_entries_blocked(monkeypatch):
    from audiobook import synth, worker

    monkeypatch.setattr(gamebox.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(gamebox.socket, "gethostname", lambda: "danny-serv")
    monkeypatch.setattr(synth, "_model", object())
    with pytest.raises(gamebox.GameboxRequired):
        synth.load_model("cpu")
    with pytest.raises(gamebox.GameboxRequired):
        synth.synthesize(None, "test", {}, 1, 1.0)
    with pytest.raises(gamebox.GameboxRequired):
        synth.compute_latents(None, None)
    with pytest.raises(gamebox.GameboxRequired):
        worker.TimeoutSynth({}, 1)
    with pytest.raises(gamebox.GameboxRequired):
        worker._worker_loop({}, None, None)
