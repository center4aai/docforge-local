"""Deterministic predicate matching and route-aware verdict aggregation."""

from __future__ import annotations

from collections import defaultdict

from .alignment_models import (
    AtomMatchResult,
    ClaimAtom,
    ClaimEvaluationResult,
    ClaimRecord,
    EvidenceAtom,
)

_CLOSED_WORLD_PREDICATES = {
    "cli_subcommand_exists",
    "config_field_exists",
    "config_enum_contains_value",
    "config_alias_exists",
    "config_alias_maps_to_field",
    "env_var_exists",
    "generated_page_exists",
    "route_exists",
    "compatibility_alias_exists",
    "ignore_policy_excludes_target",
    "ignore_policy_reference_selection_independent",
    "compatibility_alias_maps_to_first_reference_path",
}


def evaluate_claims(
    claims: list[ClaimRecord], evidence_atoms: list[EvidenceAtom]
) -> list[ClaimEvaluationResult]:
    by_kind: dict[str, list[EvidenceAtom]] = defaultdict(list)
    by_id = {e.evidence_id: e for e in evidence_atoms}
    for evidence in evidence_atoms:
        by_kind[evidence.evidence_kind].append(evidence)

    results: list[ClaimEvaluationResult] = []
    for claim in claims:
        atom_results: list[AtomMatchResult] = []
        for atom in claim.atoms:
            atom_results.append(_match_atom(atom, by_kind, evidence_atoms))
        results.append(_aggregate(claim, atom_results, by_id))
    return results


def _match_atom(
    atom: ClaimAtom, by_kind: dict[str, list[EvidenceAtom]], evidence_atoms: list[EvidenceAtom]
) -> AtomMatchResult:
    predicate = atom.predicate
    if predicate == "cli_subcommand_exists":
        return _predicate_exists(atom, by_kind.get("cli_subcommand", ()), closed_world=True)
    if predicate == "config_field_exists":
        return _predicate_exists(atom, by_kind.get("config_field", ()), closed_world=True)
    if predicate == "config_enum_contains_value":
        pool = by_kind.get("config_enum_value", ())
        needle = f"{atom.subject_value}:{atom.object_value}".lower()
        return _predicate_custom(atom, pool, needle, closed_world=True)
    if predicate == "config_alias_exists":
        return _predicate_exists(atom, by_kind.get("config_alias", ()), closed_world=True)
    if predicate == "config_alias_maps_to_field":
        return _predicate_alias_maps_to_field(atom, by_kind.get("config_alias_maps_to_field", ()))
    if predicate == "env_var_exists":
        return _predicate_exists(atom, by_kind.get("env_var", ()), closed_world=True)
    if predicate == "generated_page_exists":
        return _predicate_exists(atom, by_kind.get("generated_page", ()), closed_world=True)
    if predicate == "route_exists":
        return _predicate_exists(atom, by_kind.get("route_name", ()), closed_world=True)
    if predicate == "compatibility_alias_exists":
        return _predicate_exists(atom, by_kind.get("compatibility_alias", ()), closed_world=True)
    if predicate == "ignore_policy_excludes_target":
        return _predicate_exists(
            atom,
            by_kind.get("ignore_policy_excludes_target", ()),
            closed_world=True,
        )
    if predicate == "ignore_policy_reference_selection_independent":
        return _predicate_policy_reference_selection_independent(
            atom, by_kind.get("ignore_policy_reference_selection", ())
        )
    if predicate == "compatibility_alias_maps_to_first_reference_path":
        return _predicate_compatibility_alias_maps_to_first_reference_path(
            atom, by_kind.get("compatibility_alias_maps_to_first_reference_path", ())
        )
    if predicate == "entrypoint_exists":
        return _predicate_exists(atom, by_kind.get("entrypoint", ()), closed_world=False)
    if predicate == "framework_hint_exists":
        return _predicate_exists(atom, by_kind.get("framework_hint", ()), closed_world=False)

    # lexical fallback
    hits = []
    tokens = set(atom.anchor_terms)
    for evidence in evidence_atoms:
        if any(token and token in evidence.normalized_value for token in tokens):
            hits.append(evidence.evidence_id)
    tier = "lexical_secondary" if hits else "heuristic_fallback"
    return AtomMatchResult(
        atom_id=atom.atom_id,
        matched_evidence_ids=tuple(hits[:6]),
        match_tier=tier,
        predicate_result="unresolved",
        explanation_fragments=(
            "no decisive typed evidence; lexical candidates were present but non-authoritative"
            if hits
            else "no deterministic predicate match for lexical_hint atom",
        ),
    )


