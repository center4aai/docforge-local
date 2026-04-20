# Changelog

## Unreleased

- Structured output diagnostics UX redesign:
  - replaced raw flat warning strings with typed structured diagnostics (`code`, `severity`,
    `stage`, `summary`, `detail`, contextual refs);
  - preserved recovery/sanitization behavior while emitting diagnostics at point-of-recovery;
  - generated section pages now render `Structured Output Diagnostics` with a compact summary and
    collapsible `<details>` diagnostics view;
  - exact duplicate diagnostics are collapsed with counts in detailed view, while contextual
    differences remain distinct.

- Implementation-analysis evidence hygiene fix:
  - default repo-analysis ignores now include `docforge.toml`;
  - config-aware repo-analysis ignores now auto-exclude DocForge-owned output paths inside the
    target repository (`docs_dir`, `output_dir`, `site_dir`, and local `artifact_root`);
  - repository textual evidence no longer includes `docforge.toml` as `runtime_config`;
  - authoritative prompt evidence selection no longer treats `runtime_config` as a repository-truth
    evidence category.

- LLM transport architecture correction (streaming-first):
  - replaced scalar non-streaming completions transport with streaming-first text generation for
    OpenAI-compatible endpoints;
  - retries are now limited to pre-response/startup failures before any meaningful streamed text
    chunk is received;
  - mid-stream transport interruptions after meaningful output starts are now surfaced as
    structured non-retryable failures (no automatic duplicate resend, no partial-output salvage);
  - section generation now marks interrupted sections unavailable while continuing other sections,
    and all-section failure messaging remains clean/user-facing.

- LLM transport resilience hardening:
  - centralized outbound LLM API retry wrapper for transport/no-response failures;
  - deterministic geometric per-attempt timeout growth (`5s`, doubling each retry) capped by the
    standard LLM request-timeout constant;
  - retry exhaustion now raises structured transient failure metadata and section-level generation
    continues for other independent units where possible;
  - all-LLM-section transport exhaustion now terminates cleanly with a concise summary instead of a
    first-failure raw exception.

- Focused v0.1.3 corrective patch:
  - fixed runtime `project_root` precedence so explicit CLI `--project-root` is a true top-priority override across `doctor`, `generate-docs`, `update-docs`, and `config` effective/validation flows;
  - removed duplicate deterministic Stage 6 truth input for `reference_alignment`: deterministic general-reference analysis now uses grounded chunks as the only authoritative deterministic source;
  - hardened secret-delete UX: deletion is actionable only for `api_key_mode=keyring`; `api_key_mode=env` now returns clear manual env-var removal guidance instead of implying deletion;
  - refreshed user-facing docs (including README restructuring) and cleaned stale historical/dev-log framing from user-oriented product documentation.

- Stage 6 contradiction-semantic refinement (narrow):
  - positive no-hit outcomes for `ignore_policy_reference_selection_independent` and
    `compatibility_alias_maps_to_first_reference_path` are now deterministic `unresolved`
    (route fallback: `missing_evidence` / `not_evidenced`) instead of immediate contradiction;
  - explicit contradiction behavior is unchanged for negative claims when those relations
    are present in deterministic evidence.
- Stage 6 deterministic alignment-pack export hardening:
  - deterministic `allowed_evidence_ids` are now exported from structured routed verdict fields
    (`supporting_evidence_ids` / `contradicting_evidence_ids`) instead of parsing formatted
    `evidence_note` strings;
  - `evidence_note` remains presentation-only for human-readable trace output;
  - added regression coverage to lock evidence-ID export and orchestration behavior against future
    note-format coupling.
- Stage 6 deterministic routed claim→evidence methodology correction pass:
  - evidence inventory now derives from implementation-grounded sources (actual CLI command registry,
    canonical config field/alias metadata, section/page contracts, route registry, repo-ignore defaults,
    and runtime code-facts) instead of synthetic hardcoded policy/command lists;
  - contradiction policy now distinguishes closed-world predicates (authoritative inventory absence can
    contradict) from open-world predicates (absence remains unresolved);
  - claim atomization now better preserves shared subject/predicate context for compound and dual-policy claims;
  - relation predicates (including config alias→canonical field mapping) now run as deterministic typed relations;
  - routed LLM mapping now takes allowed evidence IDs from deterministic bundles, drops invalid IDs,
    and conservatively downgrades unsupported advisory entries while preserving deterministic contradictions;
  - unreadable routed sources are skipped from deterministic claim extraction instead of being converted into fake claim text.
