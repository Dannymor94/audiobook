"""Model-variant and model-input settings shared by the chunker (hashing) and
synth (rendering).

Pure config + string logic — no torch, no models — so the chunker can import it
cheaply and both sides derive the model id, the latents file and the text fed
to the model the SAME way. A mismatch between the hash and the synth path would
silently re-render (or worse, silently keep) the wrong audio.

Everything here defaults to the pre-1.7B behaviour when the config keys are
absent: variant "0.6B" keeps the old model id (``model.name``) and the old
latents filename, and ``text_prep`` off returns the text unchanged — so an
untouched 0.6B config hashes exactly as before.
"""
from __future__ import annotations

from pathlib import Path

from audiobook import paths

DEFAULT_VARIANT = "0.6B"
QUANTIZE_MODES = ("none", "int8")
_HUB_TEMPLATE = "models--Qwen--Qwen3-TTS-12Hz-{variant}-Base"


# ── model variant ──────────────────────────────────────────────────────────────

def variant(config: dict) -> str:
    """``model.variant`` from config ("0.6B" | "1.7B"), default 0.6B."""
    return str((config.get("model") or {}).get("variant", DEFAULT_VARIANT))


def quantize(config: dict) -> str:
    """``model.quantize`` from config ("none" | "int8"), default "none".

    int8 = torch dynamic quantization of the Linear layers (CPU only); an
    experiment, off by default. Anything else is a config typo → fail loud."""
    q = (config.get("model") or {}).get("quantize", "none")
    q = "none" if q is None else str(q).strip().lower()
    if q not in QUANTIZE_MODES:
        raise SystemExit(
            f"model.quantize: недопустимое значение {q!r} "
            f"(допустимо: {', '.join(QUANTIZE_MODES)})")
    return q


def model_id(config: dict) -> str:
    """Model identity for the chunk hash. 0.6B keeps the bare ``model.name`` so
    existing 0.6B manifests keep their hashes; any other variant is suffixed, so
    switching variant re-queues every chunk (weights differ → audio differs).
    ``quantize: int8`` appends "-int8" so int8 audio never mixes with fp32 in the
    cache; ``none`` adds nothing, so existing hashes are unchanged."""
    name = config["model"]["name"]
    v = variant(config)
    mid = name if v == DEFAULT_VARIANT else f"{name}-{v}"
    return f"{mid}-int8" if quantize(config) == "int8" else mid


def hub_dir(v: str) -> Path:
    """Local HF cache dir of the Qwen3-TTS weights for variant ``v``."""
    return paths.MODELS / "hf" / "hub" / _HUB_TEMPLATE.format(variant=v)


def latents_path(config: dict) -> Path:
    """Voice-clone prompt file for the configured reference AND model variant.

    Latents are model-specific (0.6B hidden=1024, 1.7B hidden=2048), so each
    variant has its own file next to the reference wav:
      0.6B → ref/ref1.latents.pt          (unchanged, pre-1.7B name)
      1.7B → ref/ref1.latents_1.7b.pt
    """
    ref = paths.ROOT / config["reference"]["path"]
    v = variant(config)
    if v == DEFAULT_VARIANT:
        return ref.with_suffix(".latents.pt")
    return ref.with_name(f"{ref.stem}.latents_{v.lower()}.pt")


# ── text fed to the model ──────────────────────────────────────────────────────

_QUOTES = str.maketrans("", "", "«»“”„")
# Terminal marks that already give the model a stop signal. With quotes kept, a
# closing quote also counts (the old sentinel rule); with quotes stripped it is
# gone, so it is not in the stripped set.
_TERMINAL_STRIPPED = frozenset(".!?…:;")
_TERMINAL_QUOTED = frozenset(".!?…:;»\"")


def prepare_text(text: str, config: dict) -> str:
    """The chunk text as the model should read it, before lead-in/respell.

    ``text_prep.strip_quotes``: drop «» “ ” „ — quotation marks are inaudible
    and made the model read short quoted phrases with a foreign accent.
    ``text_prep.ensure_terminal``: append "." when the text has no terminal
    mark — without one the model garbled a short phrase at word level.
    Validated by ear on 1.7B (quote_test variant c: «Я тебя чувствую» →
    "Я тебя чувствую."). Both default off. The book text and the manifest are
    never changed; this only shapes the model input (and so enters the hash
    through ``synth_text``)."""
    tp = config.get("text_prep") or {}
    t = text
    strip = bool(tp.get("strip_quotes"))
    if strip:
        t = t.translate(_QUOTES).strip()
    if tp.get("ensure_terminal"):
        terminal = _TERMINAL_STRIPPED if strip else _TERMINAL_QUOTED
        s = t.rstrip()
        if s and s[-1] not in terminal:
            t = s + "."
    return t
