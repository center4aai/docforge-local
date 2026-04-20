from typer.testing import CliRunner

from repo_autodocs.cli import app


def test_root_help_mentions_config_and_primary_workflows() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "primary configuration UX" in result.stdout
    assert "config" in result.stdout
    assert "generate-docs" in result.stdout
    assert "update-docs" in result.stdout


def test_config_help_is_available() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["config", "--help"])

    assert result.exit_code == 0
    assert "--show-effective" in result.stdout
    assert "--show-sources" in result.stdout


def test_generate_docs_help_uses_external_reference_terms() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["generate-docs", "--help"])

    assert result.exit_code == 0
    assert "Explicit external" in result.stdout
    assert "reference path" in result.stdout
    assert "--methodology-dir" in result.stdout
    assert "--reference-dir" in result.stdout


def test_update_docs_help_uses_current_contract_terms() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["update-docs", "--help"])

    assert result.exit_code == 0
    assert "deterministic git-diff planning summary" in result.stdout
    assert "Explicit external" in result.stdout
    assert "reference path" in result.stdout
