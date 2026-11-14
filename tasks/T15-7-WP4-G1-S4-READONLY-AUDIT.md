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

## Execution — owner-local, offline; separate code from protected data

**Important implementation detail confirmed in source:** `audiobook.paths.ROOT = Path(__file__).resolve().parents[2]`. Thus importing `audiobook` from a clean PR worktree makes `paths.TEXT` point to that **worktree**, not necessarily the owner's local gold. The auditor deliberately treats missing gold/todo as `BLOCKED`; it MUST NOT assume zero history from an unmounted S4 directory. It also refuses symlinked S4 files as an unsafe substitute.

**Recommended layout:** leave the owner-local audiobook worktree and S4 physically where they are. Fetch **PR #3 pinned audit SHA** into a separate code-only worktree, but run its `tests/*.py` audit using the **owner-local original `src`** first in `PYTHONPATH`. This makes `audiobook.paths.TEXT` and `OUT` resolve to the owner-local data without copying/symlinking/editing S4. PR #3 contains no `src/` changes compared to `task/T15`; independently verify this in the local worktree before run.

```bash
# Replace with the actual existing paths. Do not print actual S4 files.
export OWNER_ROOT=/Users/danny/Documents/audiobook
export PR3_WT=/tmp/audiobook-s4-audit-pr3    # pinned PR #3 code-only worktree
export UV_NO_SYNC=1
export UV_PROJECT_ENVIRONMENT="$OWNER_ROOT/.venv"
export PYTHONPATH="$OWNER_ROOT/src:$PR3_WT/tests"
export PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
cd "$OWNER_ROOT"

# Confirm the exact pinned script SHA locally before execution.
uv run pytest -q -p no:cacheprovider "$PR3_WT/tests/test_stress_s4_c3_readonly.py"
uv run python -B "$PR3_WT/tests/stress_s4_c3_readonly.py"
```

The scanner checks that **both** local `stress_gold.tsv` and `stress_gold.todo.tsv` physically exist, plus the current saved sample fingerprint. Missing any required input => BLOCKED (not zero historical rows). Archive can be absent because under current C3 it is derived/non-authoritative; present archive rows are always counted. No command creates or rewrites S4, score, samples or inventory.

The local runner must independently check the owner-defined protected-file pre/post parity (previously 416 files), with checksums retained locally and **only aggregate change counts** reported. A command status `PASS` means the **census succeeded**, not G1.6 approval or WP4 acceptance. Any `BLOCKED` means STOP, not permission to repair, create sample, merge or infer.

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
