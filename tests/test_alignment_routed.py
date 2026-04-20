import json
from pathlib import Path

import repo_autodocs.alignment as alignment_module
from repo_autodocs.alignment import build_routed_alignment_bundle, build_routed_llm_material_bundle
from repo_autodocs.deterministic import render_external_references_page
from repo_autodocs.models import (
    CodeFactsBundle,
    GroundedContextBundle,
    MethodologyChunk,
    RepoManifest,
)
from repo_autodocs.theory import discover_external_references, mark_reference_parse_statuses


def _manifest(tmp_path: Path) -> RepoManifest:
    return RepoManifest(
        project_root=tmp_path,
        top_level_directories=["src", "tests"],
        top_level_files=["pyproject.toml", "mkdocs.yml"],
    )


def _codefacts() -> CodeFactsBundle:
    bundle = CodeFactsBundle()
    bundle.detected_entrypoints = ["repo_autodocs.cli:app"]
    bundle.framework_hints = ["typer"]
    return bundle


def test_routed_alignment_core_behaviors_and_anchor_notes(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "README.md").write_text(
        """
- docforge-local foobar command is required
- generate-docs always guarantees low latency network behavior
- generated/code_structure.md is available
""".strip(),
        encoding="utf-8",
    )
    (project_root / "AGENTS.md").write_text(
        """
- Be polite and concise in responses.
- Verify generate-docs workflow before release.
""".strip(),
        encoding="utf-8",
    )
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "guide.md").write_text(
        """
- The repository exposes docforge-local generate-docs and update-docs.
- It includes runtime_entrypoints and code_structure generated pages.
- The CLI entrypoint repo_autodocs.cli:app uses typer.
""".strip(),
        encoding="utf-8",
    )

    discovery = discover_external_references(
        project_root=project_root,
        explicit_reference_paths=(refs,),
        include_readme_default=True,
        include_agent_instructions_default=True,
    )
    grounded = GroundedContextBundle(
        chunks=[
            MethodologyChunk(
                chunk_id="guide.md:0:abc",
                document_relative_path=str(refs / "guide.md"),
                index=0,
                text=(refs / "guide.md").read_text(encoding="utf-8"),
                char_count=120,
                section_hint="general",
            )
        ]
    )
    discovery = mark_reference_parse_statuses(discovery, grounded)
    routed = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=grounded,
    )

    assert routed.reference_alignment.candidates
    assert any(
        v.verdict in {"supported", "partially_supported"}
        for v in routed.reference_alignment.verdicts
    )
    assert any("entities=" in v.evidence_note for v in routed.reference_alignment.verdicts)

    agent_verdicts = {v.claim_text: v.verdict for v in routed.agent_instruction_alignment.verdicts}
    assert any(v == "out_of_scope_or_non_verifiable" for v in agent_verdicts.values())
    assert any(
        v in {"supported", "partially_supported", "not_evidenced"} for v in agent_verdicts.values()
    )

    readme_by_claim = {v.claim_text: v.verdict for v in routed.readme_claim_alignment.verdicts}
    assert any(v == "not_statically_verifiable" for v in readme_by_claim.values())
    assert any(v == "contradicted" for v in readme_by_claim.values())


def test_general_reference_deterministic_route_uses_grounded_chunks_only(
    tmp_path: Path, monkeypatch
) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    refs = tmp_path / "refs"
    refs.mkdir()
    guide = refs / "guide.md"
    guide.write_text("- docforge-local generate-docs exists.", encoding="utf-8")

    discovery = discover_external_references(
        project_root=project_root,
        explicit_reference_paths=(refs,),
    )
    grounded = GroundedContextBundle(
        chunks=[
            MethodologyChunk(
                chunk_id="guide.md:0:abc",
                document_relative_path=str(guide),
                index=0,
                text=guide.read_text(encoding="utf-8"),
                char_count=40,
                section_hint="general",
            )
        ]
    )
    seen_general_kinds: list[str] = []
    original_extract = alignment_module.extract_route_claims

    def _capture_extract(*, route: str, source_path: str, source_kind: str, text: str):
        if route == "general_reference_alignment":
            seen_general_kinds.append(source_kind)
        return original_extract(
            route=route, source_path=source_path, source_kind=source_kind, text=text
        )

    monkeypatch.setattr(alignment_module, "extract_route_claims", _capture_extract)
    build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=grounded,
    )

    assert seen_general_kinds
    assert set(seen_general_kinds) == {"grounded_chunk"}


