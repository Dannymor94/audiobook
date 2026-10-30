"""Opt-in Telegram notifications from the render box (off by default).

Credentials come from the environment only — AUDIOBOOK_TG_TOKEN and
AUDIOBOOK_TG_CHAT, kept in the git-ignored `.env` that run.sh and the systemd
unit load. Never from config.yaml or git. If either is missing, every send is a
silent no-op returning False.

This is the only outbound network the pipeline uses, and it is optional.
send() never raises and never waits longer than SEND_DEADLINE seconds: a
dead network must not stop or crash the job queue.

Message builders (job_failed, chapter_ready, queue_drained, job_interrupted)
are pure functions; jobqueue.run_worker decides when to call them.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Mapping

TOKEN_ENV = "AUDIOBOOK_TG_TOKEN"
CHAT_ENV = "AUDIOBOOK_TG_CHAT"
API = "https://api.telegram.org"
TIMEOUT = 10.0           # per HTTP request
SEND_DEADLINE = 15.0     # hard cap incl. DNS, which the socket timeout does not cover
MAX_LEN = 4000           # Telegram limit is 4096 characters
TAIL_LINES = 15
_TAIL_BYTES = 64 * 1024
_LINE_MAX = 300

log = logging.getLogger(__name__)


# ----------------------------------------------------------------- credentials

def credentials(env: Mapping[str, str] | None = None) -> tuple[str, str] | None:
    env = os.environ if env is None else env
    token = (env.get(TOKEN_ENV) or "").strip()
    chat = (env.get(CHAT_ENV) or "").strip()
    return (token, chat) if token and chat else None


def why_disabled(env: Mapping[str, str] | None = None) -> str | None:
    """Russian reason why notifications are off, or None if configured."""
    env = os.environ if env is None else env
    missing = [k for k in (TOKEN_ENV, CHAT_ENV) if not (env.get(k) or "").strip()]
    if not missing:
        return None
    return f"уведомления выключены: нет {', '.join(missing)} в окружении (.env)"


def mask(text: str, token: str | None) -> str:
    """Hide the bot token in anything that may reach a log."""
    if token:
        text = text.replace(token, "<token>")
        text = text.replace(urllib.parse.quote(token, safe=""), "<token>")
    return text


# ------------------------------------------------------------------------ send

def deliver(text: str, env: Mapping[str, str] | None = None,
            urlopen: Callable | None = None,
            deadline: float = SEND_DEADLINE) -> tuple[bool, str]:
    """Post `text` to the chat. Returns (sent, Russian reason). Never raises."""
    creds = credentials(env)
    if creds is None:
        return False, why_disabled(env) or "уведомления выключены"
    token, chat = creds
    try:
        req = urllib.request.Request(
            f"{API}/bot{token}/sendMessage",
            data=urllib.parse.urlencode({
                "chat_id": chat,
                "text": _clip(text, MAX_LEN),
                "disable_web_page_preview": "true",
            }).encode("utf-8"),
            method="POST",
        )
    except Exception as e:  # noqa: BLE001  (a malformed token must not crash anyone)
        reason = mask(f"{type(e).__name__}: {e}", token)
        log.warning("telegram: не отправлено: %s", reason)
        return False, reason
    return _submit(req, token, urlopen, deadline)


def _submit(req, token: str, urlopen: Callable | None, deadline: float) -> tuple[bool, str]:
    """POST ``req`` in a daemon thread with a hard deadline. Never raises."""
    opener = urlopen or urllib.request.urlopen
    result: dict[str, object] = {}

    def _post() -> None:
        try:
            with opener(req, timeout=TIMEOUT) as resp:
                body = resp.read()
            data = json.loads(body.decode("utf-8", errors="replace") or "{}")
            result["ok"] = data.get("ok") is True
            if not result["ok"]:
                result["err"] = str(data.get("description") or "ответ без ok")
        except urllib.error.HTTPError as e:
            desc = ""
            try:
                desc = json.loads(e.read().decode("utf-8", errors="replace")).get("description", "")
            except Exception:  # noqa: BLE001
                pass
            result["err"] = f"HTTP {e.code}{': ' + desc if desc else ''}"
        except Exception as e:  # noqa: BLE001
            result["err"] = f"{type(e).__name__}: {e}"

    t = threading.Thread(target=_post, name="tg-notify", daemon=True)
    t.start()
    t.join(deadline)
    if t.is_alive():
        reason = f"нет ответа за {deadline:g} с"
    elif result.get("ok"):
        return True, "отправлено"
    else:
        reason = mask(str(result.get("err") or "неизвестная ошибка"), token)
    log.warning("telegram: не отправлено: %s", reason)
    return False, reason


AUDIO_DEADLINE = 60.0          # a 2–3 MB mp3 over a slow uplink
MAX_AUDIO_BYTES = 45 * 1024 * 1024   # Bot API limit is 50 MB


def multipart(fields: dict[str, str], file_field: str, path: Path,
              mime: str = "audio/mpeg") -> tuple[bytes, str]:
    """multipart/form-data body (stdlib only) → (body, content-type)."""
    import uuid
    boundary = f"----audiobook{uuid.uuid4().hex}"
    out = bytearray()
    for k, v in fields.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n"
                f"{v}\r\n").encode("utf-8")
    fname = path.name.encode("ascii", "replace").decode("ascii")
    out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
            f"filename=\"{fname}\"\r\nContent-Type: {mime}\r\n\r\n").encode("utf-8")
    out += path.read_bytes()
    out += f"\r\n--{boundary}--\r\n".encode("utf-8")
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def deliver_audio(path: Path, caption: str, title: str = "",
                  env: Mapping[str, str] | None = None, urlopen: Callable | None = None,
                  deadline: float = AUDIO_DEADLINE) -> tuple[bool, str]:
    """Send an mp3 to the chat (sendAudio). Returns (sent, reason). Never raises."""
    creds = credentials(env)
    if creds is None:
        return False, why_disabled(env) or "уведомления выключены"
    token, chat = creds
    try:
        if not path.exists():
            return False, f"нет файла {path.name}"
        if path.stat().st_size > MAX_AUDIO_BYTES:
            return False, f"файл больше {MAX_AUDIO_BYTES // 2**20} МБ"
        fields = {"chat_id": chat, "caption": _clip(caption, 1000)}
        if title:
            fields["title"] = _clip(title, 60)
        body, ctype = multipart(fields, "audio", path)
        req = urllib.request.Request(f"{API}/bot{token}/sendAudio", data=body,
                                     headers={"Content-Type": ctype}, method="POST")
    except Exception as e:  # noqa: BLE001
        return False, mask(f"{type(e).__name__}: {e}", token)
    return _submit(req, token, urlopen, deadline)


def send(text: str, env: Mapping[str, str] | None = None,
         urlopen: Callable | None = None, deadline: float = SEND_DEADLINE) -> bool:
    """Fire-and-forget: True if Telegram accepted the message. Never raises."""
    try:
        return deliver(text, env, urlopen, deadline)[0]
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------- builders

def _host(host: str | None) -> str:
    if host:
        return host
    try:
        return socket.gethostname() or "?"
    except Exception:  # noqa: BLE001
        return "?"


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _args(job: Mapping) -> str:
    return " ".join(str(a) for a in job.get("args") or []) or "?"


def job_failed(job: Mapping, log_tail: str, host: str | None = None) -> str:
    code = job.get("exit_code")
    head = f"ОШИБКА {_host(host)}: задача упала (код {code})\n{_args(job)}\nid {job.get('id', '?')}"
    if job.get("error"):
        head += f"\n{job['error']}"
    tail = (log_tail or "").strip()
    if not tail:
        return _clip(head, MAX_LEN)
    room = MAX_LEN - len(head) - 20
    if room <= 0:
        return _clip(head, MAX_LEN)
    if len(tail) > room:
        tail = "…" + tail[-max(room, 0):]
    return f"{head}\n\nхвост лога:\n{tail}"


def chapter_ready(section: str, extra: str = "", host: str | None = None) -> str:
    msg = f"ГОТОВО {_host(host)}: глава {section}\nmaster --section {section}"
    if extra.strip():
        msg += f"\n{extra.strip()}"
    return _clip(msg, MAX_LEN)


def queue_drained(n_done: int, n_failed: int, host: str | None = None) -> str:
    return (f"ОЧЕРЕДЬ ПУСТА {_host(host)}: выполнено {n_done}, "
            f"с ошибкой {n_failed}")


def job_interrupted(job: Mapping, attempts: int, host: str | None = None) -> str:
    return _clip(f"СНЯТА {_host(host)}: задача прервана {attempts} раз(а), "
                 f"перенесена в done как interrupted\n{_args(job)}\n"
                 f"id {job.get('id', '?')}\n"
                 f"снова: ./run.sh queue add -- {_args(job)}", MAX_LEN)


# ------------------------------------------------------------------- helpers

def master_section(args: list[str]) -> str | None:
    """Section of a full-section `master --section S` job (no --first), else None."""
    if not args or args[0] != "master":
        return None
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--section", default=None)
    p.add_argument("--first", default=None)
    p.add_argument("--chapter", default=None)
    try:
        ns = p.parse_known_args([str(a) for a in args[1:]])[0]
    except SystemExit:
        return None
    if ns.first not in (None, "", "0"):
        return None
    section = (ns.section or "").strip()
    return section or None


def log_tail(path: Path, n: int = TAIL_LINES) -> str:
    """Last `n` non-empty lines of a job log (progress-bar \\r updates collapsed)."""
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - _TAIL_BYTES))
            raw = f.read()
    except OSError:
        return ""
    lines = []
    for ln in raw.decode("utf-8", errors="replace").split("\n"):
        ln = ln.rstrip("\r").split("\r")[-1].rstrip()   # CRLF logs on Windows
        if ln.strip():
            lines.append(_clip(ln, _LINE_MAX))
    return "\n".join(lines[-n:])


def elapsed(started: str | None, finished: str | None) -> str:
    """'за 1 ч 05 мин' between two ISO timestamps of a job, '' if unknown."""
    from datetime import datetime
    try:
        sec = int((datetime.fromisoformat(str(finished))
                   - datetime.fromisoformat(str(started))).total_seconds())
    except (TypeError, ValueError):
        return ""
    if sec < 0:
        return ""
    h, m = divmod(sec // 60, 60)
    if h:
        return f"за {h} ч {m:02d} мин"
    return f"за {m} мин" if m else f"за {sec} с"


def chapter_extra(job: Mapping, tail: str) -> str:
    """Duration of the master job plus its loudness line, for chapter_ready."""
    parts = [elapsed(job.get("started"), job.get("finished")),
             last_line_with(tail, "final mp3:")]
    return "\n".join(x for x in parts if x)


def last_line_with(text: str, prefix: str) -> str:
    for ln in reversed(text.splitlines()):
        if ln.strip().startswith(prefix):
            return ln.strip()
    return ""


# ------------------------------------------------------------------------ CLI

def cli_test(env: Mapping[str, str] | None = None, urlopen: Callable | None = None) -> int:
    """`notify-test`: send «проверка связи», say whether it went and why not."""
    sent, reason = deliver(f"{_host(None)}: проверка связи", env, urlopen)
    if sent:
        print("GREEN  telegram: отправлено, проверь чат")
        return 0
    print(f"RED    telegram: не отправлено — {reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(cli_test())
