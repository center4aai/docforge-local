from __future__ import annotations

from pathlib import Path

import pytest
from conftest import copy_fixture_repo
from typer.testing import CliRunner

from repo_autodocs.cli import (
    POWERSHELL_COMPLETION_BLOCK_END,
    POWERSHELL_COMPLETION_BLOCK_START,
    _install_powershell_completion,
    _upsert_managed_block,
    _write_text_atomic,
    app,
)


def _create_minimal_project(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "mkdocs.yml").write_text("site_name: Test Docs\n", encoding="utf-8")
    (root / "README.md").write_text("# test\n", encoding="utf-8")


def test_generate_docs_bootstraps_docs_dir_on_first_run(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    _create_minimal_project(project_root)
    runner = CliRunner()

    result = runner.invoke(app, ["generate-docs", "--project-root", str(project_root)])

    assert result.exit_code == 0
    assert (project_root / ".docforge-local" / "docs").is_dir()
    assert (project_root / ".docforge-local" / "docs" / "generated" / "overview.md").exists()


def test_generate_docs_continues_when_optional_methodology_missing(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    _create_minimal_project(project_root)
    runner = CliRunner()

    result = runner.invoke(app, ["generate-docs", "--project-root", str(project_root)])

    assert result.exit_code == 0
    assert (
        "PASS: reference inputs not explicitly provided (optional explicit inputs disabled)"
        in result.stdout
    )


def test_generate_docs_fails_for_missing_required_project_root(tmp_path: Path) -> None:
    runner = CliRunner()
    missing_root = tmp_path / "does-not-exist"

    result = runner.invoke(app, ["generate-docs", "--project-root", str(missing_root)])

    assert result.exit_code == 1
    assert f"FAIL: project_root missing or not a directory: {missing_root}" in result.stdout
    assert not missing_root.exists()
    assert not (missing_root / ".docforge-local" / "docs").exists()
    assert not (missing_root / ".docforge-local" / "site").exists()


def test_generate_docs_is_idempotent_after_bootstrap(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    _create_minimal_project(project_root)
    runner = CliRunner()

    first = runner.invoke(app, ["generate-docs", "--project-root", str(project_root)])
    second = runner.invoke(app, ["generate-docs", "--project-root", str(project_root)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert (project_root / ".docforge-local" / "docs" / "generated" / "architecture.md").exists()


def test_install_powershell_completion_creates_new_profile(tmp_path: Path, monkeypatch) -> None:
    profile = tmp_path / "Microsoft.PowerShell_profile.ps1"
    monkeypatch.setattr("repo_autodocs.cli._resolve_powershell_profile_path", lambda _: profile)

    _install_powershell_completion(
        prog_name="docforge-local",
        complete_var="_DOCFORGE_LOCAL_COMPLETE",
        shell="pwsh",
    )

    assert profile.exists()
    content = profile.read_text(encoding="utf-8")
    assert POWERSHELL_COMPLETION_BLOCK_START in content
    assert POWERSHELL_COMPLETION_BLOCK_END in content


def test_install_powershell_completion_handles_missing_trailing_newline(
    tmp_path: Path, monkeypatch
) -> None:
    profile = tmp_path / "Microsoft.PowerShell_profile.ps1"
    profile.write_text('$env:PYTHONUTF8 = "1"', encoding="utf-8")
    monkeypatch.setattr("repo_autodocs.cli._resolve_powershell_profile_path", lambda _: profile)

    _install_powershell_completion(
        prog_name="docforge-local",
        complete_var="_DOCFORGE_LOCAL_COMPLETE",
        shell="pwsh",
    )

    content = profile.read_text(encoding="utf-8")
    assert '$env:PYTHONUTF8 = "1"\n# >>> docforge-local completion >>>' in content


def test_install_powershell_completion_handles_existing_trailing_newline(
    tmp_path: Path, monkeypatch
) -> None:
    profile = tmp_path / "Microsoft.PowerShell_profile.ps1"
    profile.write_text("Import-Module PSReadLine\n", encoding="utf-8")
    monkeypatch.setattr("repo_autodocs.cli._resolve_powershell_profile_path", lambda _: profile)

    _install_powershell_completion(
        prog_name="docforge-local",
        complete_var="_DOCFORGE_LOCAL_COMPLETE",
        shell="pwsh",
    )

    content = profile.read_text(encoding="utf-8")
    assert "Import-Module PSReadLine\n# >>> docforge-local completion >>>" in content


def test_install_powershell_completion_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    profile = tmp_path / "Microsoft.PowerShell_profile.ps1"
    monkeypatch.setattr("repo_autodocs.cli._resolve_powershell_profile_path", lambda _: profile)

    _install_powershell_completion(
        prog_name="docforge-local",
        complete_var="_DOCFORGE_LOCAL_COMPLETE",
        shell="pwsh",
    )
    _install_powershell_completion(
        prog_name="docforge-local",
        complete_var="_DOCFORGE_LOCAL_COMPLETE",
        shell="pwsh",
    )

    content = profile.read_text(encoding="utf-8")
    assert content.count(POWERSHELL_COMPLETION_BLOCK_START) == 1
    assert content.count(POWERSHELL_COMPLETION_BLOCK_END) == 1


def test_install_completion_does_not_require_llm_env_vars(tmp_path: Path, monkeypatch) -> None:
    profile = tmp_path / "Microsoft.PowerShell_profile.ps1"
    monkeypatch.setattr("repo_autodocs.cli._resolve_powershell_profile_path", lambda _: profile)
    monkeypatch.delenv("REPO_AUTODOCS_MODEL_NAME", raising=False)
    monkeypatch.delenv("REPO_AUTODOCS_BASE_URL", raising=False)
    monkeypatch.delenv("REPO_AUTODOCS_API_KEY_ENV_VAR", raising=False)

    _install_powershell_completion(
        prog_name="docforge-local",
        complete_var="_DOCFORGE_LOCAL_COMPLETE",
        shell="pwsh",
    )

    assert profile.exists()


def test_atomic_write_failure_preserves_existing_profile(tmp_path: Path, monkeypatch) -> None:
    profile = tmp_path / "Microsoft.PowerShell_profile.ps1"
    original = "Import-Module PSReadLine\n"
    profile.write_text(original, encoding="utf-8")

    def _fail_replace(src: Path, dst: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("repo_autodocs.cli.os.replace", _fail_replace)

    with pytest.raises(OSError):
        _write_text_atomic(profile, "new content")

    assert profile.read_text(encoding="utf-8") == original


def test_upsert_replaces_existing_completion_block_without_duplication() -> None:
    existing = (
        "Import-Module PSReadLine\n"
        "# >>> docforge-local completion >>>\n"
        "old completion\n"
        "# <<< docforge-local completion <<<\n"
        "Write-Host done\n"
    )
    block = (
        "# >>> docforge-local completion >>>\nnew completion\n# <<< docforge-local completion <<<"
    )
    updated = _upsert_managed_block(
        existing_text=existing,
        block_text=block,
        start_marker=POWERSHELL_COMPLETION_BLOCK_START,
        end_marker=POWERSHELL_COMPLETION_BLOCK_END,
    )

    assert updated.count(POWERSHELL_COMPLETION_BLOCK_START) == 1
    assert "new completion" in updated
    assert "old completion" not in updated


def test_top_level_install_completion_flag_invokes_public_cli(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        "repo_autodocs.cli._install_completion",
        lambda shell=None: ("bash", Path("/tmp/docforge-complete.sh")),
    )

    result = runner.invoke(app, ["--install-completion"])

    assert result.exit_code == 0
    expected_path = str(Path("/tmp/docforge-complete.sh"))
    assert f"bash completion installed in {expected_path}" in result.stdout
    assert "Completion will take effect once you restart the terminal" in result.stdout


def test_top_level_show_completion_flag_invokes_public_cli(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setattr(
        "repo_autodocs.cli._show_completion",
        lambda shell=None: "# completion-script",
    )

    result = runner.invoke(app, ["--show-completion"])

    assert result.exit_code == 0
    assert "# completion-script" in result.stdout


def test_root_invocation_without_args_does_not_fail_with_usage_error() -> None:
    runner = CliRunner()

    result = runner.invoke(app, [])

    assert result.exit_code == 0


def test_subcommand_still_works_with_root_callback_enabled(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    _create_minimal_project(project_root)
    runner = CliRunner()

    result = runner.invoke(app, ["generate-docs", "--project-root", str(project_root)])

    assert result.exit_code == 0
    assert (project_root / ".docforge-local" / "docs" / "generated" / "overview.md").exists()


def test_generate_docs_supports_relative_project_root_from_controlled_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repo_path = copy_fixture_repo(workspace, "minimal_cli_repo")
    monkeypatch.chdir(workspace)
    runner = CliRunner()

    result = runner.invoke(app, ["generate-docs", "--project-root", "minimal_cli_repo"])

    assert result.exit_code == 0
    assert (repo_path / ".docforge-local" / "docs" / "generated" / "overview.md").exists()
