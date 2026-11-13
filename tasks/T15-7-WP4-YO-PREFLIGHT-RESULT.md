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

## G0 full-corpus run on SHA 52bcb9a — coverage PASS, test schema FAIL (reported)

Owner relayed Sonnet's **offline real-.venv, exclusive worktree** verification at PR #3 SHA
`52bcb9a1aea556df76c67b4b4f9bd2b20330b6ed`:

| Evidence | Reported result |
|---|---|
| Four targeted test modules | **49 passed, 2 failed, 0 skipped** |
| Full pytest with `-rs` | **1842 passed, 2 failed, 11 skipped** |
| Additional five baseline-dependent tests | **5 passed, 0 failed** after attaching local S2 baseline |
| Private read-only CLI audit | `G0_COVERAGE_MEASURED`, exit 0, `g0_closed=false` |
| Eligible source→fragment→pre-respell mapping | **51,629 verified / 51,629 eligible**, 0 unsupported |
| Selected source-key identity and mapping | **320 verified / 320 selected**, 0 unsupported |
| Inventory | 76,036 rows, 56 sections, 5,121 chunks with eligible occurrences |
| Verified pre-restored | **223 eligible**, **40 selected** |
| Selected pre=0/post=0 | **280** |
| Selected pre=1/post=1 | **40** |
| Selected pre/post mismatches | **0** |
| Source/conf/metadata files changed | **0/416**; no added/deleted files |

The **two failures were output-schema bugs in this test-only collector**, not mapping failures:
`test_synthetic_current_sample_coverage_is_aggregate_only` raised `KeyError: selected_pre_restored` in a zero-restoration fixture; `test_bad_fragment_is_reported_as_unsupported_not_no_restoration` raised `KeyError: selected_verified` in an unsupported fixture. The `Counter` returned `0` when indexed but the final JSON iterated only present keys, omitting zero buckets.

**Coordinator self-fix:** updated `tests/stress_yo_g0_readonly.py` to initialize all six eligible/selected observation buckets, four pre/post cells and both pre-restored counters to explicit 0; each stratum also emits a stable six-status shape. Added a new regression test comparing full schemas between supported/unsupported fixtures plus zero-key assertions in existing tests. Commits `10672830` and `43c0749b`. A stdlib-only isolated `Counter` schema smoke passed (18 fixed keys). **These new changes have NOT yet run in the actual audiobook `.venv`; the two prior failures remain OPEN until a fresh focused pytest PASS on the final PR SHA.**

The five additional baseline-dependent SKIPs were individually resolved: four in `test_sutrace.py`, one in `test_wordprov.py`. The other six SKIPs have documented gating: three `RUN_SLOW=1`, two absent torch quantization engine, one optional pinned offline smoke. The 11 original SKIPs therefore do not, by themselves, indicate an execution regression.

### Global fingerprints (counts and global fingerprints only; no private word/row data)

```text
source_fp          e0f552b20a178b2fbf6257a4db04ed4160acc085b191162e2c73b3c8520e44a1
analysis_fp        bfd3b9857820017dc2e5d1924e80cfbac70e758628e1c0dfbd648922d2e3f010
sample_fp          4440c58699ea22de8b53eb96587ff4b72f5d426247e5a731c6de91cdd41f0986
yo_map_sha256      da007a0acfcdff347138aeb70a9ea2fd4e99a81f896ba4cc47898ce988923e74
norm_content_sha256 fcc0cc79f878fe135173b7ae9435262c72f4023b19237a59fbbf2dfc688bf112
prep_config_sha256 b7e75ac564e7da04b1ba1edceeb713df5cca3703dc1f1321c09e0421a371d18a
```

**Interpretation:** The complete-current-snapshot **mapping-coverage subgate** is empirically PASS. This does **not** approve Option B/B′, bind future per-label historical YO evidence, or resolve sample/1→sample/2 or C3/YO completeness. Broader G0 / WP-4 remains BLOCKED and `g0_closed=false`.

**Narrow follow-up:** rerun the four PR #3 modules after the zero-counter fix in the actual installed offline audiobook `.venv`, recording the final SHA. Optionally run the full suite once with unchanged S2 baseline. Do NOT rerun real sample/merge/score, edit gold, change production code or merge the draft PR without a separate owner/architecture decision.


## G0 installed-runtime feedback from Sonnet (reported for pinned SHA cab53397)

The owner supplied Sonnet's read-only result for **PR #3 SHA `cab53397dc551ac894e539ef51dfdae043b0adcb`** in the real audiobook `.venv`:

