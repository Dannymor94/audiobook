---
id: T15-7-WP4-YO-PREFLIGHT
title: Read-only synthetic pre-respell and fragment-ordinal proof
status: review
owner: codex-gpt-6
agent: coordinator
branch: task/T15-7-yo-risk-audit
estimate_active_h: 2-5
actual_active_h: unknown
---

# T15-7 WP-4 — G0 pre-respell feasibility probe, not GO

**Date:** 2026-11-13. **Decision:** `PARTIAL_PROOF / G0_NOT_CLOSED`. **Owner:** B and B′ remain unapproved. No source/production/ADR/gold changes, no model/voice/manuscript uploads, no render.

## Source-verified pipeline facts

- `voicecfg.prepare_text` calls `yo.restore` when `text_prep.yo_restore` is on; quote stripping, terminal punctuation and open-end processing follow. It runs **before** the lead-in, `pronounce.respell` and sentinel.
- `SUTrace.prep_text` and `WordOcc.form_synth` refer to **post-respell** synthesis tokens, not the candidate required for historical YO evidence.
- `wordprov.process_section_occs` exposes `chunk_word_index` for the original source stream, while `su_token_index` is from the post-respell SUTrace token stream. These two indices **must never be silently equated**.
- `yo.book_map()` derives from local .norm content and a cached mtime-based lookup. A same-invocation observation must pin/recheck the **actual mapping content digest**, not assume a later `book_map()` call reproduces a historical result. An mtime timestamp is not immutable evidence.

## Tests independently authored

1. `tests/test_stress_yo_prerespell_proof.py`: **test-only** deterministic experiment. Requires two matching observations: exact source-token→prepared-token at a **grounded** ordinal and direct `yo.restore` on the raw fragment under a controlled map. Pure forward `е/Е→ё/Ё` edits only; NFC, case, unchanged word count and source-vowel coordinates verified. Reject no ordinal, mixed/reverse edits, changed word count, lead-in contamination, prep/direct disagreement. This file contains two repo-module integration tests with `pytest.importorskip` that **must execute on Sonnet's installed project**.
2. `tests/test_stress_yo_fragment_witness.py`: **test-only** deterministic exact ordinal witness. If the ordered source chunk words match the concatenation of all raw fragment word streams exactly, then the verified `chunk_word_index` maps to one fragment + local ordinal; repeated same-spelling words are disambiguated only by this position. Any mismatch, duplicate insertion, missing fragment, case change, Unicode change or lead-in inclusion returns `UnsupportedWitness`. This test does NOT derive the source chunk word stream or prove correspondence to `source_key` on its own.

**Local execution:** An equivalent standalone prototype (the full pre-respell matrix, with two project-import tests skipped due to missing installed private audiobook package) ran **26 passed, 2 skipped** for each `PYTHONHASHSEED=1,2,3`. The exact fragment-witness test file ran **14 passed** for each of the same seeds. This yields **40 local pure/synthetic passes per seed** across prototypes, with **2 project-integration tests not run**. Do **not** quote these counts as the project full suite, or as proof that the code from the pushed branch has run end-to-end. GitHub PR source was verified on readback.

## G0 outstanding — required before architectural approval

1. Using actual `WordOcc` + `SectionMap` and `chunk_fragments`, independently validate that the source chunk word stream equals the concatenated raw fragment word stream. Prove `source_key → chunk_word_index → fragment ordinal` for synthetic single and multi-fragment cases. **No token search or post-respell index as fallback.** Unsupported mappings must stop.
2. Run the two repo-integrated tests against the actual `voicecfg`, `yo` and `pronounce` modules in the proper offline project environment; their imports were unavailable to the coordinator's isolated Python. Assert that a phrase-level pronunciation override cannot masquerade as `yo_restore`.
3. Snapshot `yo_restore` mapping and configuration with an immutable digest; ensure a mapping/config change between observation, reviewer labeling and score invalidates **only the restoration evidence**. Never reconstruct historical evidence from current synthesis or mtime alone.
4. Test real (aggregate-only) coverage rates by mapping status after source-private/local validation, without copying words, labels, per-row hashes or contexts to Github/chat. An unalignable case is `UNSUPPORTED`, not negative YO evidence.
5. Before applying B′, resolve the independent sample/1→sample/2 and current-versus-history C3/YO quality completeness questions in the architecture audit; no gold/sampling migration is permitted yet.

## Suggested narrow agent command (after coordinator GO for read-only tests only)

```bash
PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  uv run pytest -q -p no:cacheprovider \
  tests/test_stress_yo_prerespell_proof.py \
  tests/test_stress_yo_fragment_witness.py
```

This is **not** permission to edit protected production code, regenerate inventory or publish a new gold sample. Draft PR #3 holds only test files and audit documentation.
