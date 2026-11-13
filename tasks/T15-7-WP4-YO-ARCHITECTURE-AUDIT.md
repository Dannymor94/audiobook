---
id: T15-7-WP4-YO-ARCHITECTURE-AUDIT
title: Independent risk audit of unapproved Option B and proposed B-prime/staged fallback
status: review
owner: codex-gpt-6
agent: coordinator
branch: task/T15-7-yo-risk-audit
order: 17
depends_on: [T15-7-WP4-YO-OWNER-APPROVAL]
estimate_active_h: 3-6
estimate_qa_h: 1-2
actual_active_h: unknown
actual_elapsed_h: unknown
---

# T15-7 WP-4 / Sol F1 — Independent architecture risk audit

**Date:** 2026-11-13  
**Repository/base:** `Dannymor94/audiobook` / `task/T15`  
**Source of architect proposal:** owner-supplied document `TASK: T15-7-WP4-YO-ADR`, headed **STATUS: BLOCKED — OWNER APPROVAL REQUIRED**. The proposal itself is NOT approved.  
**Owner decision:** **Option B not approved; further architecture review requested**.  
**Authoritative current contract:** `tasks/T15-7-FINAL-ADR.md` §§5, 10–13.  
**Accepted code baseline:** `f4a8dea2026fb35b104e81d396672bd96d9b0c59`. Final WP4 report `tasks/T15-7-WP4.md` documents independent Sol **CHANGES_REQUIRED**; full reported suite was 1,798 passed / 6 skipped, but those checks do not close F1.  
**Scope:** architecture and read-only repository inspection. **No normative ADR, production-code, manifest, owner S4, source, audio or cache changes.** No new execution/QA PASS claim. WP4 BLOCKED, WP5/T16/T17/render HOLD.

## Executive conclusion

Option B's core split is necessary: **immutable human source-vowel stress truth** must not depend on a later `form_synth`; **human correctness of a particular е→ё restoration** requires its own exact, persistent observation identity. However, **B as written is not implementation-ready**. It has at least four high-severity unanswered contracts and two workflow risks. Approve neither B nor an implementation until the below P0/P1 gates are settled.

**Preferred path: B′ (repaired, gated proposal), not unconditional B**:
1. First prove a safe read-only pre-respell restoration observation and a one-to-one source-token coordinate mapping, with unsupported cases fail-closed.
2. Specify one consistent restoration property for sampling, evidence and YO scoring; explicitly version the sample policy and preserve old blank todo/snapshots.
3. Separate **annotation completeness** from **usable stress for accuracy** and from **current restoration evidence completeness**.
4. Define snapshot/evidence fingerprint semantics, two-ledger read consistency, archive/conflict/owner-correction rules before modifying code or S4 data.
5. Only after a revised signed ADR + explicit owner approval: implement a bounded patch, independent synthetic oracles, full regression and one targeted Sol review.

A lower-scope fallback **C-stage** is described below if pre-respell provenance cannot be proven without protected synthesis changes. It requires its own explicit ADR approval and must not falsely claim full WP4/YO acceptance.

## Grounded implementation facts (read-only source inspection)

1. `wordprov.process_section_occs` sets `WordOcc.form_synth` from aligned tokens in `SUTrace.prep_text`. `SUTrace.prep_text` is the **final string sent to the engine**, after respell and sentinel/pad handling; it is **not** an immutable independent pre-respell restoration observation.
2. `sutrace` calls `voicecfg.prepare_text(text, cfg, open_end)` and then `leadin.pad`, `pronounce.respell`, `synth.apply_sentinel`. `synth.prepare_synth_text` documents the same order `text_prep → pad → respell → sentinel`. The first operation is a **plausible candidate** to observe restoration **before respell**, but per-source-word mapping and fragment identity have not been proven across every case.
3. `voicecfg.prepare_text` applies optional `yo.restore`, quote stripping, open-end and terminal punctuation. `yo.restore` is token-based, but `yo.book_map()` depends on local book spelling. Matching a source word to a prepared fragment must therefore be explicit, not guessed from a final synthesized token.
4. `stress_eval.yo_changed(occ)` currently compares `occ.form_synth` with `occ.form_source`; this also controls the `yo_changed` sample stratum and the `Observation.yo_changed` property used by the YO denominator. This is a **post-respell** observation.
5. Current `inspect_ledger` checks validity against the **current** `occ` and compares (`gold_vowel`, `yo_correct`) for active conflicts. Current `_accepted_vowels` maps source-less `gold_vowel=yo` to the **current** `occ.form_synth`. These are precisely the independently found Sol F1 issues.
6. Current `score` uses the one active stress ledger and emits `gold_sha256` but has **no restoration-ledger digest** or two-ledger read fence. Current `sample_fp` has algorithm `sample/1` and a selected-key digest but no per-key stratum assignment digest. The 320 owner todo rows are currently blank, not a migratable set of human decisions.
7. `.gitignore` has `/text/stress_gold*.tsv`, covering the proposed private S4 TSV paths, but actual P1 ignore/index checks remain mandatory for each new destination and same-directory transaction temp.