def _predicate_exists(
    atom: ClaimAtom,
    pool: list[EvidenceAtom] | tuple[EvidenceAtom, ...],
    *,
    closed_world: bool,
) -> AtomMatchResult:
    target = (atom.object_value or atom.subject_value).lower()
    hits = [e for e in pool if e.normalized_value == target or e.display_anchor.lower() == target]

    if hits and atom.polarity == "positive":
        return AtomMatchResult(
            atom_id=atom.atom_id,
            matched_evidence_ids=tuple(e.evidence_id for e in hits),
            match_tier="exact_primary",
            predicate_result="supported",
            explanation_fragments=(
                "matched "
                f"{atom.object_kind or atom.subject_kind}={target} "
                f"from actual {hits[0].source_category} registry",
            ),
        )

    if hits and atom.polarity == "negative":
        return AtomMatchResult(
            atom_id=atom.atom_id,
            matched_evidence_ids=(),
            contradiction_evidence_ids=tuple(e.evidence_id for e in hits),
            match_tier="exact_primary",
            predicate_result="contradicted",
            explanation_fragments=(f"contradicted: deterministic inventory contains {target}",),
        )

    if (not hits) and atom.polarity == "positive" and closed_world:
        return AtomMatchResult(
            atom_id=atom.atom_id,
            matched_evidence_ids=(),
            contradiction_evidence_ids=(),
            match_tier="structured_primary",
            predicate_result="contradicted",
            explanation_fragments=(
                f"contradicted: canonical deterministic inventory does not contain {target}",
            ),
        )

    if (not hits) and atom.polarity == "positive":
        return AtomMatchResult(
            atom_id=atom.atom_id,
            matched_evidence_ids=(),
            match_tier="structured_primary",
            predicate_result="unresolved",
            explanation_fragments=(f"no decisive typed evidence for {target}",),
        )

    return AtomMatchResult(
        atom_id=atom.atom_id,
        matched_evidence_ids=(),
        match_tier="structured_primary",
        predicate_result="supported",
        explanation_fragments=(f"negative claim consistent: {target} absent",),
    )


def _predicate_custom(
    atom: ClaimAtom,
    pool: list[EvidenceAtom] | tuple[EvidenceAtom, ...],
    needle: str,
    *,
    closed_world: bool,
) -> AtomMatchResult:
    hits = [e for e in pool if needle == e.normalized_value or needle in e.normalized_value]
    if hits and atom.polarity == "positive":
        return AtomMatchResult(
            atom_id=atom.atom_id,
            matched_evidence_ids=tuple(e.evidence_id for e in hits),
            match_tier="structured_primary",
            predicate_result="supported",
            explanation_fragments=(f"matched {atom.predicate} via typed relation {needle}",),
        )
    if hits and atom.polarity == "negative":
        return AtomMatchResult(
            atom_id=atom.atom_id,
            matched_evidence_ids=(),
            contradiction_evidence_ids=tuple(e.evidence_id for e in hits),
            match_tier="structured_primary",
            predicate_result="contradicted",
            explanation_fragments=(f"contradicted: relation {needle} exists",),
        )
    if atom.polarity == "positive" and closed_world:
        return AtomMatchResult(
            atom_id=atom.atom_id,
            matched_evidence_ids=(),
            match_tier="structured_primary",
            predicate_result="contradicted",
            explanation_fragments=(f"contradicted: canonical relation {needle} not found",),
        )
    return AtomMatchResult(
        atom_id=atom.atom_id,
        matched_evidence_ids=(),
        match_tier="heuristic_fallback",
        predicate_result="unresolved",
        explanation_fragments=(f"no deterministic relation match for {atom.predicate}",),
    )


