# T15-6C11 Normative Test Register

**Branch:** `task/T15`  
**HEAD at time of writing:** `8b55518`  
**Full pytest baseline:** 1284 passed, 5 skipped  
**Collected in `test_unitmap_spans.py`:** 387 cases across 220 functions  

---

## Source material

| Source | Status |
|--------|--------|
| `tasks/T15-sync-2026-11-11.md` §"Нормативные требования 1–37" | Mapping exists but marked INCOMPLETE |
| Commit history `d5c15cf`…`8b55518` — group headers added per commit | Primary evidence for group definitions |
| No standalone normative contract document found in repository | **SOURCE_NOT_FOUND** |

The original normative contract 1–37 was never committed as a standalone document.
Group headers were added in `b6b6d3c` (T15-6C11-3) alongside their first tests;
groups not present in that or later commits have no source-of-truth in the repository.

---

## Group register

### Pre-numbered tests (structural / API contracts)

These tests carry no group number. They were added in commits `d5c15cf` and `f43a1a2`.

| Section | Functions | Collected cases | Status |
|---------|-----------|----------------|--------|
| Atom fields, frozen, offsets, unit_id | 5 | 5 | VERIFIED |
| ChunkSpan fields, frozen, hashable, structural | 8 | 8 | VERIFIED |
| AnnotationError code, detail, reason alias, mismatch_idx, no-manuscript | 5 | 5 | VERIFIED |
| Gate #2 NFC (unit + chunk) | 4 | 4 | VERIFIED |
| Gate #12 inner-paragraph newline | 4 | 4 | VERIFIED |
| Gate #14 manifest ordering | 7 | 7 | VERIFIED |
| Gate #25 empty chunk | 5 | 5 | VERIFIED |
| check_gates fail-closed path | 5 | 5 | VERIFIED |
| map_chunks helpers / _mk_* fixtures | 2 | 2 | VERIFIED |
| source_atoms (single impl, matches map_section stream) | 2 | 2 | VERIFIED |
| SectionMap structure basics (frozen, section field, spans count, stream) | 4 | 4 | VERIFIED |
| **Subtotal pre-numbered** | **51 functions** | **51 cases** | |

---

### Numbered groups — original normative requirements (#1–#18)

Defined in commit `b6b6d3c` (T15-6C11-3). No separate source document exists.

