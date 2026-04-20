from pathlib import Path

from repo_autodocs.alignment_claims import atomize_claim, extract_route_claims
from repo_autodocs.alignment_evidence import build_evidence_atoms
from repo_autodocs.alignment_matcher import evaluate_claims
from repo_autodocs.alignment_models import ClaimAtom, ClaimRecord
from repo_autodocs.models import CodeFactsBundle, RepoManifest
from repo_autodocs.orchestration import _sanitize_mapping_entries
from repo_autodocs.structured_output import AlignmentMappingEntry, TheoryAlignmentMapping


def _manifest() -> RepoManifest:
    return RepoManifest(
        project_root=Path("/tmp/repo"), top_level_directories=["src"], top_level_files=["README.md"]
    )


def _codefacts() -> CodeFactsBundle:
    bundle = CodeFactsBundle()
    bundle.detected_entrypoints = ["repo_autodocs.cli:app"]
    bundle.framework_hints = ["typer"]
    return bundle


def test_claim_atomization_propagates_shared_subject_for_cli_objects() -> None:
    atoms, logic = atomize_claim(
        claim_id="c1",
        claim_text="supports docforge-local generate-docs and update-docs",
    )
    assert logic == "and"
    assert len(atoms) == 2
    assert all(a.predicate == "cli_subcommand_exists" for a in atoms)
    assert {a.object_value for a in atoms} == {"generate-docs", "update-docs"}


def test_claim_atomization_splits_dual_policy_claim_into_two_typed_atoms() -> None:
    atoms, logic = atomize_claim(
        claim_id="c2",
        claim_text=(
            "README is ignored for implementation analysis but can still be "
            "selected as a reference target"
        ),
    )
    assert logic == "and"
    assert len(atoms) == 2
    assert atoms[0].predicate == "ignore_policy_excludes_target"
    assert atoms[0].object_value == "README.md"
    assert atoms[1].predicate == "ignore_policy_reference_selection_independent"
    assert atoms[1].object_value == "default_reference_targets_independent"
    assert atoms[0].subject_value == atoms[1].subject_value == "readme"


def test_closed_world_absence_is_contradicted_for_cli_subcommand() -> None:
    claims = extract_route_claims(
        route="readme_claim_alignment",
        source_path="README.md",
        source_kind="readme_claims",
        text="- docforge-local made-up-command exists",
    )
    evidence = build_evidence_atoms(_manifest(), _codefacts())
    results = evaluate_claims(claims, evidence)
    assert results[0].final_verdict == "contradicted"


def test_open_world_absence_stays_unresolved_for_framework_hint() -> None:
    claims = extract_route_claims(
        route="readme_claim_alignment",
        source_path="README.md",
        source_kind="readme_claims",
        text="- framework is flask",
    )
    evidence = build_evidence_atoms(_manifest(), _codefacts())
    results = evaluate_claims(claims, evidence)
    assert results[0].final_verdict == "not_evidenced"


def test_relation_predicate_alias_maps_to_field_is_evaluated() -> None:
    claims = extract_route_claims(
        route="general_reference_alignment",
        source_path="ref.md",
        source_kind="general_reference",
        text="- methodology_dir maps to reference_paths",
    )
    evidence = build_evidence_atoms(_manifest(), _codefacts())
    results = evaluate_claims(claims, evidence)
    assert results[0].final_verdict == "supported"


def test_relation_predicate_alias_maps_to_first_explicit_reference_path_is_evaluated() -> None:
    claims = extract_route_claims(
        route="general_reference_alignment",
        source_path="ref.md",
        source_kind="general_reference",
        text="- reference_dir maps to the first explicit reference path",
    )
    evidence = build_evidence_atoms(_manifest(), _codefacts())
    results = evaluate_claims(claims, evidence)
    assert results[0].final_verdict == "supported"
    assert "matched compatibility relation reference_dir->first_explicit_reference_path" in (
        results[0].evidence_note
    )


def test_methodology_dir_maps_to_first_explicit_reference_path_is_extracted() -> None:
    claims = extract_route_claims(
        route="general_reference_alignment",
        source_path="ref.md",
        source_kind="general_reference",
        text="- methodology_dir maps to the first explicit reference path",
    )
    assert len(claims) == 1
    assert len(claims[0].atoms) == 1
    atom = claims[0].atoms[0]
    assert atom.predicate == "compatibility_alias_maps_to_first_reference_path"
    assert atom.subject_value == "methodology_dir"
    assert atom.object_value == "first_explicit_reference_path"


def test_agent_instruction_contrast_claim_keeps_shared_subject_and_typed_policy_relation() -> None:
    atoms, logic = atomize_claim(
        claim_id="c3",
        claim_text=(
            "agent instruction files are excluded from repo analysis but still discoverable as "
            "references"
        ),
    )
    assert logic == "and"
    assert len(atoms) == 2
    assert atoms[0].predicate == "ignore_policy_excludes_target"
    assert atoms[1].predicate == "ignore_policy_reference_selection_independent"
    assert atoms[0].subject_value == atoms[1].subject_value == "agent_instruction"
    assert atoms[1].object_value == "default_reference_targets_independent"


