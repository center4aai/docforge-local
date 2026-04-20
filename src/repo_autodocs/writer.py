"""Writers for generated markdown section artifacts."""

from __future__ import annotations

from pathlib import Path

from repo_autodocs.localization import GeneratedTextLanguage, localize


def write_generated_sections(sections: dict[str, str], output_dir: Path) -> list[Path]:
    """Write generated section markdown files into output directory."""

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, markdown in sections.items():
        path = output_dir / filename
        path.write_text(markdown, encoding="utf-8")
        written.append(path)
    return sorted(written)


def write_generated_readme(
    output_dir: Path,
    *,
    include_debug_artifacts: bool = False,
    generated_text_language: GeneratedTextLanguage = "en",
) -> Path:
    """Write an index page for generated section artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    readme_path = output_dir / "README.md"
    lines = [
        "# Generated Documentation",
        "",
        localize(
            generated_text_language,
            "writer.generated_notice",
            "These files are generated artifacts and may be regenerated at any time.",
        ),
        localize(
            generated_text_language,
            "writer.reference_notice",
            "Optional external references are analyzed from configured explicit "
            "reference paths and",
        ),
        localize(
            generated_text_language,
            "writer.reference_notice_cont",
            "default-selected targets (README/agent instruction files) when enabled.",
        ),
        "",
        "## Pages",
        "",
        "- [Project Snapshot](project_snapshot.md)",
        "- [Overview](overview.md)",
        "- [Architecture](architecture.md)",
        "- [Code Structure](code_structure.md)",
        "- [Runtime Entrypoints](runtime_entrypoints.md)",
        "- [Reference Alignment](reference_alignment.md)",
        "- [Agent Instruction Alignment](agent_instruction_alignment.md)",
        "- [README Claim Alignment](readme_claim_alignment.md)",
        "- [Theory Alignment (Deprecated Compatibility)](theory_alignment.md)",
    ]
    if include_debug_artifacts:
        lines.extend(
            [
                "",
                "## Debug artifacts (opt-in)",
                "",
                "- [Prompt Grounding Debug](prompt_grounding_debug.md)",
                "- [Code Facts Debug](code_facts_debug.md)",
            ]
        )
    lines.append("")
    readme_path.write_text("\n".join(lines), encoding="utf-8")
    return readme_path


def write_prompt_grounding_debug_artifact(markdown: str, output_dir: Path) -> Path:
    """Write deterministic prompt grounding debug markdown artifact."""

    return write_markdown_artifact(
        markdown=markdown, output_path=output_dir / "prompt_grounding_debug.md"
    )


def write_code_facts_debug_artifact(markdown: str, output_dir: Path) -> Path:
    """Write deterministic code-facts debug markdown artifact."""

    return write_markdown_artifact(
        markdown=markdown, output_path=output_dir / "code_facts_debug.md"
    )


def write_markdown_artifact(markdown: str, output_path: Path) -> Path:
    """Write a standalone markdown artifact to an explicit path."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path
