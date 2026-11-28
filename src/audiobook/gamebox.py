"""Fail closed for real TTS outside the owner-approved gamebox.

This is an accidental-execution guard, not hardware attestation or sandbox.
No environment-variable overrides. Resource/queue preflight is separate.
"""
from __future__ import annotations

import platform
import socket


class GameboxRequired(RuntimeError):
    """Real TTS is not authorized on this host."""


def require_gamebox() -> None:
    """Use OS-reported hostname, not HOSTNAME or a caller-supplied setting."""
    try:
        system = platform.system()
        hostname = socket.gethostname()
    except Exception as exc:
        raise GameboxRequired("GAMEBOX_REQUIRED: host identity unavailable") from exc
    if system != "Linux" or hostname != "danny-serv":
        raise GameboxRequired(
            "GAMEBOX_REQUIRED: real TTS allowed only on Linux danny-serv"
        )
