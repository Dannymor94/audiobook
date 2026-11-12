# T15-7 WP-2 — Independent Acceptance and B1 Closure

**Date:** 2026-11-12  
**Coordinator decision:** **WP-2 ACCEPTED**, R1–R7 CLOSED; **B1 RUAccent interface CLOSED**.  
**Accepted implementation SHA:** `d3f51854a283b90b94e141ace35f5a62d952b00a`  
**Evidence:** Final independently authored Sol targeted acceptance, recovered and verified by subsequent independent Sol transition check. The coordinator was provided the independent report and its aggregate reproducibility evidence. This file records that evidence, not a separate local execution by the coordinator.

## Gate A — WP-2: PASS

- Seven original defects (multi-fragment coordinates, trace failures, F1 pre-respell positions, excluded source fingerprint, manifest key-access guard, valid T1 without F6, strict canonical TSV) were independently reproduced at the rejected SHA and independently closed at the accepted SHA.
- Exact corpus: **56 sections, 4,624 source units, 77,998 atoms, 5,127 SU records**.
- **76,036 word occurrences**: 76,033 aligned; 3 existing `prep_token_mismatch`; no coercion or silent remapping. Zero L-a/L-b/L-c link errors. 5,124 fully aligned chunks.
- Frozen accepted S2 baseline: stored and freshly computed `D = 0346b71f7b3f3c2078a144b56a8374a8998bf6b722d25af1fe0ce2a07ec1a5d6`; identical ordered SU identities/input hashes; unchanged baseline bytes.
- Independent full pytest: **1,479 passed, 5 skipped**. Arithmetic `1,391 + 88 = 1,479`. Focused with `PYTHONHASHSEED=1/2/3`: 186 passed for each. Privacy P1/P4, protected code and manifests unchanged, diff check PASS.
- No synthesis, source changes, audio or cache writes, manifest regeneration, RUAccent publication or gold writes.

## Gate B — T15-7.0c RUAccent interface: PASS

The independent Sol check repeated the original **three S1 synthetic offline probes** in two fresh processes using the pinned local RUAccent runtime. Outputs were byte-identical across processes and matched prior evidence.

| Synthetic probe | Input/output tokens | Stress + markers | е→ё changes | Token-order fold |
|---|---:|---:|---:|---|
| 1 | 5 / 5 | 4 | 0 | PASS |
| 2 | 5 / 5 | 4 | 0 | PASS |
| 3 | 4 / 4 | 4 | 3 | PASS |

**Pinned aggregate model/config content identity (SHA-256):** `2f670f53b1fcdcea328a63388ac76ccfdbff11cc593011795d1fd3dc6c70ccbd`. Identity covers 76 model/dictionary/package files plus loader and initialization settings. `ruaccent 1.5.8.3`, `transformers 4.57.3`, `torch 2.14.0`, `onnxruntime 1.30.0`; turbo, `use_dictionary=True`, CPU, `tiny_mode=False`.

Network and repo writes were denied in the independent probe sandbox; manuscript/audio/cache reads denied. Model/config and 107,030 repository entries unchanged by size/mtime/mode. This evidence validates the **runtime interface and repeatability only**, not pronunciation correctness or audio quality. No raw local model files, synthetic outputs or private data are published in Git.

## Next dependency state

- **WP-2: DONE.** `tasks/T15-7-WP2.md`, `tasks/T15-7-WP2-FIX.md`, `tasks/T15-7-WP2-WP3-TRANSITION.md` marked done.
- **B1: CLOSED** for T15-7.1b, T15-7.5 and dependent WP-3 tasks.
- **WP-3: ELIGIBLE for a single combined Sonnet work package**: historical v4 TSV baseline (7.1b) → advisory RUAccent analysis F6/analysis_fp (7.5) → atomic inventory publication/consumer validation (7.6), with hard internal STOP gates and **one** independent Sol exit review.
- **B2 snapshot authority remains OPEN** and blocks T16/T17 and any future full render decisions, **not WP-3**. Current frozen manifests still fail `ensure_manifest_current` on 56 sections; do not regenerate or silently treat as current.
- **Historical published inventory v3 is not an acceptable v4 byte baseline.** A local, ignored v4 baseline must be proved before inventory publisher code changes.
- No full synthesis, external transfers or rendering are authorized.
