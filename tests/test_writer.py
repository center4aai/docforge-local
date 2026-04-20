from pathlib import Path

from repo_autodocs.writer import (
    write_generated_readme,
    write_generated_sections,
    write_prompt_grounding_debug_artifact,
)


def test_writer_outputs_generated_sections_and_readme(tmp_path: Path) -> None:
    sections = {
        "overview.md": "# Overview\n",
        "architecture.md": "# Architecture\n",
        "code_structure.md": "# Code Structure\n",
        "runtime_entrypoints.md": "# Runtime Entrypoints\n",
        "reference_alignment.md": "# Reference Alignment\n",
        "agent_instruction_alignment.md": "# Agent Instruction Alignment\n",
        "readme_claim_alignment.md": "# README Claim Alignment\n",
        "theory_alignment.md": "# Theory Alignment\n",
    }

    written = write_generated_sections(sections, tmp_path)
    readme = write_generated_readme(tmp_path)

    assert [p.name for p in written] == [
        "agent_instruction_alignment.md",
        "architecture.md",
        "code_structure.md",
        "overview.md",
        "readme_claim_alignment.md",
        "reference_alignment.md",
        "runtime_entrypoints.md",
        "theory_alignment.md",
    ]
    assert all(path.exists() for path in written)
    assert readme.exists()
    assert "Generated Documentation" in readme.read_text(encoding="utf-8")
    assert "Reference Alignment" in readme.read_text(encoding="utf-8")
    assert "Theory Alignment (Deprecated Compatibility)" in readme.read_text(encoding="utf-8")
    assert "Prompt Grounding Debug" not in readme.read_text(encoding="utf-8")


def test_writer_can_include_debug_links_when_requested(tmp_path: Path) -> None:
    readme = write_generated_readme(tmp_path, include_debug_artifacts=True)

    assert "Prompt Grounding Debug" in readme.read_text(encoding="utf-8")


def test_writer_generated_readme_supports_ru_prose_only(tmp_path: Path) -> None:
    readme = write_generated_readme(tmp_path, generated_text_language="ru")
    text = readme.read_text(encoding="utf-8")
    assert "# Generated Documentation" in text
    assert "сгенерированными артефактами" in text


def test_writer_outputs_prompt_grounding_debug_artifact(tmp_path: Path) -> None:
    path = write_prompt_grounding_debug_artifact("# Debug\n", tmp_path)

    assert path == tmp_path / "prompt_grounding_debug.md"
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "# Debug\n"
