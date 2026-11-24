# STRESS-100 — owner target and release gates

Owner direction: ChatGPT is lead developer and owns implementation, research,
CI, review, documentation and coordination. Local agents execute only tasks
requiring inaccessible local models, manuscript, author reference or hardware.
No repeat manual word hunts. Preserve approved WAVs; Chapter 1 not accepted;
FULL_RENDER=NO_GO until separate owner authorization.

## Ordered gates
| Gate | Deliverable | Acceptance | Responsibility |
|---|---|---|---|
| S1 | PR #38 text consensus, chapter + whole book | exact local source and all five known errors reconciled; counts, no private output in GitHub | local operator runs existing code |
| S2 | Full normalized-token ledger | independent canonical expected section inventory matches; every token run accounted; missing/duplicate findings rejected | lead develops; local operator runs |
| S3 | Contextual lexical decisions | every stress-required occurrence has an evidence-bound decision; ambiguity, names, ё, compounds, clitics, abbreviations and foreign/number expansions explicitly handled; unresolved count zero before text release | lead implements resolver; local operator runs |
| S4 | Controllable synthesis | legally suitable, pinned checkpoint or alternative; isolated matched trial on five known failures plus clean, ambiguous, and ordinary-word controls; actual stress, wording, voice, pace and RTF measured | lead research and test design; local operator only for inference |
| S5 | Acoustic coverage | every spoken lexical occurrence aligned to its expected realization; independently calibrated stress detector, uncertainty/omission/repetition tracked; no unresolved errors; report measured accuracy and uncertainty, not guaranteed perfection | lead develops calibration/evaluation; local operator runs |
| S6 | Release | accepted control chapter, cache and locked audio preserved, owner authorization for larger render | lead coordinates; owner approves |

## Meaning of 100%
100% accounting is deterministic and achievable. 100% correct text labels and
100% acoustic adherence are targets, not established facts. Dual agreement is
not gold truth. No-vowel and one-vowel words may be clitics; never imply they
are acoustically verified. Source-to-normalized completeness is a separate
gate (including spoken punctuation/numbers). An independent section inventory
must come from canonical book metadata, not from listing the same audit input.
The ledger covers Unicode token runs; hyphenated components are explicitly
review-required. Symbols that normalization should expand are not a proof of
speech equivalence. No automatic decisions based on simple majority voting.

## Local execution after S1
Use a separate green coverage checkout, and reuse the existing private S1
whole-book output without new predictor inference:
`uv run --no-sync python -m audiobook.stress_coverage --book-text-dir "$BOOK_TEXT_DIR" --audit-dir "$BOOK_AUDIT_DIR" --expected-sections "$EXPECTED_SECTIONS_JSON" --out "$NEW_PRIVATE_LEDGER_DIR"`

Expected sections JSON is an exact list of normalized filenames derived from
canonical book metadata independently; no glob-generated substitute. Report
aggregate counts, missing section/normalization issues, not filenames, text,
per-token records, audio or private paths. Keep outputs local. S2 is
accounting only; release_ready is always false. No new synthesis or merge.
