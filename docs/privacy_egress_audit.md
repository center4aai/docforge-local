# Privacy and outbound egress audit for DocForge Local

**Scope:** current v0.1.3 code paths, CLI workflows, LLM auth/egress validation, site-building behavior, and environment-dependent secret-storage behavior.  
**Method note:** this document distinguishes explicit runtime network behavior from local-only code paths and from merely network-capable dependencies.

## Scope and evidence standard

This audit is intended to answer a narrow question:

**What outbound network behavior is actually part of the current DocForge Local product contract, and what remains local-only?**

The document is based on repository-grounded findings summarized in the internal review material. It is not a generic dependency audit and it does not treat “a dependency could make HTTP requests” as equivalent to “DocForge Local currently sends repository data there.”

## High-level posture

The current privacy posture can be summarized as follows:

- default deterministic operation is **local-only**
- meaningful runtime egress exists only through the **configured OpenAI-compatible LLM endpoint**
- LLM use is **optional and explicit**
- there is no documented hidden fallback vendor endpoint
- generated site publishing is local and does not introduce configured analytics/CDN behavior in the reviewed baseline
- secret handling changes local storage behavior, not egress destination

## Explicit network-capable behavior

The meaningful runtime egress surface in the current implementation is the **OpenAI-compatible LLM endpoint** used by the current LLM client, and only when LLM mode is actually enabled.

The current reviewed contract is:

- the client is constructed with explicit `base_url`
- it may also use a resolved API key, depending on auth mode
- requests are sent only when the user enables LLM-assisted operation

The validation contract described in the review material requires:

- `model_name` when LLM mode is enabled
- `base_url` when LLM mode is enabled
- `base_url` to be an absolute `http(s)` URL

That is the explicit outbound egress contract reflected in the current audit basis.

## Local-only behavior

The following behavior is treated as local-only in the current v0.1.3 baseline:

- deterministic generation when LLM mode is disabled
- repository scanning
- reference discovery
- PDF and DOCX text extraction
- deterministic alignment
- debug artifact generation
- config editing and validation
- local MkDocs site build and publishing workflow

The review material also notes that deterministic flows are reinforced by tests asserting that local deterministic execution does not instantiate or call the OpenAI client in no-LLM mode.

## Runtime posture matrix

| Command / mode | Current posture | Network / egress implication |
|---|---|---|
| `doctor` | local validation only | none expected |
| `doctor --privacy` | local validation + privacy report rendering | none expected |
| `generate-docs` | deterministic local scan + render + MkDocs build by default | none expected |
| `update-docs` | deterministic update-plan + regeneration workflow | none expected unless LLM is explicitly enabled |
| `generate-docs --use-llm` | same local pipeline, but section synthesis may call the configured LLM endpoint | egress only to configured `base_url` if validation passes |
| `update-docs --use-llm` | same as above with update-plan prelude | egress only to configured `base_url` if validation passes |

## Privacy report posture

The current review material describes `doctor --privacy` as exposing a privacy report that distinguishes between:

- `local-only`
- `llm-config-invalid`
- `llm-endpoint-enabled`

The important privacy implication is that the report is expected to show configured allowed endpoint(s), not hidden or implicit fallback destinations.

## Current auth model

The current auth surface is explicitly modeled in three modes.

### `api_key_mode=env`

- resolves the key from `api_key_env_var`
- deletion is manual in the user’s shell/profile
- DocForge Local does not “own” the external shell environment itself

### `api_key_mode=keyring`

- resolves from OS/user keyring
- storage and deletion are handled through keyring-backed flows
- actual usability depends on a usable backend and the relevant secret naming/config fields

### `api_key_mode=none`

- no key is resolved
- requests may still be attempted if the configured endpoint allows anonymous access

This matters because the older privacy wording in the project history can over-imply that API-key-based auth is always central. The v0.1.3 baseline is more explicit and more flexible than that.

## What is absent in the currently reviewed baseline

The reviewed material says the current codebase does **not** show the following as first-class behavior:

- hidden fallback to a vendor endpoint when `base_url` is missing
- telemetry export
- analytics beacons
- remote CDN/script injection in generated docs
- remote font loading configured by project MkDocs settings

This should be phrased conservatively as **not present in the currently inspected code/config**, not as an eternal guarantee about every future version.

The same review basis also notes that the generated site theme configuration disables remote fonts via `theme.font: false`, and that no analytics/CDN settings are configured in the reviewed MkDocs setup.

## Dependency capability versus real egress

This distinction should remain explicit.

Dependencies such as `openai`, `httpx`, or other HTTP-capable libraries are evidence of **potential capability in the dependency graph**. They are **not** by themselves evidence that DocForge Local sends repository data anywhere in default operation.

Under the current contract:

- no-LLM mode remains local-only
- configured LLM mode creates a deliberate user-chosen egress path to the configured endpoint
- other major workflow surfaces remain local filesystem operations

## Secret-storage caveat

Keyring support changes **where credentials are stored locally**, not where documentation or repository data is sent.

That is still operationally important because keyring behavior is environment-dependent:

- usable backend availability depends on host OS/runtime configuration
- secret-management UX therefore varies by environment
- reproducibility of the secret path is lower than plain file-only config

This is a secret-storage caveat, not a new outbound-evidence surface.

## Verification anchors

The review material identifies the following file classes as the main verification anchors for this audit:

- privacy/egress validation logic
- the LLM client and request path
- secret resolution and keyring/env/none behavior
- CLI runtime validation flow
- MkDocs and publisher behavior
- tests that enforce the intended no-LLM and privacy-report posture

In the project tree, those anchors correspond to the privacy, LLM, secrets, CLI, publishing, and privacy-related test modules described by the internal review.

## Uncertainty notes

The following caveats should remain explicit.

- Keyring behavior is **environment-dependent** because backend usability matters, not just Python import success.
- If a user points `base_url` at a reverse proxy, gateway, or self-hosted inference service, the privacy implications depend on that external system. The project can validate URL shape, but not remote service policy.
- This document distinguishes carefully between **runtime egress actually performed by the product** and **network capability present somewhere in the dependency stack**.
- Statements in this document are tied to the currently reviewed baseline, not to all future versions.

## Source list

This audit is primarily repository-grounded. The main source families are the project files and tests summarized in the internal review material, especially the areas covering:

- privacy report generation and egress validation
- LLM client construction and outbound request path
- secret resolution
- CLI workflow behavior
- publisher / MkDocs behavior
- privacy-related tests

## Summary

The current v0.1.3 posture is straightforward:

- **default mode is local-only**
- **explicit LLM mode introduces the only meaningful configured outbound egress path**
- **that egress path is bounded to a user-configured endpoint**
- **there is no reviewed evidence of hidden telemetry or hidden vendor fallback**
- **keyring changes local secret handling, not egress destination**

That is a stronger and more precise privacy story than the older project documents implied, but it should still be communicated with proper caveats about environment dependence and external endpoint policy.
