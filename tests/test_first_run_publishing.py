from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from repo_autodocs.cli import app


def _write_nav_mkdocs(repo_root: Path) -> None:
    (repo_root / "mkdocs.yml").write_text(
        """
site_name: First Run Test
nav:
  - Home: index.md
  - Context:
      - Project Brief: context/project_brief.md
      - External References: context/external_references.md
  - Generated:
      - Project Snapshot: generated/project_snapshot.md
      - Overview: generated/overview.md
      - Architecture: generated/architecture.md
      - Code Structure: generated/code_structure.md
      - Runtime Entrypoints: generated/runtime_entrypoints.md
      - Reference Alignment: generated/reference_alignment.md
      - Agent Instruction Alignment: generated/agent_instruction_alignment.md
      - README Claim Alignment: generated/readme_claim_alignment.md
      - Theory Alignment: generated/theory_alignment.md
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


def test_first_run_scaffolds_missing_nav_pages_and_builds_usable_site(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project(repo_path)

    runner = CliRunner()
    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert (repo_path / ".docforge-local" / "site" / "index.html").exists()
    assert "WARNING -" not in result.stdout

    project_brief = (
        repo_path / ".docforge-local" / "docs" / "context" / "project_brief.md"
    ).read_text(encoding="utf-8")
    assert "AUTO-GENERATED PLACEHOLDER" not in project_brief
    assert "## Observed evidence" in project_brief
    assert "DOCFORGE:MANAGED" in project_brief


def test_scaffolding_never_overwrites_authored_pages(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project(repo_path)
    authored = repo_path / ".docforge-local" / "docs" / "context" / "project_brief.md"
    authored.parent.mkdir(parents=True, exist_ok=True)
    authored.write_text("# Real Project Brief\n\nOwned by repository author.\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert (
        authored.read_text(encoding="utf-8")
        == "# Real Project Brief\n\nOwned by repository author.\n"
    )


def test_deterministic_home_preserves_authored_index_page(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project(repo_path)
    authored = repo_path / ".docforge-local" / "docs" / "index.md"
    authored.parent.mkdir(parents=True, exist_ok=True)
    authored.write_text("# Authored Home\n\nKeep me.\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert authored.read_text(encoding="utf-8") == "# Authored Home\n\nKeep me.\n"


def test_deterministic_project_brief_preserves_authored_context_page(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project(repo_path)
    authored = repo_path / ".docforge-local" / "docs" / "context" / "project_brief.md"
    authored.parent.mkdir(parents=True, exist_ok=True)
    authored.write_text("# Authored Brief\n\nKeep me.\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert authored.read_text(encoding="utf-8") == "# Authored Brief\n\nKeep me.\n"


def test_external_references_page_generated_when_not_provided(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project(repo_path)

    runner = CliRunner()
    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0

    page = repo_path / ".docforge-local" / "docs" / "context" / "external_references.md"
    assert page.exists()
    content = page.read_text(encoding="utf-8")
    assert "Default-selected targets discovered: 1" in content
    assert "README.md" in content


def test_local_filesystem_build_uses_file_friendly_html_links(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project(repo_path)

    runner = CliRunner()
    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert (repo_path / ".docforge-local" / "site" / "context" / "project_brief.html").exists()
    assert not (
        repo_path / ".docforge-local" / "site" / "context" / "project_brief" / "index.html"
    ).exists()


def test_generate_docs_first_run_succeeds_without_mkdocs_config(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project_without_mkdocs(repo_path)

    runner = CliRunner()
    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert (repo_path / ".docforge-local" / "site" / "index.html").exists()
    assert (repo_path / ".docforge-local" / "docs" / "generated" / "overview.md").exists()
    assert (repo_path / ".docforge-local" / "docs" / "generated" / "code_structure.md").exists()
    assert (
        repo_path / ".docforge-local" / "docs" / "generated" / "runtime_entrypoints.md"
    ).exists()
    assert (repo_path / ".docforge-local" / "site" / "generated" / "code_structure.html").exists()
    assert (
        repo_path / ".docforge-local" / "site" / "generated" / "runtime_entrypoints.html"
    ).exists()
    assert (repo_path / ".docforge-local" / "docs" / "context" / "project_brief.md").exists()
    assert "WARNING -" not in result.stdout
    assert not (repo_path / "mkdocs.yml").exists()
    assert not list(repo_path.glob("docforge-mkdocs-fallback-*.yml"))
    assert not list(repo_path.glob("docforge-mkdocs-effective-*.yml"))


def test_update_docs_uses_same_scaffolding_guarantees(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project(repo_path)

    runner = CliRunner()
    result = runner.invoke(app, ["update-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert (repo_path / ".docforge-local" / "site" / "index.html").exists()
    assert (repo_path / ".docforge-local" / "docs" / "generated" / "code_structure.md").exists()
    assert (
        repo_path / ".docforge-local" / "docs" / "generated" / "runtime_entrypoints.md"
    ).exists()
    assert not (repo_path / ".docforge-local" / "docs" / "adr" / "README.md").exists()


def test_update_docs_first_run_succeeds_without_mkdocs_config(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project_without_mkdocs(repo_path)

    runner = CliRunner()
    result = runner.invoke(app, ["update-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert (repo_path / ".docforge-local" / "site" / "index.html").exists()
    assert (repo_path / ".docforge-local" / "docs" / "generated" / "overview.md").exists()
    assert not (repo_path / "mkdocs.yml").exists()


def test_first_run_use_llm_writes_substantive_stage4_pages(tmp_path: Path, monkeypatch) -> None:
    repo_path = tmp_path / "repo"
    _create_minimal_project_without_mkdocs(repo_path)
    monkeypatch.setenv("REPO_AUTODOCS_MODEL_NAME", "gpt-test")
    monkeypatch.setenv("REPO_AUTODOCS_BASE_URL", "http://127.0.0.1:11434/v1")

    class _FakeClient:
        pass

    monkeypatch.setattr(
        "repo_autodocs.sections.OpenAICompatibleLLMClient.from_config",
        lambda _config: _FakeClient(),
    )
    monkeypatch.setattr(
        "repo_autodocs.sections.orchestrate_llm_section",
        lambda **kwargs: type(
            "_Result",
            (),
            {
                "final_markdown": (
                    f"# {kwargs['section_name'].replace('_', ' ').title()}\n\n"
                    "## Structured\n\n- Substantive generated content.\n"
                )
            },
        )(),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path), "--use-llm"])

    assert result.exit_code == 0
    assert (repo_path / ".docforge-local" / "site" / "index.html").exists()
    for name in ("code_structure.md", "runtime_entrypoints.md"):
        text = (repo_path / ".docforge-local" / "docs" / "generated" / name).read_text(
            encoding="utf-8"
        )
        assert "Substantive generated content." in text
        assert "AUTO-GENERATED PLACEHOLDER" not in text
