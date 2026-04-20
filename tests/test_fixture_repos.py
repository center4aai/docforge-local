from pathlib import Path

from conftest import copy_fixture_repo
from typer.testing import CliRunner

from repo_autodocs.cli import app


def test_fixture_repo_with_methodology_runs_end_to_end_deterministic_generation(
    tmp_path: Path,
) -> None:
    repo_path = copy_fixture_repo(tmp_path, "repo_with_methodology")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "generate-docs",
            "--project-root",
            str(repo_path),
            "--reference-dir",
            str(repo_path / "docs" / "context" / "methodology"),
        ],
    )

    assert result.exit_code == 0
    assert (
        "External references summary: explicit_inputs=1, discovered=1, parsed=1, unparsed=0"
        in result.stdout
    )
    assert (repo_path / ".docforge-local" / "docs" / "generated" / "project_snapshot.md").exists()
    assert (repo_path / ".docforge-local" / "site" / "index.html").exists()
