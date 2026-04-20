"""Source-aware configuration loader."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from repo_autodocs.config_models import AppConfig, ConfigValueSource
from repo_autodocs.config_paths import default_user_config_file
from repo_autodocs.models import ProjectPaths

DEFAULT_CONFIG_FILE_NAME = "docforge.toml"


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    loaded = tomllib.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _as_str(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return str(v)


def _as_bool(v: Any, default: bool) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _as_float(v: Any, default: float) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _as_tuple_str(v: Any) -> tuple[str, ...]:
    if v is None:
        return ()
    if isinstance(v, list):
        return tuple(str(item) for item in v)
    if isinstance(v, tuple):
        return tuple(str(item) for item in v)
    return (str(v),)


def _split_env_multi_value(raw: str) -> tuple[str, ...]:
    normalized = raw.replace(os.pathsep, ",")
    return tuple(token.strip() for token in normalized.split(",") if token.strip())


def _resolve_path(raw: str | None, *, default: Path, base_dir: Path) -> Path:
    if raw is None or raw.strip() == "":
        return default.resolve()
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = base_dir / p
    return p.resolve()


def _resolve_optional_path(raw: str | None, *, base_dir: Path) -> Path | None:
    if raw is None or raw.strip() == "":
        return None
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = base_dir / p
    return p.resolve()


def _nested(config: dict[str, Any], *keys: str) -> Any:
    node: Any = config
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _pick(
    field_name: str,
    *,
    cli_key: str | None = None,
    env_keys: tuple[str, ...] = (),
    project_keys: tuple[tuple[str, ...], ...] = (),
    user_keys: tuple[tuple[str, ...], ...] = (),
    cli: dict[str, Any],
    project_data: dict[str, Any],
    user_data: dict[str, Any],
    default: Any,
    value_sources: dict[str, ConfigValueSource],
) -> Any:
    if cli_key and cli.get(cli_key) is not None:
        value_sources[field_name] = ConfigValueSource(field_name, "cli", cli_key)
        return cli[cli_key]

    for env_key in env_keys:
        env_val = os.getenv(env_key)
        if env_val is not None:
            value_sources[field_name] = ConfigValueSource(field_name, "env", env_key)
            return env_val

    for key_path in project_keys:
        v = _nested(project_data, *key_path)
        if v is not None:
            value_sources[field_name] = ConfigValueSource(
                field_name,
                "project_config",
                ".".join(key_path),
                deprecated_alias_used=key_path[-1] == "methodology_dir",
            )
            return v

    for key_path in user_keys:
        v = _nested(user_data, *key_path)
        if v is not None:
            value_sources[field_name] = ConfigValueSource(
                field_name,
                "user_config",
                ".".join(key_path),
                deprecated_alias_used=key_path[-1] == "methodology_dir",
            )
            return v

    value_sources[field_name] = ConfigValueSource(field_name, "default", "default")
    return default


def load_config(
    project_root: Path | None = None,
    *,
    config_file: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> AppConfig:
    """Load config with precedence: CLI > env > project config > user config > defaults."""

    cli = cli_overrides or {}
    value_sources: dict[str, ConfigValueSource] = {}
    deprecation_warnings: list[str] = []

    default_root = project_root.resolve() if project_root else Path.cwd().resolve()
    user_config_file = default_user_config_file()
    user_data = _load_toml(user_config_file)

    root_locator_raw = (
        _as_str(cli.get("project_root"))
        or os.getenv("REPO_AUTODOCS_PROJECT_ROOT")
        or _as_str(_nested(user_data, "project_root"))
        or _as_str(_nested(user_data, "paths", "project_root"))
    )
    locate_root = _resolve_path(root_locator_raw, default=default_root, base_dir=default_root)
    project_config_file = (
        config_file.resolve() if config_file else (locate_root / DEFAULT_CONFIG_FILE_NAME)
    )
    project_data = _load_toml(project_config_file)

    project_root_raw = _pick(
        "project_root",
        cli_key="project_root",
        env_keys=("REPO_AUTODOCS_PROJECT_ROOT",),
        project_keys=(("project_root",), ("paths", "project_root")),
        user_keys=(("project_root",), ("paths", "project_root")),
        cli=cli,
        project_data=project_data,
        user_data=user_data,
        default=str(default_root),
        value_sources=value_sources,
    )
    root = _resolve_path(_as_str(project_root_raw), default=default_root, base_dir=default_root)

    if config_file is None and root != locate_root:
        project_config_file = root / DEFAULT_CONFIG_FILE_NAME
        project_data = _load_toml(project_config_file)

    docs_dir_raw = _pick(
        "docs_dir",
        cli_key="docs_dir",
        env_keys=("REPO_AUTODOCS_DOCS_DIR",),
        project_keys=(("docs_dir",), ("paths", "docs_dir")),
        user_keys=(("docs_dir",), ("paths", "docs_dir")),
        cli=cli,
        project_data=project_data,
        user_data=user_data,
        default=str(root / ".docforge-local" / "docs"),
        value_sources=value_sources,
    )
    docs_dir = _resolve_path(
        _as_str(docs_dir_raw), default=root / ".docforge-local" / "docs", base_dir=root
    )

    reference_paths_raw = _pick(
        "reference_paths",
        cli_key="reference_paths",
        env_keys=("REPO_AUTODOCS_REFERENCE_PATHS",),
        project_keys=(
            ("references", "paths"),
            ("reference_paths",),
            ("reference_dir",),
            ("methodology_dir",),
        ),
        user_keys=(
            ("references", "paths"),
            ("reference_paths",),
            ("reference_dir",),
            ("methodology_dir",),
        ),
        cli=cli,
        project_data=project_data,
        user_data=user_data,
        default=(),
        value_sources=value_sources,
    )

    if value_sources["reference_paths"].source_key in {"reference_dir", "methodology_dir"}:
        deprecation_warnings.append(
            "`reference_dir`/`methodology_dir` are compatibility aliases; "
            "prefer [references].paths."
        )
    if value_sources["reference_paths"].deprecated_alias_used:
        deprecation_warnings.append(
            "`methodology_dir` is deprecated and will be removed in a future release. "
            "Use `reference_dir` / `--reference-dir` / REPO_AUTODOCS_REFERENCE_DIR."
        )

    if isinstance(reference_paths_raw, str):
        if os.getenv("REPO_AUTODOCS_REFERENCE_PATHS") is not None:
            tokens = [
                item.strip() for item in reference_paths_raw.split(os.pathsep) if item.strip()
            ]
        else:
            tokens = [reference_paths_raw]
    else:
        tokens = list(_as_tuple_str(reference_paths_raw))

    if cli.get("reference_dir"):
        tokens = [str(cli["reference_dir"])]
        value_sources["reference_paths"] = ConfigValueSource(
            "reference_paths", "cli", "reference_dir"
        )
    elif cli.get("methodology_dir"):
        tokens = [str(cli["methodology_dir"])]
        value_sources["reference_paths"] = ConfigValueSource(
            "reference_paths", "cli", "methodology_dir", deprecated_alias_used=True
        )
        deprecation_warnings.append(
            "`methodology_dir` is deprecated and will be removed in a future release. "
            "Use `reference_dir` / `--reference-dir` / REPO_AUTODOCS_REFERENCE_DIR."
        )
    elif os.getenv("REPO_AUTODOCS_REFERENCE_DIR") is not None:
        tokens = [os.getenv("REPO_AUTODOCS_REFERENCE_DIR", "")]
        value_sources["reference_paths"] = ConfigValueSource(
            "reference_paths", "env", "REPO_AUTODOCS_REFERENCE_DIR"
        )
    elif os.getenv("REPO_AUTODOCS_METHODOLOGY_DIR") is not None:
        tokens = [os.getenv("REPO_AUTODOCS_METHODOLOGY_DIR", "")]
        value_sources["reference_paths"] = ConfigValueSource(
            "reference_paths", "env", "REPO_AUTODOCS_METHODOLOGY_DIR", deprecated_alias_used=True
        )
        deprecation_warnings.append(
            "`REPO_AUTODOCS_METHODOLOGY_DIR` is deprecated and will be removed in a future "
            "release. Use `REPO_AUTODOCS_REFERENCE_PATHS` or `REPO_AUTODOCS_REFERENCE_DIR`."
        )

    reference_paths = tuple(
        p for t in tokens if (p := _resolve_optional_path(str(t), base_dir=root)) is not None
    )

    output_dir_raw = _pick(
        "output_dir",
        cli_key="output_dir",
        env_keys=("REPO_AUTODOCS_OUTPUT_DIR", "REPO_AUTODOCS_GENERATED_DOCS_DIR"),
        project_keys=(("output_dir",), ("paths", "output_dir"), ("output", "output_dir")),
        user_keys=(("output_dir",), ("paths", "output_dir"), ("output", "output_dir")),
        cli=cli,
        project_data=project_data,
        user_data=user_data,
        default=str(docs_dir / "generated"),
        value_sources=value_sources,
    )
    output_dir = _resolve_path(
        _as_str(output_dir_raw), default=docs_dir / "generated", base_dir=root
    )

    site_dir_raw = _pick(
        "site_dir",
        cli_key="site_dir",
        env_keys=("REPO_AUTODOCS_SITE_DIR",),
        project_keys=(("site_dir",), ("paths", "site_dir"), ("output", "site_dir")),
        user_keys=(("site_dir",), ("paths", "site_dir"), ("output", "site_dir")),
        cli=cli,
        project_data=project_data,
        user_data=user_data,
        default=str(root / ".docforge-local" / "site"),
        value_sources=value_sources,
    )
    site_dir = _resolve_path(
        _as_str(site_dir_raw), default=root / ".docforge-local" / "site", base_dir=root
    )

    model_name = _as_str(
        _pick(
            "model_name",
            cli_key="model_name",
            env_keys=("REPO_AUTODOCS_MODEL_NAME",),
            project_keys=(("model_name",), ("llm", "model_name")),
            user_keys=(("model_name",), ("llm", "model_name")),
            cli=cli,
            project_data=project_data,
            user_data=user_data,
            default=None,
            value_sources=value_sources,
        )
    )
    base_url = _as_str(
        _pick(
            "base_url",
            cli_key="base_url",
            env_keys=("REPO_AUTODOCS_BASE_URL",),
            project_keys=(("base_url",), ("llm", "base_url")),
            user_keys=(("base_url",), ("llm", "base_url")),
            cli=cli,
            project_data=project_data,
            user_data=user_data,
            default=None,
            value_sources=value_sources,
        )
    )
    api_key_env_var = (
        _as_str(
            _pick(
                "api_key_env_var",
                cli_key="api_key_env_var",
                env_keys=("REPO_AUTODOCS_API_KEY_ENV_VAR",),
                project_keys=(("api_key_env_var",), ("llm", "api_key_env_var")),
                user_keys=(("api_key_env_var",), ("llm", "api_key_env_var")),
                cli=cli,
                project_data=project_data,
                user_data=user_data,
                default="OPENAI_API_KEY",
                value_sources=value_sources,
            )
        )
        or "OPENAI_API_KEY"
    )
    api_key_mode_raw = _as_str(
        _pick(
            "api_key_mode",
            cli_key="api_key_mode",
            env_keys=("REPO_AUTODOCS_API_KEY_MODE",),
            project_keys=(("llm", "api_key_mode"), ("api_key_mode",)),
            user_keys=(("llm", "api_key_mode"), ("api_key_mode",)),
            cli=cli,
            project_data=project_data,
            user_data=user_data,
            default="env",
            value_sources=value_sources,
        )
    )
    api_key_mode = api_key_mode_raw if api_key_mode_raw in {"env", "keyring", "none"} else "env"
    api_key_secret_name = _as_str(
        _pick(
            "api_key_secret_name",
            cli_key="api_key_secret_name",
            env_keys=("REPO_AUTODOCS_API_KEY_SECRET_NAME",),
            project_keys=(("llm", "api_key_secret_name"), ("api_key_secret_name",)),
            user_keys=(("llm", "api_key_secret_name"), ("api_key_secret_name",)),
            cli=cli,
            project_data=project_data,
            user_data=user_data,
            default=None,
            value_sources=value_sources,
        )
    )

    temperature = _as_float(
        _pick(
            "temperature",
            cli_key="temperature",
            env_keys=("REPO_AUTODOCS_TEMPERATURE",),
            project_keys=(("temperature",), ("llm", "temperature")),
            user_keys=(("temperature",), ("llm", "temperature")),
            cli=cli,
            project_data=project_data,
            user_data=user_data,
            default=0.2,
            value_sources=value_sources,
        ),
        0.2,
    )
    enable_llm = _as_bool(
        _pick(
            "enable_llm",
            cli_key="enable_llm",
            env_keys=("REPO_AUTODOCS_ENABLE_LLM",),
            project_keys=(("enable_llm",), ("llm", "enable_llm")),
            user_keys=(("enable_llm",), ("llm", "enable_llm")),
            cli=cli,
            project_data=project_data,
            user_data=user_data,
            default=False,
            value_sources=value_sources,
        ),
        False,
    )
    debug_artifacts = _as_bool(
        _pick(
            "debug_artifacts",
            cli_key="debug_artifacts",
            env_keys=("REPO_AUTODOCS_DEBUG_ARTIFACTS",),
            project_keys=(("debug_artifacts",),),
            user_keys=(("debug_artifacts",),),
            cli=cli,
            project_data=project_data,
            user_data=user_data,
            default=False,
            value_sources=value_sources,
        ),
        False,
    )

    language_raw = _as_str(
        _pick(
            "generated_text_language",
            cli_key="generated_text_language",
            env_keys=("REPO_AUTODOCS_GENERATED_TEXT_LANGUAGE",),
            project_keys=(("generation", "generated_text_language"), ("generated_text_language",)),
            user_keys=(("generation", "generated_text_language"), ("generated_text_language",)),
            cli=cli,
            project_data=project_data,
            user_data=user_data,
            default="en",
            value_sources=value_sources,
        )
    )
    if language_raw not in {"en", "ru"}:
        language_raw = "en"

    include_readme_default = _as_bool(
        _pick(
            "reference_include_readme_default",
            env_keys=("REPO_AUTODOCS_REFERENCE_INCLUDE_README_DEFAULT",),
            project_keys=(("references", "include_readme_default"),),
            user_keys=(("references", "include_readme_default"),),
            cli=cli,
            project_data=project_data,
            user_data=user_data,
            default=True,
            value_sources=value_sources,
        ),
        True,
    )
    include_agents_default = _as_bool(
        _pick(
            "reference_include_agent_instructions_default",
            env_keys=("REPO_AUTODOCS_REFERENCE_INCLUDE_AGENT_INSTRUCTIONS_DEFAULT",),
            project_keys=(("references", "include_agent_instructions_default"),),
            user_keys=(("references", "include_agent_instructions_default"),),
            cli=cli,
            project_data=project_data,
            user_data=user_data,
            default=True,
            value_sources=value_sources,
        ),
        True,
    )
    readme_patterns_raw = _pick(
        "reference_default_readme_patterns",
        env_keys=("REPO_AUTODOCS_REFERENCE_DEFAULT_README_PATTERNS",),
        project_keys=(("references", "default_readme_patterns"),),
        user_keys=(("references", "default_readme_patterns"),),
        cli=cli,
        project_data=project_data,
        user_data=user_data,
        default=("README.md",),
        value_sources=value_sources,
    )
    if value_sources["reference_default_readme_patterns"].source == "env" and isinstance(
        readme_patterns_raw, str
    ):
        reference_default_readme_patterns = _split_env_multi_value(readme_patterns_raw)
    else:
        reference_default_readme_patterns = _as_tuple_str(readme_patterns_raw)
    if not reference_default_readme_patterns:
        reference_default_readme_patterns = ("README.md",)

    agent_patterns_raw = _pick(
        "reference_default_agent_instruction_patterns",
        env_keys=("REPO_AUTODOCS_REFERENCE_DEFAULT_AGENT_INSTRUCTION_PATTERNS",),
        project_keys=(("references", "default_agent_instruction_patterns"),),
        user_keys=(("references", "default_agent_instruction_patterns"),),
        cli=cli,
        project_data=project_data,
        user_data=user_data,
        default=(
            "**/AGENTS.md",
            "**/CLAUDE.md",
            "**/CODEX.md",
            "**/CURSOR.md",
            "**/AIDER.md",
            "**/CONTINUE.md",
            "**/GEMINI.md",
        ),
        value_sources=value_sources,
    )
    if value_sources["reference_default_agent_instruction_patterns"].source == "env" and isinstance(
        agent_patterns_raw, str
    ):
        reference_default_agent_instruction_patterns = _split_env_multi_value(agent_patterns_raw)
    else:
        reference_default_agent_instruction_patterns = _as_tuple_str(agent_patterns_raw)
    if not reference_default_agent_instruction_patterns:
        reference_default_agent_instruction_patterns = (
            "**/AGENTS.md",
            "**/CLAUDE.md",
            "**/CODEX.md",
            "**/CURSOR.md",
            "**/AIDER.md",
            "**/CONTINUE.md",
            "**/GEMINI.md",
        )

    use_repo_defaults = _as_bool(
        _pick(
            "use_repo_analysis_default_ignores",
            env_keys=("REPO_AUTODOCS_USE_REPO_ANALYSIS_DEFAULT_IGNORES",),
            project_keys=(("repo_analysis", "use_default_ignores"),),
            user_keys=(("repo_analysis", "use_default_ignores"),),
            cli=cli,
            project_data=project_data,
            user_data=user_data,
            default=True,
            value_sources=value_sources,
        ),
        True,
    )
    use_repo_gitignore = _as_bool(
        _pick(
            "use_repo_gitignore",
            env_keys=("REPO_AUTODOCS_USE_REPO_GITIGNORE",),
            project_keys=(("repo_analysis", "use_repo_gitignore"),),
            user_keys=(("repo_analysis", "use_repo_gitignore"),),
            cli=cli,
            project_data=project_data,
            user_data=user_data,
            default=True,
            value_sources=value_sources,
        ),
        True,
    )
    ignore_patterns_raw = _pick(
        "repo_analysis_ignore_patterns",
        env_keys=("REPO_AUTODOCS_REPO_ANALYSIS_IGNORE_PATTERNS",),
        project_keys=(("repo_analysis", "ignore_patterns"),),
        user_keys=(("repo_analysis", "ignore_patterns"),),
        cli=cli,
        project_data=project_data,
        user_data=user_data,
        default=(),
        value_sources=value_sources,
    )
    if value_sources["repo_analysis_ignore_patterns"].source == "env" and isinstance(
        ignore_patterns_raw, str
    ):
        ignore_patterns = _split_env_multi_value(ignore_patterns_raw)
    else:
        ignore_patterns = _as_tuple_str(ignore_patterns_raw)

    unignore_patterns_raw = _pick(
        "repo_analysis_unignore_patterns",
        env_keys=("REPO_AUTODOCS_REPO_ANALYSIS_UNIGNORE_PATTERNS",),
        project_keys=(("repo_analysis", "unignore_patterns"),),
        user_keys=(("repo_analysis", "unignore_patterns"),),
        cli=cli,
        project_data=project_data,
        user_data=user_data,
        default=(),
        value_sources=value_sources,
    )
    if value_sources["repo_analysis_unignore_patterns"].source == "env" and isinstance(
        unignore_patterns_raw, str
    ):
        unignore_patterns = _split_env_multi_value(unignore_patterns_raw)
    else:
        unignore_patterns = _as_tuple_str(unignore_patterns_raw)

    return AppConfig(
        project_paths=ProjectPaths(
            project_root=root,
            docs_dir=docs_dir,
            reference_dir=reference_paths[0] if reference_paths else None,
            output_dir=output_dir,
            site_dir=site_dir,
        ),
        model_name=model_name,
        base_url=base_url,
        api_key_env_var=api_key_env_var,
        api_key_mode=api_key_mode,  # type: ignore[arg-type]
        api_key_secret_name=api_key_secret_name,
        temperature=temperature,
        enable_llm=enable_llm,
        debug_artifacts=debug_artifacts,
        generated_text_language=language_raw,  # type: ignore[arg-type]
        reference_paths=reference_paths,
        reference_include_readme_default=include_readme_default,
        reference_include_agent_instructions_default=include_agents_default,
        reference_default_readme_patterns=reference_default_readme_patterns,
        reference_default_agent_instruction_patterns=reference_default_agent_instruction_patterns,
        use_repo_analysis_default_ignores=use_repo_defaults,
        use_repo_gitignore=use_repo_gitignore,
        repo_analysis_ignore_patterns=ignore_patterns,
        repo_analysis_unignore_patterns=unignore_patterns,
        value_sources=value_sources,
        deprecation_warnings=deprecation_warnings,
    )
