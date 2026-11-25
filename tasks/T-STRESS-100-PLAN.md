# STRESS-100 — independent A / B / C tracks (revision 2)

Owner-approved direction 2026-11-25: coverage is not correctness. No acoustic
stress detector is reliable enough for an obligatory release gate. ChatGPT
owns implementation, CI, coordination and documentation. Local agents only
perform inaccessible local execution. All private manuscript, maps, audio and
references stay local. Existing approved WAVs and cache remain intact.

This revision supersedes the previous ordered S1–S6 acceptance dependencies.
Existing PRs #38–#44 and their private evidence are reused. S4a/S4b experiments
remain research evidence; Voicy failed the quality comparison and is not promoted.

## A — deterministic stress map (Mac; independent, priority)

Timebox: three working days from actual A kickoff; record actual start and
deadline in MSK. Stop lexical refinement at the deadline. Unresolved cases are
valid output and do not block A completion, B or C. Do not extend the timebox
for model research or exhaustive human review.

DONE:
- Private stress_map.jsonl contains exactly one row per multisyllabic Cyrillic
  occurrence in canonical normalized source, independently reconciled against
  the section inventory and exact occurrence ledger. Mixed-token and compound
  components must not disappear; flag them unresolved if unsafe. Other
  normalization/foreign-number expansions and monosyllabic clitics remain
  separately accounted by the existing token ledger, not falsely stress-verified.
- Each row has source ID, row hash, exact start/end and ordinal, original word,
  zero-based codepoint stress index or null, status in auto/confirmed/unresolved,
  evidence/decision source, and sorted unique risk_flags. Confirmed means an
  explicit recorded human/approved exception decision, never model agreement.
  Auto is an evidence-based proposal, not gold. Unresolved uses null, retains
  competing candidates and the reason. No synthetic substitution of a word.
- Explicit immutable human decisions scoped to exact source occurrence/hash
  (or demonstrably unambiguous approved dictionary rule); stale decisions
  rejected. Preserve ё/case/punctuation. No global override of homographs.
- Manifest: source inventory and source file hashes; RUAccent package version,
  actual loaded nn/ and dictionary/ file SHA256 inventory, exact settings
  (currently turbo/use_dictionary=True), runtime dependencies, auxiliary
  dictionaries and their hashes/licenses, Silero version/weights if used,
  saved predictor evidence hashes, case-policy version, builder commit,
  input decision/risk inventory hashes and map SHA256. Do not invent retrospective
  provenance for old outputs: label historical evidence as such; obtain missing
  hashes for the newly executed pass. No timestamps/absolute paths in canonical
  map bytes. Two independent builds from identical frozen evidence must
  produce byte-identical UTF-8 LF JSONL (canonical key order and row order).
  This is reproducibility of assembly, not a claim of model determinism or accuracy.
- Report counts per status and each risk flag, number of distinct risky
  occurrences/forms, unmapped known-error anchors, map SHA256, completeness.
  Count actual risk union; never assume hundreds before measuring.
- Map DONE != book release-ready. 100% accounting does not mean 100% linguistic
  or acoustic correctness.

### A1 — reuse, then one case-policy pass

Reuse existing normalized-book audit (51,633 multisyllabic findings in prior
snapshot), independent section/token ledger, Wiktionary evidence and replay.
The existing Wiktionary table is lossy (drops alternatives): one entry does
not prove a word unambiguous. Use RUAccent homograph inventory or other vetted
multi-reading lexicon; explicitly flag unknown ambiguity coverage rather than
asserting completeness. Preserve all evidence; no majority vote by itself.

One bounded paired Title-case diagnostic on Mac: lowercase only standalone
Cyrillic Title-case tokens in a COPY of the full original line passed to
RUAccent (first letter uppercase, rest lowercase; no all caps, mixed tokens,
compound edits or source changes). Preserve full context; exact positional
alignment back to original text, retain original case. Compare against stored
original-case predictions from same pinned configuration; if comparable
provenance is not established, label comparison limitation or rerun the original
arm within timebox. Record changed stress/ё, new or repaired alignment failures,
proper-name and homograph flags, known gold/owner-confirmed controls if available.
The CF card's reported capitalization effect is a hypothesis, not book-specific
proof. Do not adopt indiscriminately on agreement counts; preserve ambiguous
changed cases for review. No further tuning cycles. The map builder can consume
frozen evidence with either case policy, documented explicitly.

### A2 — decision policy and listening risk queue

