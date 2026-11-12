"""Observational SU trace: captures what the existing synthesizer would receive.

Read-only. Does not import or call synth, worker, voicecfg, pronounce or engine
from the production side — only uses the pure preparation functions via their
public interfaces. The synthesis path is unmodified and unaware of this module.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

# Config keys accessed by voicecfg.prepare_text and leadin.fires/pad.
DECLARED_TOP_LEVEL_CONFIG_KEYS = frozenset({"text_prep", "render"})


class _KeyRecordingConfig(dict):
    """Wraps a config dict and records every top-level key read."""

    def __init__(self, inner: dict) -> None:
        super().__init__(inner)
        self._accessed: set[str] = set()

    def get(self, key, default=None):  # type: ignore[override]
        self._accessed.add(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self._accessed.add(key)
        return super().__getitem__(key)

    def __contains__(self, key):  # type: ignore[override]
        self._accessed.add(key)
        return super().__contains__(key)


@dataclass
class SUTrace:
    section: str
    chunk_id: str
    fragment: int | None
    prep_text: str           # final string sent to TTS engine
    pad_len: int             # chars of lead-in prefix in prep_text (0 when no lead-in)
    matches: list[dict]      # respell hits in post_pad: [{start,end,key,value}]
    final_sha256: str        # sha256(prep_text.encode())
    phrase_sha256: str | None  # sha256(phrase.encode()) or None
    status: str              # "ok" | "trace_mismatch"


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _read_manifest(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _reconstruct(post_pad: str, matches: list[dict]) -> str:
    """Rebuild respelled string from match list; must equal pronounce.respell output."""
    parts: list[str] = []
    pos = 0
    for m in matches:
        parts.append(post_pad[pos:m["start"]])
        parts.append(m["value"])
        pos = m["end"]
    parts.append(post_pad[pos:])
    return "".join(parts)


def _trace_su(section: str, chunk_id: str, fragment: int | None,
              text: str, open_end: bool,
              cfg: _KeyRecordingConfig, phrase_stored,
              table: dict, sentinel: str) -> SUTrace:
    """Build one SUTrace record for a single text fragment."""
    from audiobook import leadin as leadin_mod
    from audiobook import voicecfg
    from audiobook.pronounce import build_pattern, respell
    from audiobook.synth import apply_sentinel

    text_prepped = voicecfg.prepare_text(text, cfg, open_end)
    if phrase_stored is leadin_mod.AUTO:
        phrase = leadin_mod.fires(text_prepped, cfg)
    else:
        phrase = phrase_stored

    post_pad = leadin_mod.pad(text_prepped, phrase) if phrase else text_prepped

    if not post_pad.endswith(text_prepped):
        return SUTrace(
            section=section, chunk_id=chunk_id, fragment=fragment,
            prep_text="", pad_len=0, matches=[], final_sha256="",
            phrase_sha256=None, status="trace_unsupported",
        )
    pad_len = len(post_pad) - len(text_prepped)

    pat = build_pattern(table)
    matches: list[dict] = (
        [{"start": m.start(), "end": m.end(), "key": m.group(0), "value": table[m.group(0)]}
         for m in pat.finditer(post_pad)]
        if pat else []
    )
    respelled = respell(post_pad, table)
    if _reconstruct(post_pad, matches) != respelled:
        return SUTrace(
            section=section, chunk_id=chunk_id, fragment=fragment,
            prep_text=respelled, pad_len=pad_len, matches=matches,
            final_sha256="", phrase_sha256=None, status="trace_mismatch",
        )

    final = apply_sentinel(respelled, sentinel)
    return SUTrace(
        section=section,
        chunk_id=chunk_id,
        fragment=fragment,
        prep_text=final,
        pad_len=pad_len,
        matches=matches,
        final_sha256=_sha256(final),
        phrase_sha256=_sha256(phrase) if phrase is not None else None,
        status="ok",
    )


def trace_section(section: str, config: dict, table: dict, sentinel: str) -> list[SUTrace]:
    """Trace all SUs for one section. Raises ValueError on trace_mismatch or unexpected config keys."""
    from audiobook import paths
    from audiobook import leadin as leadin_mod
    from audiobook.synth import chunk_fragments, row_leadin

    cfg = _KeyRecordingConfig(config)
    rows = _read_manifest(paths.OUT / "sections" / section / "manifest.jsonl")
    enum_pause_ms = config.get("pauses_ms", {}).get("enum_pause_ms", 0)
    results: list[SUTrace] = []

    for row in rows:
        phrase_arg = row_leadin(row)   # leadin.AUTO if "leadin" absent in row
        open_end = row.get("open_end", False)

        if enum_pause_ms:
            frags = chunk_fragments(row["text"], config)
        else:
            frags = [(row["text"], 0, False)]

        for fi, (frag_text, _pause, is_enum) in enumerate(frags):
            fragment = fi if len(frags) > 1 else None
            # strip trailing ? from enum items — production behaviour in _synth_one_chunk
            text = frag_text.rstrip("?") if is_enum and frag_text.endswith("?") else frag_text
            # enum fragments always use AUTO phrase and open_end=False (production default args)
            eff_phrase = leadin_mod.AUTO if len(frags) > 1 else phrase_arg
            eff_open_end = False if len(frags) > 1 else open_end

            t = _trace_su(section, row["id"], fragment, text, eff_open_end,
                          cfg, eff_phrase, table, sentinel)
            if t.status == "trace_mismatch":
                raise ValueError(
                    f"trace_mismatch: section={section} chunk={row['id']} fragment={fragment}"
                )
            results.append(t)

    unexpected = cfg._accessed - DECLARED_TOP_LEVEL_CONFIG_KEYS
    if unexpected:
        raise ValueError(f"Unexpected config keys accessed: {unexpected}")

    return results
