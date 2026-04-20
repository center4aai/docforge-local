from pathlib import Path

from reference_fixtures import write_minimal_docx
from typer.testing import CliRunner

from repo_autodocs.cli import app


def test_ground_methodology_command_writes_debug_artifact(tmp_path: Path) -> None:
    methodology_dir = tmp_path / "docs" / "context" / "methodology"
    methodology_dir.mkdir(parents=True)
    (methodology_dir / "notes.md").write_text("# Notes\n\nSome methodology text.", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "ground-methodology",
            "--project-root",
            str(tmp_path),
            "--write-debug-artifact",
        ],
    )

    assert result.exit_code == 0
    assert "Discovered sources:" in result.stdout
    assert "Ingested documents:" in result.stdout
    assert "deprecated" in result.stdout
    assert (tmp_path / ".docforge-local" / "docs" / "generated" / "reference_grounding.md").exists()


def test_ground_reference_command_writes_debug_artifact(tmp_path: Path) -> None:
    methodology_dir = tmp_path / "docs" / "context" / "methodology"
    methodology_dir.mkdir(parents=True)
    (methodology_dir / "notes.md").write_text("# Notes\n\nSome methodology text.", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "ground-reference",
            "--project-root",
            str(tmp_path),
            "--write-debug-artifact",
        ],
    )

    assert result.exit_code == 0
    assert "Discovered sources:" in result.stdout
    assert (tmp_path / ".docforge-local" / "docs" / "generated" / "reference_grounding.md").exists()


def test_ground_reference_command_accepts_reference_dir_option(tmp_path: Path) -> None:
    refs = tmp_path / "refs"
    refs.mkdir(parents=True)
    (refs / "notes.md").write_text("# Notes\n\nSome methodology text.", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "ground-reference",
            "--project-root",
            str(tmp_path),
            "--reference-dir",
            str(refs),
            "--write-debug-artifact",
        ],
    )

    assert result.exit_code == 0
    assert "Discovered sources: 1" in result.stdout


def test_ground_reference_command_reports_mixed_format_counts(tmp_path: Path) -> None:
    refs = tmp_path / "refs"
    refs.mkdir(parents=True)
    (refs / "notes.md").write_text("# Notes\n\nSome methodology text.", encoding="utf-8")
    write_minimal_docx(refs / "notes.docx")
    (refs / "legacy.rst").write_text("not ingestible", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "ground-reference",
            "--project-root",
            str(tmp_path),
            "--reference-dir",
            str(refs),
            "--write-debug-artifact",
        ],
    )

    assert result.exit_code == 0
    assert "Discovered files: 3" in result.stdout
    assert "Ingest-eligible files: 2" in result.stdout
    assert "Discovered sources: 2" in result.stdout