def _predicate_alias_maps_to_field(
    atom: ClaimAtom, pool: list[EvidenceAtom] | tuple[EvidenceAtom, ...]
) -> AtomMatchResult:
    alias = atom.subject_value.lower()
    field = (atom.object_value or "").lower()
    hits = [
        e
        for e in pool
        if str(e.metadata.get("alias", "")).lower() == alias
        and str(e.metadata.get("canonical", "")).lower() == field
    ]
    if hits and atom.polarity == "positive":
        return AtomMatchResult(
            atom_id=atom.atom_id,
            matched_evidence_ids=tuple(e.evidence_id for e in hits),
            match_tier="structured_primary",
            predicate_result="supported",
            explanation_fragments=(f"matched alias mapping {alias}->{field}",),
        )
    if hits and atom.polarity == "negative":
        return AtomMatchResult(
            atom_id=atom.atom_id,
            matched_evidence_ids=(),
            contradiction_evidence_ids=tuple(e.evidence_id for e in hits),
            match_tier="structured_primary",
            predicate_result="contradicted",
            explanation_fragments=(f"contradicted: alias mapping {alias}->{field} exists",),
        )
    if atom.polarity == "positive":
        return AtomMatchResult(
            atom_id=atom.atom_id,
            matched_evidence_ids=(),
            match_tier="structured_primary",
            predicate_result="contradicted",
            explanation_fragments=(f"contradicted: alias mapping {alias}->{field} not found",),
        )
    return AtomMatchResult(
        atom_id=atom.atom_id,
        matched_evidence_ids=(),
        match_tier="structured_primary",
        predicate_result="supported",
        explanation_fragments=(f"negative claim consistent for alias mapping {alias}->{field}",),
    )


def _predicate_policy_reference_selection_independent(
    atom: ClaimAtom, pool: list[EvidenceAtom] | tuple[EvidenceAtom, ...]
) -> AtomMatchResult:
    relation = (atom.object_value or "").lower()
    hits = [e for e in pool if e.normalized_value == relation]
    if hits and atom.polarity == "positive":
        relation_note = (
            "default reference targets remain independent from repo ignore"
            if relation == "default_reference_targets_independent"
            else "explicit reference paths remain independent from repo ignore"
        )
        return AtomMatchResult(
            atom_id=atom.atom_id,
            matched_evidence_ids=tuple(e.evidence_id for e in hits),
            match_tier="structured_primary",
            predicate_result="supported",
            explanation_fragments=(f"matched policy relation {relation_note}",),
        )
    if hits and atom.polarity == "negative":
        return AtomMatchResult(
            atom_id=atom.atom_id,
            matched_evidence_ids=(),
            contradiction_evidence_ids=tuple(e.evidence_id for e in hits),
            match_tier="structured_primary",
            predicate_result="contradicted",
            explanation_fragments=(f"contradicted: policy relation {relation} exists",),
        )
    if atom.polarity == "positive":
        return AtomMatchResult(
            atom_id=atom.atom_id,
            matched_evidence_ids=(),
            match_tier="structured_primary",
            predicate_result="unresolved",
            explanation_fragments=(
                f"no decisive deterministic policy relation found for {relation}",
            ),
        )
    return AtomMatchResult(
        atom_id=atom.atom_id,
        matched_evidence_ids=(),
        match_tier="structured_primary",
        predicate_result="supported",
        explanation_fragments=(f"negative claim consistent for policy relation {relation}",),
    )


