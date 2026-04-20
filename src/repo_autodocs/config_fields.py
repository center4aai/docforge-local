"""Editable configuration field catalog for the config manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from repo_autodocs.config_models import AppConfig

FieldType = Literal["path", "string", "float", "bool", "enum", "string_list"]
FieldScope = Literal["project", "user"]


@dataclass(frozen=True, slots=True)
class ConfigField:
    key: str
    label: str
    description: str
    field_type: FieldType
    canonical_path: tuple[str, ...]
    legacy_paths: tuple[tuple[str, ...], ...]
    scopes: tuple[FieldScope, ...] = ("project", "user")
    enum_values: tuple[str, ...] = ()
    active_now: bool = True

    def supports_scope(self, scope: FieldScope) -> bool:
        return scope in self.scopes


def _stringify(value: object) -> str:
    if value is None:
        return "<unset>"
    if isinstance(value, tuple):
        return ", ".join(str(item) for item in value)
    return str(value)


FIELDS: tuple[ConfigField, ...] = (
    ConfigField(
        key="project_root",
        label="Project root",
        description="Repository root path used for scanning and generation.",
        field_type="path",
        canonical_path=("paths", "project_root"),
        legacy_paths=(("project_root",),),
    ),
    ConfigField(
        key="docs_dir",
        label="Docs directory",
        description="Managed docs root path.",
        field_type="path",
        canonical_path=("paths", "docs_dir"),
        legacy_paths=(("docs_dir",),),
    ),
    ConfigField(
        key="output_dir",
        label="Generated output directory",
        description="Directory where generated markdown pages are written.",
        field_type="path",
        canonical_path=("paths", "output_dir"),
        legacy_paths=(("output_dir",), ("output", "output_dir")),
    ),
    ConfigField(
        key="site_dir",
        label="Site directory",
        description="Directory where MkDocs builds HTML.",
        field_type="path",
        canonical_path=("paths", "site_dir"),
        legacy_paths=(("site_dir",), ("output", "site_dir")),
    ),
    ConfigField(
        key="reference_paths",
        label="Reference paths",
        description=(
            "External reference paths (0..N explicit files/directories) used for routed "
            "alignment and optional grounding."
        ),
        field_type="string_list",
        canonical_path=("references", "paths"),
        legacy_paths=(("reference_paths",), ("reference_dir",), ("methodology_dir",)),
    ),
    ConfigField(
        key="reference_include_readme_default",
        label="Default include README",
        description="Default reference-target toggle for README in routed reference workflows.",
        field_type="bool",
        canonical_path=("references", "include_readme_default"),
        legacy_paths=(),
    ),
    ConfigField(
        key="reference_include_agent_instructions_default",
        label="Default include agent instructions",
        description="Default reference-target toggle for AI-agent instruction files.",
        field_type="bool",
        canonical_path=("references", "include_agent_instructions_default"),
        legacy_paths=(),
    ),
    ConfigField(
        key="reference_default_readme_patterns",
        label="Default README target patterns",
        description="Glob patterns for default README reference-target selection.",
        field_type="string_list",
        canonical_path=("references", "default_readme_patterns"),
        legacy_paths=(),
    ),
    ConfigField(
        key="reference_default_agent_instruction_patterns",
        label="Default agent-instruction patterns",
        description="Glob patterns for default AI-agent instruction target selection.",
        field_type="string_list",
        canonical_path=("references", "default_agent_instruction_patterns"),
        legacy_paths=(),
    ),
    ConfigField(
        key="use_repo_analysis_default_ignores",
        label="Use repo-analysis default ignores",
        description="Enable built-in implementation-analysis ignore defaults.",
        field_type="bool",
        canonical_path=("repo_analysis", "use_default_ignores"),
        legacy_paths=(),
    ),
    ConfigField(
        key="use_repo_gitignore",
        label="Use .gitignore for repo-analysis",
        description="Apply repository .gitignore patterns during implementation analysis.",
        field_type="bool",
        canonical_path=("repo_analysis", "use_repo_gitignore"),
        legacy_paths=(),
    ),
    ConfigField(
        key="repo_analysis_ignore_patterns",
        label="Repo-analysis ignore patterns",
        description="Additional gitignore-style ignore patterns for implementation analysis.",
        field_type="string_list",
        canonical_path=("repo_analysis", "ignore_patterns"),
        legacy_paths=(),
    ),
    ConfigField(
        key="repo_analysis_unignore_patterns",
        label="Repo-analysis unignore patterns",
        description="Gitignore-style unignore patterns applied after ignore rules.",
        field_type="string_list",
        canonical_path=("repo_analysis", "unignore_patterns"),
        legacy_paths=(),
    ),
    ConfigField(
        key="generated_text_language",
        label="Generated text language",
        description="Language preference for generated explanatory prose (`en` or `ru`).",
        field_type="enum",
        enum_values=("en", "ru"),
        canonical_path=("generation", "generated_text_language"),
        legacy_paths=(("generated_text_language",),),
        active_now=True,
    ),
    ConfigField(
        key="enable_llm",
        label="Enable LLM by default",
        description="Default LLM mode toggle.",
        field_type="bool",
        canonical_path=("llm", "enable_llm"),
        legacy_paths=(("enable_llm",),),
    ),
    ConfigField(
        key="model_name",
        label="LLM model name",
        description="Model identifier for OpenAI-compatible endpoint.",
        field_type="string",
        canonical_path=("llm", "model_name"),
        legacy_paths=(("model_name",),),
    ),
    ConfigField(
        key="base_url",
        label="LLM base URL",
        description="OpenAI-compatible endpoint URL.",
        field_type="string",
        canonical_path=("llm", "base_url"),
        legacy_paths=(("base_url",),),
    ),
    ConfigField(
        key="temperature",
        label="LLM temperature",
        description="Sampling temperature used in LLM mode.",
        field_type="float",
        canonical_path=("llm", "temperature"),
        legacy_paths=(("temperature",),),
    ),
    ConfigField(
        key="api_key_mode",
        label="API key mode",
        description="Credential source mode: env, keyring, or none.",
        field_type="enum",
        enum_values=("env", "keyring", "none"),
        canonical_path=("llm", "api_key_mode"),
        legacy_paths=(("api_key_mode",),),
    ),
    ConfigField(
        key="api_key_env_var",
        label="API key env var name",
        description="Environment variable name used when api_key_mode=env.",
        field_type="string",
        canonical_path=("llm", "api_key_env_var"),
        legacy_paths=(("api_key_env_var",),),
    ),
    ConfigField(
        key="api_key_secret_name",
        label="API key secret name",
        description="Keyring secret identifier used when api_key_mode=keyring.",
        field_type="string",
        canonical_path=("llm", "api_key_secret_name"),
        legacy_paths=(("api_key_secret_name",),),
    ),
)

FIELD_MAP = {f.key: f for f in FIELDS}


def get_field_value(config: AppConfig, field_key: str) -> object:
    return getattr(config, field_key)


def format_effective_value(config: AppConfig, field_key: str) -> str:
    return _stringify(get_field_value(config, field_key))
