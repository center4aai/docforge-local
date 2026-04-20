from pathlib import Path

from typer.testing import CliRunner

from repo_autodocs.cli import app


def test_generate_sections_command_deterministic_mode(tmp_path: Path) -> None:
    methodology_dir = tmp_path / "docs" / "context" / "methodology"
    methodology_dir.mkdir(parents=True)
    (methodology_dir / "notes.md").write_text("# Notes\n\nMethod grounding.", encoding="utf-8")

    src_dir = tmp_path / "src" / "sample"
    src_dir.mkdir(parents=True)
    (src_dir / "cli.py").write_text(
        "def run() -> None:\n    return None\n\nif __name__ == '__main__':\n    run()\n",
        encoding="utf-8",
    )

    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "generate-sections",
            "--project-root",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "docs" / "generated"),
        ],
    )

    output_dir = tmp_path / "docs" / "generated"
    assert result.exit_code == 0
    assert "Generated sections mode: deterministic" in result.stdout
    assert "Grounded external reference context: documents=" in result.stdout
    assert "Code facts summary:" in result.stdout
    assert (output_dir / "overview.md").exists()
    assert (output_dir / "architecture.md").exists()
    assert (output_dir / "theory_alignment.md").exists()
    assert (output_dir / "reference_alignment.md").exists()
    assert (output_dir / "agent_instruction_alignment.md").exists()
    assert (output_dir / "readme_claim_alignment.md").exists()
    assert (output_dir / "code_structure.md").exists()
    assert (output_dir / "runtime_entrypoints.md").exists()
    assert (output_dir / "README.md").exists()
    assert not (output_dir / "prompt_grounding_debug.md").exists()
    assert not (output_dir / "code_facts_debug.md").exists()
    assert "## What This Project Appears To Be" in (output_dir / "overview.md").read_text(
        encoding="utf-8"
    )
    assert "## Structural Organization" in (output_dir / "architecture.md").read_text(
        encoding="utf-8"
    )
    assert "Deprecated compatibility page" in (output_dir / "theory_alignment.md").read_text(
        encoding="utf-8"
    )


def test_generate_sections_command_writes_debug_artifacts_when_enabled(tmp_path: Path) -> None:
    src_dir = tmp_path / "src" / "sample"
    src_dir.mkdir(parents=True)
    (src_dir / "cli.py").write_text("def run() -> None:\n    return None\n", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "generate-sections",
            "--project-root",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "docs" / "generated"),
            "--debug-artifacts",
        ],
    )

    output_dir = tmp_path / "docs" / "generated"
    assert result.exit_code == 0
    assert (output_dir / "prompt_grounding_debug.md").exists()
    assert (output_dir / "code_facts_debug.md").exists()


def test_generate_sections_does_not_delete_reference_grounding_artifact(tmp_path: Path) -> None:
    src_dir = tmp_path / "src" / "sample"
    src_dir.mkdir(parents=True)
    (src_dir / "cli.py").write_text("def run() -> None:\n    return None\n", encoding="utf-8")
    output_dir = tmp_path / "docs" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    grounding = output_dir / "reference_grounding.md"
    grounding.write_text("# Existing grounding\n", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "generate-sections",
            "--project-root",
            str(tmp_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert grounding.exists()


def test_generate_sections_accepts_reference_dir_option(tmp_path: Path) -> None:
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "guide.md").write_text("# Guide\n\nexternal context", encoding="utf-8")
    src_dir = tmp_path / "src" / "sample"
    src_dir.mkdir(parents=True)
    (src_dir / "cli.py").write_text("def run() -> None:\n    return None\n", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "generate-sections",
            "--project-root",
            str(tmp_path),
            "--reference-dir",
            str(refs),
            "--output-dir",
            str(tmp_path / "docs" / "generated"),
        ],
    )

    assert result.exit_code == 0
    assert "documents=1" in result.stdout


def test_generate_sections_accepts_repeatable_reference_path_option(tmp_path: Path) -> None:
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "guide.md").write_text("# Guide", encoding="utf-8")
    single_file = tmp_path / "note.txt"
    single_file.write_text("hello", encoding="utf-8")
    src_dir = tmp_path / "src" / "sample"
    src_dir.mkdir(parents=True)
    (src_dir / "cli.py").write_text("def run() -> None:\n    return None\n", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "generate-sections",
            "--project-root",
            str(tmp_path),
            "--reference-path",
            str(refs),
            "--reference-path",
            str(single_file),
            "--output-dir",
            str(tmp_path / "docs" / "generated"),
        ],
    )

    assert result.exit_code == 0
    assert "documents=2" in result.stdout


def test_generate_sections_respects_env_llm_when_flag_not_explicit(
    tmp_path: Path, monkeypatch
) -> None:
    src_dir = tmp_path / "src" / "sample"
    src_dir.mkdir(parents=True)
    (src_dir / "cli.py").write_text("def run() -> None:\n    return None\n", encoding="utf-8")
    monkeypatch.setenv("REPO_AUTODOCS_ENABLE_LLM", "true")
    monkeypatch.delenv("REPO_AUTODOCS_MODEL_NAME", raising=False)
    monkeypatch.delenv("REPO_AUTODOCS_BASE_URL", raising=False)
    runner = CliRunner()

    result = runner.invoke(app, ["generate-sections", "--project-root", str(tmp_path)])

    assert result.exit_code == 1
    assert "FAIL: llm model_name missing" in result.stdout