- Final Stage 6 residual corrective pass (narrow, no redesign):
  - strengthened relation handling for `reference_dir`/`methodology_dir` compatibility mapping to first explicit reference path and explicit reference-selection independence policy relations;
  - hardened advisory-only routed LLM mapping sanitization so any mapping entry with zero valid deterministic evidence IDs is downgraded to route fallback status (with deterministic contradiction preservation still taking precedence);
  - moved policy-style contradiction checks for reference-selection independence onto dedicated policy predicates instead of generic closed-world existence shortcuts.
- Finalized Stage 6 routed alignment with a deterministic typed claim→evidence engine:
  route-aware claim extraction/atomization, typed evidence atoms, predicate-based matching tiers,
  deterministic route-specific aggregation, and deterministic explanation traces.
- Routed LLM mapping is now advisory-only against deterministic claim/evidence packs with
  evidence-ID constraints and contradiction-preservation safeguards.
- Added maintainer architecture documentation: `docs/context/routed_alignment_architecture.md`.
- Deterministic routed claim-evidence analysis was hardened with route-aware normalized claims,
  entity extraction (commands/pages/config/path/module/entrypoint/framework), tiered matching
  (explicit anchor vs structured partial vs lexical fallback), and stronger contradiction checks.
- Agent-instruction deterministic classification now cleanly separates normative style/process
  guidance from verifiable workflow/config/output/feature claims.
- README deterministic classification now more consistently routes runtime/performance/availability
  guarantees to `not_statically_verifiable` while preserving static verification for command/
  config/output surface claims.
- Russian language repair prompt payloads now use canonical JSON serialization instead of Python repr.
- Interactive `docforge-local config` UX now states immediate persistence semantics explicitly and
  clarifies that `validate` checks current effective saved config.
- External-references helper text now uses platform-neutral guidance for
  `REPO_AUTODOCS_REFERENCE_PATHS` separators.
- Removed obsolete archived release checklists (`docs/release_checklist_v0_1_0.md`,
  `docs/release_checklist_v0_1_1.md`) and corresponding MkDocs nav entries.
- Routed deterministic alignment now uses explicit route-specific candidate extraction for:
  general references, AI-agent instructions, and README claims.
- Deterministic agent-instruction analysis now separates verifiable implementation claims from
  normative/process guidance and emits deterministic `out_of_scope_or_non_verifiable` verdicts.
- Deterministic README analysis now separates statically checkable claims from runtime/availability/
  latency style claims and emits deterministic `not_statically_verifiable` verdicts.
- Routed LLM mapping stage now enforces per-route status enums in the mapping prompt contract
  (`reference_alignment`, `agent_instruction_alignment`, `readme_claim_alignment`).
- Evidence indexing/matching now includes expanded anchors for commands/config/output/text tokens
  to reduce brittle token-overlap verdicting.
- Interactive `docforge-local config` now uses scope-filtered field indexing in interactive mode and
  handles invalid/unsupported interactive edit/reset selections gracefully.
- User-facing wording cleanup continues from legacy “methodology/theory” phrasing toward
  external-reference/routed-alignment terminology in prompts/debug surfaces, while preserving
  compatibility shims and aliases.
- Added hidden `discover-references` alias while preserving hidden deprecated
  `discover-theory` compatibility behavior.
- Localization behavior is unchanged in this pass; generated prose language scope remains `en|ru`
  explanatory-text only.

- Routed LLM alignment prompts now include route-specific source material bundles for general references, agent-instruction files, and README claims.
- Deterministic routed alignment extraction/verdicting was strengthened with an explicit claim pipeline (extraction, normalization/deduplication, evidence matching, route-aware verdicting) across general references, agent instructions, and README claims.
- Routed LLM material-bundle preparation now treats per-route source file I/O as best-effort and records unreadable-file diagnostics instead of crashing on `OSError`.
- Default README/agent reference-target discovery is now configurable via pattern lists in config/env while preserving boolean toggle compatibility.
- Keyring availability reporting now requires a usable backend (not import-only detection), with clearer status messages for missing package vs unusable backend.
- Structured-output mapping fallback is now section-aware so repaired/synthesized statuses always stay within each route section’s allowed enum.

## v0.1.3 — 2026-04-15

### Added

