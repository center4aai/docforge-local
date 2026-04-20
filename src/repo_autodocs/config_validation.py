"""Validation helpers for config-manager draft/effective state."""

from __future__ import annotations

import os
from dataclasses import dataclass

from repo_autodocs.config_models import AppConfig
from repo_autodocs.privacy import validate_llm_egress_config
from repo_autodocs.secrets import api_key_present, keyring_status


@dataclass(slots=True)
class ValidationReport:
    passes: list[str]
    warnings: list[str]
    failures: list[str]


def validate_config(config: AppConfig) -> ValidationReport:
    passes: list[str] = []
    warnings: list[str] = []
    failures: list[str] = []

    if config.project_root.exists() and config.project_root.is_dir():
        passes.append(f"project_root exists: {config.project_root}")
    else:
        failures.append(f"project_root missing or not a directory: {config.project_root}")

    if config.docs_dir.exists() and config.docs_dir.is_dir():
        passes.append(f"docs_dir exists: {config.docs_dir}")
    else:
        warnings.append(f"docs_dir does not exist yet: {config.docs_dir}")

    if config.output_dir.parent.exists():
        passes.append(f"output_dir parent exists: {config.output_dir.parent}")
    else:
        warnings.append(f"output_dir parent missing: {config.output_dir.parent}")

    if config.site_dir.parent.exists():
        passes.append(f"site_dir parent exists: {config.site_dir.parent}")
    else:
        warnings.append(f"site_dir parent missing: {config.site_dir.parent}")

    llm_failures = validate_llm_egress_config(config)
    if llm_failures:
        failures.extend(llm_failures)
    elif config.enable_llm:
        passes.append("llm endpoint configuration is valid")

    if config.api_key_mode == "env":
        if config.api_key_env_var:
            passes.append(f"api_key_mode=env uses variable: {config.api_key_env_var}")
            if os.getenv(config.api_key_env_var):
                passes.append(f"api key present in env var: {config.api_key_env_var}")
            else:
                warnings.append(f"api key env var is not set: {config.api_key_env_var}")
    elif config.api_key_mode == "keyring":
        keyring = keyring_status()
        if not keyring.available:
            failures.append(
                f"api_key_mode=keyring requires usable keyring backend: {keyring.reason}"
            )
        elif not config.api_key_secret_name:
            failures.append("api_key_secret_name required when api_key_mode=keyring")
        elif api_key_present(config):
            passes.append("api key present in keyring")
        else:
            warnings.append("api key not found in keyring for configured secret name")
    else:
        warnings.append("api_key_mode=none: requests will be sent without authentication")

    return ValidationReport(passes=passes, warnings=warnings, failures=failures)