## Ranked architecture risks and required amendments

| ID | Severity | Problem in unapproved B | Required B′ design rule / evidence |
|---|---|---|---|
| R0 | **P0** | Proposed `yo_evidence.form_synth` is called a pre-respell spelling while current `WordOcc.form_synth` is post-respell; using it may manufacture an incorrect historical restoration. | Rename field semantically to `restored_form_pre_respell` (or define a strict versioned alias) and prove a safe read-only token observation before `pronounce.respell`. Any unalignable/mixed transform => explicit UNSUPPORTED/ERROR, never y/n or inferred history. |
| R1 | **P0** | B says "missing usable stress truth => INCOMPLETE" and "COMPLETE needs usable stress for every selected row", although current ADR §10 permits `ambiguous` and `unknown_name` as valid human labels excluded from accuracy denominators. Some real samples would become impossible to complete honestly. | Define **three separate counts**: label completeness (a valid present human answer, including ambiguous/unknown), stress usability (nonempty accepted indices), restoration-evidence completeness. A valid ambiguous/unknown label satisfies labeling; stays excluded from stress accuracy. Unresolved legacy synth-only `yo` does **not** satisfy labeling and requires relabel. |
| R2 | **P0** | Sampling `yo_changed` is derived from post-respell `form_synth`; B's new evidence and YO gate rely on pre-respell `yo_restore`. A phrase respell can add/remove ё without any independent orthographic restoration. | One normative `restoration_observation` predicate from verified **pre-respell** source→candidate change must drive sample classification, YO property and required evidence. If this changes semantics, explicitly bump `sample/1` policy version and revalidate/regenerate sample safely. |
| R3 | **P1** | Two authoritative ledgers are independently atomic, but score currently reads only the stress ledger. A concurrent YO ledger mutation or restoration change could lead to a falsely COMPLETE score or untraceable result. | Score must snapshot **both** ledger bytes/digests, validate current sample+generation+restoration, recheck both before atomic output, and record both `gold_sha256` and `yo_evidence_sha256` (including a no-file marker) in the **ignored score JSON**. Detect modification => ERROR/no publish; no cross-ledger write transaction. **Readers of a saved score must also revalidate both ledger digests and generation before using a persisted COMPLETE result.** |
| R4 | **P1** | B removes historical `yo_correct` from the definition of a stress conflict, correctly, but doesn't fully specify active precedence among `ambiguous`, `unknown_name`, `LEGACY_YO_UNRESOLVED`, source-native `yo`, numeric and `variants`. | Canonicalize comparable stress truth to a source-vowel **set**. Exact same sets are semantically identical (source-native unique `ё` and its numeric index); disjoint/different usable sets conflict. Unusable/legacy rows remain in history without blocking a newly supplied usable stress label. Never select newest date. |
| R5 | **P1** | With an unchanged source identity, two conflicting numeric human labels cannot be corrected using the existing append-only C3 ten-column ledger (it would remain permanently ERROR). That limitation existed before B but affects its promised "relabel" workflow. | Define a separate explicitly owner-authorized **adjudication/correction procedure** with audit trail, or consciously scope it out and STOP for any conflicting usable truth. Do not pretend the proposed `merge` repairs current numeric-vs-numeric disagreement. |
| R6 | **P1** | Proposed separate YO todo is not bound to the old 320-row sample policy beyond restored source identity. Reclassifying strata or regenerating a sample could overwrite edited todo or reuse an old sample_fp. | Version `sample` policy and include a deterministic per-stratum selected-key commitment in private sample identity, not only global selected keys. Never overwrite an existing hand-edited/unmerged todo; preserve original local S4 bytes pending explicit migration. |
| R7 | **P1** | B permits multiple `е→ё` replacements in one word yet labels the whole proposed word with a single `y/n`. Ambiguous whether `n` means one or all changes are wrong and how `yo_precision` is interpreted. | Define `yo_correct=y` iff **all** changes in that exact candidate are correct; `n` iff candidate as a whole is incorrect (at least one wrong); one observation per selected word. If owners need per-position accuracy, switch to per-position evidence instead, explicitly. |
| R8 | **P1** | Specified sidecar column name `form_synth` invites coupling to the post-respell WordOcc field and fingerprint. `restored_vowel_indices` could disagree with spelling. | Require source and candidate in NFC, same token length/codepoint coordinates, same case policy, only forward `е/Е→ё/Ё` edits and nonempty changes; derive indices independently in **source vowel coordinates**, compare them to serialized values, recalc canonical fp and reject mismatch. No mixed edits or reverse changes. |
| R9 | **P1** | Historical `yo_correct=y/n` in ten-column gold has no old restoration target. An old data row may still look current under five-field identity but is not reusable YO evidence. | Preserve original 10 columns exactly. New stress rows use `yo_correct=na`. Historical y/n stays for provenance only; never count as current YO evidence, migrate or infer a fingerprint from current analysis/date. Legacy synth-only `yo` remains unscorable with explicit status. |
| R10 | **P2** | C3 archive, malformed sidecar, source reversion A→B→A and same-fingerprint conflicts need separate state handling. | Invalid schema/digest and current same-fp contradictory y/n => ERROR; historical records remain retained; restoring exact source identity+candidate A reuses A only if **entire** fingerprint matches; no "latest date" fallback; validate old-format rows as historical without reinterpreting against current analysis. |
| R11 | **P2** | Newly ignored private sidecar/todo/txn outputs may leak via alternate suffix paths, logs or score reports. | Apply existing P1/P4 to every final/temp path **before writing**, verify ignored/untracked, and keep real per-token source/candidate text and row hashes exclusively in S4/S3. Logs/reports contain only aggregate counts and scoped digests. |

