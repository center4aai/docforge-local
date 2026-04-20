"""Internal typed models for deterministic routed claim→evidence alignment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RouteName = Literal[
    "general_reference_alignment", "agent_instruction_alignment", "readme_claim_alignment"
]


@dataclass(frozen=True, slots=True)
class ClaimAtom:
    atom_id: str
    subject_kind: str
    subject_value: str
    predicate: str
    object_kind: str | None
    object_value: str | None
    polarity: Literal["positive", "negative"]
    modality: Literal["descriptive", "must", "should", "forbidden", "unknown"]
    qualifiers: tuple[str, ...] = ()
    anchor_terms: tuple[str, ...] = ()
    alias_terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClaimRecord:
    claim_id: str
    route: RouteName
    source_path: str
    source_kind: str
    source_section_hint: str
    original_text: str
    normalized_text: str
    language_hint: str
    claim_type: str
    is_statically_verifiable: bool
    logic: Literal["single", "and", "or"]
    atoms: tuple[ClaimAtom, ...]
    is_verifiable_instruction: bool | None = None
    instruction_scope: (
        Literal["workflow", "config", "output", "feature", "policy", "style", "process", "unknown"]
        | None
    ) = None


@dataclass(frozen=True, slots=True)
class EvidenceAtom:
    evidence_id: str
    evidence_kind: str
    source_path: str
    source_category: str
    display_anchor: str
    normalized_value: str
    raw_excerpt: str
    line_start: int | None = None
    line_end: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AtomMatchResult:
    atom_id: str
    matched_evidence_ids: tuple[str, ...]
    match_tier: Literal[
        "exact_primary", "structured_primary", "lexical_secondary", "heuristic_fallback"
    ]
    predicate_result: Literal["supported", "unresolved", "contradicted"]
    contradiction_evidence_ids: tuple[str, ...] = ()
    explanation_fragments: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClaimEvaluationResult:
    claim_id: str
    route: RouteName
    final_verdict: str
    atom_results: tuple[AtomMatchResult, ...]
    supporting_evidence_ids: tuple[str, ...]
    contradicting_evidence_ids: tuple[str, ...]
    evidence_note: str
    uncertainty_note: str
