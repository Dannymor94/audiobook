---
id: T15-7-WP4-YO-G1-DECISION-PACKET
title: Post-G0 source-derived proposal for architectural approval — not normative
status: blocked
owner: owner-and-claude-chat-architect
agent: coordinator
branch: task/T15-7-yo-risk-audit
depends_on: [T15-7-WP4-YO-PREFLIGHT]
---

# T15-7 WP-4 — G1 Decision Packet (PROPOSAL, NOT APPROVAL)

**Date:** 2026-11-13. **Authority:** architect proposes exact amendments; owner accepts or rejects.  
**STOP:** Option B and B′ are NOT approved. No normative ADR, production, gold-ledger, sample, cache, model or audio modifications are authorized by this document. PR #3 stays draft/unmerged.

## Inputs accepted as technical evidence, with limits

- Sonnet, offline .venv at PR #3 pinned SHA `650127b90199342dfe4d1e555784025e11056f2f`: **52 targeted G0 PASS, 0 FAIL, 0 SKIP**. Full regression **1,845 PASS, 0 FAIL, 11 SKIP**. Distinguish this from independent Sol acceptance, which is not granted.
- Earlier real-corpus read-only audit: 76,036 inventory rows, 51,629 eligible (**all 51,629 verified**), 320/320 selected source→fragment→pre-respell mappings verified; unsupported=0. 223 eligible and 40 selected had verified pre-respell restoration; selected pre/post disagreements=0. This is empirical coverage for that current source/generation, not a future-proof guarantee.
- The S2 baseline-dependent test gap: previous run with local S2 baseline had 1,849 PASS / 1 FAIL / 6 SKIP; latest 1,845 PASS / 0 FAIL / 11 SKIP. Both collect 1,856 tests. Five more SKIPs are consistent with absent S2 fixture in latest worktree, but `-rs` node IDs for latest run were not supplied. Do not silently claim S2 parity was reverified.
- Research-only `stress_yo_g0_readonly.py` deliberately outputs `g0_closed=false`. It proves one current snapshot's mapping support, not correctness of historical or new human gold judgments.

## Architect questions requiring explicit, internally consistent answers

### G1.1 — Source-stress truth vs unresolved historical shorthand

**Recommendation:** source-only coordinate space. For ten-field stress TSV, numeric `gold_vowel=i` / `variants:i|j` means source-vowel indices; `yo` may be used **only** when the *source token itself* has exactly one ё. A historical `yo` label whose source has no ё is preserved verbatim but marked `LEGACY_YO_UNRESOLVED` and is NOT scored, must request a human source-index relabel. No synthesis-derived conversion. `yo_correct` in historical ten-field entries is provenance, not current restoration truth.

**Required decision:** how is an unresolved historical row represented and is it excluded from current conflict comparisons? If an old shorthand and a new numeric row share the same source identity, must the new human answer become active without rewriting the historical row? Define exact C3 ordering; never choose latest date. Empty existing 320-row todo requires no migration.

### G1.2 — Human-annotation completeness vs usable metric denominator

**Recommendation:** valid `ambiguous` and `unknown_name` are **completed human annotations** but lack usable stress truth. They satisfy the selected-key labeling requirement and are excluded only from applicable accuracy denominators, with explicit counts. `LEGACY_YO_UNRESOLVED` is NOT a completed label. For usable truth require at most one compatible active source-vowel set and no conflicting human decisions.

**Required decision:** exact COMPLETE/INCOMPLETE/ERROR matrix, particularly if usable denominator is zero for one or all strata. Never promise PASS based on an empty denominator; mark metrics/gates INCONCLUSIVE/NO_EVIDENCE explicitly according to statistical contract.

### G1.3 — Sampling population/policy and preserved H04 todo

**Observed risk:** current `sample/1` commits to selected key set, counts and global source/analysis fingerprints, but does **not** commit to the exact assignment `source_key → stratum`; synthetic test shows a fingerprint collision when memberships swap.

**Recommendation:** new `sample/2` policy explicitly identifies *which signal* defines `yo_changed` (verified pre-respell restoration, **not** post-respell), eligibility, deterministic strata precedence, selected per-stratum source keys and sorted per-key stratum assignment digest. A policy version bump must produce a new sample identity and current sample must be independently revalidated. Preserve the original ignored 320-row todo and sample artifacts **byte-identically** until a separate owner-approved local migration/regeneration; no overwrite just because labels are currently blank. Same selected keys cannot bypass policy identity change.

**Required decision:** is the YO stratum intended to measure verified **pre-respell yo_restore only**, or *any* change in TTS input spelling? Choose one; do not use the former for the denominator and the latter for the sample. Clarify if a strata assignment change alone should make a sample stale; recommended YES.

### G1.4 — Specific restoration identity (proposed local evidence)