def test_advisory_mapping_without_valid_ids_downgrades_even_from_non_fallback_status() -> None:
    mapping = TheoryAlignmentMapping(
        reference_notes="r",
        code_notes="c",
        entries=(
            AlignmentMappingEntry(
                reference_claim="claim",
                code_anchor="anchor",
                status="contradicted",
                evidence_note="fake:missing",
                uncertainty_note="",
            ),
        ),
    )
    sanitized = _sanitize_mapping_entries(
        mapping, {"cli_subcommand:generate-docs"}, "readme_claim_alignment"
    )
    assert sanitized.entries[0].status == "not_evidenced"
    assert any(d.code == "mapping.no_valid_ids_status_downgraded" for d in sanitized.diagnostics)


def test_lexical_fallback_never_supported_without_typed_match() -> None:
    claims = extract_route_claims(
        route="general_reference_alignment",
        source_path="ref.md",
        source_kind="general_reference",
        text="- documentation quality feels modern and comprehensive",
    )
    evidence = build_evidence_atoms(_manifest(), _codefacts())
    results = evaluate_claims(claims, evidence)
    assert all(r.final_verdict != "supported" for r in results)


def _single_atom_claim(*, claim_id: str, route: str, atom: ClaimAtom) -> ClaimRecord:
    return ClaimRecord(
        claim_id=claim_id,
        route=route,  # type: ignore[arg-type]
        source_path="ref.md",
        source_kind="general_reference",
        source_section_hint="",
        original_text=claim_id,
        normalized_text=claim_id,
        language_hint="en",
        claim_type="policy",
        is_statically_verifiable=True,
        logic="single",
        atoms=(atom,),
    )


def test_policy_reference_selection_positive_absence_is_unresolved_not_contradicted() -> None:
    claim = _single_atom_claim(
        claim_id="c-policy-missing",
        route="general_reference_alignment",
        atom=ClaimAtom(
            atom_id="a1",
            subject_kind="policy",
            subject_value="readme",
            predicate="ignore_policy_reference_selection_independent",
            object_kind="relation",
            object_value="default_reference_targets_independent",
            polarity="positive",
            modality="descriptive",
        ),
    )
    evidence = [
        atom
        for atom in build_evidence_atoms(_manifest(), _codefacts())
        if atom.evidence_kind != "ignore_policy_reference_selection"
    ]
    result = evaluate_claims([claim], evidence)[0]
    assert result.final_verdict == "missing_evidence"
    assert all(atom.predicate_result != "contradicted" for atom in result.atom_results)
    assert "no decisive deterministic policy relation found" in result.evidence_note


def test_compatibility_alias_positive_absence_is_unresolved_not_contradicted() -> None:
    claim = _single_atom_claim(
        claim_id="c-compat-missing",
        route="general_reference_alignment",
        atom=ClaimAtom(
            atom_id="a2",
            subject_kind="compatibility_alias",
            subject_value="reference_dir",
            predicate="compatibility_alias_maps_to_first_reference_path",
            object_kind="reference_path",
            object_value="first_explicit_reference_path",
            polarity="positive",
            modality="descriptive",
        ),
    )
    evidence = [
        atom
        for atom in build_evidence_atoms(_manifest(), _codefacts())
        if atom.evidence_kind != "compatibility_alias_maps_to_first_reference_path"
    ]
    result = evaluate_claims([claim], evidence)[0]
    assert result.final_verdict == "missing_evidence"
    assert all(atom.predicate_result != "contradicted" for atom in result.atom_results)
    assert "no decisive deterministic compatibility relation found" in result.evidence_note


def test_policy_reference_selection_negative_claim_is_contradicted_when_relation_exists() -> None:
    claim = _single_atom_claim(
        claim_id="c-policy-negative",
        route="general_reference_alignment",
        atom=ClaimAtom(
            atom_id="a3",
            subject_kind="policy",
            subject_value="readme",
            predicate="ignore_policy_reference_selection_independent",
            object_kind="relation",
            object_value="default_reference_targets_independent",
            polarity="negative",
            modality="descriptive",
        ),
    )
    result = evaluate_claims([claim], build_evidence_atoms(_manifest(), _codefacts()))[0]
    assert result.final_verdict == "contradicted"
    assert any(atom.predicate_result == "contradicted" for atom in result.atom_results)


def test_compatibility_alias_negative_claim_is_contradicted_when_relation_exists() -> None:
    claim = _single_atom_claim(
        claim_id="c-compat-negative",
        route="general_reference_alignment",
        atom=ClaimAtom(
            atom_id="a4",
            subject_kind="compatibility_alias",
            subject_value="reference_dir",
            predicate="compatibility_alias_maps_to_first_reference_path",
            object_kind="reference_path",
            object_value="first_explicit_reference_path",
            polarity="negative",
            modality="descriptive",
        ),
    )
    result = evaluate_claims([claim], build_evidence_atoms(_manifest(), _codefacts()))[0]
    assert result.final_verdict == "contradicted"
    assert any(atom.predicate_result == "contradicted" for atom in result.atom_results)