- Focused `test_stress_yo_prerespell_proof.py` + `test_stress_yo_fragment_witness.py`: **43 passed / 0 failed / 0 skipped in 0.94 s**; all four previously skipped installed-module tests ran.
- Full worktree regression: **1,836 passed / 11 skipped in 28.11 s**.
- **Regression arithmetic cross-check:** prior WP-4 report had 1,798 passed / 6 skipped (1,804 collected); this G0 run reports 1,836 passed / 11 skipped (1,847 collected). Delta = **+43 collected, +38 passed, +5 skipped**. Since the 43 focused G0 tests all PASS, this may indicate five formerly passing unrelated tests were skipped under a different machine/environment. **Require `uv run pytest -q -rs` skip reasons and compare test node IDs before any final QA acceptance.** Do not infer a regression solely from counts, and do not claim parity without the evidence.
- Real-module source_key→chunk ordinal→fragment test: four synthetic occurrences across single/two fragments PASS.
- `voicecfg.prepare_text` before respell agrees with direct `yo.restore` on the synthetic controlled map; phrase-respell 2→1 token explicitly excluded; `yo_restore=False` does not inherit respell's ё; stale `yo.book_map` at fixed maximum mtime reproduced.
- Owner reports no protected-file mutation, no real sample regeneration and no merge.

These are **reported Sonnet results**, not a separate coordinator-run independent Sol review, not evidence of real-corpus coverage, and not test results for the later commits of PR #3. **G0 remains PARTIAL / OPEN.**

## Next self-executed deliverable — local read-only aggregate coverage script

The coordinator added `tests/stress_yo_g0_readonly.py` and synthetic `tests/test_stress_yo_g0_readonly.py` to PR #3. The script reads the *validated current* v5 inventory and existing local section manifests, proves exact source_key/chunk-word/raw-fragment positions, checks pre-respell token with direct pinned-map restoration, and reports only counts and **global** source/map/config/sample hashes. It rejects an mtime-stale `yo.book_map` and checks source bytes, map and config again before reporting; it never writes ledgers, inventory, manifests, score JSON, audio or model files. G0 remains false even on zero-unsupported coverage.

**These two newly authored files have not yet been executed in the actual audiobook `.venv`; do not infer PASS from the earlier 43-test report.** Run only in an isolated, offline worktree with local private data available; do not commit/copy its private inputs or row identities. Aggregate JSON only.

```bash
export UV_NO_SYNC=1
export UV_PROJECT_ENVIRONMENT=/Users/danny/Documents/audiobook/.venv
export PYTHONPATH=/tmp/audiobook-wp4-g0-cab5339/src  # update to the NEW worktree src
export PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

uv run pytest -q -p no:cacheprovider tests/test_stress_yo_g0_readonly.py
python -B tests/stress_yo_g0_readonly.py
```

Use the *actual new isolated worktree path* for `PYTHONPATH`; the old cab5339 path is an example, not a correct path for later commits. Report only `status`, aggregate `counts`, `selected_by_stratum`, `yo_map_sha256`, `norm_content_sha256`, `prep_config_sha256`, `sample_fp` and a privacy/baseline statement. Do NOT transmit real source words, source keys, fragment strings, paths containing book text, per-token hashes, labels or the owner's S4 files.

### Additional source-only fingerprint oracle

`tests/test_stress_yo_sample_policy_collision.py` demonstrates a **current `sample/1` collision** with two invented words: swap which word belongs to `omograph` while preserving the exact selected keys, stratum counts, source_fp, analysis_fp and current policy targets. The resulting `sample_fp` is identical even though `strata_by_key` differs. A proposed, sorted **assignment digest** would distinguish the states. This is a characterization test of the existing code, **not an approved `sample/2` algorithm**, and was added after Sonnet's original 43 PASS run.

### Exact minimal new-worktree commands

```bash
# Run from an isolated worktree checked out to PR #3's latest head.
export UV_NO_SYNC=1
export UV_PROJECT_ENVIRONMENT=/Users/danny/Documents/audiobook/.venv
export PYTHONPATH="$PWD/src"
export PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
uv run pytest -q -p no:cacheprovider \
  tests/test_stress_yo_prerespell_proof.py \
  tests/test_stress_yo_fragment_witness.py \
  tests/test_stress_yo_g0_readonly.py \
  tests/test_stress_yo_sample_policy_collision.py
uv run python -B tests/stress_yo_g0_readonly.py
```

**No new-test results are claimed at this head.** The collector must return `G0_COVERAGE_MEASURED` or `G0_UNSUPPORTED_PRESENT`, with only aggregate counts and global fingerprints. `ERROR` is an explicit preflight failure, not a zero-restoration result. The command does not write the sample or owner S4 gold/todo/archive and must not be modified to do so. Following the run, check all protected S4 file digests against their before snapshot locally without posting their contents. Owner Option B/B′ approval remains pending.

