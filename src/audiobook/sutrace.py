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

# Full dotted-path allowlist of config keys accessed by voicecfg.prepare_text,
# leadin.carrier/fires, and synth.chunk_fragments.  Derived from source inspection
# (T15-7.0d, D2).  Any access outside this set means an unexpected dependency has
# been introduced — fail closed rather than silently ignore it.
DECLARED_CONFIG_PATHS = frozenset({
    # voicecfg.prepare_text
    "text_prep",
    "text_prep.yo_restore",
    "text_prep.strip_quotes",
    "text_prep.open_end",
    "text_prep.ensure_terminal",
    # leadin.carrier / leadin.fires
    "render",
    "render.leadin",
    "render.leadin.phrase",
    "render.leadin.max_chars",
    # synth.chunk_fragments
    "pauses_ms",
    "pauses_ms.enum_pause_ms",
    "pauses_ms.sentence",
})

# Backward-compatible alias kept so existing tests that import the old name continue.
DECLARED_TOP_LEVEL_CONFIG_KEYS = DECLARED_CONFIG_PATHS


class _DeepRecordingConfig:
    """Wraps a config dict and records every mapping access as a full dotted path.

    Nested dict values returned by .get() / [] are themselves wrapped so that
    access to e.g. config["text_prep"]["strip_quotes"] records the path
    "text_prep.strip_quotes".  Non-dict values (ints, bools, strings) are
    returned as-is.  Production helpers never check isinstance(config, dict), so
    this pure wrapper is safe to pass in place of a plain dict.
    """

    def __init__(self, inner: dict, prefix: str = "",
                 accessed: set[str] | None = None) -> None:
        self._inner = inner
        self._prefix = prefix
        self._accessed: set[str] = accessed if accessed is not None else set()

    def _path(self, key: str) -> str:
        return f"{self._prefix}.{key}" if self._prefix else str(key)

    def _wrap(self, value, key: str):
        if isinstance(value, dict):
            return _DeepRecordingConfig(value, self._path(key), self._accessed)
        return value

    def get(self, key, default=None):  # type: ignore[override]
        self._accessed.add(self._path(key))
        value = self._inner.get(key, default)
        return self._wrap(value, key)

    def __getitem__(self, key):
        self._accessed.add(self._path(key))
        value = self._inner[key]
        return self._wrap(value, key)

    def __contains__(self, key):  # type: ignore[override]
        self._accessed.add(self._path(key))
        return key in self._inner

    def __bool__(self) -> bool:
        return bool(self._inner)


# Backward-compatible alias.
_KeyRecordingConfig = _DeepRecordingConfig


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
    status: str              # "ok" | "trace_mismatch" | "trace_unsupported"


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
              cfg: _DeepRecordingConfig, phrase_stored,
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
    """Trace all SUs for one section.

    Raises ValueError on trace_mismatch or unexpected config keys accessed.
    Mirrors production synth._synth_one_chunk exactly:
      - len(frags)==1  → use row["text"], row_leadin(row), open_end  (fragment=None)
      - len(frags)>1   → per-fragment text with question-mark trim, AUTO phrase,
                         open_end=False, integer fragment indexes.
    """
    from audiobook import paths
    from audiobook import leadin as leadin_mod
    from audiobook.synth import chunk_fragments, row_leadin

    # Single tracking wrapper shared for the whole section so the guard sees the
    # union of all keys accessed during this call.
    cfg = _DeepRecordingConfig(config)
    rows = _read_manifest(paths.OUT / "sections" / section / "manifest.jsonl")
    results: list[SUTrace] = []

    for row in rows:
        phrase_arg = row_leadin(row)   # leadin.AUTO if "leadin" absent in row
        open_end = row.get("open_end", False)

        # Pass cfg so chunk_fragments' pauses_ms.* accesses are tracked.
        frags = chunk_fragments(row["text"], cfg)

        if len(frags) == 1:
            # Production _synth_one_chunk: len(frags)==1 → prepare on row["text"]
            # with the row's stored phrase and open_end flag.
            t = _trace_su(section, row["id"], None, row["text"], open_end,
                          cfg, phrase_arg, table, sentinel)
            if t.status == "trace_mismatch":
                raise ValueError(
                    f"trace_mismatch: section={section} chunk={row['id']}"
                )
            results.append(t)
        else:
            # Production _synth_one_chunk: multi-fragment enum split.
            for fi, (frag_text, _pause, is_enum) in enumerate(frags):
                frag = frag_text.rstrip("?") if is_enum and frag_text.endswith("?") else frag_text
                t = _trace_su(section, row["id"], fi, frag, False,
                              cfg, leadin_mod.AUTO, table, sentinel)
                if t.status == "trace_mismatch":
                    raise ValueError(
                        f"trace_mismatch: section={section} chunk={row['id']} frag={fi}"
                    )
                results.append(t)

    unexpected = cfg._accessed - DECLARED_CONFIG_PATHS
    if unexpected:
        raise ValueError(f"Unexpected config keys accessed: {unexpected}")

    return results
