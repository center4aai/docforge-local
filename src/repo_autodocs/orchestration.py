"""Stage-7 LLM orchestration for multi-step structured section synthesis."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from repo_autodocs.llm import LLMClient
from repo_autodocs.localization import GeneratedTextLanguage
from repo_autodocs.models import (
    CodeFactsBundle,
    GroundedContextBundle,
    RepoManifest,
    RouteLLMMaterial,
    TheorySource,
)
from repo_autodocs.prompts import (
    build_agent_instruction_alignment_prompt,
    build_architecture_prompt,
    build_code_structure_prompt,
    build_overview_prompt,
    build_readme_claim_alignment_prompt,
    build_reference_alignment_prompt,
    build_runtime_entrypoints_prompt,
    build_theory_alignment_prompt,
)
from repo_autodocs.rendering import get_section_contract, render_structured_section_page
from repo_autodocs.structured_output import (
    DiagnosticSeverity,
    FinalSectionPayload,
    SectionNotes,
    StructuredDiagnostic,
    TheoryAlignmentMapping,
    fallback_mapping_status_for_section,
    parse_alignment_mapping_output,
    parse_final_section_output,
    parse_section_notes_output,
)

_MAPPING_ALLOWED_STATUS_BY_SECTION: dict[str, tuple[str, ...]] = {
    "reference_alignment": ("supported", "partially_supported", "missing_evidence", "contradicted"),
    "agent_instruction_alignment": (
        "supported",
        "partially_supported",
        "not_evidenced",
        "contradicted",
        "out_of_scope_or_non_verifiable",
    ),
    "readme_claim_alignment": (
        "supported",
        "partially_supported",
        "not_evidenced",
        "contradicted",
        "not_statically_verifiable",
    ),
    "theory_alignment": (
        "supported",
        "partially_supported",
        "missing_evidence",
        "contradicted",
        "unclear",
    ),
}


@dataclass(frozen=True, slots=True)
class SectionOrchestrationResult:
    """Final section artifact bundle with inspectable intermediates."""

    section_name: str
    final_markdown: str
    notes: SectionNotes
    final_payload: FinalSectionPayload
    mapping: TheoryAlignmentMapping | None = None
    stages_run: tuple[str, ...] = field(default_factory=tuple)


def _is_usable(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped and len(stripped) >= 24)


def _json_only_instruction(stage_name: str) -> str:
    return "\n".join(
        [
            f"[OUTPUT CONTRACT: {stage_name}]",
            "Return ONLY one valid JSON object that matches the schema given below.",
            "Do not wrap the JSON in markdown code fences.",
            "Do not add prose, explanations, comments, bullets, or any text before or after the JSON object.",
            "Do not rename keys, translate keys, or add extra top-level keys.",
            "If a field is not needed, still follow the schema exactly and use an empty string or empty array when appropriate.",
        ]
    )


def _build_notes_example(section_name: str) -> dict[str, object]:
    return {
        "notes_markdown": (
            f"- OBS: Grounded observation for {section_name}\n"
            "- OBS: Another evidence-backed observation\n"
            "- UNCERTAINTY: State explicitly what cannot be concluded from the provided evidence"
        ),
        "observations": [
            "Concrete observation backed by repository or reference evidence.",
            "Another concise observation grounded in the provided material.",
        ],
        "uncertainty_flags": [
            "Evidence is incomplete for one aspect of the section.",
        ],
    }


def _render_notes_json_schema(section_name: str) -> str:
    example_json = json.dumps(_build_notes_example(section_name), ensure_ascii=False, indent=2)
    return "\n\n".join(
        [
            "[NOTES JSON SCHEMA]",
            "Top-level keys:",
            '- "notes_markdown": string. A compact markdown note sheet for downstream synthesis. '
            "Use short grounded bullets and explicitly mark uncertainty when needed.",
            '- "observations": array of strings. Each item is one concise evidence-backed observation.',
            '- "uncertainty_flags": array of strings. Each item is one explicit uncertainty, limitation, or evidence gap.',
            "Hard constraints:",
            "- Return exactly one JSON object with exactly these three top-level keys.",
            "- Keep all array items as plain strings.",
            "- Do not return nested objects inside observations or uncertainty_flags.",
            "Valid example JSON:",
            example_json,
        ]
    )


def _mapping_statuses_for_section(section_name: str) -> tuple[str, ...]:
    return _MAPPING_ALLOWED_STATUS_BY_SECTION.get(
        section_name, _MAPPING_ALLOWED_STATUS_BY_SECTION["theory_alignment"]
    )


def _build_mapping_example(section_name: str, allowed_ids: set[str]) -> dict[str, object]:
    statuses = _mapping_statuses_for_section(section_name)
    preferred_positive = "supported" if "supported" in statuses else statuses[0]
    fallback_status = fallback_mapping_status_for_section(section_name)

    retained_id = sorted(allowed_ids)[0] if allowed_ids else None
    if retained_id:
        evidence_note = (
            f"Valid deterministic evidence ID: {retained_id}. "
            "This advisory mapping is grounded in the provided deterministic bundle."
        )
        status = preferred_positive
    else:
        evidence_note = (
            "No valid deterministic evidence ID was available in the provided bundle. "
            "The entry therefore remains conservative."
        )
        status = fallback_status

    return {
        "reference_notes": "Reference-side candidate claims extracted from the provided materials.",
        "code_notes": "Code-side candidate anchors extracted from authoritative repository evidence.",
        "entries": [
            {
                "reference_claim": f"Representative claim for {section_name}",
                "code_anchor": "Representative repository/code anchor",
                "status": status,
                "evidence_note": evidence_note,
                "uncertainty_note": "State uncertainty explicitly when evidence is partial or absent.",
            }
        ],
    }


def _render_mapping_json_schema(section_name: str, allowed_ids: set[str]) -> str:
    statuses = ", ".join(_mapping_statuses_for_section(section_name))
    evidence_id_guidance = (
        ", ".join(sorted(allowed_ids))
        if allowed_ids
        else "(no valid deterministic evidence IDs were extracted from the provided route materials)"
    )
    example_json = json.dumps(
        _build_mapping_example(section_name, allowed_ids),
        ensure_ascii=False,
        indent=2,
    )
    return "\n\n".join(
        [
            "[MAPPING JSON SCHEMA]",
            "Top-level keys:",
            '- "reference_notes": string. Compact synthesis of reference-side candidate claims.',
            '- "code_notes": string. Compact synthesis of code-side candidate anchors.',
            '- "entries": array of mapping entry objects.',
            "Entry object keys:",
            '- "reference_claim": string. One normalized claim from the reference side.',
            '- "code_anchor": string. One concise repository/code anchor or implementation anchor.',
            f'- "status": string enum. Allowed values for this section are exactly: {statuses}.',
            '- "evidence_note": string. Describe evidence conservatively. '
            "If valid deterministic evidence IDs are available, mention only those valid IDs.",
            '- "uncertainty_note": string. Explain ambiguity, insufficiency, or verification limits.',
            "Deterministic evidence ID rule:",
            "Use only evidence IDs already present in the provided deterministic bundle.",
            f"Currently visible valid deterministic evidence IDs: {evidence_id_guidance}",
            "If no valid deterministic evidence ID applies, keep the status conservative rather than inventing IDs.",
            "Hard constraints:",
            "- Return exactly one JSON object with exactly these top-level keys: reference_notes, code_notes, entries.",
            "- Each entries item must be a JSON object with exactly these keys: "
            "reference_claim, code_anchor, status, evidence_note, uncertainty_note.",
            "- Do not add extra entry keys.",
            "Valid example JSON:",
            example_json,
        ]
    )


def _build_final_section_example(section_name: str) -> dict[str, object]:
    contract = get_section_contract(section_name)
    section_blocks: dict[str, list[dict[str, str]]] = {}

    for idx, heading in enumerate(contract.headings):
        if idx == 0:
            section_blocks[heading] = [
                {
                    "kind": "paragraph",
                    "text": "Observed repository evidence is summarized here with grounded prose.",
                },
                {
                    "kind": "bullet",
                    "text": "Concise evidence-backed implementation fact.",
                },
                {
                    "kind": "labeled_bullet",
                    "label": "Inference",
                    "text": "Interpretation that is clearly separated from direct evidence.",
                },
                {
                    "kind": "numbered_item",
                    "text": "Ordered analytical point supported by the provided material.",
                },
            ]
        else:
            section_blocks[heading] = [
                {
                    "kind": "paragraph",
                    "text": f"Grounded analysis for the heading '{heading}'.",
                }
            ]

    return {
        "title": contract.title,
        "section_blocks": section_blocks,
    }


def _render_required_heading_key_explanations(section_name: str) -> str:
    contract = get_section_contract(section_name)
    lines = ["Required keys inside section_blocks:"]
    for heading in contract.headings:
        lines.append(
            f'- "{heading}": array of block objects for the required H2 heading "{heading}". '
            "This key must appear exactly as written."
        )
    return "\n".join(lines)


def _render_final_json_schema(section_name: str) -> str:
    contract = get_section_contract(section_name)
    example_json = json.dumps(
        _build_final_section_example(section_name),
        ensure_ascii=False,
        indent=2,
    )
    return "\n\n".join(
        [
            "[FINAL SECTION JSON SCHEMA]",
            "Top-level keys:",
            f'- "title": string. Must equal the canonical section title "{contract.title}".',
            '- "section_blocks": object. Maps every required heading key to an array of block objects.',
            _render_required_heading_key_explanations(section_name),
            "Block object keys:",
            '- "kind": string enum. Allowed values are exactly: "paragraph", "bullet", '
            '"labeled_bullet", "numbered_item".',
            '- "text": string. Human-readable analytical content. Do not put markdown headings inside this text.',
            '- "label": string. Use only when kind == "labeled_bullet". Omit for other block kinds.',
            "Hard constraints:",
            "- Return exactly one JSON object with exactly these top-level keys: title, section_blocks.",
            "- Do not add extra top-level keys.",
            "- section_blocks must be a JSON object, not an array.",
            "- Every required heading key must be present exactly as written.",
            "- Each heading value must be an array of JSON block objects.",
            "- Do not emit unsupported block kinds.",
            "- Do not emit markdown headings inside block text.",
            "Valid example JSON:",
            example_json,
        ]
    )


def _build_language_repair_example(
    payload: FinalSectionPayload, section_name: str
) -> dict[str, object]:
    section_blocks: dict[str, list[dict[str, object]]] = {}
    contract = get_section_contract(section_name)

    for heading in contract.headings:
        original_blocks = payload.section_blocks.get(heading, ())
        repaired_blocks: list[dict[str, object]] = []
        if not original_blocks:
            repaired_blocks.append(
                {
                    "kind": "paragraph",
                    "text": "Краткое русскоязычное пояснение, сохраняющее исходную структуру раздела.",
                }
            )
        else:
            for block in original_blocks:
                item: dict[str, object] = {"kind": block.kind, "text": "Русскоязычный текст блока."}
                if block.kind == "labeled_bullet":
                    item["label"] = block.label or "Inference"
                repaired_blocks.append(item)
        section_blocks[heading] = repaired_blocks

    return {"section_blocks": section_blocks}


def _render_language_repair_schema(payload: FinalSectionPayload, section_name: str) -> str:
    example_json = json.dumps(
        _build_language_repair_example(payload, section_name),
        ensure_ascii=False,
        indent=2,
    )
    return "\n\n".join(
        [
            "[LANGUAGE REPAIR JSON SCHEMA]",
            "Top-level keys:",
            '- "section_blocks": object. Preserve the same heading keys that were provided in the input payload.',
            _render_required_heading_key_explanations(section_name),
            "Block object keys:",
            '- "kind": string enum. Preserve the same allowed kind values: "paragraph", "bullet", '
            '"labeled_bullet", "numbered_item".',
            '- "text": string. Rewrite only this field into Russian prose when needed.',
            '- "label": string. Preserve for labeled_bullet blocks only. Do not add it to other block kinds.',
            "Hard constraints:",
            '- Return exactly one JSON object with exactly one top-level key: "section_blocks".',
            "- Preserve the same heading keys as the input payload.",
            "- Preserve block ordering and block kinds.",
            "- Rewrite text values into Russian only when needed.",
            "- Do not translate commands, flags, identifiers, filenames, paths, verdict labels, or quoted excerpts.",
            "Valid example JSON:",
            example_json,
        ]
    )


def _call_stage_with_retry(
    *,
    client: LLMClient,
    stage_name: str,
    system_prompt: str,
    user_prompt: str,
    attempts: int = 2,
) -> str:
    for _ in range(attempts):
        response = client.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            operation_label=stage_name,
        )
        if _is_usable(response):
            return response
    return response if "response" in locals() else ""


def _section_base_prompt(
    section_name: str,
    manifest: RepoManifest,
    theory_sources: list[TheorySource],
    grounded_bundle: GroundedContextBundle | None,
    code_facts_bundle: CodeFactsBundle | None,
    route_materials: list[RouteLLMMaterial] | None,
) -> str:
    if section_name == "overview":
        return build_overview_prompt(manifest, theory_sources, grounded_bundle, code_facts_bundle)
    if section_name == "architecture":
        return build_architecture_prompt(
            manifest, theory_sources, grounded_bundle, code_facts_bundle
        )
    if section_name == "code_structure":
        return build_code_structure_prompt(
            manifest, theory_sources, grounded_bundle, code_facts_bundle
        )
    if section_name == "runtime_entrypoints":
        return build_runtime_entrypoints_prompt(
            manifest, theory_sources, grounded_bundle, code_facts_bundle
        )
    if section_name == "reference_alignment":
        return build_reference_alignment_prompt(
            manifest, theory_sources, grounded_bundle, code_facts_bundle, route_materials
        )
    if section_name == "agent_instruction_alignment":
        return build_agent_instruction_alignment_prompt(
            manifest, theory_sources, grounded_bundle, code_facts_bundle, route_materials
        )
    if section_name == "readme_claim_alignment":
        return build_readme_claim_alignment_prompt(
            manifest, theory_sources, grounded_bundle, code_facts_bundle, route_materials
        )
    return build_theory_alignment_prompt(
        manifest, theory_sources, grounded_bundle, code_facts_bundle
    )


def _generate_notes(*, section_name: str, client: LLMClient, base_prompt: str) -> SectionNotes:
    notes_prompt = "\n\n".join(
        [
            f"[STAGE: {section_name}:notes]",
            _json_only_instruction(f"{section_name}:notes"),
            base_prompt,
            _render_notes_json_schema(section_name),
        ]
    )
    notes_text = _call_stage_with_retry(
        client=client,
        stage_name=f"{section_name}:notes",
        system_prompt=(
            "You generate intermediate analytical notes from evidence. "
            "Return only one valid JSON object that matches the provided schema."
        ),
        user_prompt=notes_prompt,
    )
    parsed = parse_section_notes_output(section_name, notes_text)
    if parsed.observations or parsed.uncertainty_flags or parsed.notes_markdown:
        return parsed

    repaired = _call_stage_with_retry(
        client=client,
        stage_name=f"{section_name}:notes-repair",
        system_prompt=(
            "Repair invalid notes output. "
            "Return only one valid JSON object that matches the provided schema."
        ),
        user_prompt="\n\n".join(
            [
                f"[STAGE: {section_name}:notes-repair]",
                _json_only_instruction(f"{section_name}:notes-repair"),
                base_prompt,
                "The previous response failed structured parsing.",
                "[PREVIOUS INVALID RESPONSE]",
                notes_text,
                _render_notes_json_schema(section_name),
            ]
        ),
    )
    return parse_section_notes_output(section_name, repaired)


def _build_theory_mapping(
    *,
    client: LLMClient,
    base_prompt: str,
    section_name: str,
    route_materials: list[RouteLLMMaterial] | None = None,
) -> TheoryAlignmentMapping:
    allowed_statuses = mapping_status_instruction_for_section(section_name)
    allowed_evidence_ids = _extract_allowed_evidence_ids(route_materials)
    contradicted_hints = _extract_contradicted_claim_hints(base_prompt)
    reference_notes = _call_stage_with_retry(
        client=client,
        stage_name=f"{section_name}:reference-notes",
        system_prompt=(
            "Extract reference-side concepts and claims from grounded external material. "
            "Do not fabricate claims beyond provided evidence."
        ),
        user_prompt="\n\n".join(
            [
                f"[STAGE: {section_name}:reference-notes]",
                f"[ROUTE: {section_name}]",
                base_prompt,
                "List candidate reference concepts/claims as concise bullets.",
            ]
        ),
    )

    code_notes = _call_stage_with_retry(
        client=client,
        stage_name=f"{section_name}:code-notes",
        system_prompt=(
            "Extract candidate repository/code implementation anchors from authoritative evidence."
        ),
        user_prompt="\n\n".join(
            [
                f"[STAGE: {section_name}:code-notes]",
                f"[ROUTE: {section_name}]",
                base_prompt,
                "List code-side implementation anchors as concise bullets.",
            ]
        ),
    )

    mapping_text = _call_stage_with_retry(
        client=client,
        stage_name=f"{section_name}:mapping",
        system_prompt=(
            "Map reference claims to code anchors and classify each using only the allowed status enum. "
            "Return only one valid JSON object that matches the provided schema."
        ),
        user_prompt="\n\n".join(
            [
                f"[STAGE: {section_name}:mapping]",
                _json_only_instruction(f"{section_name}:mapping"),
                f"[ROUTE: {section_name}]",
                "Reference claim notes:",
                reference_notes,
                "Code anchor notes:",
                code_notes,
                f"Allowed status enum for this section: {allowed_statuses}",
                (
                    "Use only evidence IDs already present in the provided deterministic bundle. "
                    "Do not invent evidence IDs."
                ),
                (
                    "If no provided evidence ID applies, keep status conservative "
                    "and explain uncertainty."
                ),
                _render_mapping_json_schema(section_name, allowed_evidence_ids),
            ]
        ),
    )
    parsed = parse_alignment_mapping_output(section_name, mapping_text)
    parsed = _sanitize_mapping_entries(parsed, allowed_evidence_ids, section_name)
    parsed = _enforce_deterministic_contradictions(parsed, contradicted_hints)
    if not parsed.reference_notes:
        parsed = TheoryAlignmentMapping(
            reference_notes=reference_notes,
            code_notes=code_notes,
            entries=parsed.entries,
            diagnostics=parsed.diagnostics,
        )
    return parsed


def _extract_contradicted_claim_hints(base_prompt: str) -> set[str]:
    hints: set[str] = set()
    for match in re.finditer(
        r'"claim_text"\s*:\s*"([^"]+)"[^\n\r]{0,200}?"status"\s*:\s*"contradicted"',
        base_prompt,
        flags=re.IGNORECASE,
    ):
        hints.add(match.group(1).strip().lower())
    return hints


def _enforce_deterministic_contradictions(
    mapping: TheoryAlignmentMapping, contradicted_hints: set[str]
) -> TheoryAlignmentMapping:
    if not contradicted_hints:
        return mapping
    adjusted = []
    diagnostics = list(mapping.diagnostics)
    for idx, entry in enumerate(mapping.entries):
        claim = entry.reference_claim.lower()
        if (
            any(hint and hint in claim for hint in contradicted_hints)
            and entry.status != "contradicted"
        ):
            adjusted.append(
                type(entry)(
                    reference_claim=entry.reference_claim,
                    code_anchor=entry.code_anchor,
                    status="contradicted",
                    evidence_note=entry.evidence_note,
                    uncertainty_note=entry.uncertainty_note,
                )
            )
            diagnostics.append(
                StructuredDiagnostic(
                    code="mapping.deterministic_contradiction_preserved",
                    severity=DiagnosticSeverity.WARNING,
                    stage="mapping",
                    summary="Deterministic contradiction preserved",
                    detail=(
                        f"Preserved contradicted status over advisory status '{entry.status}' "
                        "for deterministic contradiction hint."
                    ),
                    operation_ref=f"entry:{idx}",
                    location_ref=entry.reference_claim[:120],
                )
            )
            continue
        adjusted.append(entry)
    return TheoryAlignmentMapping(
        reference_notes=mapping.reference_notes,
        code_notes=mapping.code_notes,
        entries=tuple(adjusted),
        diagnostics=tuple(diagnostics),
    )


def _extract_allowed_evidence_ids(route_materials: list[RouteLLMMaterial] | None) -> set[str]:
    if not route_materials:
        return set()
    ids: set[str] = set()
    for material in route_materials:
        if material.source_path != "deterministic_alignment_pack":
            continue
        try:
            payload = json.loads(material.excerpt)
        except json.JSONDecodeError:
            continue
        for value in payload.get("allowed_evidence_ids", []):
            if isinstance(value, str) and value.strip():
                ids.add(value.strip().lower())
    return ids


def _sanitize_mapping_entries(
    mapping: TheoryAlignmentMapping, allowed_ids: set[str], section_name: str
) -> TheoryAlignmentMapping:
    entries = []
    diagnostics = list(mapping.diagnostics)
    for idx, entry in enumerate(mapping.entries):
        referenced = set(re.findall(r"[a-z_]+:[a-z0-9_./-]+", entry.evidence_note.lower()))
        unknown = sorted(referenced - allowed_ids) if allowed_ids else sorted(referenced)
        retained = sorted(referenced & allowed_ids) if allowed_ids else []
        evidence_note = entry.evidence_note
        status = entry.status
        claim_ref = entry.reference_claim[:120]
        if unknown:
            diagnostics.append(
                StructuredDiagnostic(
                    code="mapping.unknown_evidence_ids_dropped",
                    severity=DiagnosticSeverity.WARNING,
                    stage="mapping",
                    summary="Unknown evidence IDs were dropped from advisory mapping",
                    detail=f"Dropped evidence IDs: {', '.join(unknown)}",
                    operation_ref=f"entry:{idx}",
                    location_ref=claim_ref,
                )
            )
            for token in unknown:
                evidence_note = evidence_note.replace(token, "")
            evidence_note = (
                re.sub(r"\s+", " ", evidence_note).strip() or "No valid evidence IDs retained."
            )
        if not retained:
            fallback = fallback_mapping_status_for_section(section_name)
            if status != fallback:
                prior_status = status
                status = fallback
                diagnostics.append(
                    StructuredDiagnostic(
                        code="mapping.no_valid_ids_status_downgraded",
                        severity=DiagnosticSeverity.WARNING,
                        stage="mapping",
                        summary="Advisory mapping status downgraded",
                        detail=(
                            "No valid deterministic evidence IDs remained; "
                            f"status transitioned {prior_status} -> {fallback}."
                        ),
                        operation_ref=f"entry:{idx}",
                        location_ref=claim_ref,
                    )
                )
        entries.append(
            type(entry)(
                reference_claim=entry.reference_claim,
                code_anchor=entry.code_anchor,
                status=status,
                evidence_note=evidence_note,
                uncertainty_note=entry.uncertainty_note,
            )
        )
    return TheoryAlignmentMapping(
        reference_notes=mapping.reference_notes,
        code_notes=mapping.code_notes,
        entries=tuple(entries),
        diagnostics=tuple(diagnostics),
    )


def mapping_status_instruction_for_section(section_name: str) -> str:
    statuses = _MAPPING_ALLOWED_STATUS_BY_SECTION.get(
        section_name, _MAPPING_ALLOWED_STATUS_BY_SECTION["theory_alignment"]
    )
    return ", ".join(statuses)


def _synthesize_final_section(
    *,
    section_name: str,
    client: LLMClient,
    base_prompt: str,
    notes: SectionNotes,
    mapping: TheoryAlignmentMapping | None,
    theory_sources: list[TheorySource],
    grounded_bundle: GroundedContextBundle | None,
    generated_text_language: GeneratedTextLanguage,
) -> FinalSectionPayload:
    contract = get_section_contract(section_name)
    mapping_block = ""
    if mapping is not None:
        mapping_lines = [
            "[ROUTED REFERENCE ALIGNMENT MAPPING SUMMARY]",
            f"mapping_entry_count: {len(mapping.entries)}",
        ]
        for entry in mapping.entries:
            mapping_lines.append(
                "- "
                f"status={entry.status}; claim={entry.reference_claim}; "
                f"code_anchor={entry.code_anchor}; evidence={entry.evidence_note}; "
                f"uncertainty={entry.uncertainty_note}"
            )
        mapping_block = "\n".join(mapping_lines)

    final_prompt = "\n\n".join(
        [
            f"[STAGE: {section_name}:final]",
            _json_only_instruction(f"{section_name}:final"),
            base_prompt,
            "[INTERMEDIATE ANALYTICAL NOTES]",
            notes.notes_markdown,
            mapping_block,
            _render_final_json_schema(section_name),
            _language_directive(generated_text_language),
        ]
    )
    final_text = _call_stage_with_retry(
        client=client,
        stage_name=f"{section_name}:final",
        system_prompt=(
            "You synthesize final structured page content from intermediate notes. "
            "Return only one valid JSON object that matches the provided schema."
        ),
        user_prompt=final_prompt,
    )
    payload = parse_final_section_output(
        section_name=section_name,
        raw_text=final_text,
        section_title=contract.title,
        required_headings=contract.headings,
    )
    if payload.diagnostics:
        prior_mapping_context = ""
        if mapping is not None:
            prior_mapping_context = "\n".join(
                [
                    "[INTERMEDIATE MAPPING CONTEXT]",
                    f"reference_notes: {mapping.reference_notes}",
                    f"code_notes: {mapping.code_notes}",
                ]
            )
        repaired_text = _call_stage_with_retry(
            client=client,
            stage_name=f"{section_name}:final-repair",
            system_prompt=(
                "Repair structured section output. "
                "Return only one valid JSON object that matches the provided schema."
            ),
            user_prompt="\n\n".join(
                [
                    f"[STAGE: {section_name}:final-repair]",
                    _json_only_instruction(f"{section_name}:final-repair"),
                    "The previous response failed structured validation.",
                    base_prompt,
                    "[INTERMEDIATE ANALYTICAL NOTES]",
                    notes.notes_markdown,
                    mapping_block,
                    prior_mapping_context,
                    "[PREVIOUS INVALID RESPONSE]",
                    final_text,
                    _render_final_json_schema(section_name),
                    _language_directive(generated_text_language),
                ]
            ),
        )
        repaired_payload = parse_final_section_output(
            section_name=section_name,
            raw_text=repaired_text,
            section_title=contract.title,
            required_headings=contract.headings,
        )
        if len(repaired_payload.section_blocks) >= len(payload.section_blocks):
            payload = repaired_payload

    aggregate_warnings = (
        payload.diagnostics + notes.diagnostics + ((mapping.diagnostics) if mapping else ())
    )
    payload_with_warnings = FinalSectionPayload(
        section_name=payload.section_name,
        title=payload.title,
        section_blocks=payload.section_blocks,
        diagnostics=aggregate_warnings,
    )
    return _repair_language_if_needed(
        payload_with_warnings,
        section_name=section_name,
        client=client,
        generated_text_language=generated_text_language,
    )


def _language_directive(generated_text_language: GeneratedTextLanguage) -> str:
    if generated_text_language == "ru":
        return (
            "Language directive: generate Russian prose for block text only. Keep JSON keys, "
            "heading keys, canonical title values, commands, flags, identifiers, filenames, "
            "paths, verdict labels, and source quotes unchanged."
        )
    return (
        "Language directive: generate English prose for block text. Keep JSON keys, heading keys, "
        "canonical title values, commands, flags, identifiers, filenames, paths, verdict labels, "
        "and source quotes unchanged."
    )


def _needs_russian_repair(payload: FinalSectionPayload) -> bool:
    texts = [block.text for blocks in payload.section_blocks.values() for block in blocks]
    joined = " ".join(texts)
    latin = len(re.findall(r"[A-Za-z]", joined))
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", joined))
    return bool(joined.strip()) and cyrillic < max(12, latin // 4)


def _repair_language_if_needed(
    payload: FinalSectionPayload,
    *,
    section_name: str,
    client: LLMClient,
    generated_text_language: GeneratedTextLanguage,
) -> FinalSectionPayload:
    if generated_text_language != "ru" or not _needs_russian_repair(payload):
        return payload

    serialized = {
        heading: [asdict(block) for block in blocks]
        for heading, blocks in payload.section_blocks.items()
    }
    repair_prompt = "\n\n".join(
        [
            f"[STAGE: {section_name}:language-repair]",
            _json_only_instruction(f"{section_name}:language-repair"),
            "Rewrite only block text values into Russian.",
            "Keep heading keys and title untouched.",
            "Do not translate commands, flags, identifiers, filenames, paths, "
            "verdict labels, or quoted excerpts.",
            "[INPUT PAYLOAD TO REWRITE]",
            json.dumps(serialized, ensure_ascii=False, indent=2),
            _render_language_repair_schema(payload, section_name),
        ]
    )
    repaired_text = _call_stage_with_retry(
        client=client,
        stage_name=f"{section_name}:language-repair",
        system_prompt=(
            "Repair language in structured payload. "
            "Return only one valid JSON object that matches the provided schema."
        ),
        user_prompt=repair_prompt,
    )
    parsed = parse_final_section_output(
        section_name=section_name,
        raw_text=repaired_text,
        section_title=payload.title,
        required_headings=get_section_contract(section_name).headings,
    )
    if _needs_russian_repair(parsed):
        return payload
    return FinalSectionPayload(
        section_name=payload.section_name,
        title=payload.title,
        section_blocks=parsed.section_blocks,
        diagnostics=payload.diagnostics
        + (
            StructuredDiagnostic(
                code="final_output.russian_language_repair_applied",
                severity=DiagnosticSeverity.INFO,
                stage="language_repair",
                summary="Russian language repair pass applied",
                detail="Structured block text was repaired to Russian output.",
                location_ref=section_name,
            ),
        ),
    )


def _build_provenance_note(
    theory_sources: list[TheorySource],
    grounded_bundle: GroundedContextBundle | None,
) -> str:
    chunk_count = len(grounded_bundle.chunks) if grounded_bundle else 0
    return "\n".join(
        [
            "> **Provenance note**",
            "> - Repository facts source: deterministic `scan_repository` manifest.",
            "> - Code facts source: deterministic `ast`-based structural extraction.",
            (
                "> - Methodology grounding: "
                f"{'present' if chunk_count else 'absent'} "
                f"(sources={len(theory_sources)}, selected_chunks_available={chunk_count})."
            ),
        ]
    )


def orchestrate_llm_section(
    *,
    section_name: str,
    client: LLMClient,
    manifest: RepoManifest,
    theory_sources: list[TheorySource],
    grounded_bundle: GroundedContextBundle | None,
    code_facts_bundle: CodeFactsBundle | None,
    route_materials: list[RouteLLMMaterial] | None = None,
    generated_text_language: GeneratedTextLanguage = "en",
) -> SectionOrchestrationResult:
    """Run section-aware Stage-7 orchestration and return final + intermediate artifacts."""

    base_prompt = _section_base_prompt(
        section_name,
        manifest,
        theory_sources,
        grounded_bundle,
        code_facts_bundle,
        route_materials,
    )
    stages_run: list[str] = []

    notes = _generate_notes(section_name=section_name, client=client, base_prompt=base_prompt)
    stages_run.append(f"{section_name}:notes")

    mapping: TheoryAlignmentMapping | None = None
    if section_name in {
        "theory_alignment",
        "reference_alignment",
        "agent_instruction_alignment",
        "readme_claim_alignment",
    }:
        mapping = _build_theory_mapping(
            client=client,
            base_prompt=base_prompt,
            section_name=section_name,
            route_materials=route_materials,
        )
        stages_run.extend(
            [
                f"{section_name}:reference-notes",
                f"{section_name}:code-notes",
                f"{section_name}:mapping",
            ]
        )

    payload = _synthesize_final_section(
        section_name=section_name,
        client=client,
        base_prompt=base_prompt,
        notes=notes,
        mapping=mapping,
        theory_sources=theory_sources,
        grounded_bundle=grounded_bundle,
        generated_text_language=generated_text_language,
    )
    stages_run.append(f"{section_name}:final")

    final_page = render_structured_section_page(
        section_name=section_name,
        section_blocks=payload.section_blocks,
        provenance_note=_build_provenance_note(theory_sources, grounded_bundle),
        diagnostics=payload.diagnostics,
    )

    return SectionOrchestrationResult(
        section_name=section_name,
        final_markdown=final_page,
        notes=notes,
        final_payload=payload,
        mapping=mapping,
        stages_run=tuple(stages_run),
    )