Unambiguous vetted dictionary candidate or context-supported candidate -> auto;
dictionary conflict, unresolved alignment/ambiguity or unsafe token -> unresolved
unless an explicit supported decision resolves it; human recorded decision ->
confirmed. Agreement alone is not proof of unambiguity. Preserve alternative
readings. Risk flags include homograph, dictionary_exception/conflict,
unresolved, known_model_error, proper_name/yo/context/token if applicable.
Map known prior errors to exact source anchors; if not yet uniquely mapped,
retain an explicit unmatched risk entry, never guess. Produce private deduplicated
listening queue with exact occurrence-to-chunk provenance (or UNMAPPED).
Group multiple risky occurrences per chunk to avoid repeat listening; distinguish
lexical reuse from acoustic occurrence checks. A person evaluates actual audio
against the source sentence/expected stress, and voice integrity. Whisper may
help locate words or detect omissions, not validate stress. No uncalibrated
meter2/acoustic detector in production acceptance. No claim that unflagged
occurrences are correct. Owner listening is bounded; unresolved remains visible.

## B — Stress CF (BLOCKED: owner rights decision)

Do not provision, integrate, run CF or meter2 until owner explicitly decides
whether a research-only trial with disclosed unlicensed training sources is
acceptable. Commercial use additionally needs sufficient rights clearance;
owner consent to research is not legal clearance for paid distribution.
No automatic substitution. If authorized, one bounded pinned experiment,
with separate stress/wording/voice judgments, exact matched controls and
no repeated parameter tuning. Use U+0301 adapter-specific projection only
where stress resolved; preserve original words and skip unresolved marks.
Do not assume reported detector rates are human accuracy.
If no material quality benefit or no rights clearance, retain stock. If
commercially eligible and demonstrably superior, plan at most one authorized
rerender of affected output.

## C — stock Qwen production path (independent of A and B)

Prepare section inventory, approved/locked audio/cache and existing output
reconciliation, pinned configuration and remaining section queue. No wait for
A or B; unresolved map entries do not block rendering. Stock Qwen receives
only its existing supported preprocessing and already approved pronunciation
rules, not raw U+0301 or '+'. Map-based pronunciation changes require targeted
validation; do not globally rewrite pronounce.yaml. Existing owner approval
boundary remains: FULL_RENDER=NO_GO until explicit owner authorization;
this plan does not itself launch the book. After authorization, use the
existing per-section queue and resume cache; skip accepted/locked output,
do not delete media or regenerate approved material without approval.

Gamebox persistent storage, detached worker, common heavy.lock, no concurrent
B/C heavyweight processes. Existing ./run.sh queue section SECTION --workers N
queues one section pipeline (chunk/synth/qc/assemble/master/suspects). Inspect
actual production config, RAM/disk, queue state and existing artifacts before
enqueueing. No whole-book synth/chunk command in queue. Existing queue parser
does NOT accept a standalone python -m stress probe as a job. Before any B
heavy task, integrate a minimal allowed queue CLI entry or use a separately
reviewed worker path holding the SAME canonical lock for the entire job;
never bypass by starting from an isolated checkout with its own lock.
No queue development now while B is blocked. A stays on Mac.

Final release: separate owner signoff on content/audio quality and rights.
No claim of 100% stress accuracy. Report known unresolved and listening gaps.
Maintain actual timings and evidence; no fabricated starts/ETAs.

## Existing evidence and historical gates

Prior S1–S3 evidence (#38–#44) remains valid as evidence, not human approval.
Prior S4a raw acute failed; S4b Voicy technical PASS but quality no promotion.
Prior S5 detector calibration remains research, not a mandatory dependency.
Old S3 unresolved-zero and S5 exhaustive acoustic-verification requirements
are superseded by this plan. Preserve previous commits and reports.

## 2026-11-25 — owner correction: one manifest pass before synthesis

A1/A2 and initial A3 completed. No recurring relink automation needed. Create
all missing production manifests once, preserving existing ones byte-for-byte,
then link the frozen stress map against the entire manifest set. Existing
chunk --missing-only skips existing manifests and refuses missing-manifest
directories with chunk artifacts. Record before/after hashes for all existing
manifests and WAVs, especially locked audio. Do not rechunk stale sections
automatically; synth preflight rejects stale manifests. The known 58 normalized
vs 56 render section difference is an empty section and short contents heading;
report any risks in intentionally excluded text explicitly, never invent a
chunk or guarantee 6510/6510 before measurement.

render_all.sh now defaults to manifest preparation (--prepare-only), with no
synthesis. Explicit --render is required to enqueue section synth jobs using
existing manifests. 1.7B maximum two workers, default two; conservative
MemAvailable admission 27 GiB for two or 15 GiB for one, not a peak-RSS
guarantee. Use one worker if the two-worker budget is unavailable. No automatic
shutdown; no implicit rechunk on render; check current hashes and valid locked
audio before enqueue, verify remaining incomplete chunks afterwards.
Existing full-render approval boundary remains. A preparation only, no new
synthesis, B blocked. QC/assemble/master remain subsequent per-section steps,
not implied by a successful synthesis queue.