Severity: P0 = must resolve before owner approves any implementation; P1 = normative contract/test requirement for a trustworthy merge/score; P2 = mandatory acceptance validation.

## Proposed B′ normative contract (NOT approved)

### B′.1 Source-stress truth

- **Source-only** coordinates. `gold_vowel=i`, `variants:i|j` name 0-based indices in `form_source`; `yo` allowed only when source itself has exactly one `ё`. The accepted-vowel set is derived from `form_source` **only**, never `form_synth` or a restoration fingerprint.
- Existing source-less `gold_vowel=yo` rows are retained byte-for-byte as `LEGACY_YO_UNRESOLVED`, not interpreted, silently migrated or discarded. They trigger a stress todo and INCOMPLETE until an explicit source-index label is added.
- `ambiguous` / `unknown_name`: valid completed human answers, but no usable stress truth; exclude from applicable precision/accuracy denominators, report excluded counts. They are NOT an excuse to invent a stress index and do NOT necessarily make the whole score incomplete.
- One active **usable semantic** truth per source identity. Equivalence means equal accepted source-vowel sets. Distinct usable sets => ERROR. Unusable answers and legacy shorthand have separate historical states; their coexistence with a later usable label does not by itself make a semantic conflict.
- For **real correction** of a wrong numeric label with unchanged source identity, retain ERROR pending owner adjudication; do not silently adopt date ordering. Explicit owner correction workflow is a separate decision, or the evaluator must advertise that limitation.

### B′.2 Restoration observation

- Observe candidate **after** `voicecfg.prepare_text` has applied `yo.restore` and **before** `pronounce.respell`, excluding a lead-in carrier/sentinel. This proposal does not authorize edits to `voicecfg`, `sutrace` or `synth`.
- Prefer independent source→pre-respell verification: apply the read-only current `yo.restore` mapping to the exact original source token AND extract the corresponding token from the correctly identified prepared fragment. Both must agree exactly with one-to-one alignment; otherwise FAIL CLOSED (`YO_OBSERVATION_UNSUPPORTED`) instead of labeling, scoring or fabricating evidence.
- If `text_prep.yo_restore` is disabled and only `pronounce.respell` adds ё, it is **not** a restorative YO observation. Preserve the original WordOcc/provenance and Qwen synthesis inputs unchanged.
- Proposed sidecar rename **`restored_form_pre_respell`** instead of `form_synth` (new, no approved data to migrate). Indices are source-vowel positions of forward е→ё changes; require byte-exact policy after NFC/case validation. Unsupported transformation => explicit status, not "no restoration" and not YO_NO_EVIDENCE.
- `restoration_fp` = SHA-256 of canonical `yo-evidence/1` object containing the exact five-field source identity, named observed pre-respell candidate and verified sorted source-vowel indices. Do not include unrelated `analysis_fp`; include an explicit `observation_contract_version` so a future producer change cannot silently preserve a fingerprint across different observation semantics.

