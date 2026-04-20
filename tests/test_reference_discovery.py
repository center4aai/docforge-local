from pathlib import Path

from repo_autodocs.grounding import build_grounded_context_bundle
from repo_autodocs.theory import (
    discover_external_references,
    mark_reference_parse_statuses,
    select_theory_grounding_sources,
)


def test_reference_discovery_supports_multiple_inputs_and_defaults(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "README.md").write_text("# Readme\n", encoding="utf-8")
    (project_root / "AGENTS.md").write_text("# Agent\n", encoding="utf-8")

    refs_a = tmp_path / "refs_a"
    refs_b = tmp_path / "refs_b"
    refs_a.mkdir()
    refs_b.mkdir()
    (refs_a / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (refs_b / "notes.txt").write_text("notes", encoding="utf-8")
    (refs_b / "legacy.rst").write_text("unsupported", encoding="utf-8")

    discovery = discover_external_references(
        project_root=project_root,
        explicit_reference_paths=(refs_a, refs_b, refs_a / "guide.md"),
        include_readme_default=True,
        include_agent_instructions_default=True,
    )

    assert [source.display_path for source in discovery.sources] == [
        "AGENTS.md",
        "README.md",
        str(refs_a / "guide.md"),
        str(refs_b / "legacy.rst"),
        str(refs_b / "notes.txt"),
    ]
    assert sum(1 for source in discovery.sources if source.origin == "explicit") == 3
    assert sum(1 for source in discovery.sources if source.origin == "default") == 2
    assert {source.kind for source in discovery.sources} == {
        "general_reference",
        "agent_instruction",
        "readme_claims",
    }


def test_grounding_subset_excludes_readme_and_agent_routes(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "README.md").write_text("# Readme\n", encoding="utf-8")
    (project_root / "AGENTS.md").write_text("# Agent\n", encoding="utf-8")

    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "guide.md").write_text("# Guide\n", encoding="utf-8")

    discovery = discover_external_references(
        project_root=project_root,
        explicit_reference_paths=(refs,),
        include_readme_default=True,
        include_agent_instructions_default=True,
    )

    grounding_sources = select_theory_grounding_sources(discovery)
    assert [source.relative_path for source in grounding_sources] == [str(refs / "guide.md")]

    grounded = build_grounded_context_bundle(grounding_sources)
    with_status = mark_reference_parse_statuses(discovery, grounded)
    by_path = {source.display_path: source for source in with_status.sources}
    assert by_path[str(refs / "guide.md")].parse_status == "parsed"
    assert by_path[str(refs / "guide.md")].participated_in_grounding is True
    assert by_path["README.md"].parse_status == "not_attempted"
    assert by_path["AGENTS.md"].parse_status == "not_attempted"


def test_reference_discovery_handles_explicit_file_and_missing_path(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    ref_file = tmp_path / "reference.md"
    ref_file.write_text("# ref", encoding="utf-8")

    discovery = discover_external_references(
        project_root=project_root,
        explicit_reference_paths=(ref_file, tmp_path / "missing"),
    )

    assert len(discovery.sources) == 1
    assert discovery.sources[0].display_path == str(ref_file)
    assert discovery.sources[0].ingest_eligible is True


def test_explicit_readme_file_routes_to_readme_claim_alignment(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    readme = tmp_path / "README.md"
    readme.write_text("# README", encoding="utf-8")

    discovery = discover_external_references(
        project_root=project_root,
        explicit_reference_paths=(readme,),
    )

    assert len(discovery.sources) == 1
    source = discovery.sources[0]
    assert source.origin == "explicit"
    assert source.kind == "readme_claims"
    assert source.route == "readme_claim_alignment"


def test_explicit_directory_readme_routes_to_readme_claim_alignment(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    explicit_dir = tmp_path / "refs"
    explicit_dir.mkdir()
    (explicit_dir / "README.md").write_text("# README", encoding="utf-8")

    discovery = discover_external_references(
        project_root=project_root,
        explicit_reference_paths=(explicit_dir,),
    )

    assert len(discovery.sources) == 1
    source = discovery.sources[0]
    assert source.origin == "explicit"
    assert source.kind == "readme_claims"
    assert source.route == "readme_claim_alignment"


def test_default_target_patterns_are_configurable(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "README-main.md").write_text("# README", encoding="utf-8")
    (project_root / "docs" / "TEAM_AGENT.md").parent.mkdir(parents=True)
    (project_root / "docs" / "TEAM_AGENT.md").write_text("# Agent", encoding="utf-8")

    discovery = discover_external_references(
        project_root=project_root,
        include_readme_default=True,
        include_agent_instructions_default=True,
        default_readme_patterns=("README-*.md",),
        default_agent_instruction_patterns=("**/*AGENT.md",),
    )

    assert {source.display_path for source in discovery.sources} == {
        "README-main.md",
        "docs/TEAM_AGENT.md",
    }

    assert all("\\" not in source.display_path for source in discovery.sources)
