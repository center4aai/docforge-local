"""Markdown generation helpers for deterministic project snapshots."""

from __future__ import annotations

from repo_autodocs.localization import localize
from repo_autodocs.models import GenerationRequest, GenerationResult


def generate_project_snapshot(request: GenerationRequest) -> GenerationResult:
    """Generate a minimal markdown snapshot from deterministic inputs."""

    manifest = request.manifest
    root_label = manifest.project_root.name or "."
    lines: list[str] = [
        "# Project Snapshot",
        "",
        f"- **Project root label:** `{root_label}`",
        f"- **Has .git:** `{manifest.has_git_dir}`",
        f"- **Has pyproject.toml:** `{manifest.has_pyproject}`",
        f"- **Has mkdocs.yml:** `{manifest.has_mkdocs_config}`",
        f"- **Has docs/**: `{manifest.has_docs_dir}`",
        f"- **Has src/**: `{manifest.has_src_dir}`",
        f"- **Has tests/**: `{manifest.has_tests_dir}`",
        "",
        "## Top-level directories",
        "",
    ]

    if manifest.top_level_directories:
        lines.extend(f"- `{name}`" for name in manifest.top_level_directories)
    else:
        lines.append("- _None detected_")

    lines.extend(["", "## Top-level files", ""])
    if manifest.top_level_files:
        lines.extend(f"- `{name}`" for name in manifest.top_level_files)
    else:
        lines.append("- _None detected_")

    lines.extend(
        [
            "",
            localize(
                request.generated_text_language,
                "generator.methodology_heading",
                "## Discovered external reference files",
            ),
            "",
        ]
    )
    if request.theory_sources:
        for source in request.theory_sources:
            lines.append(
                f"- `{source.relative_path}` ({source.extension}, {source.size_bytes} bytes)"
            )
    else:
        lines.append("- _No supported external reference files discovered_")

    lines.extend(
        [
            "",
            "## Scope note",
            "",
            localize(
                request.generated_text_language,
                "generator.scope_note",
                "This page is a deterministic repository snapshot. "
                "It is not full architecture documentation.",
            ),
            "",
        ]
    )

    return GenerationResult(markdown="\n".join(lines))
