# T15-7 WP-0 — Coordinator Acceptance Record

**Date:** 2026-11-12  
**Source:** Independent Codex Sol reports supplied to the coordinator. This record preserves their relevant non-sensitive results; it is not a second local execution by the coordinator.  
**Authoritative architecture:** `tasks/T15-7-FINAL-ADR.md`  
**Implementation plan:** `tasks/T15-7-EXECUTION-PLAN.md`

## T15-7.0b — Protect local gold and corpus outputs

**Independent Sol verdict:** PASS at `7cb8688589f81992c8c4e50cb04e9996e7c2b533`, directly compared with `b2e22bde493847eb1b05d08ae8dddefc7fee09a3`.

- Only `.gitignore` (3 added lines) and the task status (`todo` -> `review`) changed.
- `/text/stress_gold*.tsv` protects local gold/todo/archive/transaction paths.
- Existing `out/` and `/out` protection preserved.
- Six `git check-ignore` checks succeeded; six individual Git index checks returned not-tracked; S2/S3/S4 tracked counts 0.
- Synthetic fixture path remains eligible for Git.
- Independent `uv run pytest -q`: **1293 passed, 5 skipped**, exit 0.
- No private corpus, audio or short-fragment hash artifacts were committed.
- Task file still showed `status: review` when this record was created; a permitted task-status-only update to `done` may be included in the next agent's metadata commit after verifying this independent PASS.

## T15-7.0d — Read-only implementation contracts

**Independent Sol verdict:** PASS. Reference SHA `437471da6f11b202a6a1eeb0fd6f30f3b1bfa412`, local code SHA `7cb8688589f81992c8c4e50cb04e9996e7c2b533`. The sole intervening commit added scouting documentation; production code identical.

- **D1 manifest/config:** all 5,127 frozen disk rows have `n:int`, `id:str`, `text:str`, `pause_after_ms:int`. Optional `open_end` and `leadin` absent in this snapshot; preserve default semantics. `hash` supplies cache/freshness evidence. `seed_override` does not affect SU text.
- **D2 SU flow:** manifest text -> `voicecfg.prepare_text` -> stored or automatic lead-in/pad -> `pronounce.respell` -> sentinel -> TTS engine input. Enumeration fragments use the production fragment branch with question-mark stripping and AUTO lead-in; active `enum_pause_ms=0`, so current disk snapshot uses normal SUs. `phrase=None` and `phrase=""` must remain distinct even though neither pads.
- **D3 identities/Unicode:** `unit_id` in `unitmap.Atom` is zero-based **int**, stable only for unchanged ordered units. `WordOcc` ADR specifies decimal string for its serialized representation; this is a boundary conversion for the later WP-2, **not** a reason to change 6C11. Target units 4,624; U+0301 source occurrences 0.
- **D4 inventory:** `stress_fp.load_current` accepts extra summary keys but verifies only archived summary SHA, not TSV freshness. Published inventory algorithm v3 is stale against code v4. No `inventory.tmp` or `inventory.old`; `inventory/current.json` present; 6 archive generations/summaries. No recovery/publisher code invoked.
- **D5 mapping:** read-only guarded audit PASS **56/56** target sections (58 total, 2 approved exclusions), 4,624 units, 5,127 chunks, 77,998/77,998 atoms consumed, 0 errors; input checksums unchanged. No manuscript excerpts disclosed.
- **D6 readiness:** 7.1a technical prerequisites PASS subject to coordinator authorization. S2 local fixture path ignored and S1 synthetic path not ignored. `ensure_manifest_current` and read-only impact outcomes still need capturing as ACTUAL outcomes during 7.1a; never assume they PASS or have impact=0.
- Independent full pytest: **1293 passed, 5 skipped**, exit 0. Worktree clean.

## Gate and next action

**WP-0 requirement for WP-1:** SATISFIED (7.0b PASS, 7.0d PASS, Final ADR approved).

**Authorize no work outside WP-1**: the coordinator will separately authorize Sonnet T15-7.1a + T15-7.2 as a bounded combined package with one Sol independent review on its final pinned SHA. All individual STOP conditions and tests remain mandatory.

Unresolved later gates:
- **B1:** reproducible pinned offline RUAccent probe evidence, required before 7.1b and 7.5.
- **B2:** owner chooses future rendering snapshot; not required for WP-1/WP-2.
- **B3:** absent approval journal; F2 remains unknown and does not block.
- **B4:** publisher crash tests in 7.6.

Production 6C11, synth inputs and cache remain unchanged. No full render or external transfer is authorized.
