# Routed Alignment Architecture (Stage 6)

This document describes the finalized deterministic routed-alignment engine used by DocForge Local v0.1.3.

## Why routed

Stage 6 keeps three logically separate routes:

- `reference_alignment`
- `agent_instruction_alignment`
- `readme_claim_alignment`

The engine must not collapse these into one generic flow because each route has different claim semantics and verdict rules.

## Deterministic claim→evidence pipeline

1. **Route-aware claim extraction**
2. **Claim normalization**
3. **Context-preserving claim atomization** (`single` / `and` / `or`, shared-subject propagation, dual-policy split)
4. **Implementation-grounded typed evidence atom inventory build**
5. **Candidate retrieval**
6. **Deterministic predicate matching**
7. **Route-aware verdict aggregation**
8. **Structured deterministic explanation rendering**

## Internal model concepts

The internal engine uses:

- `ClaimRecord`
- `ClaimAtom`
- `EvidenceAtom`
- `AtomMatchResult`
- `ClaimEvaluationResult`

These are internal implementation types, not a public API contract.

## Route-specific claim typing

### `reference_alignment`

Targets implementation-relevant reference requirements:

- feature/config/routing/compatibility/output/ignore-policy requirements.

### `agent_instruction_alignment`

Splits into:

- implementation-verifiable instructions (`workflow`, `config`, `output`, `feature`, `policy`)
- non-verifiable guidance (`style`, broad `process`) → `out_of_scope_or_non_verifiable`

### `readme_claim_alignment`

Splits static vs non-static claims:

- static: capability/config/CLI/output/compatibility claims
- non-static: runtime/performance/quality/experience claims → `not_statically_verifiable`

## Matching and tiers

Predicates operate on typed atoms/evidence and include relation checks (for example: `config_alias_maps_to_field`, `compatibility_alias_maps_to_first_reference_path`, and policy relation checks for reference-selection independence), not only existence checks.

Implementation-grounded evidence sources include:

- actual CLI command registry (`cli.py`)
- canonical config field catalog + alias metadata (`config_fields.py`)
- generated page contract (`sections.py`)
- routed page names (`alignment` route surface)
- ignore defaults/rules from the repo-ignore engine (`repo_ignore.py`) plus explicit reference-selection policy relations:
  - `ignore_policy_reference_selection:explicit_reference_paths_independent`
  - `ignore_policy_reference_selection:default_reference_targets_independent`
- runtime/code facts (`entrypoint`, `framework_hint`, module/code facts)

Tiers:

- `exact_primary`
- `structured_primary`
- `lexical_secondary`
- `heuristic_fallback`

`lexical_secondary` supports discovery only and cannot by itself produce `supported`.

## Contradictions and unresolved outcomes

Contradiction requires explicit deterministic basis.

- **Closed-world predicates** may use deterministic absence as contradiction (for inventories treated as authoritative).
- **Open-world predicates** do not convert absence into contradiction; they remain unresolved.
- Policy/compatibility relation predicates for:
  - `ignore_policy_reference_selection_independent`
  - `compatibility_alias_maps_to_first_reference_path`
  use conservative unresolved semantics on positive no-hit (absence alone is not contradiction).

- `reference_alignment`: unresolved without contradiction → `missing_evidence`
- `agent_instruction_alignment`: unresolved without contradiction → `not_evidenced`
- `readme_claim_alignment`: unresolved without contradiction → `not_evidenced`

## Optional LLM layer (advisory only)

For routed alignment pages, LLM mapping consumes deterministic claim/evidence bundles and route-specific allowed statuses.

Hard limits:

- may not invent new evidence IDs
- allowed evidence IDs come only from deterministic alignment-pack payload IDs (no prompt-wide regex scraping)
- unknown evidence IDs are dropped; if no valid ID remains, mapping is always conservatively downgraded (except deterministic contradiction preservation)
- may not emit out-of-route statuses
- may not override deterministic contradictions

## Anti-regression invariants

- keep route/page names stable
- keep compatibility shim `generated/theory_alignment.md`
- keep deterministic no-LLM mode as baseline
- do not reintroduce overlap-only truth assignment
- do not introduce embedding/vector retrieval as final verdict logic
- do not evaluate policy-style reference-selection relations through generic closed-world existence helpers; use dedicated policy relation predicates
