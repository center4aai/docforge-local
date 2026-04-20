# Open-source dependency and license audit for DocForge Local

**Scope:** direct dependencies declared in `pyproject.toml` for DocForge Local v0.1.3, plus a concise sample of notable transitive dependencies relevant to CLI/runtime, MkDocs/Material, OpenAI-compatible networking, document ingestion, and keyring integration.  
**Audit posture:** this is a technical release-audit artifact, not legal advice.

## Scope and method

This document summarizes the dependency and license surface of the current DocForge Local v0.1.3 baseline using the internal review material as the source of repository-grounded facts.

The audit is intentionally split into:

1. **Direct declared dependencies** from the project manifest
2. **A small notable transitive sample**, not a full SBOM
3. **Repository-level reuse observations**
4. **Uncertainty notes** about what still requires release-time verification

License notes below are **best-effort public attributions**, not a substitute for final legal review.

## Direct dependencies

### Build dependency

| Package | Declared constraint | Role in project | Public license note | MIT-compatibility note |
|---|---:|---|---|---|
| `hatchling` | `>=1.25` | build backend | Best-effort public attribution: MIT | Typically treated as permissive and generally compatible; re-check package metadata before release. |

### Direct runtime dependencies

| Package | Declared constraint | Role in DocForge Local | Public license note | MIT-compatibility note |
|---|---:|---|---|---|
| `jinja2` | `>=3.1` | templating / rendering support in docs toolchain | Best-effort public attribution: BSD-3-Clause | Generally compatible with MIT. |
| `mkdocs` | `>=1.6` | static site build engine | Best-effort public attribution: BSD-2-Clause | Generally compatible with MIT. |
| `mkdocs-material` | `>=9.6` | theme / navigation / presentation layer | Best-effort public attribution: MIT | Generally compatible with MIT. |
| `openai` | `>=1.40` | OpenAI-compatible client SDK for optional LLM mode | Best-effort public attribution: Apache-2.0 | Generally compatible with MIT. |
| `pypdf` | `>=4.3` | PDF ingestion for reference materials | Best-effort public attribution: BSD-3-Clause | Generally compatible with MIT. |
| `pydantic` | `>=2.8` | typed models / validation | Best-effort public attribution: MIT | Generally compatible with MIT. |
| `pyyaml` | `>=6.0` | YAML handling for MkDocs, scaffolding, config | Best-effort public attribution: MIT | Generally compatible with MIT. |
| `rich` | `>=13.7` | terminal UI output | Best-effort public attribution: MIT | Generally compatible with MIT. |
| `typer` | `>=0.12` | CLI framework | Best-effort public attribution: MIT | Generally compatible with MIT. |
| `docx2txt` | `>=0.8` | DOCX ingestion for reference materials | Best-effort public attribution: MIT | Generally compatible with MIT. |
| `platformdirs` | `>=4.3` | user-config path resolution | Best-effort public attribution: MIT | Generally compatible with MIT. |
| `tomlkit` | `>=0.13` | structured TOML editing / persistence | Best-effort public attribution: MIT | Generally compatible with MIT. |
| `pathspec` | `>=0.12` | gitignore-like repo-analysis ignore engine | Best-effort public attribution: MPL-2.0 | Usually compatible as a dependency, but worth explicit release review because MPL is file-level copyleft rather than plain permissive. |
| `keyring` | `>=25.0` | keyring-backed secret storage path | Best-effort public attribution: MIT | Generally compatible with MIT, but backend/runtime behavior is environment-dependent. |

### Direct development dependencies

| Package | Declared constraint | Role | Public license note | MIT-compatibility note |
|---|---:|---|---|---|
| `pytest` | `>=8.2` | test runner | Best-effort public attribution: MIT | Dev-only; generally compatible with MIT. |
| `ruff` | `>=0.6` | lint / format | Best-effort public attribution: MIT | Dev-only; generally compatible with MIT. |

## Repository-grounded interpretation of the dependency surface

The v0.1.3 dependency surface is meaningfully broader than the older v0.1.0-era audit.

The current baseline clearly depends not only on:

- CLI framework and terminal rendering
- MkDocs and MkDocs Material
- the OpenAI Python SDK

but also on:

- PDF and DOCX reference ingestion
- user-config path resolution
- structured TOML editing and persistence
- pathspec-based ignore semantics
- keyring-backed secret flows