def test_routed_alignment_distinguishes_supported_partial_and_missing(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "AGENTS.md").write_text(
        """
- Be polite in responses.
- docforge-local generate-docs command exists.
- docforge-local imaginary-command is supported.
""".strip(),
        encoding="utf-8",
    )
    (project_root / "README.md").write_text(
        """
- The tool supports docforge-local generate-docs.
- The tool always guarantees low latency.
- This repository is authored by robots.
""".strip(),
        encoding="utf-8",
    )
    refs = tmp_path / "refs"
    refs.mkdir()
    guide = refs / "guide.md"
    guide.write_text(
        """
- docforge-local generate-docs update-docs config commands are present.
- The CLI entrypoint repo_autodocs.cli:app uses typer.
- docforge-local exists.
- claims about unknown commands should be contradicted when detected.
""".strip(),
        encoding="utf-8",
    )
    discovery = discover_external_references(
        project_root=project_root,
        explicit_reference_paths=(refs,),
        include_readme_default=True,
        include_agent_instructions_default=True,
    )
    grounded = GroundedContextBundle(
        chunks=[
            MethodologyChunk(
                chunk_id="guide.md:0:abc",
                document_relative_path=str(guide),
                index=0,
                text=guide.read_text(encoding="utf-8"),
                char_count=150,
                section_hint="general",
            )
        ]
    )
    discovery = mark_reference_parse_statuses(discovery, grounded)
    routed = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=grounded,
    )

    assert any(v.verdict == "supported" for v in routed.reference_alignment.verdicts)
    assert any(v.verdict == "missing_evidence" for v in routed.reference_alignment.verdicts)
    assert any(
        v.verdict == "out_of_scope_or_non_verifiable"
        for v in routed.agent_instruction_alignment.verdicts
    )
    assert any(v.verdict == "contradicted" for v in routed.agent_instruction_alignment.verdicts)
    assert any(
        v.verdict == "not_statically_verifiable" for v in routed.readme_claim_alignment.verdicts
    )
    assert any(
        v.verdict in {"supported", "contradicted"} for v in routed.readme_claim_alignment.verdicts
    )


def test_agent_instruction_route_splits_verifiable_vs_normative_claims(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "AGENTS.md").write_text(
        """
- Keep a friendly tone in all responses.
- Run `docforge-local generate-docs --project-root /repo` before release.
""".strip(),
        encoding="utf-8",
    )
    discovery = discover_external_references(
        project_root=project_root,
        include_agent_instructions_default=True,
    )
    routed = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=GroundedContextBundle(),
    )
    by_claim = {v.claim_text: v.verdict for v in routed.agent_instruction_alignment.verdicts}
    assert any(v == "out_of_scope_or_non_verifiable" for v in by_claim.values())
    assert any(v == "supported" for v in by_claim.values())


def test_readme_route_marks_runtime_guarantees_not_statically_verifiable(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "README.md").write_text(
        """
- The CLI always responds in under 50ms over the network.
- The project supports docforge-local generate-docs.
""".strip(),
        encoding="utf-8",
    )
    discovery = discover_external_references(
        project_root=project_root,
        include_readme_default=True,
    )
    routed = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=GroundedContextBundle(),
    )
    verdicts = {v.claim_text: v.verdict for v in routed.readme_claim_alignment.verdicts}
    assert "not_statically_verifiable" in verdicts.values()
    assert any(v == "supported" for v in verdicts.values())


def test_agent_instruction_unsupported_command_is_contradicted(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "AGENTS.md").write_text(
        "- Run docforge-local made-up-command before release.\n",
        encoding="utf-8",
    )
    discovery = discover_external_references(
        project_root=project_root,
        include_agent_instructions_default=True,
    )
    routed = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=GroundedContextBundle(),
    )

    assert any(v.verdict == "contradicted" for v in routed.agent_instruction_alignment.verdicts)


