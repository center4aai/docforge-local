# Project Brief

## Problem

Teams need a local-first CLI that generates repository documentation from real project contents while preserving clear control over privacy and outbound egress.

## Functional requirements

The current shipped workflow supports:
1. repository scanning and deterministic code-fact extraction (Python-first);
2. optional external reference ingestion from a user-provided reference directory;
3. generated Markdown documentation as the source of truth;
4. local HTML publishing via MkDocs Material;
5. first-run bootstrap/scaffolding for docs and navigation;
6. on-demand refresh via `update-docs`;
7. optional OpenAI-compatible LLM mode when explicitly enabled.

## Constraints

- Python 3.12+
- `uv` only
- OpenAI-compatible model endpoint configured outside the repo
- Markdown is the canonical documentation source
- HTML is generated from Markdown
- deterministic extraction is preferred over free-form LLM inference

## Quality bar

The documentation should be:
- grounded in actual repository contents;
- explicit about uncertainty;
- modular and navigable;
- maintainable across updates;
- useful both for developers and for project owners.

## Product posture

Keep the pipeline simple, deterministic, and local-first by default; treat LLM usage as optional and externally configured.
