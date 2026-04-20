# DocForge Local Documentation

DocForge Local (`docforge-local`) is a local-first CLI that generates repository documentation from deterministic repository/code evidence, with optional OpenAI-compatible LLM synthesis.

## Current release candidate: v0.1.3

This documentation set is organized as:

- **User guide** content for runtime behavior, configuration precedence, and generated-output expectations.
- **Generated output** examples for the full routed page set (`overview`, `architecture`, `code_structure`, `runtime_entrypoints`, `reference_alignment`, `agent_instruction_alignment`, `readme_claim_alignment`) plus deprecated compatibility shim `theory_alignment`.
- **Maintainer/internal** material (audits, release checklists, ADR index) grouped separately in site navigation.

## Stable user workflows

1. `doctor` / `doctor --privacy`
2. `generate-docs`
3. `update-docs`

## Output defaults

By default, generated outputs are isolated under:

- `.docforge-local/docs/generated/` (Markdown)
- `.docforge-local/site/` (HTML)

Debug artifacts are opt-in via `--debug-artifacts` (or `REPO_AUTODOCS_DEBUG_ARTIFACTS=true`).