def test_readme_static_claims_supported_runtime_claims_not_statically_verifiable(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "README.md").write_text(
        """
- The tool supports docforge-local generate-docs.
- Generated page code_structure.md is available.
- The CLI guarantees real-time 10ms latency.
""".strip(),
        encoding="utf-8",
    )
    discovery = discover_external_references(
        project_root=project_root,
        include_readme_default=True,
    )
    routed = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=GroundedContextBundle(),
    )

    by_claim = {v.claim_text: v.verdict for v in routed.readme_claim_alignment.verdicts}
    assert by_claim["The tool supports docforge-local generate-docs."] == "supported"
    assert by_claim["Generated page code_structure.md is available."] in {
        "supported",
        "partially_supported",
    }
    assert by_claim["The CLI guarantees real-time 10ms latency."] == "not_statically_verifiable"


def test_lexical_overlap_alone_does_not_produce_supported(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "README.md").write_text(
        "- The project documentation quality feels modern and comprehensive.\n",
        encoding="utf-8",
    )
    discovery = discover_external_references(
        project_root=project_root,
        include_readme_default=True,
    )
    routed = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=GroundedContextBundle(),
    )

    assert all(v.verdict != "supported" for v in routed.readme_claim_alignment.verdicts)


def test_routed_readme_ignore_but_reference_selection_policy_is_supported(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    readme = project_root / "README.md"
    claim = (
        "README is ignored for implementation analysis but can still be selected "
        "as a reference target."
    )
    readme.write_text(
        f"- {claim}\n",
        encoding="utf-8",
    )
    discovery = discover_external_references(
        project_root=project_root, explicit_reference_paths=(readme,)
    )
    routed = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=GroundedContextBundle(),
    )
    by_claim = {v.claim_text: v for v in routed.readme_claim_alignment.verdicts}
    verdict = by_claim[claim]
    assert verdict.verdict in {"supported", "partially_supported"}
    assert (
        "matched policy relation default reference targets remain independent from repo ignore"
        in (verdict.evidence_note)
    )


def test_routed_agent_ignore_but_reference_discovery_policy_is_supported(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    agent = project_root / "AGENTS.md"
    claim = (
        "agent instruction files are excluded from repo analysis but still "
        "discoverable as references."
    )
    agent.write_text(
        f"- {claim}\n",
        encoding="utf-8",
    )
    discovery = discover_external_references(
        project_root=project_root, explicit_reference_paths=(agent,)
    )
    grounded = GroundedContextBundle(
        chunks=[
            MethodologyChunk(
                chunk_id="AGENTS.md:0:policy",
                document_relative_path=str(agent),
                index=0,
                text=agent.read_text(encoding="utf-8"),
                char_count=90,
                section_hint="general",
            )
        ]
    )
    routed = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=grounded,
    )
    verdicts = routed.reference_alignment.verdicts
    assert verdicts
    assert all(
        "canonical deterministic inventory does not contain default_reference_targets_independent"
        not in v.evidence_note
        for v in verdicts
    )
    assert any(v.verdict in {"supported", "partially_supported"} for v in verdicts)


def test_routed_compatibility_alias_first_reference_path_relation(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    ref = tmp_path / "refs.md"
    ref.write_text("- reference_dir maps to the first explicit reference path.\n", encoding="utf-8")
    discovery = discover_external_references(
        project_root=project_root, explicit_reference_paths=(ref,)
    )
    grounded = GroundedContextBundle(
        chunks=[
            MethodologyChunk(
                chunk_id="refs.md:0:compat",
                document_relative_path=str(ref),
                index=0,
                text=ref.read_text(encoding="utf-8"),
                char_count=64,
                section_hint="general",
            )
        ]
    )
    routed = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=grounded,
    )
    assert any(v.verdict == "supported" for v in routed.reference_alignment.verdicts)
    assert any(
        "matched compatibility relation reference_dir->first_explicit_reference_path"
        in v.evidence_note
        for v in routed.reference_alignment.verdicts
    )


