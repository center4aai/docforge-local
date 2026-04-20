from __future__ import annotations

import os
from pathlib import Path

from repo_autodocs.config import load_config
from repo_autodocs.config_fields import FIELD_MAP
from repo_autodocs.config_store import ConfigStore
from repo_autodocs.theory import discover_external_references


def test_config_precedence_defaults_to_user_project_env_cli(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    user_cfg = tmp_path / "user.toml"
    user_cfg.write_text("docs_dir='user_docs'\n", encoding="utf-8")
    monkeypatch.setenv("REPO_AUTODOCS_USER_CONFIG_FILE", str(user_cfg))

    config = load_config(project_root=project_root)
    assert config.docs_dir == (project_root / "user_docs").resolve()
    assert config.get_value_source("docs_dir").source == "user_config"

    (project_root / "docforge.toml").write_text("docs_dir='project_docs'\n", encoding="utf-8")
    config = load_config(project_root=project_root)
    assert config.docs_dir == (project_root / "project_docs").resolve()
    assert config.get_value_source("docs_dir").source == "project_config"

    monkeypatch.setenv("REPO_AUTODOCS_DOCS_DIR", "env_docs")
    config = load_config(project_root=project_root)
    assert config.docs_dir == (project_root / "env_docs").resolve()
    assert config.get_value_source("docs_dir").source == "env"

    config = load_config(project_root=project_root, cli_overrides={"docs_dir": "cli_docs"})
    assert config.docs_dir == (project_root / "cli_docs").resolve()
    assert config.get_value_source("docs_dir").source == "cli"


def test_load_config_defaults_llm_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("REPO_AUTODOCS_ENABLE_LLM", raising=False)
    monkeypatch.delenv("REPO_AUTODOCS_API_KEY_ENV_VAR", raising=False)
    project_root = tmp_path / "repo"
    project_root.mkdir()

    config = load_config(project_root=project_root)

    assert config.enable_llm is False
    assert config.api_key_env_var == "OPENAI_API_KEY"
    assert config.docs_dir == config.project_root / ".docforge-local" / "docs"
    assert config.reference_dir is None
    assert config.output_dir == config.docs_dir / "generated"
    assert config.generated_docs_dir == config.docs_dir / "generated"
    assert config.site_dir == config.project_root / ".docforge-local" / "site"
    assert config.generated_text_language == "en"


def test_load_config_llm_enabled_from_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REPO_AUTODOCS_ENABLE_LLM", "true")
    monkeypatch.setenv("REPO_AUTODOCS_MODEL_NAME", "gpt-test")
    monkeypatch.setenv("REPO_AUTODOCS_API_KEY_ENV_VAR", "DOCS_KEY")
    monkeypatch.setenv("REPO_AUTODOCS_TEMPERATURE", "0.6")

    project_root = tmp_path / "repo"
    project_root.mkdir()
    config = load_config(project_root=project_root)

    assert config.enable_llm is True
    assert config.model_name == "gpt-test"
    assert config.api_key_env_var == "DOCS_KEY"
    assert config.temperature == 0.6


def test_load_config_file_values_flat_and_structured(tmp_path: Path) -> None:
    (tmp_path / "docforge.toml").write_text(
        "\n".join(
            [
                "[paths]",
                "docs_dir = 'docs_custom'",
                "output_dir = 'docs_custom/out'",
                "site_dir = 'site_custom'",
                "",
                "[references]",
                "paths = ['docs_custom/references', 'shared_refs']",
                "",
                "[generation]",
                "generated_text_language = 'ru'",
                "",
                "[repo_analysis]",
                "ignore_patterns = ['*.tmp']",
                "unignore_patterns = ['keep.tmp']",
                "",
                "[llm]",
                "api_key_mode = 'none'",
                "temperature = 0.7",
                "enable_llm = true",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(project_root=tmp_path)

    assert config.docs_dir == (tmp_path / "docs_custom").resolve()
    assert config.reference_paths == (
        (tmp_path / "docs_custom/references").resolve(),
        (tmp_path / "shared_refs").resolve(),
    )
    assert config.output_dir == (tmp_path / "docs_custom/out").resolve()
    assert config.site_dir == (tmp_path / "site_custom").resolve()
    assert config.generated_text_language == "ru"
    assert config.repo_analysis_ignore_patterns == ("*.tmp",)
    assert config.repo_analysis_unignore_patterns == ("keep.tmp",)
    assert config.api_key_mode == "none"
    assert config.temperature == 0.7
    assert config.enable_llm is True


def test_load_config_accepts_deprecated_aliases(tmp_path: Path) -> None:
    (tmp_path / "docforge.toml").write_text('methodology_dir = "legacy_refs"\n', encoding="utf-8")

    config = load_config(project_root=tmp_path)

    assert config.reference_dir == (tmp_path / "legacy_refs").resolve()
    assert config.deprecation_warnings


def test_output_dir_legacy_env_alias_supported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REPO_AUTODOCS_GENERATED_DOCS_DIR", "legacy_generated")

    config = load_config(project_root=tmp_path)

    assert config.output_dir == (tmp_path / "legacy_generated").resolve()
    assert config.get_value_source("output_dir").source_key == "REPO_AUTODOCS_GENERATED_DOCS_DIR"


def test_invalid_language_falls_back_to_en(tmp_path: Path) -> None:
    (tmp_path / "docforge.toml").write_text(
        "[generation]\ngenerated_text_language='de'\n", encoding="utf-8"
    )
    config = load_config(project_root=tmp_path)
    assert config.generated_text_language == "en"


def test_user_config_override_path_and_relative_resolution(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    user_cfg = tmp_path / "user-config.toml"
    user_cfg.write_text("[paths]\ndocs_dir='docs_user'\n", encoding="utf-8")
    monkeypatch.setenv("REPO_AUTODOCS_USER_CONFIG_FILE", str(user_cfg))

    config = load_config(project_root=project_root)

    assert config.docs_dir == (project_root / "docs_user").resolve()


def test_api_key_mode_parsing_defaults_to_env_on_invalid(tmp_path: Path) -> None:
    (tmp_path / "docforge.toml").write_text("[llm]\napi_key_mode='bad'\n", encoding="utf-8")
    config = load_config(project_root=tmp_path)
    assert config.api_key_mode == "env"


def test_windows_style_paths_are_preserved_as_paths(tmp_path: Path) -> None:
    cfg = tmp_path / "docforge.toml"
    cfg.write_text("reference_dir='C:/refs'\n", encoding="utf-8")
    config = load_config(project_root=tmp_path)
    assert isinstance(config.reference_dir, Path)


def test_store_migrates_legacy_flat_key_to_canonical_on_write(tmp_path: Path) -> None:
    cfg = tmp_path / "docforge.toml"
    cfg.write_text("docs_dir='legacy_docs'\n", encoding="utf-8")

    store = ConfigStore(project_root=tmp_path, scope="project")
    store.set_field("docs_dir", "structured_docs")

    config = load_config(project_root=tmp_path)
    assert config.docs_dir == (tmp_path / "structured_docs").resolve()
    assert config.get_value_source("docs_dir").source_key == "paths.docs_dir"


def test_ignore_pattern_env_vars_parse_multi_values(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REPO_AUTODOCS_REPO_ANALYSIS_IGNORE_PATTERNS", "a.py,b.py")
    monkeypatch.setenv("REPO_AUTODOCS_REPO_ANALYSIS_UNIGNORE_PATTERNS", "a.py")

    config = load_config(project_root=tmp_path)

    assert config.repo_analysis_ignore_patterns == ("a.py", "b.py")
    assert config.repo_analysis_unignore_patterns == ("a.py",)


def test_store_can_persist_project_root_field(tmp_path: Path) -> None:
    store = ConfigStore(project_root=tmp_path, scope="project")
    store.set_field("project_root", ".")

    config = load_config(project_root=tmp_path)
    assert config.project_root == tmp_path.resolve()


def test_reference_paths_env_is_canonical_and_singular_env_alias_compatibility(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("REPO_AUTODOCS_REFERENCE_PATHS", f"refs_a{os.pathsep}refs_b")
    config = load_config(project_root=tmp_path)
    assert len(config.reference_paths) == 2
    assert config.get_value_source("reference_paths").source_key == "REPO_AUTODOCS_REFERENCE_PATHS"

    monkeypatch.delenv("REPO_AUTODOCS_REFERENCE_PATHS", raising=False)
    monkeypatch.setenv("REPO_AUTODOCS_REFERENCE_DIR", "legacy_refs")
    config = load_config(project_root=tmp_path)
    assert config.reference_paths == ((tmp_path / "legacy_refs").resolve(),)
    assert config.reference_dir == (tmp_path / "legacy_refs").resolve()


def test_default_reference_toggles_are_behaviorally_active(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "README.md").write_text("# readme", encoding="utf-8")
    (project_root / "AGENTS.md").write_text("# agents", encoding="utf-8")
    (project_root / "docforge.toml").write_text(
        "[references]\ninclude_readme_default=true\ninclude_agent_instructions_default=false\n",
        encoding="utf-8",
    )
    config = load_config(project_root=project_root)
    discovery = discover_external_references(
        project_root=config.project_root,
        explicit_reference_paths=config.reference_paths,
        include_readme_default=config.reference_include_readme_default,
        include_agent_instructions_default=config.reference_include_agent_instructions_default,
        default_readme_patterns=config.reference_default_readme_patterns,
        default_agent_instruction_patterns=config.reference_default_agent_instruction_patterns,
    )
    assert any(source.display_path == "README.md" for source in discovery.sources)
    assert all(source.display_path != "AGENTS.md" for source in discovery.sources)


def test_default_reference_target_patterns_are_loaded_from_config(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "docforge.toml").write_text(
        "\n".join(
            [
                "[references]",
                "default_readme_patterns=['README-*.md']",
                "default_agent_instruction_patterns=['**/*AGENT.md']",
            ]
        ),
        encoding="utf-8",
    )
    config = load_config(project_root=project_root)

    assert config.reference_default_readme_patterns == ("README-*.md",)
    assert config.reference_default_agent_instruction_patterns == ("**/*AGENT.md",)


def test_generated_text_language_field_is_active_and_not_future_worded() -> None:
    field = FIELD_MAP["generated_text_language"]
    assert field.active_now is True
    assert "partial" not in field.description.lower()
    assert "later" not in field.description.lower()