def _predicate_compatibility_alias_maps_to_first_reference_path(
    atom: ClaimAtom, pool: list[EvidenceAtom] | tuple[EvidenceAtom, ...]
) -> AtomMatchResult:
    alias = atom.subject_value.lower()
    target = (atom.object_value or "").lower()
    hits = [
        e
        for e in pool
        if str(e.metadata.get("alias", "")).lower() == alias
        and str(e.metadata.get("target", "")).lower() == target
    ]
    if hits and atom.polarity == "positive":
        return AtomMatchResult(
            atom_id=atom.atom_id,
            matched_evidence_ids=tuple(e.evidence_id for e in hits),
            match_tier="structured_primary",
            predicate_result="supported",
            explanation_fragments=(
                f"matched compatibility relation {alias}->first_explicit_reference_path",
            ),
        )
    if hits and atom.polarity == "negative":
        return AtomMatchResult(
            atom_id=atom.atom_id,
            matched_evidence_ids=(),
            contradiction_evidence_ids=tuple(e.evidence_id for e in hits),
            match_tier="structured_primary",
            predicate_result="contradicted",
            explanation_fragments=(
                "contradicted: compatibility relation "
                f"{alias}->first_explicit_reference_path exists",
            ),
        )
    if atom.polarity == "positive":
        return AtomMatchResult(
            atom_id=atom.atom_id,
            matched_evidence_ids=(),
            match_tier="structured_primary",
            predicate_result="unresolved",
            explanation_fragments=(
                "no decisive deterministic compatibility relation found for "
                f"{alias}->first_explicit_reference_path",
            ),
        )
    return AtomMatchResult(
        atom_id=atom.atom_id,
        matched_evidence_ids=(),
        match_tier="structured_primary",
        predicate_result="supported",
        explanation_fragments=(
            "negative claim consistent for compatibility relation "
            f"{alias}->first_explicit_reference_path",
        ),
    )


def _aggregate(
    claim: ClaimRecord, atom_results: list[AtomMatchResult], by_id: dict[str, EvidenceAtom]
) -> ClaimEvaluationResult:
    contradiction_ids = sorted(
        {eid for r in atom_results for eid in r.contradiction_evidence_ids if eid in by_id}
    )
    support_ids = sorted(
        {eid for r in atom_results for eid in r.matched_evidence_ids if eid in by_id}
    )

    supportive_atoms = [
        r
        for r in atom_results
        if r.predicate_result == "supported"
        and r.match_tier in {"exact_primary", "structured_primary"}
    ]
    contradicted_atoms = [r for r in atom_results if r.predicate_result == "contradicted"]
    unresolved_atoms = [r for r in atom_results if r.predicate_result == "unresolved"]

    if claim.route == "agent_instruction_alignment" and not claim.is_statically_verifiable:
        verdict = "out_of_scope_or_non_verifiable"
    elif claim.route == "readme_claim_alignment" and not claim.is_statically_verifiable:
        verdict = "not_statically_verifiable"
    elif contradicted_atoms:
        verdict = "contradicted"
    elif supportive_atoms and not unresolved_atoms:
        verdict = "supported"
    elif supportive_atoms and unresolved_atoms:
        verdict = "partially_supported"
    else:
        verdict = (
            "missing_evidence" if claim.route == "general_reference_alignment" else "not_evidenced"
        )

    frags: list[str] = []
    for result in atom_results:
        frags.extend(result.explanation_fragments)
    if contradicted_atoms:
        frags.append("explicit contradiction basis is deterministic")
    elif not support_ids:
        frags.append(
            "no decisive typed evidence; lexical candidates were present but non-authoritative"
        )

    uncertainty = ""
    if any(r.match_tier == "lexical_secondary" for r in atom_results):
        uncertainty = "lexical candidate matches present but non-authoritative"

    if verdict == "supported" and not supportive_atoms:
        verdict = (
            "missing_evidence" if claim.route == "general_reference_alignment" else "not_evidenced"
        )

    return ClaimEvaluationResult(
        claim_id=claim.claim_id,
        route=claim.route,
        final_verdict=verdict,
        atom_results=tuple(atom_results),
        supporting_evidence_ids=tuple(support_ids),
        contradicting_evidence_ids=tuple(contradiction_ids),
        evidence_note="; ".join(frags[:8]),
        uncertainty_note=uncertainty,
    )
