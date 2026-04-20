"""Deterministic routed alignment analysis for external references."""

from __future__ import annotations

import json

from repo_autodocs.alignment_claims import extract_route_claims
from repo_autodocs.alignment_evidence import build_evidence_atoms
from repo_autodocs.alignment_matcher import evaluate_claims
from repo_autodocs.models import (
    AlignmentCandidate,
    AlignmentVerdictEntry,
    CodeFactsBundle,
    GroundedContextBundle,
    RepoManifest,
    RouteAlignmentResult,
    RoutedAlignmentBundle,
    RoutedLLMMaterialBundle,
    RouteLLMMaterial,
)
from repo_autodocs.theory import ReferenceDiscovery


def build_routed_alignment_bundle(
    *,
    discovery: ReferenceDiscovery,
    manifest: RepoManifest,
    code_facts_bundle: CodeFactsBundle,
    grounded_bundle: GroundedContextBundle,
) -> RoutedAlignmentBundle:
    bundle = RoutedAlignmentBundle()
    evidence_atoms = build_evidence_atoms(manifest, code_facts_bundle)

    route_inputs: dict[str, list[tuple[str, str, str]]] = {
        "general_reference_alignment": [],
        "agent_instruction_alignment": [],
        "readme_claim_alignment": [],
    }

    for chunk in grounded_bundle.chunks:
        route_inputs["general_reference_alignment"].append(
            (f"{chunk.document_relative_path}#{chunk.chunk_id}", "grounded_chunk", chunk.text)
        )

    unreadable_by_route: dict[str, list[str]] = {
        "general_reference_alignment": [],
        "agent_instruction_alignment": [],
        "readme_claim_alignment": [],
    }
    for source in discovery.sources:
        if source.route not in route_inputs:
            continue
        if source.route == "general_reference_alignment":
            # Deterministic truth layer for general references is grounded chunks only.
            # Raw source texts remain available for inventory/status and optional advisory use.
            continue
        try:
            text = source.path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            unreadable_by_route[source.route].append(f"{source.display_path}: {exc}")
            continue
        route_inputs[source.route].append((source.display_path, source.kind, text))

    bundle.reference_alignment = _evaluate_route(
        route="general_reference_alignment",
        items=route_inputs["general_reference_alignment"],
        evidence_atoms=evidence_atoms,
        unreadable_sources=unreadable_by_route["general_reference_alignment"],
    )
    bundle.agent_instruction_alignment = _evaluate_route(
        route="agent_instruction_alignment",
        items=route_inputs["agent_instruction_alignment"],
        evidence_atoms=evidence_atoms,
        unreadable_sources=unreadable_by_route["agent_instruction_alignment"],
    )
    bundle.readme_claim_alignment = _evaluate_route(
        route="readme_claim_alignment",
        items=route_inputs["readme_claim_alignment"],
        evidence_atoms=evidence_atoms,
        unreadable_sources=unreadable_by_route["readme_claim_alignment"],
    )
    return bundle


