# ALG-02 decision / ALG-03 next gate

## ALG-02 CLOSED — no production promotion

Owner review page ee7dc086b0651375; operator reports exact WAV/plan/receipt/key
identity verification. 8 pairs: candidate 1 win, 3 equal, 4 losses by ordinal
overall labels. Development 1/1/2; heldout 0/2/2. Baseline 3 OK / 2 UNSURE /
3 BAD; uppercase 1 OK / 2 UNSURE / 5 BAD. Tests reported 745 passed, 5 skipped.
No new TTS or production changes. No claim of word-level stress accuracy:
target-specific paired judgments are incomplete. Earlier isolated success
does not establish generalization. Close uppercase pilot, preserve its code
and evidence as research only. No more register, doubling or seed-only tuning.
Do not deploy any candidate merely because it won an overall comparison.

## ALG-03 — rhythm design, independent of stress

Code audit: chunker.enum_splits already recognizes depth-zero short enumeration
segments (20 character limit, subordinate/byline guards). chunker includes
enum_pause_ms in hashes of applicable chunks. voice_plan.source_anchors already
tracks exact source ordinal, offsets and boundary types. Assembly pause knobs
alone cannot correct timing inside spoken chunks. Reuse existing mechanisms
before creating another segmentation system.

First dry-run: measure current enum coverage on the frozen CH1 manifests
and the owner-marked rhythm failures; verify actual config and worker execution
path. Classify missed genuine lists, false-positive boundaries, protected spans
(quoted phrases, hyphenated words, preposition/clitic groups, numbers), and
whether existing splitting can harm voice continuity. Use exact source offsets;
never cut a word or introduce lexical changes. No guessing by text substring.
Compare existing rule with a conservative boundary planner using synthetic
positive/negative fixtures and private exact local examples. Default OFF;
preserve current hashes/audio and lock semantics. Do not change chunk identity
or global pause settings before impact is measured.

Gate: one focused controlled A/B only after the runtime GAMEBOX_REQUIRED guard
and owner-approved execution scope. Fixed model/reference/seed; isolate rhythm
from stress control. Evaluate naturalness, lexical integrity, stress and voice
independently; use local HTML with verified WAV lineage. No new render until
these prerequisites. Do not manually patch individual WAVs or replace narration
with original author recordings.

## ALG-04 — stress control architecture

Compare truly explicit phoneme/stress-conditioned alternatives rather than
more text casing tricks. Research public model capabilities, licenses including
training-data rights, offline CPU feasibility, voice cloning and verified
Russian stress control. Existing CF rights block is unchanged. No downloads or
inference until a candidate is justified and authorized. No claim of automatic
acoustic stress verification by dictionaries or Whisper.

Chapter 2 / FULL_RENDER remain NO_GO. GAMEBOX-FIRST enforcement is a mandatory
runtime prerequisite, not only documentation. No production promotion or merge.
