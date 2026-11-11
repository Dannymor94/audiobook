# T15-6C11 Normative Test Register

**Branch:** `task/T15`
**HEAD at time of writing:** `b096682`
**Full pytest baseline:** 1293 passed, 5 skipped
**Collected in `test_unitmap_spans.py`:** 396 cases, 286 unique test functions

---

## Counting methodology

**Test function:** a unique `def test_*` name, regardless of parametrization.
**Collected case:** one pytest node after parametrize expansion; a function with
`@pytest.mark.parametrize("x", [a, b, c])` contributes 3 collected cases.

Counts verified by:
```
uv run pytest --collect-only -q tests/test_unitmap_spans.py
```
Functions = `| sed 's/\[.*//' | sort -u | wc -l` on the output lines.
Cases = total count in the last summary line.

Group membership is determined by the test name prefix:
- `test_<N>_*` → group #N
- `test_3b_*` / `test_3c_*` / `test_3d_*` → implementation sub-groups 3b/3c/3d
- anything else → pre-numbered

---

## Source material

| Source | Status |
|--------|--------|
| `tasks/T15-sync-2026-11-11.md` §"Нормативные требования 1–37" | Mapping exists but marked INCOMPLETE |
| Commit history `d5c15cf`…`b096682` — group headers added per commit | Primary evidence for group definitions |
| No standalone normative contract document found in repository | **SOURCE_NOT_FOUND** |

The original normative contract 1–37 was never committed as a standalone document.
Group headers were added in `b6b6d3c` (T15-6C11-3) alongside their first tests.
Groups not present in that or any later commit have no source-of-truth in the repository.

---

## Pre-numbered tests (structural / API contracts)

Added in `d5c15cf` and `f43a1a2`. No group number in name.