| Group | Requirement (from header + test behavior) | Test functions | Collected cases | Status |
|-------|------------------------------------------|---------------|----------------|--------|
| **#1** | Basic success: single chunk, multi-chunk same unit, multi-unit | `test_map_basic_single_chunk`, `test_map_multiple_chunks_same_unit`, `test_map_chunks_across_units` | 3 | VERIFIED |
| **#2** | NFC gate fires for unit and chunk violations | `test_gate_nfc_*` (4 functions above) | 4 | VERIFIED (pre-numbered) |
| **#3** | Stream exhausted: extra chunk or empty source | `test_map_stream_exhausted_extra_chunk`, `test_map_stream_exhausted_empty_source`, `test_map_genuine_exhaustion`, `test_map_mismatch_before_exhaustion` | 4 | VERIFIED |
| **#4** | Trailing source atoms → `TRAILING_SOURCE` | `test_map_trailing_source_atoms`, `test_map_trailing_source_multiple_units` | 2 | VERIFIED |
| **#5–7** | Atom mismatch: case/ё-е/punctuation (subdivisions not individually specified) | `test_map_atom_mismatch_case`, `_uppercase`, `_yo_e`, `_e_yo`, `_trailing_punct`, `_added_punct`, `_different_word` | 7 | PARTIAL — subdivisions #5/#6/#7 not individually defined in any source |
| **#8** | NBSP and double spaces succeed (source or chunk) | `test_map_nbsp_in_source`, `test_map_double_space_in_source`, `test_map_double_space_in_chunk` | 3 | VERIFIED |
| **#9** | Single newlines succeed (in source, between chunks) | `test_map_newline_in_source`, `test_map_newline_between_chunks`, `test_gate_single_newline_multiple_units`, `test_gate_inner_para_single_newline_ok` | 4 | VERIFIED |
| **#10** | Repeated identical atoms: sequential OK, reused-atom stops | `test_map_repeated_atoms_sequential`, `test_map_reused_atom_stops` | 2 | VERIFIED |
| **#11** | Cross-kind chunk → `KIND_AMBIGUOUS`; same kind two units OK | `test_map_kind_ambiguous`, `test_map_same_kind_two_units_ok`, `test_map_heading_kind` | 3 | VERIFIED |
| **#12** | Inner-paragraph newline gate | `test_gate_inner_para_*` (4 functions above) | 4 | VERIFIED (pre-numbered) |
| **#13** | **No definition found in any commit, task file, or sync report** | — | 0 | **SOURCE_NOT_FOUND** |
| **#14** | Manifest ordering gate | `test_gate_manifest_order_*` (7 functions above) | 7 | VERIFIED (pre-numbered) |
| **#15** | Zero-Cyrillic chunk as separate manifest chunk | `test_map_zero_cyrillic_chunk_punct`, `test_map_zero_cyrillic_between_cyr_chunks` | 2 | VERIFIED |
| **#16** | Zero-Cyrillic chunk as unit tail | `test_map_zero_cyrillic_tail_of_unit`, `test_map_zero_cyrillic_separate_tail_atom` | 2 | VERIFIED |
| **#17** | Reconstruction from spans reproduces atom text | `test_map_reconstruction_from_spans`, `test_map_reconstruction_multi_unit` | 2 | VERIFIED |
| **#18** | Skipped atoms / gaps → `ATOM_MISMATCH` | `test_map_skipped_atom_mismatch` | 1 | VERIFIED |
| **#19–24** | **No definitions found in any commit, task file, or sync report** | — | 0 | **SOURCE_NOT_FOUND** |
| **#25** | Empty chunk gate | `test_gate_empty_chunk_*` (5 functions above) | 5 | VERIFIED (pre-numbered) |
| **#26** | **No definition found in any commit, task file, or sync report** | — | 0 | **SOURCE_NOT_FOUND** |

---

### Numbered groups — implementation-phase requirements (#27+)

Added during T15-6C11-3b through TD-3; not part of the original 1–26 contract.

| Group | Task / Requirement | Functions | Collected cases | Status |
|-------|--------------------|-----------|----------------|--------|
| **#27** | Atom provenance by unit split (commit `36e29b2`, T15-6C11-3e) | 4 | 4 | VERIFIED |
| **#28** | Independent maps retain texts; `chunk_atoms()` signature; UNKNOWN_CHUNK | 3 | 3 | VERIFIED |
| **#29** | Manually specified provenance literals; fuzz boundary check | 4 | 4 | VERIFIED |
| **#30** | AST guards: no SectionMap/ChunkSpan construction outside `unitmap.py`; no `dataclasses.replace()` in importers; `chunk_atoms()` no tokenization | 4 | 4 | VERIFIED |
| **#31** | `map_chunks()` ≡ `list(map_section(...).spans)` | 2 | 2 | VERIFIED |
| **#32** | UNKNOWN_CHUNK diagnostic privacy; section validation (2 xfails closed in 3f1) | 7 | 7 | VERIFIED |
| **#33** | INVALID_SECTION diagnostic privacy (T15-6C11-3f1a/b) | 9 | 9 | VERIFIED |
| **#34** | INVALID_SECTION precedence over malformed secondary inputs | 5 | 5 | VERIFIED |
| **#35** | 58 production section identifiers valid under approved regex (T15-6C11-3f1) | 1 | 58 | VERIFIED |
| **#36** | `validate_section()` public API valid/invalid inputs (T15-6C11-3f1) | 2 | 19 | VERIFIED |
| **#37** | INVALID_SECTION exception structure and attributes | 4 | 4 | VERIFIED |
| **#38** | `AnnotationError` constructor boundary sanitization (T15-6C11-3f1b) | 8 | 8 | VERIFIED |
| **#39** | `chunk_atoms()` hostile/spoofed `chunk_id` boundary (T15-6C11-3f1c) | 9 | 9 | VERIFIED |
| **#40** | `chunk_atoms()` suppresses exception context for unknown string IDs (T15-6C11-3f1d) | 3 | 3 | VERIFIED |
| **#41** | `_validate_chunk_span` integrity checks (T15-6C11-3g) | 17 | 17 | VERIFIED |
| **#42** | Independently computed atom-range boundaries (T15-6C11-3g1) | 9 | 9 | VERIFIED |
| **#43** | `ChunkSpan` metadata type validation (T15-6C11-3g2) | 17 | 17 | VERIFIED |
| **#44** | Corrupted `ChunkSpan.chunk_id` diagnostics (T15-6C11-3g3) | 8 | 8 | VERIFIED |
| **#45** | AST guard alias bypass regression (T15-6C11-3h, TD-1, TD-2) | 14 | 14 | VERIFIED |
| **#46** | Malformed top-level `units`/`chunks` containers (T15-6C11-3i) | 13 | 41 | VERIFIED |
| **#47** | `annotate_units()` malformed-container hardening (TD-3) | 6 | 14 | VERIFIED |