def test_routed_relation_positive_absence_stays_conservative(monkeypatch, tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    ref = tmp_path / "refs.md"
    ref.write_text("- reference_dir maps to the first explicit reference path.\n", encoding="utf-8")
    discovery = discover_external_references(
        project_root=project_root, explicit_reference_paths=(ref,)
    )
    grounded = GroundedContextBundle(
        chunks=[
            MethodologyChunk(
                chunk_id="refs.md:0:compat",
                document_relative_path=str(ref),
                index=0,
                text=ref.read_text(encoding="utf-8"),
                char_count=64,
                section_hint="general",
            )
        ]
    )

    original = alignment_module.build_evidence_atoms

    def _filtered_evidence(*args, **kwargs):  # type: ignore[no-untyped-def]
        atoms = original(*args, **kwargs)
        return [
            atom
            for atom in atoms
            if atom.evidence_kind != "compatibility_alias_maps_to_first_reference_path"
        ]

    monkeypatch.setattr(alignment_module, "build_evidence_atoms", _filtered_evidence)

    routed = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=grounded,
    )
    assert routed.reference_alignment.verdicts
    assert all(v.verdict != "contradicted" for v in routed.reference_alignment.verdicts)
    assert any(v.verdict == "missing_evidence" for v in routed.reference_alignment.verdicts)
    assert any(
        "no decisive deterministic compatibility relation found" in v.evidence_note
        for v in routed.reference_alignment.verdicts
    )


def test_external_reference_page_includes_routed_per_source_status(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    refs = tmp_path / "refs"
    refs.mkdir()
    guide = refs / "guide.md"
    guide.write_text("- generate-docs command exists", encoding="utf-8")
    discovery = discover_external_references(
        project_root=project_root, explicit_reference_paths=(refs,)
    )
    grounded = GroundedContextBundle(
        chunks=[
            MethodologyChunk(
                chunk_id="guide.md:0:abc",
                document_relative_path=str(guide),
                index=0,
                text=guide.read_text(encoding="utf-8"),
                char_count=30,
                section_hint="general",
            )
        ]
    )
    discovery = mark_reference_parse_statuses(discovery, grounded)
    routed = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=grounded,
    )

    page = render_external_references_page(
        discovery=discovery,
        grounded_bundle=grounded,
        routed_alignment=routed,
        supported_ingest_extensions=[".md", ".txt"],
        generated_text_language="en",
    )

    assert "Route analysis" in page
    assert "attempted=yes" in page
    assert "candidates=" in page


def test_routed_llm_material_bundle_contains_route_specific_sources(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "README.md").write_text(
        "# Usage\n- Run docforge-local generate-docs.\n", encoding="utf-8"
    )
    (project_root / "AGENTS.md").write_text(
        "# Workflow\n- Validate config before running update-docs.\n", encoding="utf-8"
    )
    refs = tmp_path / "refs"
    refs.mkdir()
    guide = refs / "guide.md"
    guide.write_text("# Theory\n- General alignment statement.\n", encoding="utf-8")
    discovery = discover_external_references(
        project_root=project_root,
        explicit_reference_paths=(refs,),
        include_readme_default=True,
        include_agent_instructions_default=True,
    )
    grounded = GroundedContextBundle(
        chunks=[
            MethodologyChunk(
                chunk_id="guide.md:0",
                document_relative_path=str(guide),
                index=0,
                text=guide.read_text(encoding="utf-8"),
                char_count=40,
                section_hint="Theory",
            )
        ]
    )
    routed_materials = build_routed_llm_material_bundle(
        discovery=discovery, grounded_bundle=grounded
    )

    assert any(
        item.source_path.endswith("README.md") for item in routed_materials.readme_claim_alignment
    )
    assert any(
        item.source_path.endswith("AGENTS.md")
        for item in routed_materials.agent_instruction_alignment
    )
    assert any(str(guide) in item.source_path for item in routed_materials.reference_alignment)


