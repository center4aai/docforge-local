from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from repo_autodocs.cli import app


def _write_nav_mkdocs(repo_root: Path) -> None:
    (repo_root / "mkdocs.yml").write_text(
        """
site_name: Docs Dir Override Test
nav:
  - Home: index.md
  - Context:
      - Project Brief: context/project_brief.md
  - Generated:
      - Project Snapshot: generated/project_snapshot.md
      - Overview: generated/overview.md
""".strip(),
        encoding="utf-8",
    )


def _create_minimal_project(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    _write_nav_mkdocs(repo_root)
    (repo_root / "README.md").write_text("# Example\n", encoding="utf-8")
    (repo_root / "src" / "sample").mkdir(parents=True, exist_ok=True)
    (repo_root / "src" / "sample" / "cli.py").write_text(
        "def run() -> int:\n    return 0\n", encoding="utf-8"
    )


def _create_minimal_project_without_mkdocs(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "README.md").write_text("# Example\n", encoding="utf-8")
    (repo_root / "src" / "sample").mkdir(parents=True, exist_ok=True)
    (repo_root / "src" / "sample" / "cli.py").write_text(
        "def run() -> int:\n    return 0\n", encoding="utf-8"
    )


def test_generate_docs_respects_cli_docs_dir_override_end_to_end(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project(repo_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["generate-docs", "--project-root", str(repo_path), "--docs-dir", "custom_docs"],
    )

    assert result.exit_code == 0
    assert (repo_path / "custom_docs" / "generated" / "overview.md").exists()
    assert (repo_path / "custom_docs" / "context" / "project_brief.md").exists()
    assert (repo_path / ".docforge-local" / "site" / "index.html").exists()
    assert not (repo_path / "docs").exists()


def test_generate_docs_respects_config_file_docs_dir_override_end_to_end(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project(repo_path)
    (repo_path / "docforge.toml").write_text('docs_dir = "team_docs"\n', encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert (repo_path / "team_docs" / "generated" / "overview.md").exists()
    assert (repo_path / ".docforge-local" / "site" / "index.html").exists()
    assert not (repo_path / "docs").exists()


def test_scaffolding_preserves_authored_page_under_overridden_docs_root(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project(repo_path)

    authored = repo_path / "custom_docs" / "context" / "project_brief.md"
    authored.parent.mkdir(parents=True, exist_ok=True)
    authored.write_text("# Real Project Brief\n\nOwned by repository author.\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["generate-docs", "--project-root", str(repo_path), "--docs-dir", "custom_docs"],
    )

    assert result.exit_code == 0
    assert (
        authored.read_text(encoding="utf-8")
        == "# Real Project Brief\n\nOwned by repository author.\n"
    )


def test_generate_docs_uses_env_docs_dir_override_even_when_mkdocs_implies_default_docs(
    tmp_path: Path, monkeypatch
) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project(repo_path)
    monkeypatch.setenv("REPO_AUTODOCS_DOCS_DIR", "env_docs")

    runner = CliRunner()
    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert (repo_path / "env_docs" / "generated" / "overview.md").exists()
    assert (repo_path / "env_docs" / "context" / "project_brief.md").exists()
    assert not (repo_path / "docs").exists()


def test_update_docs_respects_docs_dir_override_end_to_end(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project(repo_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["update-docs", "--project-root", str(repo_path), "--docs-dir", "custom_docs"],
    )

    assert result.exit_code == 0
    assert (repo_path / "custom_docs" / "generated" / "overview.md").exists()
    assert (repo_path / ".docforge-local" / "site" / "index.html").exists()
    assert not (repo_path / "docs").exists()


def test_generate_docs_without_mkdocs_respects_cli_docs_dir_override(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project_without_mkdocs(repo_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["generate-docs", "--project-root", str(repo_path), "--docs-dir", "custom_docs"],
    )

    assert result.exit_code == 0
    assert (repo_path / "custom_docs" / "generated" / "overview.md").exists()
    assert (repo_path / "custom_docs" / "context" / "project_brief.md").exists()
    assert (repo_path / ".docforge-local" / "site" / "index.html").exists()
    assert not (repo_path / "docs").exists()