---

## Test arithmetic verification

### TD-2 discrepancy (+7 reported, +6 observed)

**Diff check:** `git diff 13306a9 4562a75 -- tests/test_unitmap_spans.py | grep "^+def test_"` → **6 functions**.

The TD-2 delivery text reported "7 tests". The 7th item was `_unitmap_module_aliases`, a helper function (no `test_` prefix) added in the same commit. It was counted in error. No test code is missing or duplicated.

**Arithmetic:** 1264 (TD-1 baseline) + 6 collected cases = **1270**. ✓

### TD-3 discrepancy (+13 reported, +14 observed)

**Diff check:** `git diff 8b55518^ 8b55518 -- tests/test_unitmap_spans.py | grep "^+def test_"` → **6 functions**.

Parametrization: `test_47_annotate_units_malformed_units` → 5 params `[None, {}, "string", 42, ()]`; `test_47_annotate_units_malformed_chunks` → 5 params. Four non-parametrized functions add 4 cases. Total collected: **5 + 5 + 4 = 14**.

The delivery text reported "13 additions". That was a function-count (6 functions implied 13 by counting each param separately but missing one). Actual collected: 14. Arithmetic: 1270 + 14 = **1284**. ✓

---

## Full collected-case breakdown (test_unitmap_spans.py)

| Category | Collected cases |
|----------|----------------|
| Pre-numbered (Atom, ChunkSpan, AnnotationError, Gates, check_gates, helpers) | 51 |
| Groups #1–#18 (original requirements, some pre-numbered) | 37 |
| Group #3b (manifest ID disclosure, 8 functions) | 8 |
| Group #3c (strict input schema, 22 functions) | 22 |
| Group #3d (CRLF / Unicode blank-line, 10 functions) | 10 |
| Groups #27–#31 (provenance, AST, map_chunks equality) | 17 |
| Groups #32–#40 (diagnostic privacy, section validation, chunk_atoms) | 117 |
| Groups #41–#44 (ChunkSpan integrity) | 51 |
| Group #45 (AST alias bypass) | 14 |
| Group #46 (malformed containers — 6C11-3i) | 41 |
| Group #47 (annotate_units hardening — TD-3) | 14 |
| Other named tests (SectionMap structure, source_atoms cross-checks) | 5 |
| **Total** | **387** |

---

## Unresolved source gaps — architect decision required

| Gap | Description |
|-----|-------------|
| Groups #13, #19–24, #26 | No definition in any commit, task file, sync report, architecture decision record, or code comment. The sync report `tasks/T15-sync-2026-11-11.md` already marked these INCOMPLETE. No test covers them. |
| Subdivisions #5/#6/#7 | Group header groups three requirements together (`#5–7`). The original individual definitions are absent. All seven `test_map_atom_mismatch_*` tests exist under the combined header; whether they satisfy all three original requirements cannot be verified without the original definitions. |
| Original normative contract document | The full 1–37 contract was referenced by the sync report as absent. It was never committed. The register above reconstructs requirements from commit headers and test behavior, not from an authoritative specification. |

No speculative definitions were invented. The gaps above require an architect decision: either provide the missing definitions so tests can be written, or formally close the gaps as not-required for T15-6C11.
