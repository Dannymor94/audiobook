---
id: T15-7-WP4-G1-S4-READONLY-AUDIT
title: Owner-authorized local S4 C3 compatibility census
status: pass_owner_c3_decision_pending
owner: owner
agent: coordinator
branch: task/T15-7-yo-risk-audit
---

# T15-7 WP4 — read-only S4 compatibility: owner GO, no migration

## Audit result — PASS for S4 census, owner C3 decision still pending

**Evidence provenance:** user supplied Sonnet's exact owner-local offline read-only run at pinned SHA `355507df2789840adb2925f644818ccd899be8c6`, on 2026-11-14. These are **agent-reported local results**, not independently re-executed by the coordinator; the owner-local S4 files are not present in GitHub and cannot be inspected in this session.

| Domain | Owner-local reported aggregates |
|---|---|
| Synthetic module | **17 PASS / 0 FAIL / 0 SKIP** |
| Scanner | **PASS**; `authorized_migration=false`, `s4_modified=false`, `production_modified=false` |
| `stress_gold.tsv` | present; **0 data rows**, 0 unique/repeated `source_key`, 0 separate source-identity versions, 0 stale/current-conflicting rows, **0 human labels** |
| `stress_gold.archive.tsv` | present; **0 rows**, 0 unmatched |
| `stress_gold.todo.tsv` | present; **320 rows**, **320 blank**, 0 complete/partial/unmerged human annotations |
| Source snapshot | G0 **51,629 eligible verified**, selected G0 unsupported **0** |
| Selected RESTORED | **320 selected inspected; 40 restored; 0 F1-rule exclusions, 0 flag exclusions, 0 overlap** |
| `YO_EVALUABLE = RESTORED ∧ f1_rule=null ∧ f1_flag=none` | **40/40 selected RESTORED** evaluable, 0 excluded |
| File parity | Owner reports `text/` file count **246 before and after** and unchanged local MD5 for gold/todo; no file mutations. Scope is **not** the former 416-file protected parity and must not be described as a fresh 416-file hash verification |
| Diff | Reported `src/` change versus G0 baseline **0 files** |

**Result:** `PASS` for **read-only compatibility census**, **not** WP4 quality acceptance or authorization. Reported script recommendation: `PREFER_MINIMAL_C3_KEEP_CURRENT_LEDGER_NO_MIGRATION`. Historical source-only human annotation data are absent **on the measured snapshot**; the blank 320-row todo must still be preserved byte-for-byte. This does not prove that all possible external backups or earlier disconnected versions are absent.

### Coordinator's recommendation (not an owner decision)

**Retain current C3: one authoritative `text/stress_gold.tsv` version-ledger; derived, non-authoritative `stress_gold.archive.tsv`. Do not switch to an authoritative archive or introduce a migration.** It is the simplest model with one authoritative stress file, existing atomicity/fail-closed provenance and no migration just to rearrange empty data.

The one known limitation remains: if a human later submits **two conflicting numeric annotations of unchanged source identity**, existing C3 raises `GOLD_ACTIVE_CONFLICT` and does not let the user correct by appending. Do not silently select the newer row. A separate, explicit owner-approved correction/adjudication contract could be added later, preserving the prior human decision and audit trail without introducing two authoritative stress files now.

**Owner decision now requested:** confirm **`G1.6: REJECT_PROPOSED_ARCHIVE_AUTHORITY; RETAIN_CURRENT_C3_VERSION_LEDGER`** (or decline and request another model). This is a decision on architecture only, never a gold/sample/ADR/code/PR-merge GO. A / G1.1–G1.5 remains `APPROVED_IN_PRINCIPLE`. B / G1.6 remains `DEFERRED_NOT_APPROVED` until actual explicit reply.

**After owner decision:** request complete normative ADR targeting G1.1–G1.5 with C3 retained, exact `T01–T42` including T06/T27/T28, source-only stress and YO observation schema, dual stress/YO ledgers and persisted-score freshness. Submit proposed ADR for owner review and one independent Sol architectural check. **Only then** request production implementation permission. No H04/S4 write/sample regeneration/render authorization.

---

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
