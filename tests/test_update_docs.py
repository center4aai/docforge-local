from pathlib import Path

from conftest import copy_fixture_repo, init_git_repo
from typer.testing import CliRunner

from repo_autodocs.cli import app
from repo_autodocs.gitops import list_changed_files
from repo_autodocs.llm import LLMServiceError
from repo_autodocs.update import build_update_plan, render_update_plan


def _create_minimal_project(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "mkdocs.yml").write_text("site_name: Test Docs\n", encoding="utf-8")
    (root / "README.md").write_text("# test\n", encoding="utf-8")


def test_update_docs_fails_for_missing_required_project_root_without_bootstrap(
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    missing_root = tmp_path / "does-not-exist"

    result = runner.invoke(app, ["update-docs", "--project-root", str(missing_root)])

    assert result.exit_code == 1
    assert f"FAIL: project_root missing or not a directory: {missing_root}" in result.stdout
    assert not missing_root.exists()
    assert not (missing_root / ".docforge-local" / "docs").exists()
    assert not (missing_root / ".docforge-local" / "site").exists()


def test_update_docs_bootstraps_outputs_on_valid_first_run(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project(repo_path)
    runner = CliRunner()

    result = runner.invoke(app, ["update-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert (repo_path / ".docforge-local" / "docs").is_dir()
    assert (repo_path / ".docforge-local" / "docs" / "generated").is_dir()
    assert (repo_path / ".docforge-local" / "docs" / "generated" / "overview.md").exists()


def test_update_docs_falls_back_when_not_git_repo(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    result = runner.invoke(app, ["update-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert "Git diff available: no" in result.stdout
    assert "Git diff unavailable; using full regeneration." in result.stdout
    assert (repo_path / ".docforge-local" / "docs" / "generated" / "overview.md").exists()


def test_update_docs_handles_src_changes(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    init_git_repo(repo_path)
    (repo_path / "src" / "sample" / "cli.py").write_text(
        "def run() -> int:\n    return 1\n", encoding="utf-8"
    )

    runner = CliRunner()
    result = runner.invoke(app, ["update-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert "Git diff available: yes" in result.stdout
    assert "source_changed: True" in result.stdout
    assert (
        "Source files changed under src/; regenerating code facts and documentation."
        in result.stdout
    )


def test_update_docs_handles_methodology_changes(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "repo_with_methodology")
    init_git_repo(repo_path)
    method_file = repo_path / "docs" / "context" / "methodology" / "notes.md"
    method_file.write_text("# Updated\n\nMethod change", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "update-docs",
            "--project-root",
            str(repo_path),
            "--reference-dir",
            str(repo_path / "docs" / "context" / "methodology"),
        ],
    )

    assert result.exit_code == 0
    assert (
        "External reference files changed; regrounding references and regenerating documentation."
        in result.stdout
    )
    assert ".docforge-local/docs/context/external_references.md" in result.stdout


def test_update_docs_handles_docs_and_config_changes(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "repo_with_methodology")
    init_git_repo(repo_path)
    (repo_path / "mkdocs.yml").write_text("site_name: changed\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["update-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert "docs_or_config_changed: True" in result.stdout
    assert "Docs/config files changed; forcing full regeneration." in result.stdout


def test_update_planner_reason_is_readable() -> None:
    plan = build_update_plan(
        changed_files=["README.md"],
        explicit_reference_roots_relative=["docs/context/methodology"],
        explicit_reference_files_relative=[],
        default_reference_targets_relative=[],
        out_of_repo_reference_paths=[],
    )

    assert plan.reason
    assert "unrelated files changed" in plan.reason


def test_git_changed_files_detects_modified_paths(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    init_git_repo(repo_path)
    changed = repo_path / "src" / "sample" / "cli.py"
    changed.write_text("def run() -> str:\n    return 'ok'\n", encoding="utf-8")

    files = list_changed_files(repo_path)

    assert files is not None
    assert "src/sample/cli.py" in files


def test_update_docs_supports_relative_project_root_from_controlled_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repo_path = copy_fixture_repo(workspace, "minimal_cli_repo")
    monkeypatch.chdir(workspace)
    runner = CliRunner()

    result = runner.invoke(app, ["update-docs", "--project-root", "minimal_cli_repo"])

    assert result.exit_code == 0
    assert (repo_path / ".docforge-local" / "docs" / "generated" / "overview.md").exists()


def test_update_docs_cli_project_root_overrides_env_project_root(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cli_repo = copy_fixture_repo(workspace, "minimal_cli_repo")
    env_repo = copy_fixture_repo(workspace, "repo_with_methodology")
    monkeypatch.setenv("REPO_AUTODOCS_PROJECT_ROOT", str(env_repo))
    runner = CliRunner()

    result = runner.invoke(app, ["update-docs", "--project-root", str(cli_repo)])

    assert result.exit_code == 0
    assert f"Repo path: {cli_repo.resolve()}" in result.stdout
    assert (cli_repo / ".docforge-local" / "docs" / "generated" / "overview.md").exists()
    assert not (env_repo / ".docforge-local" / "docs" / "generated" / "overview.md").exists()


def test_update_docs_use_llm_connection_failure_prints_friendly_fail(
    tmp_path: Path, monkeypatch
) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()
    monkeypatch.setenv("REPO_AUTODOCS_MODEL_NAME", "gpt-test")
    monkeypatch.setenv("REPO_AUTODOCS_BASE_URL", "http://127.0.0.1:11434/v1")

    def _raise_conn(*args, **kwargs):
        raise LLMServiceError("LLM request timed out while contacting http://127.0.0.1:11434/v1.")

    monkeypatch.setattr("repo_autodocs.cli.generate_sections", _raise_conn)

    result = runner.invoke(app, ["update-docs", "--project-root", str(repo_path), "--use-llm"])

    assert result.exit_code == 1
    assert (
        "FAIL: LLM request timed out while contacting http://127.0.0.1:11434/v1." in result.stdout
    )
    assert "Traceback" not in result.stdout


def test_update_docs_uses_env_debug_artifacts_when_flag_not_explicit(
    tmp_path: Path, monkeypatch
) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    monkeypatch.setenv("REPO_AUTODOCS_DEBUG_ARTIFACTS", "true")
    runner = CliRunner()

    result = runner.invoke(app, ["update-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert (
        repo_path / ".docforge-local" / "docs" / "generated" / "prompt_grounding_debug.md"
    ).exists()


def test_update_docs_uses_project_config_generated_language_ru(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    init_git_repo(repo_path)
    (repo_path / "docforge.toml").write_text(
        "[generation]\ngenerated_text_language='ru'\n",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["update-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    overview = (repo_path / ".docforge-local" / "docs" / "generated" / "overview.md").read_text(
        encoding="utf-8"
    )
    generated_readme = (
        repo_path / ".docforge-local" / "docs" / "generated" / "README.md"
    ).read_text(encoding="utf-8")
    external_refs = (
        repo_path / ".docforge-local" / "docs" / "context" / "external_references.md"
    ).read_text(encoding="utf-8")

    assert "Этот обзор детерминированный" in overview
    assert "сгенерированными артефактами" in generated_readme
    assert "Статус-отчёт по опциональным внешним reference-материалам." in external_refs
    assert "# Overview" in overview
    assert "# Generated Documentation" in generated_readme


def test_update_planner_supports_multiple_reference_inputs_and_out_of_repo_paths() -> None:
    plan = build_update_plan(
        changed_files=["refs/guide.md", "README.md"],
        explicit_reference_roots_relative=["refs"],
        explicit_reference_files_relative=["docs/context/reference.md"],
        default_reference_targets_relative=["README.md", "AGENTS.md"],
        out_of_repo_reference_paths=["/tmp/external-refs"],
    )

    assert plan.reference_changed is True
    assert "External reference files changed" in plan.reason
    rendered = render_update_plan(plan)
    assert "reference_change_detection_limitations:" in rendered


def test_external_reference_helper_uses_platform_neutral_path_separator_guidance(
    tmp_path: Path,
) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    result = runner.invoke(app, ["update-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    external_refs = (
        repo_path / ".docforge-local" / "docs" / "context" / "external_references.md"
    ).read_text(encoding="utf-8")
    assert "<path1><path_sep><path2>" in external_refs
    assert "platform path separator" in external_refs
