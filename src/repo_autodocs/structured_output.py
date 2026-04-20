"""Structured-output parsing, validation, and recovery for LLM orchestration stages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

ALLOWED_MAPPING_STATUSES = {
    "supported",
    "contradicted",
    "partially_supported",
    "unclear",
    "missing_evidence",
}
ALLOWED_MAPPING_STATUSES_BY_SECTION = {
    "theory_alignment": ALLOWED_MAPPING_STATUSES,
    "reference_alignment": {"supported", "partially_supported", "missing_evidence", "contradicted"},
    "agent_instruction_alignment": {
        "supported",
        "partially_supported",
        "not_evidenced",
        "contradicted",
        "out_of_scope_or_non_verifiable",
    },
    "readme_claim_alignment": {
        "supported",
        "partially_supported",
        "not_evidenced",
        "contradicted",
        "not_statically_verifiable",
    },
}


class DiagnosticSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class StructuredDiagnostic:
    code: str
    severity: DiagnosticSeverity
    stage: str
    summary: str
    detail: str
    operation_ref: str = ""
    location_ref: str = ""


@dataclass(frozen=True, slots=True)
class DiagnosticSummaryItem:
    code: str
    severity: DiagnosticSeverity
    stage: str
    summary: str
    count: int


def _diag(
    *,
    code: str,
    severity: DiagnosticSeverity,
    stage: str,
    summary: str,
    detail: str,
    operation_ref: str = "",
    location_ref: str = "",
) -> StructuredDiagnostic:
    return StructuredDiagnostic(
        code=code,
        severity=severity,
        stage=stage,
        summary=summary,
        detail=detail,
        operation_ref=operation_ref,
        location_ref=location_ref,
    )


def allowed_mapping_statuses_for_section(section_name: str) -> set[str]:
    return ALLOWED_MAPPING_STATUSES_BY_SECTION.get(section_name, ALLOWED_MAPPING_STATUSES)


def fallback_mapping_status_for_section(section_name: str) -> str:
    allowed = allowed_mapping_statuses_for_section(section_name)
    for preferred in ("missing_evidence", "not_evidenced", "unclear", "partially_supported"):
        if preferred in allowed:
            return preferred
    return next(iter(sorted(allowed))) if allowed else "missing_evidence"


@dataclass(frozen=True, slots=True)
class SectionNotes:
    section_name: str
    notes_markdown: str
    observations: tuple[str, ...]
    uncertainty_flags: tuple[str, ...]
    diagnostics: tuple[StructuredDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class AlignmentMappingEntry:
    reference_claim: str
    code_anchor: str
    status: str
    evidence_note: str
    uncertainty_note: str


@dataclass(frozen=True, slots=True)
class TheoryAlignmentMapping:
    reference_notes: str
    code_notes: str
    entries: tuple[AlignmentMappingEntry, ...]
    diagnostics: tuple[StructuredDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class FinalSectionPayload:
    section_name: str
    title: str
    section_blocks: dict[str, tuple[SectionBlock, ...]]
    diagnostics: tuple[StructuredDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class SectionBlock:
    kind: str
    text: str
    label: str = ""


@dataclass(frozen=True, slots=True)
class ParsedPayload:
    payload: dict[str, object]
    diagnostics: tuple[StructuredDiagnostic, ...] = ()


def try_parse_json_payload(raw_text: str) -> ParsedPayload | None:
    cleaned = raw_text.strip()
    if not cleaned:
        return None

    candidates = [cleaned]
    if "```" in cleaned:
        for block in cleaned.split("```"):
            normalized = block.strip()
            if normalized.startswith("json"):
                normalized = normalized[4:].strip()
            if normalized.startswith("{"):
                candidates.append(normalized)

    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidates.append(cleaned[first : last + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return ParsedPayload(payload=parsed)
    return None


def _as_clean_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_string_list(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(_as_clean_str(item) for item in value if _as_clean_str(item))
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    return ()


def _extract_prefixed_bullets(markdown: str, prefix: str) -> tuple[str, ...]:
    values: list[str] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith(prefix):
            values.append(line[len(prefix) :].strip())
    return tuple(value for value in values if value)


def parse_section_notes_output(section_name: str, raw_text: str) -> SectionNotes:
    parsed = try_parse_json_payload(raw_text)
    if parsed is None:
        observations = _extract_prefixed_bullets(raw_text, "- OBS:")
        uncertainty = _extract_prefixed_bullets(raw_text, "- UNCERTAINTY:")
        return SectionNotes(
            section_name=section_name,
            notes_markdown=raw_text.strip(),
            observations=observations,
            uncertainty_flags=uncertainty,
            diagnostics=(
                _diag(
                    code="notes.non_json_recovered_from_bullets",
                    severity=DiagnosticSeverity.WARNING,
                    stage="notes",
                    summary="Notes stage returned non-JSON output",
                    detail="Recovered notes/observations using markdown bullet prefixes.",
                    location_ref=section_name,
                ),
            ),
        )

    payload = parsed.payload
    notes_markdown = _as_clean_str(payload.get("notes_markdown") or payload.get("notes"))
    observations = _as_string_list(payload.get("observations"))
    uncertainty = _as_string_list(payload.get("uncertainty_flags") or payload.get("uncertainties"))
    if not notes_markdown:
        composed_lines = [f"- OBS: {item}" for item in observations]
        composed_lines.extend(f"- UNCERTAINTY: {item}" for item in uncertainty)
        notes_markdown = "\n".join(composed_lines).strip()

    return SectionNotes(
        section_name=section_name,
        notes_markdown=notes_markdown,
        observations=observations,
        uncertainty_flags=uncertainty,
        diagnostics=(),
    )


def parse_theory_mapping_output(raw_text: str) -> TheoryAlignmentMapping:
    return parse_alignment_mapping_output("theory_alignment", raw_text)


def parse_alignment_mapping_output(section_name: str, raw_text: str) -> TheoryAlignmentMapping:
    parsed = try_parse_json_payload(raw_text)
    fallback_status = fallback_mapping_status_for_section(section_name)
    if parsed is None:
        fallback = AlignmentMappingEntry(
            reference_claim="No reliably grounded reference claim extracted",
            code_anchor="No mapping anchor",
            status=fallback_status,
            evidence_note="Mapping stage returned non-JSON output.",
            uncertainty_note="Alignment confidence is low due to unstructured mapping output.",
        )
        return TheoryAlignmentMapping(
            reference_notes="",
            code_notes="",
            entries=(fallback,),
            diagnostics=(
                _diag(
                    code="mapping.non_json_fallback_entry_injected",
                    severity=DiagnosticSeverity.WARNING,
                    stage="mapping",
                    summary="Mapping stage returned non-JSON output",
                    detail=(
                        "Injected fallback mapping entry because structured mapping "
                        "was unavailable."
                    ),
                    location_ref=section_name,
                    operation_ref="entry:0",
                ),
            ),
        )

    payload = parsed.payload
    entries_raw = payload.get("entries")
    reference_notes = _as_clean_str(payload.get("reference_notes"))
    code_notes = _as_clean_str(payload.get("code_notes"))
    diagnostics: list[StructuredDiagnostic] = []
    entries: list[AlignmentMappingEntry] = []

    if isinstance(entries_raw, list):
        for idx, raw in enumerate(entries_raw):
            if not isinstance(raw, dict):
                diagnostics.append(
                    _diag(
                        code="mapping.non_object_entry_dropped",
                        severity=DiagnosticSeverity.WARNING,
                        stage="mapping",
                        summary="Dropped non-object mapping entry",
                        detail="Mapping entries must be objects; invalid entry was ignored.",
                        operation_ref=f"entry:{idx}",
                        location_ref=section_name,
                    )
                )
                continue
            status = _as_clean_str(raw.get("status")).lower() or fallback_status
            allowed = allowed_mapping_statuses_for_section(section_name)
            if status not in allowed:
                original_status = status
                status = fallback_status
                diagnostics.append(
                    _diag(
                        code="mapping.unsupported_status_normalized",
                        severity=DiagnosticSeverity.WARNING,
                        stage="mapping",
                        summary="Unsupported mapping status was normalized",
                        detail=(
                            "Entry status was not allowed for this route and was replaced "
                            f"with fallback '{fallback_status}' from '{original_status}'."
                        ),
                        operation_ref=f"entry:{idx}",
                        location_ref=section_name,
                    )
                )
            entry = AlignmentMappingEntry(
                reference_claim=_as_clean_str(raw.get("reference_claim")) or "Unspecified claim",
                code_anchor=_as_clean_str(raw.get("code_anchor")) or "Unspecified code anchor",
                status=status,
                evidence_note=_as_clean_str(raw.get("evidence_note"))
                or "No evidence note provided.",
                uncertainty_note=_as_clean_str(raw.get("uncertainty_note"))
                or "No uncertainty note provided.",
            )
            entries.append(entry)

    if not entries:
        entries = [
            AlignmentMappingEntry(
                reference_claim="No reliably grounded reference claim extracted",
                code_anchor="No mapping anchor",
                status=fallback_status,
                evidence_note="Mapping stage produced no valid entries.",
                uncertainty_note="Alignment confidence is low due to absent mapping artifacts.",
            )
        ]
        diagnostics.append(
            _diag(
                code="mapping.no_valid_entries_fallback_injected",
                severity=DiagnosticSeverity.WARNING,
                stage="mapping",
                summary="No valid mapping entries were found",
                detail=(
                    "Injected fallback mapping entry because mapping output had no valid entries."
                ),
                location_ref=section_name,
                operation_ref="entry:0",
            )
        )

    return TheoryAlignmentMapping(
        reference_notes=reference_notes,
        code_notes=code_notes,
        entries=tuple(entries),
        diagnostics=tuple(diagnostics),
    )


def parse_final_section_output(
    *,
    section_name: str,
    raw_text: str,
    section_title: str,
    required_headings: tuple[str, ...],
) -> FinalSectionPayload:
    parsed = try_parse_json_payload(raw_text)
    headings_by_key = {heading.casefold(): heading for heading in required_headings}
    section_blocks: dict[str, tuple[SectionBlock, ...]] = {}
    diagnostics: list[StructuredDiagnostic] = []

    if parsed is None:
        return FinalSectionPayload(
            section_name=section_name,
            title=section_title,
            section_blocks={
                required_headings[0]: (
                    SectionBlock(
                        kind="paragraph",
                        text=raw_text.strip()
                        or "No structured section content was returned by the model.",
                    ),
                )
            },
            diagnostics=(
                _diag(
                    code="final_output.non_json_preserved_raw_text",
                    severity=DiagnosticSeverity.WARNING,
                    stage="final_parse",
                    summary="Final synthesis returned non-JSON output",
                    detail="Preserved raw model text in the first required heading.",
                    location_ref=section_name,
                    operation_ref=f"heading:{required_headings[0]}",
                ),
            ),
        )

    payload = parsed.payload
    title = _as_clean_str(payload.get("title")) or section_title

    body_map = (
        payload.get("section_blocks") or payload.get("section_bodies") or payload.get("sections")
    )
    unknown_contents: list[tuple[SectionBlock, ...]] = []

    if isinstance(body_map, dict):
        for heading, raw_blocks in body_map.items():
            canonical = headings_by_key.get(_as_clean_str(heading).casefold())
            normalized, block_diagnostics = _normalize_blocks(
                raw_blocks,
                stage="final_parse",
                heading_ref=canonical or _as_clean_str(heading),
                section_name=section_name,
            )
            diagnostics.extend(block_diagnostics)
            if canonical and normalized:
                section_blocks[canonical] = normalized
            elif normalized:
                unknown_contents.append(normalized)
    elif isinstance(body_map, list):
        for row in body_map:
            if not isinstance(row, dict):
                continue
            heading = _as_clean_str(row.get("heading") or row.get("name"))
            canonical = headings_by_key.get(heading.casefold())
            candidate_blocks = (
                row.get("blocks")
                or row.get("section_blocks")
                or row.get("body")
                or row.get("content")
            )
            normalized, block_diagnostics = _normalize_blocks(
                candidate_blocks,
                stage="final_parse",
                heading_ref=canonical or heading,
                section_name=section_name,
            )
            diagnostics.extend(block_diagnostics)
            canonical = headings_by_key.get(heading.casefold())
            if canonical and normalized:
                section_blocks[canonical] = normalized
            elif normalized:
                unknown_contents.append(normalized)

    ordered_missing = [heading for heading in required_headings if heading not in section_blocks]
    for heading, recovered in zip(ordered_missing, unknown_contents, strict=False):
        section_blocks[heading] = recovered
        diagnostics.append(
            _diag(
                code="final_output.unknown_section_recovered_into_missing_slot",
                severity=DiagnosticSeverity.WARNING,
                stage="final_parse",
                summary="Recovered unknown section content into a required heading",
                detail=(
                    "Recovered structured content from an unknown/extra section entry into "
                    f"required heading '{heading}'."
                ),
                location_ref=section_name,
                operation_ref=f"heading:{heading}",
            )
        )

    if not section_blocks and required_headings:
        section_blocks[required_headings[0]] = (
            SectionBlock(
                kind="paragraph", text="No valid structured section bodies were returned."
            ),
        )
        diagnostics.append(
            _diag(
                code="final_output.no_valid_section_bodies_fallback_inserted",
                severity=DiagnosticSeverity.WARNING,
                stage="final_parse",
                summary="No valid structured section bodies were parseable",
                detail="Inserted explicit fallback body in the first required heading.",
                location_ref=section_name,
                operation_ref=f"heading:{required_headings[0]}",
            )
        )

    return FinalSectionPayload(
        section_name=section_name,
        title=title,
        section_blocks=section_blocks,
        diagnostics=tuple(diagnostics),
    )


def _normalize_blocks(
    value: object, *, stage: str, heading_ref: str, section_name: str
) -> tuple[tuple[SectionBlock, ...], list[StructuredDiagnostic]]:
    diagnostics: list[StructuredDiagnostic] = []
    if isinstance(value, str):
        text = _as_clean_str(value)
        return ((SectionBlock(kind="paragraph", text=text),) if text else ()), diagnostics
    if not isinstance(value, list):
        return (), diagnostics

    blocks: list[SectionBlock] = []
    for idx, raw in enumerate(value):
        if isinstance(raw, str):
            text = _as_clean_str(raw)
            if text:
                blocks.append(SectionBlock(kind="paragraph", text=text))
            continue
        if not isinstance(raw, dict):
            diagnostics.append(
                _diag(
                    code="final_output.non_object_block_dropped",
                    severity=DiagnosticSeverity.WARNING,
                    stage=stage,
                    summary="Dropped non-object section block",
                    detail="Section blocks must be objects with a block kind and text.",
                    operation_ref=f"block:{idx}",
                    location_ref=f"{section_name}:{heading_ref}",
                )
            )
            continue
        kind = _as_clean_str(raw.get("kind")).lower()
        text = _as_clean_str(raw.get("text") or raw.get("body") or raw.get("content"))
        label = _as_clean_str(raw.get("label"))
        if not text:
            diagnostics.append(
                _diag(
                    code="final_output.empty_block_dropped",
                    severity=DiagnosticSeverity.WARNING,
                    stage=stage,
                    summary="Dropped empty section block",
                    detail="Block text was empty after sanitization.",
                    operation_ref=f"block:{idx}",
                    location_ref=f"{section_name}:{heading_ref}",
                )
            )
            continue
        if kind not in {"paragraph", "bullet", "labeled_bullet", "numbered_item"}:
            original_kind = kind or "<missing>"
            kind = "paragraph"
            diagnostics.append(
                _diag(
                    code="final_output.unsupported_block_kind_normalized",
                    severity=DiagnosticSeverity.WARNING,
                    stage=stage,
                    summary="Unsupported block kind was normalized",
                    detail=(f"Normalized block kind from '{original_kind}' to 'paragraph'."),
                    operation_ref=f"block:{idx}",
                    location_ref=f"{section_name}:{heading_ref}",
                )
            )
        if kind == "labeled_bullet" and not label:
            label = "Note"
            diagnostics.append(
                _diag(
                    code="final_output.labeled_bullet_missing_label_normalized",
                    severity=DiagnosticSeverity.WARNING,
                    stage=stage,
                    summary="Missing labeled_bullet label was normalized",
                    detail="Applied default label 'Note' for labeled_bullet block.",
                    operation_ref=f"block:{idx}",
                    location_ref=f"{section_name}:{heading_ref}",
                )
            )
        blocks.append(SectionBlock(kind=kind, text=text, label=label))
    return tuple(blocks), diagnostics


def collapse_exact_duplicate_diagnostics(
    diagnostics: tuple[StructuredDiagnostic, ...] | list[StructuredDiagnostic],
) -> tuple[tuple[StructuredDiagnostic, int], ...]:
    deduped: dict[StructuredDiagnostic, int] = {}
    for item in diagnostics:
        deduped[item] = deduped.get(item, 0) + 1
    return tuple(deduped.items())


def group_diagnostics_for_summary(
    diagnostics: tuple[StructuredDiagnostic, ...] | list[StructuredDiagnostic],
) -> tuple[DiagnosticSummaryItem, ...]:
    grouped: dict[tuple[str, DiagnosticSeverity, str, str], int] = {}
    for item in diagnostics:
        key = (item.code, item.severity, item.stage, item.summary)
        grouped[key] = grouped.get(key, 0) + 1
    ordered = sorted(grouped.items(), key=lambda kv: (-kv[1], kv[0][0], kv[0][2]))
    return tuple(
        DiagnosticSummaryItem(
            code=code,
            severity=severity,
            stage=stage,
            summary=summary,
            count=count,
        )
        for (code, severity, stage, summary), count in ordered
    )


def summarize_diagnostics(
    diagnostics: tuple[StructuredDiagnostic, ...] | list[StructuredDiagnostic],
) -> dict[str, Any]:
    severities: dict[str, int] = {s.value: 0 for s in DiagnosticSeverity}
    by_stage: dict[str, int] = {}
    for item in diagnostics:
        severities[item.severity.value] = severities.get(item.severity.value, 0) + 1
        by_stage[item.stage] = by_stage.get(item.stage, 0) + 1
    return {
        "total": len(tuple(diagnostics)),
        "by_severity": {k: v for k, v in severities.items() if v},
        "by_stage": dict(sorted(by_stage.items(), key=lambda kv: (-kv[1], kv[0]))),
        "patterns": group_diagnostics_for_summary(diagnostics),
    }