| Section | Functions | Collected cases | Status |
|---------|-----------|----------------|--------|
| Atom (fields, frozen, offsets, unit_id, basic, whitespace, empty_string) | 7 | 7 | VERIFIED |
| ChunkSpan (exact_fields, frozen, hashable, heading_kind, no_extra_fields, spans_structural, unit_ids_frozenset, end_modes_frozenset, zero_atom_range) | 9 | 9 | VERIFIED |
| AnnotationError (code, detail, message_no_manuscript, mismatch_idx, reason_alias) | 5 | 5 | VERIFIED |
| Gate #2 NFC (unit_pass, unit_violation, chunk_violation, nfc_bad_no_empty_chunk) | 4 | 4 | VERIFIED |
| Gate #12 inner-paragraph newline (double_newline, with_spaces, with_tabs, single_ok) | 4 | 4 | VERIFIED |
| Gate #14 manifest ordering (ok, n_gap, dup_id, format_mismatch, format_too_long, n_starts_at_two, n_starts_at_zero) | 7 | 7 | VERIFIED |
| Gate #25 empty chunk (whitespace_only, empty_string, tabs_newlines, ok_punctuation_only, ok_single_char, empty_unit_allowed) | 6 | 6 | VERIFIED |
| Gate single-newline multiple units (gate_single_newline_multiple_units) | 1 | 1 | VERIFIED |
| check_gates (passes_valid, raises_subclass, empty_chunk, inner_para, manifest_order, nfc) | 6 | 6 | VERIFIED |
| source_atoms (single_implementation, matches_map_section_stream) | 2 | 2 | VERIFIED |
| SectionMap structure (is_frozen, section_field, spans_count, stream_contains_all) | 4 | 4 | VERIFIED |
| map_* numbered cases (#1,#3–11,#15–18 — see numbered groups below) | 33 | 33 | see below |
| **Subtotal** | **88** | **88** | |

---

## Numbered groups — original normative requirements (#1–#18)

Defined in `b6b6d3c` (T15-6C11-3). No separate source document exists.
Functions in this section are a subset of the 88 pre-numbered tests above
(map_* functions have no numeric prefix in their names).

| Group | Requirement (from header + test behavior) | Functions | Collected cases | Status |
|-------|------------------------------------------|-----------|----------------|--------|
| **#1** | Basic success: single chunk, multi-chunk same unit, multi-unit | 3 | 3 | VERIFIED |
| **#2** | NFC gate fires for unit and chunk violations | 4 | 4 | VERIFIED (pre-numbered) |
| **#3** | Stream exhausted + mismatch/exhaustion precedence | 4 | 4 | VERIFIED |
| **#4** | Trailing source atoms → `TRAILING_SOURCE` | 2 | 2 | VERIFIED |
| **#5–7** | Atom mismatch: case/ё-е/punctuation (subdivisions not individually specified) | 7 | 7 | PARTIAL — subdivisions #5/#6/#7 not defined in any source |
| **#8** | NBSP and double spaces succeed | 3 | 3 | VERIFIED |
| **#9** | Single newlines succeed | 4 | 4 | VERIFIED |
| **#10** | Repeated identical atoms: sequential OK, reused-atom stops | 2 | 2 | VERIFIED |
| **#11** | Cross-kind chunk → `KIND_AMBIGUOUS`; same kind two units OK; heading kind | 3 | 3 | VERIFIED |
| **#12** | Inner-paragraph newline gate | 4 | 4 | VERIFIED (pre-numbered) |
| **#13** | **No definition found in any commit, task file or sync report** | 0 | 0 | **SOURCE_NOT_FOUND** |
| **#14** | Manifest ordering gate | 7 | 7 | VERIFIED (pre-numbered) |
| **#15** | Zero-Cyrillic chunk as separate manifest chunk | 2 | 2 | VERIFIED |
| **#16** | Zero-Cyrillic chunk as unit tail | 2 | 2 | VERIFIED |
| **#17** | Reconstruction from spans reproduces atom text | 2 | 2 | VERIFIED |
| **#18** | Skipped atoms / gaps → `ATOM_MISMATCH` | 1 | 1 | VERIFIED |
| **#19–24** | **No definitions found in any commit, task file or sync report** | 0 | 0 | **SOURCE_NOT_FOUND** |
| **#25** | Empty chunk gate | 5 | 5 | VERIFIED (pre-numbered) |
| **#26** | **No definition found in any commit, task file or sync report** | 0 | 0 | **SOURCE_NOT_FOUND** |

---

## Implementation-phase groups (#27+)

Added during T15-6C11-3b through TD-12-FIX. Not part of the original 1–26 contract.

| Group | Task / Requirement | Functions | Collected cases | Status |
|-------|--------------------|-----------|----------------|--------|
| **#3b** | Unvalidated manifest ID must not appear in diagnostics (T15-6C11-3b) | 8 | 8 | VERIFIED |
| **#3c** | Strict input schema validation in validate_gates() (T15-6C11-3c) | 22 | 22 | VERIFIED |
| **#3d** | CRLF and Unicode whitespace blank-line detection (T15-6C11-3d) | 10 | 10 | VERIFIED |
| **#27** | Atom provenance by unit split (T15-6C11-3e) | 4 | 4 | VERIFIED |
| **#28** | Independent maps retain texts; `chunk_atoms()` signature; UNKNOWN_CHUNK | 3 | 3 | VERIFIED |
| **#29** | Manually specified provenance literals; fuzz boundary check | 4 | 4 | VERIFIED |
| **#30** | AST guards: no SectionMap/ChunkSpan construction outside `unitmap.py`; no `dataclasses.replace()` in importers; `chunk_atoms()` no tokenization | 4 | 4 | VERIFIED |
| **#31** | `map_chunks()` ≡ `list(map_section(...).spans)` | 2 | 2 | VERIFIED |
| **#32** | UNKNOWN_CHUNK diagnostic privacy; section validation (xfails closed in 3f1) | 7 | 7 | VERIFIED |
| **#33** | INVALID_SECTION diagnostic privacy (T15-6C11-3f1a/b) | 9 | 9 | VERIFIED |
| **#34** | INVALID_SECTION precedence over malformed secondary inputs | 5 | 5 | VERIFIED |
| **#35** | 58 production section identifiers valid under approved regex | 1 | 58 | VERIFIED |
| **#36** | `validate_section()` public API valid/invalid inputs | 2 | 19 | VERIFIED |
| **#37** | INVALID_SECTION exception structure and attributes | 4 | 4 | VERIFIED |
| **#38** | `AnnotationError` constructor boundary sanitization (T15-6C11-3f1b) | 8 | 8 | VERIFIED |
| **#39** | `chunk_atoms()` hostile/spoofed `chunk_id` boundary (T15-6C11-3f1c) | 9 | 9 | VERIFIED |
| **#40** | `chunk_atoms()` suppresses exception context for unknown string IDs (T15-6C11-3f1d) | 3 | 3 | VERIFIED |
| **#41** | `_validate_chunk_span` integrity checks (T15-6C11-3g) | 17 | 17 | VERIFIED |
| **#42** | Independently computed atom-range boundaries (T15-6C11-3g1) | 9 | 9 | VERIFIED |
| **#43** | `ChunkSpan` metadata type validation (T15-6C11-3g2) | 17 | 17 | VERIFIED |
| **#44** | Corrupted `ChunkSpan.chunk_id` diagnostics (T15-6C11-3g3) | 8 | 8 | VERIFIED |
| **#45** | AST guard alias bypass regression (T15-6C11-3h, TD-1, TD-2, TD-12-FIX) | 23 | 23 | VERIFIED |
| **#46** | Malformed top-level `units`/`chunks` containers (T15-6C11-3i) | 13 | 41 | VERIFIED |
| **#47** | `annotate_units()` malformed-container hardening (TD-3) | 6 | 14 | VERIFIED |

---

## Full collected-case breakdown (test_unitmap_spans.py)

| Category | Functions | Collected cases |
|----------|-----------|----------------|
| Pre-numbered (Atom × 7, ChunkSpan × 9, AnnotationError × 5, Gate #2 × 4, Gate #12 × 4, Gate #14 × 7, Gate #25 × 6, single-newline × 1, check_gates × 6, source_atoms × 2, SectionMap structure × 4, map_* numbered × 33) | 88 | 88 |
| Groups #3b / #3c / #3d (manifest-ID disclosure, input schema, CRLF) | 40 | 40 |
| Groups #27–#31 (provenance, AST, map_chunks equality) | 17 | 17 |
| Groups #32–#40 (diagnostic privacy, section validation, chunk_atoms) | 48 | 122 |
| Groups #41–#44 (ChunkSpan integrity) | 51 | 51 |
| Group #45 (AST alias bypass — includes TD-12-FIX additions) | 23 | 23 |
| Group #46 (malformed containers — 6C11-3i) | 13 | 41 |
| Group #47 (annotate_units hardening — TD-3) | 6 | 14 |
| **Total** | **286** | **396** |

Groups #32–#40 collected-case detail:

| Group | Functions | Cases | Note |
|-------|-----------|-------|------|
| #32 | 7 | 7 | |
| #33 | 9 | 9 | |
| #34 | 5 | 5 | |
| #35 | 1 | 58 | parametrized: 58 production section IDs |
| #36 | 2 | 19 | parametrized: valid + invalid section strings |
| #37 | 4 | 4 | |
| #38 | 8 | 8 | |
| #39 | 9 | 9 | |
| #40 | 3 | 3 | |
| **#32–40** | **48** | **122** | |

---

## TD-2 and TD-3 arithmetic (preserved from TD-4)

**TD-2 (+7 reported, +6 actual):**
`git diff 13306a9 4562a75 | grep "^+def test_"` → 6 functions.
`_unitmap_module_aliases` helper was miscounted. 1264 + 6 = 1270 ✓

**TD-3 (+13 reported, +14 actual):**
6 functions; `test_47_annotate_units_malformed_units` and `test_47_annotate_units_malformed_chunks`
each parametrized with 5 values → 5 + 5 + 4 = 14 collected cases. 1270 + 14 = 1284 ✓

**TD-12-FIX (+9 functions, +9 cases):** all non-parametrized. 1284 + 9 = 1293 ✓

---

## Unresolved source gaps — architect decision required

| Gap | Description |
|-----|-------------|
| Groups #13, #19–24, #26 | No definition in any commit, task file, sync report, architecture decision record or code comment. The sync report `tasks/T15-sync-2026-11-11.md` already marked these INCOMPLETE. No test covers them. |
| Subdivisions #5/#6/#7 | Group header groups three requirements together (`#5–7`). The original individual definitions are absent. All seven `test_map_atom_mismatch_*` tests exist under the combined header; whether they satisfy all three original requirements cannot be verified without the original definitions. |
| Original normative contract document | The full 1–37 contract was referenced by the sync report as absent. It was never committed. The register above reconstructs requirements from commit headers and test behavior only. |

No speculative definitions were invented. These gaps require an architect decision:
either supply the missing definitions so regression tests can be written,
or formally close them as not-required for T15-6C11.
