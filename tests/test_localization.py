from pathlib import Path

from repo_autodocs.config import load_config
from repo_autodocs.deterministic import (
    DeterministicContext,
    render_deterministic_sections,
    render_home_page,
)
from repo_autodocs.generator import generate_project_snapshot
from repo_autodocs.models import (
    CodeFactsBundle,
    GenerationRequest,
    GroundedContextBundle,
    RepoManifest,
)
from repo_autodocs.writer import write_generated_readme


def _ctx(tmp_path: Path) -> DeterministicContext:
    manifest = RepoManifest(
        project_root=tmp_path,
        top_level_directories=["src"],
        top_level_files=["pyproject.toml"],
    )
    code = CodeFactsBundle(detected_entrypoints=["repo_autodocs.cli:app"])
    return DeterministicContext(
        manifest=manifest,
        theory_sources=[],
        code_facts_bundle=code,
        grounded_bundle=GroundedContextBundle(),
    )


def test_default_en_deterministic_output_remains_english(tmp_path: Path) -> None:
    sections = render_deterministic_sections(_ctx(tmp_path), generated_text_language="en")
    assert "This overview is deterministic" in sections["overview.md"]


def test_ru_localizes_explanatory_prose_but_preserves_canonical_headings_and_identifiers(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path)
    sections = render_deterministic_sections(ctx, generated_text_language="ru")
    overview = sections["overview.md"]
    assert "# Overview" in overview
    assert "## What This Project Appears To Be" in overview
    assert "детерминирован" in overview
    assert "repo_autodocs.cli:app" in sections["runtime_entrypoints.md"]

    home = render_home_page(tmp_path, ctx, generated_text_language="ru")
    assert "Этот сайт был сгенерирован" in home
    assert "#" in home


def test_snapshot_and_generated_readme_localization_and_structure_stability(tmp_path: Path) -> None:
    manifest = RepoManifest(project_root=tmp_path)
    snapshot = generate_project_snapshot(
        GenerationRequest(manifest=manifest, theory_sources=[], generated_text_language="ru")
    )
    assert "# Project Snapshot" in snapshot.markdown
    assert "детерминированный снимок" in snapshot.markdown

    readme = write_generated_readme(tmp_path, generated_text_language="ru")
    text = readme.read_text(encoding="utf-8")
    assert "# Generated Documentation" in text
    assert "сгенерированными артефактами" in text


def test_generated_text_language_env_and_invalid_value_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("REPO_AUTODOCS_GENERATED_TEXT_LANGUAGE", "ru")
    config = load_config(project_root=tmp_path)
    assert config.generated_text_language == "ru"

    monkeypatch.setenv("REPO_AUTODOCS_GENERATED_TEXT_LANGUAGE", "es")
    config = load_config(project_root=tmp_path)
    assert config.generated_text_language == "en"