**Recommendation:** hold a separate ignored, append-only YO-evidence ledger, separate from the ten-field stress ledger. One y/n human judgment is tied to **one exact pre-respell candidate**, the exact 5-field source identity, a versioned observation algorithm, and source-vowel positions of *every* е→ё change. An exact current match may reuse historical evidence on A→B→A; any different target/identity requires new human judgment. `yo_correct=y` means the entire observed candidate is correct; `n` means at least one change in the candidate is incorrect (unless owner instead requests per-position labeling). The evidence field must be called `restored_form_pre_respell`, not ambiguously `form_synth`.

**Do not conflate a provenance snapshot with label validity.** Persist the global normalized source-content, YO-map and relevant config digests as proof of *which implementation produced the observation*, and recheck them on write/score. For reuse of a previously judged target, define whether only the **exact source identity + candidate + indices + algorithm version** must match, even if an unrelated normalized word alters the global YO map. Recommendation: unrelated global map change should trigger a fresh observation validation, but should **not erase the human verdict on an identical proven candidate**. The actor must say whether sample version changes separately require re-labeling.

**Critical invariant:** never use `WordOcc.form_synth`, `SUTrace.prep_text` (post-respell) or a cached map keyed only by mtime as the pre-respell evidence. The validated current G0 path is a research probe and must be specified as a deterministic read-only observer before production integration.

### G1.5 — Two authoritative ledgers, crash-safe merge and score freshness

**Recommendation:** `merge` touches stress TSV, `merge-yo` touches only YO evidence TSV. Each update is one crash-safe file replacement; do not pretend two files have a single atomic transaction. Reads and score publication must pin the byte SHA256 of both ledgers and verified current generation/sample/candidate; reread/recheck immediately before score write. Stored COMPLETE reports must be invalidated on subsequent read when any input fingerprint changes. Missing current evidence for a supported selected restoration ⇒ INCOMPLETE rc2, never default y/n. Duplicate matching evidence collapses; conflicting current y/n at same exact candidate fingerprint ⇒ ERROR. Preserve all older versions and refuse silent replacement.

**Required decision:** schema version, exact canonical fingerprint encoding, allowed values, historical-invalid/missing-file handling, concurrency fence semantics, and hard stop behavior for unsupported mappings. No private per-row text/hashes in tracked output or public logs.

### G1.6 — Same-source owner corrections and C3 collision

**Recommendation:** distinguish duplicate semantically equal source-vowel sets (e.g. source-native unique ё vs its numeric index), unscorable label types, and true contradictory usable human answers. Current ten-field C3 cannot resolve two contradictory numeric stress labels for the same unchanged source/context by merely appending a new row. Define a separate owner-authorized adjudication/revocation record or explicitly keep ERROR + manual STOP until an approved correction workflow exists. Never choose by date, agent result or post-respell orthography.

**Required decision:** whether a correction/revocation mechanism is in-scope of the first B′ patch. If not, the operator must be told the limitation and unable to overwrite a protected row implicitly.

## Risk-minimizing implementation staging (after architect + owner approval only)

1. **G1 contract freeze:** architect issues ONE targeted ADR addendum to current §§5/10/C3, sample and YO gates; owner explicitly approves. Include exact row schemas, status tables, expected tests and sample preservation rule. No code change during this stage.
2. **Self-contained pure helpers/tests** may be prepared on an isolated branch by coordinator when owner authorizes implementation; avoid S4 edits and Sonnet-owned files. Reduce total Sonnet integration burden.
3. **Sonnet local adapter** implements deterministic observer, schema-validated local evidence, `merge-yo`, score with pinned dual ledgers, explicit status and safe sample versioning. This is necessary because the code needs local state and protected baseline checks.
4. **One targeted independent Sol review** of final integrated WP-4 exact SHA, synthetic three original F1 regressions, A→B→A, missing/conflicting evidence, crash/retry, full project baseline/determinism and P1/P4.
5. H04 real owner labels can resume only under the final approved contract; no WP5/render authorization until actual gates.

## Architect response expected

```text
TASK: T15-7-WP4-YO-G1-ADR
STATUS: PROPOSED_FOR_OWNER | BLOCKED
STRESS_SOURCE_COORDINATES:
LEGACY_SYNTH_ONLY_YO:
AMBIGUOUS_UNKNOWN_NAME_COMPLETENESS:
USABLE_DENOMINATOR_ZERO_POLICY:
SAMPLE_POLICY_VERSION_AND_MEMBERSHIP_DIGEST:
PRESERVE_320_BLANK_OWNER_TODO:
OBSERVATION_SOURCE_AND_VERSION:
YO_MULTI_RESTORATION_LABEL_SEMANTICS:
RESTORATION_FINGERPRINT_AND_GLOBAL_MAP_CHANGE:
YO_EVIDENCE_SCHEMA_AND_PRIVACY:
DUAL_LEDGER_ATOMICITY_AND_SCORE_FRESHNESS:
C3_HUMAN_CORRECTION_CONFLICT_RULES:
EXACT_TEST_ORACLES:
ADR_PARAGRAPHS_TO_AMEND:
OWNER_APPROVAL_ITEMS:
NEXT_ALLOWED_ACTION:
```

**STOP on an architecture proposal.** This packet does not choose B′ for the owner or authorize implementation.