- Stage 1 v0.1.3 configuration foundation: user config support, source-aware precedence metadata, structured TOML sections, and typed forward-compatible config fields.
- Compatibility-preserving config aliases for `reference_dir`, `methodology_dir`, and `REPO_AUTODOCS_GENERATED_DOCS_DIR` remain supported.
- Stage 2 `docforge-local config` manager with interactive editing, source-aware display, scoped persistence (project/user), draft validation, shell export helpers, and keyring-based API key management flow.
- Stage 3 repo-analysis ignore engine with gitignore-like semantics and integration across implementation-analysis scanning/code-facts/prompt-evidence/deterministic helpers.
- Stage 4 LLM section engine modernization: full LLM coverage for `code_structure` and
  `runtime_entrypoints`, typed internal section block model, deterministic block rendering,
  and backward-compatible structured-output normalization.
- Stage 5 multi-input external-reference discovery/routing inventory:
  repeatable explicit reference inputs, default README/agent-target selection,
  per-source origin/kind/route/parse metadata, and multi-reference update-planning support.
- Stage 6 routed alignment workflow:
  deterministic + LLM-ready routed verdict analysis for `reference_alignment`,
  `agent_instruction_alignment`, and `readme_claim_alignment`, with a deprecated
  compatibility shim for `theory_alignment.md`.
- Stage 7 generated prose language activation:
  `generated_text_language=en|ru` now actively localizes generated explanatory prose in both
  deterministic and LLM flows while preserving canonical filenames/routes/headings/identifiers.

### Changed

- Config precedence is now `CLI > env > project config > user config > defaults`.
- README/.env docs now explicitly document `temperature`, user-config override, and compatibility alias behavior.
- Interactive config boolean editing now supports direct toggle UX.
- `project_root` is editable through `docforge-local config`.
- Shell exports for `REPO_AUTODOCS_REFERENCE_PATHS` now use the platform path separator for Windows/Unix round-trip compatibility.
- API key presence reporting in config status/validation now reflects actual env/keyring presence.
- Stage 3 remediation: helper entrypoints (`scan_repository`,
  `scan_repository_with_code_facts`, `build_code_facts_bundle`) now apply repo-analysis
  ignore rules by default with explicit opt-out for raw legacy behavior.
- Canonical user-facing external-reference language now emphasizes
  `reference_paths`/external references instead of singular methodology root terminology,
  while preserving `reference_dir`/`methodology_dir` compatibility shims.
- Explicit README routing now classifies to `readme_claims`/`readme_claim_alignment`
  even for explicit file/directory inputs.
- Stage 6 deterministic routed heuristics now use concrete implementation anchors
  (files/paths/modules/symbols/entrypoints/framework hints), stronger contradiction checks,
  and route-aware candidate classification for agent/readme analysis.
- External-reference inventory now includes per-source routed-analysis status summaries.

## v0.1.1 — 2026-04-11

Release-hardening update for **DocForge Local** (`docforge-local`) that finalizes the modernization plan and stabilizes the public product surface.

### Highlights

- Isolated default outputs under `.docforge-local/` across docs/site generation workflows.
- Improved deterministic (no-LLM) usefulness with stronger repository/code evidence output.
- Clarified explicit `reference_dir` contract while preserving deprecated compatibility aliases.
- Expanded evidence grounding and section contracts for higher-confidence generated content.
- Added deeper multi-step LLM orchestration with structured-output validation/rendering.
- Made debug artifact generation opt-in (default off) with cleanup of stale managed debug files.
- Stabilized CLI UX around primary workflows (`doctor`, `generate-docs`, `update-docs`) and marked advanced/internal commands accordingly.
- Normalized user-facing docs/config templates/help text for the final v0.1.1 contract.

## v0.1.0 — 2026-04-08

First public MVP release of **DocForge Local** (`docforge-local`).

### Highlights

- Local-first CLI workflow for repository documentation generation.
- Deterministic repository scan and Python code-facts extraction.
- Optional methodology/theory grounding in generated documentation.
- OpenAI-compatible LLM mode with explicit `base_url` configuration.
- Markdown docs generation with MkDocs Material publishing.
- Conservative `update-docs` workflow (incremental planning + reliable full regeneration).
- Release-facing privacy/egress and open-source audit documentation.

### Naming and compatibility note

- User-facing name is DocForge Local / `docforge-local`.
- Internal Python package/module remains `repo_autodocs` in v0.1.0 for compatibility and lower migration risk.
