"""Typed configuration models for DocForge Local."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from repo_autodocs.models import ProjectPaths

ConfigSourceName = Literal["default", "user_config", "project_config", "env", "cli"]
ApiKeyMode = Literal["env", "keyring", "none"]
GeneratedTextLanguage = Literal["en", "ru"]


@dataclass(slots=True, frozen=True)
class ConfigValueSource:
    """Source metadata for a resolved config field."""

    field_name: str
    source: ConfigSourceName
    source_key: str
    deprecated_alias_used: bool = False


@dataclass(slots=True)
class AppConfig:
    """Application configuration loaded from layered sources."""

    project_paths: ProjectPaths
    model_name: str | None = None
    base_url: str | None = None
    api_key_env_var: str = "OPENAI_API_KEY"
    api_key_mode: ApiKeyMode = "env"
    api_key_secret_name: str | None = None
    temperature: float = 0.2
    enable_llm: bool = False
    debug_artifacts: bool = False
    generated_text_language: GeneratedTextLanguage = "en"
    reference_paths: tuple[Path, ...] = ()
    reference_include_readme_default: bool = True
    reference_include_agent_instructions_default: bool = True
    reference_default_readme_patterns: tuple[str, ...] = ("README.md",)
    reference_default_agent_instruction_patterns: tuple[str, ...] = (
        "**/AGENTS.md",
        "**/CLAUDE.md",
        "**/CODEX.md",
        "**/CURSOR.md",
        "**/AIDER.md",
        "**/CONTINUE.md",
        "**/GEMINI.md",
    )
    use_repo_analysis_default_ignores: bool = True
    use_repo_gitignore: bool = True
    repo_analysis_ignore_patterns: tuple[str, ...] = ()
    repo_analysis_unignore_patterns: tuple[str, ...] = ()
    value_sources: dict[str, ConfigValueSource] = field(default_factory=dict)
    deprecation_warnings: list[str] = field(default_factory=list)

    @property
    def project_root(self) -> Path:
        return self.project_paths.project_root

    @property
    def docs_dir(self) -> Path:
        return self.project_paths.docs_dir

    @property
    def artifact_root(self) -> Path:
        return self.project_root / ".docforge-local"

    @property
    def reference_dir(self) -> Path | None:
        return self.reference_paths[0] if self.reference_paths else None

    @property
    def methodology_dir(self) -> Path | None:
        return self.reference_dir

    @property
    def output_dir(self) -> Path:
        return self.project_paths.output_dir

    @property
    def site_dir(self) -> Path:
        return self.project_paths.site_dir

    @property
    def generated_docs_dir(self) -> Path:
        return self.output_dir

    def get_value_source(self, field_name: str) -> ConfigValueSource:
        return self.value_sources[field_name]