If any audit preflight fails, returns `ERROR` or yields `G0_UNSUPPORTED_PRESENT`, keep B′ BLOCKED and return only aggregate error codes/counts; no heuristic fallback. This script is a **measurement tool**, not the approved restoration observer or an auto-fix. Current production code remains unmodified.


**Date:** 2026-11-13. **Decision:** `PARTIAL_PROOF / G0_NOT_CLOSED`. **Owner:** B and B′ remain unapproved. No source/production/ADR/gold changes, no model/voice/manuscript uploads, no render.

## Source-verified pipeline facts

- `voicecfg.prepare_text` calls `yo.restore` when `text_prep.yo_restore` is on; quote stripping, terminal punctuation and open-end processing follow. It runs **before** the lead-in, `pronounce.respell` and sentinel.
- `SUTrace.prep_text` and `WordOcc.form_synth` refer to **post-respell** synthesis tokens, not the candidate required for historical YO evidence.
- `wordprov.process_section_occs` exposes `chunk_word_index` for the original source stream, while `su_token_index` is from the post-respell SUTrace token stream. These two indices **must never be silently equated**.
- `yo.book_map()` derives from local .norm content and a cached mtime-based lookup. A same-invocation observation must pin/recheck the **actual mapping content digest**, not assume a later `book_map()` call reproduces a historical result. An mtime timestamp is not immutable evidence.

## Tests independently authored

1. `tests/test_stress_yo_prerespell_proof.py`: **test-only** deterministic experiment. Requires two matching observations: exact source-token→prepared-token at a **grounded** ordinal and direct `yo.restore` on the raw fragment under a controlled map. Pure forward `е/Е→ё/Ё` edits only; NFC, case, unchanged word count and source-vowel coordinates verified. Reject no ordinal, mixed/reverse edits, changed word count, lead-in contamination, prep/direct disagreement. This file contains two repo-module integration tests with `pytest.importorskip` that **must execute on Sonnet's installed project**.
2. `tests/test_stress_yo_fragment_witness.py`: **test-only** deterministic exact ordinal witness. If the ordered source chunk words match the concatenation of all raw fragment word streams exactly, then the verified `chunk_word_index` maps to one fragment + local ordinal; repeated same-spelling words are disambiguated only by this position. Any mismatch, duplicate insertion, missing fragment, case change, Unicode change or lead-in inclusion returns `UnsupportedWitness`. This test does NOT derive the source chunk word stream or prove correspondence to `source_key` on its own. It also has a project-only source-witness integration probe using `test_stress_eval_sample.context_for` and real `synth.chunk_fragments` for single and enum-multifragment cases. A separate project-only synthetic probe demonstrates that `yo.book_map()` can return cached data after content changes if path and maximum mtime stay constant; a content digest must therefore be pinned.

**Local execution:** An equivalent standalone prototype (the full pre-respell matrix, with two project-import tests skipped due to missing installed private audiobook package) ran **26 passed, 2 skipped** for each `PYTHONHASHSEED=1,2,3`. The exact fragment-witness pure tests ran **14 passed** for each of the same seeds. After adding project-only WordOcc/fragment and cached-map probes, the complete local prototype reports **40 passed, 4 skipped** at each of the three hash seeds. Four skips require the missing installed audiobook modules. These counts represent equivalent local synthetic/prototype testing; the GitHub pre-respell test file has not itself been executed in the repository runtime. Do **not** quote these counts as the project full suite, or as proof that the code from the pushed branch has run end-to-end. GitHub PR source was verified on readback.

## G0 outstanding — required before architectural approval

1. Using actual `WordOcc` + `SectionMap` and `chunk_fragments`, independently validate that the source chunk word stream equals the concatenated raw fragment word stream. Prove `source_key → chunk_word_index → fragment ordinal` for synthetic single and multi-fragment cases. **No token search or post-respell index as fallback.** Unsupported mappings must stop.
2. Run all **four** project-only probes against the actual `voicecfg`, `yo`, `pronounce`, `wordprov` and `synth.chunk_fragments` modules in the proper offline audiobook environment; their imports were unavailable to the coordinator's isolated Python. Assert that a phrase-level pronunciation override cannot masquerade as `yo_restore`.
3. Snapshot `yo_restore` mapping and configuration with an immutable content digest, not mtime alone; verify the cache-staleness reproducer and ensure a mapping/config change between observation, reviewer labeling and score invalidates **only the restoration evidence**. Never reconstruct historical evidence from current synthesis or mtime alone.
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