### B′.3 Separate authoritative YO evidence, with read fence

- One owner-local ignored evidence ledger, one owner-local ignored YO todo, each schema-validated; human y/n applies to the **exact current candidate** only. Invalid/inapplicable historical rows are retained but never reused as current.
- `merge` touches only stress ledger; `merge-yo` touches only YO evidence ledger. Both validate all rows and sample/source/candidate identity before writing, use one same-directory atomic replace+fsync per authoritative file, and are byte-idempotent for same semantic input.
- On score: first validate current inventory and sample; read and pin **both authoritative ledger byte hashes** (no sidecar allowed as "empty" only if no candidate requires it); resolve statuses; before score JSON publish reread both ledgers, current generation+sample and applicable restoration identity. If changed, ERROR/no publish. Add `yo_evidence_sha256` to local score JSON and require saved-score consumers to recheck both ledger hashes/current generation. No claim of a global filesystem transaction.
- `COMPLETE` means: each selected occurrence has a **valid human annotation** (including ambiguous/unknown, excluding unresolved shorthand) and each supported current restoration has exactly one matching y/n judgment; `INCOMPLETE rc 2` means a required annotation/evidence is missing. `ERROR` covers conflicting/malformed inputs or unsupported state that prevents safe observation. For INCOMPLETE publish **no passing gates or partial metrics**.
- After COMPLETE, `Observation.yo_changed` and the YO numerator/denominator use the **same source→pre-respell observation** as the evidence todo. An `n` for a current candidate => YO_WARN; no applicable restorations => YO_NO_EVIDENCE (not a quality PASS).
- Explicitly version `sample/2` (or prove exact invariance in a formal policy compatibility gate) because existing `sample/1` uses post-respell `yo_changed`. The current 320 blank rows remain preserved until a separately authorized safe regeneration; do not silently re-label/re-shuffle them or overwrite edited files.

### B′.4 Historical and conflict classes

| Source-stress class | Restoration evidence class | Proposed evaluator outcome |
|---|---|---|
| Native-source/numeric/variants usable | No applicable current restoration | Label complete; YO not applicable |
| Native-source/numeric/variants usable | Matching unique y/n | Label complete; current YO metrics allowed |
| Native-source/numeric/variants usable | Current restoration with missing matching evidence | INCOMPLETE, YO gate absent |
| Source-valid `ambiguous` / `unknown_name` | No applicable restoration | Annotation complete; stress-accuracy excluded, gates depend on remaining usable n |
| Source-valid `ambiguous` / `unknown_name` | Current restoration with matching y/n | Annotation complete; YO still independently measurable |
| Source-less historical `yo` | Any evidence | INCOMPLETE until human source-index relabel |
| Source stale | Any | Need new source annotation; preserve old version |
| Two conflicting usable source-stress truths | Any | ERROR; owner adjudication required |
| Conflicting current YO verdicts for same full restoration_fp | Any | ERROR |
| Unsupported pre-respell observation | Any | ERROR/explicit BLOCKED; never pretend "no restoration" |

This is an architectural **recommendation**, not existing ADR behavior or authorization.

## Alternate staged option C — smaller risk if pre-respell proof is unavailable

C is **not** a shortcut to marking the existing WP4 fully accepted. It requires a new owner-approved scoped ADR:

- First fix the **known unsafe human-stress interpretation** only: source-native yo or numeric source vowel, historic source-less yo unresolved, source-only conflict logic and synthetic Sol reproducers. Do not introduce restoration evidence storage until source→pre-respell extraction is independently proven.
- Temporarily **disable/fail-closed the automatic YO restoration-quality claim**, with an explicit state such as `YO_NOT_EVALUATED`; do not report YO_NO_EVIDENCE as if an observed restoration was verified. No current y/n inference; preserve all historical evidence as untouched.
- Preserve main score `INCOMPLETE` or `NOT_READY_FOR_YO_GATE` according to an explicit owner-approved status contract. G-hint must not be used if its own required human evidence is incomplete.
- Run tests, review source-stress correctness independently, then implement restoration ledger separately in a later bounded work package. Until then, no full WP4 YO-related gate claim.

**Trade-off:** C minimizes immediate data-model change and avoids false truth, but postpones YO precision and can delay full WP4 acceptance. B′ offers complete functionality with more validation and two-ledger complexity. Unmodified B has lower short-term implementation effort but unacceptable evidence risks.

## Required "proof before implementation" experiments (all synthetic, offline, read-only)