That broader surface matters because it changes both technical release risk and compliance review posture.

## Notable transitive dependency sample

This table is a **sample**, not a complete SBOM. Its purpose is to highlight likely compliance hotspots around the current stack.

| Package | Why it is notable here | Best-effort public license note |
|---|---|---|
| `click` | underlying CLI stack beneath Typer | BSD-3-Clause |
| `markdown` | MkDocs content/rendering path | BSD-3-Clause |
| `pymdown-extensions` | typical MkDocs Material dependency | MIT |
| `watchdog` | MkDocs ecosystem file-watching path | Apache-2.0 |
| `requests` | common MkDocs/plugin/network utility dependency | Apache-2.0 |
| `urllib3` | lower-level HTTP stack in common Python ecosystems | MIT |
| `httpx` | part of the current OpenAI Python SDK stack | BSD-3-Clause |
| `httpcore` | lower-level HTTP client transport behind `httpx` | BSD-3-Clause |
| `anyio` | async compatibility layer in modern client stacks | MIT |
| `certifi` | CA bundle distribution | MPL-2.0 |
| `charset-normalizer` | text / HTTP decoding utility | MIT |
| `idna` | URL / HTTP dependency | BSD-3-Clause |

## Third-party reuse review

In the inspected current repository paths described in the review material, there is **no obvious vendored third-party source tree** and no obvious copied theme-asset bundle.

That observation should still be stated conservatively:

- it is an observation about the inspected paths
- it is not a legal guarantee that no copied snippets or templates exist anywhere

The reviewed interpretation is that the site theme is consumed via `mkdocs-material` as a package dependency rather than as a checked-in asset tree.

## Helper script and repeatable audit workflow

The repository includes `scripts/license_inventory.py`.

Its role is useful but should be described precisely:

- it parses `pyproject.toml`
- it enumerates runtime, development, and build declarations
- it reads installed package metadata through `importlib.metadata`

That makes it useful as a **repeatable local audit helper**, but it should not be described as a complete legal review mechanism or as a definitive full transitive-license adjudication tool.

## Release-review risk notes

### Main low-risk areas

Most of the direct dependency surface appears to be conventionally permissive. In practical release-review terms, the lowest-friction part of the stack is the cluster around:

- `mkdocs-material`
- `pydantic`
- `pyyaml`
- `rich`
- `typer`
- `docx2txt`
- `platformdirs`
- `tomlkit`
- `pytest`
- `ruff`

### Areas needing explicit conservative review

Two parts of the surface deserve explicit extra attention.

#### `pathspec`

`pathspec` is notable because the review material attributes it to **MPL-2.0**. That does **not** automatically make it unusable or incompatible with the project, but it does make it worth explicit release-time review because its copyleft character is different from the otherwise mostly permissive dependency set.

#### Environment-dependent `keyring` backends

`keyring` itself is treated as permissive in the review material, but actual installed transitive dependencies and runtime behavior may vary depending on OS/backend configuration. That matters less as a pure licensing issue than as an installation/compliance reproducibility issue.

## Uncertainty and honesty notes

The following caveats should remain explicit in any published version of this audit:

- Version constraints are repository-grounded because they come from the project manifest summarized in the internal review material.
- License labels in this document are **best-effort public attributions** and should be re-checked against fresh installed metadata and official package distribution pages before release.
- This document is **not legal advice**.
- The transitive table above is illustrative, not complete.
- Environment-specific extras and optional backends, especially around `keyring`, can alter the full installed transitive set in real deployments.

## Source list

### Primary repository-grounded sources

- `pyproject.toml`
- `LICENSE`
- `scripts/license_inventory.py`

### Recommended final publication-time verification sources

Before public release or publication-oriented reuse of this audit, direct dependency license notes should be re-checked against:

- official package distribution pages
- current package metadata in a clean installed environment
- the output of the repository’s own license inventory helper

## Summary

The current v0.1.3 baseline appears operationally reasonable for an MIT-licensed project from a dependency-shape perspective, but the audit should remain conservative.

The practical summary is:

- the direct dependency surface is broader than older project docs imply
- most of the surface is still best described as permissive
- `pathspec` deserves explicit release review
- `keyring` adds environment-dependent variability
- the repository’s helper script improves repeatability, but does not replace final compliance verification
