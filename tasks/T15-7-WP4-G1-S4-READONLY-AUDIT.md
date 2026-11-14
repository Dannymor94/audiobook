---
id: T15-7-WP4-G1-S4-READONLY-AUDIT
title: Owner-authorized local S4 C3 compatibility census
status: blocked_pending_local_private_s4
owner: owner
agent: coordinator
branch: task/T15-7-yo-risk-audit
---

# T15-7 WP4 — read-only S4 compatibility: owner GO, no migration

**Owner instruction:** 2026-11-14. **A / G1.1–G1.5:** APPROVED_IN_PRINCIPLE, not implementation authorization. **B / G1.6:** DEFERRED_NOT_APPROVED. Owner authorized *only* aggregate read-only S4 compatibility measurement, with no private book text, gold rows or per-occurrence hashes leaving the machine.

## Deliverables

- `tests/stress_s4_c3_readonly.py`: read-only script; emits only safe aggregate JSON; no manual sample/merge/score invocation, no file writes. Verifies raw S4 bytes unchanged before and after; validates exact TSV column headers and row widths, refuses symlinks; internally pins source and YO snapshots and validates current inventory. Uses established G0 strict pre-respell observation and source-ordinal witness.
- `tests/test_stress_s4_c3_readonly.py`: synthetic-only oracles for absent/present S4, repeated keys vs distinct historical identities, current conflicts, filled unmerged todo, invalid/partial rows, malformed TSV, symlink safety and selected RESTORED with rule/flag truth table.

**Local synthetic helper smoke (coordinator's separate test harness): 5 PASS / 0 FAIL** for absent file, repeated historical keys, current conflicting labels, filled unmerged todo and malformed/symlink refusal. The exact GitHub combined tests and full end-to-end private S4 audit have **not** run in the owner's audiobook .venv at this writing. Never call them project PASS.

## Execution — owner-local, offline, exclusive worktree

Run at an **exact pinned PR #3 SHA**, not in an unspecified main working tree; put the original owner's local S4 `text/` data and existing validated inventory/manifest under the appropriate local read-only access paths. Never copy private S4 to GitHub, this chat or an agent's cloud workspace. Do NOT run `stress-eval sample` or `merge` just to generate missing files.

```bash
export UV_NO_SYNC=1
export UV_PROJECT_ENVIRONMENT=/Users/danny/Documents/audiobook/.venv
export PYTHONPATH="$PWD/src"
export PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

uv run pytest -q -p no:cacheprovider tests/test_stress_s4_c3_readonly.py
uv run python -B tests/stress_s4_c3_readonly.py
```

The local runner must independently check the 416-file protected parity (if that is still the scoped file set), using only pre/post checksums locally; report **counts only**, never file contents or individual per-row checksums. Command status `PASS` means only **census succeeded**, not G1.6 approval or WP4 acceptance. A `BLOCKED` reason is a reason to inspect locally, not to bypass guards.

## Count definitions

| Output | Exact meaning |
|---|---|
| `gold.rows` | Physical data rows of `text/stress_gold.tsv` (header excluded) |
| `gold.unique_source_keys` | Distinct key strings, across current + historical rows |
| `gold.source_keys_repeated` | Number of keys appearing in 2+ rows |
| `gold.repeated_key_rows_extra` | Excess physical rows beyond one per key |
| `gold.keys_with_multiple_source_identities` | Distinct five-field identities for the same key, at least two |
| `gold.extra_historical_identities` | Sum of distinct identity versions above one per key, not redundant duplicate rows |
| `gold.currently_stale_rows` | Historical rows not matching CURRENT source identity; does not mark them discardable |
| `gold.active_conflicting_keys` | Currently matching rows with distinct `(gold_vowel,yo_correct)` values under *old* C3 semantics |
| `archive.rows` | Physical archive rows, even though archive is NON-AUTHORITATIVE under current C3 |
| `archive.unmatched_to_current_gold` | Archive rows not represented in the authoritative ledger multiset, potential orphan data; BLOCKED |
| `todo.blank_rows` | All four label fields empty |
| `todo.filled_rows` | All four label fields present |
| `todo.partially_filled_rows` | Some but not all label fields present |
| `todo.filled_not_merged` | Completed todo stress/YO labels with identical five-field source identity+two semantic fields not in the authoritative ledger; labeler/date deliberately excluded like current sample guard |
| `restoration_selected.selected_restored` | Selected occurrence has independently validated pre-respell forward е→ё restoration, NOT post-respell form_synth |
| `restoration_selected.excluded_union` | Among selected RESTORED: `f1_rule is not None` OR `f1_flag != none`; each occurrence counted once |
| `restoration_selected.yo_evaluable` | Selected RESTORED with `f1_rule is None` AND `f1_flag == none` |
| `restoration_selected.excluded_f1_rule/flag/both` | Detailed overlap counts; union avoids double counting |

`present=false` distinguishes an absent file from an existing zero-row file. JSON contains only count fields, safe enum statuses and the decision recommendation; no raw text, keys, individual hashes, human labels or actual paths.

## Conditional risk comparison — NOT a G1.6 architecture approval

| C3 choice | Strong points | Risk and conditions |
|---|---|---|
| **Keep existing authoritative version-ledger**, archive derived | One authoritative stress file, existing atomic replacement/idempotence, old history retained and reversions validated; lowest immediate migration risk | Wrong human numeric labels with unchanged source identity cannot be corrected by just appending a conflicting row; must retain ERROR and seek an owner-reviewed correction mechanism |
| **One active row per key + authoritative append-only archive (proposed G1.6)** | Explicit active view and history might support audited correction/revocation | Changes authoritative ownership of history, makes recovery across multiple files more complex, requires crash+rollback oracles M1–M5, compatibility classification and an owner-approved separate migration; never assume cross-file atomicity |

**If no history and no unmerged labels:** recommend **retain the simpler current C3 version-ledger for now**, do not migrate just to split files; record the correction-workflow limitation. The owner can separately choose the new model if an explicit correction use-case justifies it.

**If any historical/stale/unmerged human data:** prioritize preserving existing authoritative history; **keep the current C3 version-ledger**, STOP on format change, and request a separate owner approval after a fully specified T01–T42 normative ADR and a testable conversion/rollback plan. Any archive-only history not in the ledger => BLOCKED, preserve all bytes.

**Regardless of counts:** A is approved in principle only; B remains deferred; no source/gold/todo/archive changes, H04, PR #3 merge, production code, WP5/T16/T17 or full render. The scorer must not begin reading an authoritative archive until a separately approved normative contract and implementation.