1. Reconstruct **the same** pre-respell token two independent ways (direct `yo.restore(source_token)` and source-aligned token from `voicecfg.prepare_text(chunk_or_fragment, cfg, open_end)`), including quotes, case, carrier, sentence punctuation, open_end and multiple fragment boundaries. Assert identical source-vowel coordinates and exact target, or STOP with diagnosis; no search-by-similar-word fallback.
2. Contrast: restoration in `yo_restore` with non-yo `respell`; restoration only inside `respell`; both present; phrase-level respell altering token boundaries; none present; source contains native `ё`; multiple е→ё; mixed other edits and unalignable fragments. Only verified pre-respell restoration is labeled.
3. Prove `sample/1` vs proposed `sample/2` change handling for 320 selected keys and local owner blank todo without overwriting or confusing `sample_fp`. Test a case where key set is unchanged but stratum assignments swap.
4. Audit status matrix for source-current `ambiguous`, `unknown_name`, numeric, `variants`, native `yo`, source-less `yo`, source-stale, and conflicting numeric gold. Test current source identity reversion without latest-date selection.
5. Two-ledger read consistency with injected mutation before/after authoritative rename and before score publish; ensure result cannot be COMPLETE without pinned matching stress and YO evidence.
6. Sidecar schema/fingerprint tamper, byte-idempotent merges, A→B→A and entire restoration-candidate y/n semantics. Test both global- and current-only historical conflict policies with a clear ADR choice.
7. P1/P4 privacy: every new S4 evidence/todo/txn path ignored+untracked; private source tokens, labeler and per-row fingerprints never in tracked files/logs/reviewer reports. In tests use invented fake words only.
8. Reproduce original three Sol F1 defects against old code, then demand regular PASS after approved patch. Existing `https://github.com/Dannymor94/audiobook/pull/2` remains an **unmerged draft**, with deliberately strict-XFAIL oracles until the normative contract is signed.

## Owner decision checklist (do not bundle as silent implementation choices)

**Gate G0 — required before approving B′:** verified pre-respell source-token observability; exact supported/unsupported handling, no protected pipeline edits.

**Gate G1 — required normative signatures:**
- Is `ambiguous/unknown_name` a completed human label with excluded accuracy denominator? **Recommended YES**, consistent with current §10 semantics.
- Must sample classification and YO population use pre-respell `yo_restore` rather than post-respell `form_synth`? **Recommended YES**, with explicit `sample/2` version bump.
- Are multi-ё changes labeled as one whole-candidate y/n observation? **Recommended YES**, unless per-vowel scoring is a product requirement.
- Is the proposed sidecar field explicitly pre-respell and verified, rather than ambiguous `form_synth`? **Recommended YES**.
- How is a **genuinely wrong numeric human annotation under unchanged source identity** corrected without silently choosing dates? **Recommended separate owner adjudication**, otherwise preserve hard ERROR and document the limitation.
- Should a missing current YO judgment block COMPLETE? **Recommended YES** for supported restoration, while no applicable restoration does not block.
- Should every score payload commit to **both** authoritative ledger digests? **Recommended YES**.

**Gate G2 — permitted code only after G0/G1 and explicit owner GO:** one bounded `stress_eval.py` implementation, synthetic tests, optional minimal command dispatch, no `stress_metrics.py` or synthesis/wordprov/voicecfg/6C11 changes, full baseline+P1/P4 gates, one targeted Sol review. The current 320 unlabeled todo entries and all old S4 files stay untouched until an explicitly safe owner-authorized workflow operation.

## Expected impact, uncertainties, and sequence

Estimated active engineering work **after** a signed contract (planning ranges, not observed): preflight prototype/proof **2–5 h**; B′ data-model/CLI/sampling/scoring correction **8–16 h**; targeted independent Sol **2–4 h**; owner annotation remains separate. C staged safety patch may be **3–7 h** plus QA **1–3 h**, but does not finish YO scoring. Blockers can add work; do not interpret these as promised wall-clock delivery.

1. Coordinator independently prepares this risk audit and, if useful, non-authoritative synthetic test scaffolding in a separate draft PR (**done as documentation only**).
2. Architect responds to G0/G1 with a revised **proposed** ADR; code remains unchanged.
3. Owner explicitly chooses B′ or C and approves precise status/sampling/ledger semantics.
4. Coordinator self-executes clearly isolated pure tests/helpers if allowed, Sonnet performs only local-runtime-dependent production integration; independent Sol verifies the final risk boundary.
5. Only after Sol PASS, coordinator closes WP4; H04 owner labeling can proceed on the approved current sample; WP5 stays HOLD until owner gold actually exists and gates are computed.

**No original source words, sound, private labels or per-occurrence hashes belong in this audit or its Git commits.**
