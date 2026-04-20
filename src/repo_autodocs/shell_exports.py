"""Shell export helpers for config values."""

from __future__ import annotations

import os
from typing import Literal

from repo_autodocs.config_models import AppConfig

ShellName = Literal["bash", "pwsh", "cmd"]


def _quote_bash(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _quote_pwsh(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def emit_shell_env(config: AppConfig, shell: ShellName) -> str:
    values: list[tuple[str, str]] = [
        ("REPO_AUTODOCS_PROJECT_ROOT", str(config.project_root)),
        ("REPO_AUTODOCS_DOCS_DIR", str(config.docs_dir)),
        ("REPO_AUTODOCS_OUTPUT_DIR", str(config.output_dir)),
        ("REPO_AUTODOCS_SITE_DIR", str(config.site_dir)),
        ("REPO_AUTODOCS_ENABLE_LLM", str(config.enable_llm).lower()),
        ("REPO_AUTODOCS_MODEL_NAME", config.model_name or ""),
        ("REPO_AUTODOCS_BASE_URL", config.base_url or ""),
        ("REPO_AUTODOCS_TEMPERATURE", str(config.temperature)),
        ("REPO_AUTODOCS_API_KEY_MODE", config.api_key_mode),
        ("REPO_AUTODOCS_API_KEY_ENV_VAR", config.api_key_env_var),
        ("REPO_AUTODOCS_API_KEY_SECRET_NAME", config.api_key_secret_name or ""),
        ("REPO_AUTODOCS_GENERATED_TEXT_LANGUAGE", config.generated_text_language),
        (
            "REPO_AUTODOCS_REFERENCE_INCLUDE_README_DEFAULT",
            str(config.reference_include_readme_default).lower(),
        ),
        (
            "REPO_AUTODOCS_REFERENCE_INCLUDE_AGENT_INSTRUCTIONS_DEFAULT",
            str(config.reference_include_agent_instructions_default).lower(),
        ),
        (
            "REPO_AUTODOCS_REFERENCE_DEFAULT_README_PATTERNS",
            os.pathsep.join(config.reference_default_readme_patterns),
        ),
        (
            "REPO_AUTODOCS_REFERENCE_DEFAULT_AGENT_INSTRUCTION_PATTERNS",
            os.pathsep.join(config.reference_default_agent_instruction_patterns),
        ),
        (
            "REPO_AUTODOCS_USE_REPO_ANALYSIS_DEFAULT_IGNORES",
            str(config.use_repo_analysis_default_ignores).lower(),
        ),
        ("REPO_AUTODOCS_USE_REPO_GITIGNORE", str(config.use_repo_gitignore).lower()),
        (
            "REPO_AUTODOCS_REPO_ANALYSIS_IGNORE_PATTERNS",
            ",".join(config.repo_analysis_ignore_patterns),
        ),
        (
            "REPO_AUTODOCS_REPO_ANALYSIS_UNIGNORE_PATTERNS",
            ",".join(config.repo_analysis_unignore_patterns),
        ),
    ]

    if config.reference_paths:
        values.append(
            (
                "REPO_AUTODOCS_REFERENCE_PATHS",
                os.pathsep.join(str(p) for p in config.reference_paths),
            )
        )

    lines = ["# docforge-local config export (non-secret values only)"]
    if shell == "bash":
        lines.extend(f"export {name}={_quote_bash(value)}" for name, value in values)
    elif shell == "pwsh":
        lines.extend(f"$env:{name} = {_quote_pwsh(value)}" for name, value in values)
    elif shell == "cmd":
        lines.extend(f"set {name}={value}" for name, value in values)
    else:
        raise ValueError(f"Unsupported shell: {shell}")

    lines.append("# API key value is never emitted. Set it separately or use keyring mode.")
    return "\n".join(lines) + "\n"