def _evaluate_route(
    *, route: str, items: list[tuple[str, str, str]], evidence_atoms, unreadable_sources: list[str]
) -> RouteAlignmentResult:
    result = RouteAlignmentResult(route=route, source_count=len(items))
    all_claims = []
    for source_path, source_kind, text in items:
        claims = extract_route_claims(
            route=route, source_path=source_path, source_kind=source_kind, text=text
        )
        all_claims.extend(claims)
        for claim in claims:
            result.candidates.append(
                AlignmentCandidate(
                    route=route,
                    source_path=claim.source_path,
                    claim_text=claim.original_text,
                    claim_type=claim.claim_type,
                    verifiable=claim.is_statically_verifiable,
                    rationale=(
                        f"logic={claim.logic}; atoms={len(claim.atoms)}"
                        + (
                            f"; instruction_scope={claim.instruction_scope}"
                            if claim.instruction_scope
                            else ""
                        )
                    ),
                )
            )

    for evaluation in evaluate_claims(all_claims, evidence_atoms):
        claim = next(c for c in all_claims if c.claim_id == evaluation.claim_id)
        evidence_label = (
            f"entities={','.join(a.subject_value for a in claim.atoms) or 'none'}; "
            f"evidence_ids={','.join(evaluation.supporting_evidence_ids) or 'none'}; "
            f"contradictions={','.join(evaluation.contradicting_evidence_ids) or 'none'}; "
            f"match_trace={evaluation.evidence_note}"
        )
        if evaluation.uncertainty_note:
            evidence_label += f"; uncertainty={evaluation.uncertainty_note}"
        if unreadable_sources:
            evidence_label += f"; technical_warning=unreadable_sources:{len(unreadable_sources)}"
        result.verdicts.append(
            AlignmentVerdictEntry(
                route=route,
                source_path=claim.source_path,
                claim_text=claim.original_text,
                claim_type=claim.claim_type,
                verdict=evaluation.final_verdict,
                evidence_note=evidence_label,
                supporting_evidence_ids=evaluation.supporting_evidence_ids,
                contradicting_evidence_ids=evaluation.contradicting_evidence_ids,
            )
        )
    return result


def build_routed_llm_material_bundle(
    *,
    discovery: ReferenceDiscovery,
    grounded_bundle: GroundedContextBundle,
    routed_alignment: RoutedAlignmentBundle | None = None,
) -> RoutedLLMMaterialBundle:
    """Build route-specific bounded source excerpts for LLM alignment prompting."""

    bundle = RoutedLLMMaterialBundle()
    for chunk in grounded_bundle.chunks[:12]:
        bundle.reference_alignment.append(
            RouteLLMMaterial(
                route="general_reference_alignment",
                source_path=chunk.document_relative_path,
                section_hint=chunk.section_hint or "chunk",
                excerpt=chunk.text[:600],
            )
        )

    for source in discovery.sources:
        if source.route not in {"agent_instruction_alignment", "readme_claim_alignment"}:
            continue
        try:
            text = source.path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            text = f"Skipped unreadable source ({exc.__class__.__name__}): {exc}"

        section_hint = "source_excerpt"
        if text.startswith("Skipped unreadable source"):
            section_hint = "Unreadable source"
        material = RouteLLMMaterial(
            route=source.route,
            source_path=source.display_path,
            section_hint=section_hint,
            excerpt=text[:1000],
        )
        if source.route == "agent_instruction_alignment":
            bundle.agent_instruction_alignment.append(material)
        else:
            bundle.readme_claim_alignment.append(material)

    if routed_alignment is not None:
        for section_name, route_result, sink in (
            (
                "reference_alignment",
                routed_alignment.reference_alignment,
                bundle.reference_alignment,
            ),
            (
                "agent_instruction_alignment",
                routed_alignment.agent_instruction_alignment,
                bundle.agent_instruction_alignment,
            ),
            (
                "readme_claim_alignment",
                routed_alignment.readme_claim_alignment,
                bundle.readme_claim_alignment,
            ),
        ):
            allowed_ids: list[str] = []
            for verdict in route_result.verdicts:
                allowed_ids.extend(verdict.supporting_evidence_ids)
                allowed_ids.extend(verdict.contradicting_evidence_ids)
            payload = {
                "route": section_name,
                "allowed_evidence_ids": sorted(set(allowed_ids)),
                "deterministic_claims": [
                    {
                        "claim_text": c.claim_text,
                        "claim_type": c.claim_type,
                        "source_path": c.source_path,
                    }
                    for c in route_result.candidates[:12]
                ],
                "deterministic_verdicts": [
                    {
                        "claim_text": v.claim_text,
                        "status": v.verdict,
                        "evidence_note": v.evidence_note,
                    }
                    for v in route_result.verdicts[:12]
                ],
            }
            sink.append(
                RouteLLMMaterial(
                    route=route_result.route,
                    source_path="deterministic_alignment_pack",
                    section_hint="Deterministic claim/evidence pack",
                    excerpt=json.dumps(payload, ensure_ascii=False, indent=2),
                )
            )

    return bundle
