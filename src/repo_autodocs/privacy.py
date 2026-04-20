"""Privacy and outbound egress helpers."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from repo_autodocs.config import AppConfig


@dataclass(slots=True)
class PrivacyReport:
    """Deterministic summary of runtime egress guarantees."""

    mode: str
    guarantee: str
    allowed_egress_endpoints: list[str]


def validate_llm_egress_config(config: AppConfig) -> list[str]:
    """Return validation failures for LLM egress-related configuration."""

    failures: list[str] = []
    if not config.enable_llm:
        return failures

    if not config.model_name:
        failures.append("llm model_name missing")

    if not config.base_url:
        failures.append("llm base_url missing")
        return failures

    parsed = urlparse(config.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        failures.append("llm base_url must be an absolute http(s) URL")

    return failures


def build_privacy_report(config: AppConfig, use_llm: bool) -> PrivacyReport:
    """Build a user-facing privacy status for doctor/reporting paths."""

    if not use_llm:
        return PrivacyReport(
            mode="local-only",
            guarantee=(
                "Deterministic local mode is active: repository data and optional external "
                "reference materials remain local to this machine."
            ),
            allowed_egress_endpoints=[],
        )

    validation_failures = validate_llm_egress_config(config)
    endpoint = config.base_url.strip() if config.base_url else "<missing>"
    if validation_failures:
        return PrivacyReport(
            mode="llm-config-invalid",
            guarantee=(
                "LLM mode requested, but configuration is incomplete; no privacy guarantee for LLM "
                "egress can be asserted until failures are fixed."
            ),
            allowed_egress_endpoints=[endpoint],
        )

    return PrivacyReport(
        mode="llm-endpoint-enabled",
        guarantee=(
            "LLM mode is active: repository data and optional external reference materials may be "
            "sent only to the configured LLM API endpoint."
        ),
        allowed_egress_endpoints=[endpoint],
    )