def test_alignment_pack_allowed_evidence_ids_use_structured_verdict_fields(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    readme = project_root / "README.md"
    readme.write_text("- The tool supports docforge-local generate-docs.\n", encoding="utf-8")
    discovery = discover_external_references(project_root=project_root, include_readme_default=True)
    routed = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=GroundedContextBundle(),
    )
    assert routed.readme_claim_alignment.verdicts
    verdict = routed.readme_claim_alignment.verdicts[0]
    assert verdict.supporting_evidence_ids or verdict.contradicting_evidence_ids

    verdict.evidence_note = "presentation-only note without deterministic id fields"
    routed_materials = build_routed_llm_material_bundle(
        discovery=discovery,
        grounded_bundle=GroundedContextBundle(),
        routed_alignment=routed,
    )
    pack = next(
        item
        for item in routed_materials.readme_claim_alignment
        if item.source_path == "deterministic_alignment_pack"
    )
    payload = json.loads(pack.excerpt)
    expected = sorted(
        set(verdict.supporting_evidence_ids) | set(verdict.contradicting_evidence_ids)
    )
    assert payload["allowed_evidence_ids"] == expected


def test_routed_llm_material_bundle_skips_unreadable_route_file(
    tmp_path: Path, monkeypatch
) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    readme = project_root / "README.md"
    readme.write_text("# Usage\n- docforge-local generate-docs.\n", encoding="utf-8")
    discovery = discover_external_references(
        project_root=project_root,
        explicit_reference_paths=(),
        include_readme_default=True,
        include_agent_instructions_default=False,
    )
    grounded = GroundedContextBundle()

    original = Path.read_text

    def _broken_read_text(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self == readme:
            raise OSError("permission denied")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _broken_read_text)

    routed_materials = build_routed_llm_material_bundle(
        discovery=discovery, grounded_bundle=grounded
    )

    assert routed_materials.readme_claim_alignment
    assert routed_materials.readme_claim_alignment[0].section_hint == "Unreadable source"
    assert "permission denied" in routed_materials.readme_claim_alignment[0].excerpt


def test_unreadable_source_is_skipped_from_deterministic_claim_extraction(
    tmp_path: Path, monkeypatch
) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    readme = project_root / "README.md"
    readme.write_text("- docforge-local generate-docs exists\n", encoding="utf-8")
    discovery = discover_external_references(project_root=project_root, include_readme_default=True)
    original = Path.read_text

    def _broken_read_text(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self == readme:
            raise OSError("permission denied")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _broken_read_text)
    routed = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=GroundedContextBundle(),
    )
    assert routed.readme_claim_alignment.candidates == []
    assert routed.readme_claim_alignment.verdicts == []


def test_compound_claim_yields_partial_support_for_missing_clause(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    refs = tmp_path / "refs"
    refs.mkdir()
    guide = refs / "guide.md"
    guide.write_text(
        "- supports docforge-local generate-docs and friendly workflow guidance\n",
        encoding="utf-8",
    )
    discovery = discover_external_references(
        project_root=project_root, explicit_reference_paths=(refs,), include_readme_default=False
    )
    grounded = GroundedContextBundle(
        chunks=[
            MethodologyChunk(
                chunk_id="guide.md:0:compound",
                document_relative_path=str(guide),
                index=0,
                text=guide.read_text(encoding="utf-8"),
                char_count=70,
                section_hint="general",
            )
        ]
    )
    routed = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=grounded,
    )
    assert any(v.verdict == "partially_supported" for v in routed.reference_alignment.verdicts)


def test_explanation_notes_include_decisive_basis_not_overlap_only(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / "README.md").write_text(
        "- docforge-local generate-docs exists\n",
        encoding="utf-8",
    )
    discovery = discover_external_references(project_root=project_root, include_readme_default=True)
    routed = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=_manifest(project_root),
        code_facts_bundle=_codefacts(),
        grounded_bundle=GroundedContextBundle(),
    )
    note = routed.readme_claim_alignment.verdicts[0].evidence_note
    assert "evidence_ids=" in note
    assert "matched" in note or "deterministic" in note
    assert "overlap" not in note
