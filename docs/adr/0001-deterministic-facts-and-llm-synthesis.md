# ADR 0001: Deterministic Facts with OpenAI-Compatible Synthesis

## Status
Accepted

## Context
The MVP needs to evolve from deterministic snapshots to section-oriented documentation generation.
We need a synthesis layer that can improve explanation quality without replacing deterministic repository facts.

## Decision
- Deterministic repository scan output remains the source of truth for implementation facts.
- Section synthesis is routed through a narrow LLM client boundary with an OpenAI-compatible provider.
- Generated Markdown sections are written to `docs/generated/` as reproducible artifacts.
- Offline/stub mode remains the default so tests and local workflows do not require network calls.

## Consequences
- The architecture cleanly separates scan facts, prompt assembly, LLM invocation, and writing.
- Runtime provider details are configured outside the repository using environment variables.
- Generated pages can be published by MkDocs without changing canonical methodology source files.
