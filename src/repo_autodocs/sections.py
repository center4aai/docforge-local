"""Section-level orchestration for generated markdown docs."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from repo_autodocs.config import AppConfig
from repo_autodocs.deterministic import DeterministicContext, render_deterministic_sections
from repo_autodocs.grounding import build_grounded_context_bundle
from repo_autodocs.llm import (
    LLMClient,
    LLMServiceError,
    LLMStreamInterruptedFailure,
    LLMTransientFailure,
    OpenAICompatibleLLMClient,
)
from repo_autodocs.models import (
    CodeFactsBundle,
    GroundedContextBundle,
    RepoManifest,
    RoutedLLMMaterialBundle,
    TheorySource,
)
from repo_autodocs.orchestration import orchestrate_llm_section
from repo_autodocs.prompts import (
    build_agent_instruction_alignment_prompt,
    build_architecture_prompt,
    build_code_structure_prompt,
    build_overview_prompt,
    build_readme_claim_alignment_prompt,
    build_reference_alignment_prompt,
    build_runtime_entrypoints_prompt,
)
from repo_autodocs.rendering import (
    SectionBlock,
    get_section_contract,
    render_structured_section_page,
)
from repo_autodocs.structured_output import DiagnosticSeverity, StructuredDiagnostic

SECTION_TO_FILENAME = {
    "overview": "overview.md",
    "architecture": "architecture.md",
    "code_structure": "code_structure.md",
    "runtime_entrypoints": "runtime_entrypoints.md",
    "reference_alignment": "reference_alignment.md",
    "agent_instruction_alignment": "agent_instruction_alignment.md",
    "readme_claim_alignment": "readme_claim_alignment.md",
    "theory_alignment": "theory_alignment.md",
}

LLM_SECTION_KEYS = (
    "overview",
    "architecture",
    "code_structure",
    "runtime_entrypoints",
    "reference_alignment",
    "agent_instruction_alignment",
    "readme_claim_alignment",
)

logger = logging.getLogger(__name__)


def build_section_inputs(
    manifest: RepoManifest,
    theory_sources: list[TheorySource],
    grounded_bundle: GroundedContextBundle | None,
    code_facts_bundle: CodeFactsBundle | None,
    llm_route_materials: RoutedLLMMaterialBundle | None = None,
) -> dict[str, str]:
    """Build deterministic prompt text per section key."""

    return {
        "overview": build_overview_prompt(
            manifest,
            theory_sources,
            grounded_bundle,
            code_facts_bundle,
        ),
        "architecture": build_architecture_prompt(
            manifest,
            theory_sources,
            grounded_bundle,
            code_facts_bundle,
        ),
        "code_structure": build_code_structure_prompt(
            manifest,
            theory_sources,
            grounded_bundle,
            code_facts_bundle,
        ),
        "runtime_entrypoints": build_runtime_entrypoints_prompt(
            manifest,
            theory_sources,
            grounded_bundle,
            code_facts_bundle,
        ),
        "reference_alignment": build_reference_alignment_prompt(
            manifest,
            theory_sources,
            grounded_bundle,
            code_facts_bundle,
            llm_route_materials.reference_alignment if llm_route_materials else None,
        ),
        "agent_instruction_alignment": build_agent_instruction_alignment_prompt(
            manifest,
            theory_sources,
            grounded_bundle,
            code_facts_bundle,
            llm_route_materials.agent_instruction_alignment if llm_route_materials else None,
        ),
        "readme_claim_alignment": build_readme_claim_alignment_prompt(
            manifest,
            theory_sources,
            grounded_bundle,
            code_facts_bundle,
            llm_route_materials.readme_claim_alignment if llm_route_materials else None,
        ),
        "theory_alignment": (
            "# Theory Alignment\n\nDeprecated compatibility shim. "
            "See reference_alignment, agent_instruction_alignment, readme_claim_alignment."
        ),
    }


def _resolve_client(config: AppConfig) -> tuple[LLMClient, str, str]:
    client = OpenAICompatibleLLMClient.from_config(config)
    return client, "llm", config.model_name or "unknown"


def _build_header(mode: str, model: str, section: str, timestamp: datetime | None) -> str:
    timestamp_value = timestamp.isoformat() if timestamp else "none"
    return "\n".join(
        [
            "<!--",
            "Generated section artifact",
            f"section: {section}",
            f"generation_mode: {mode}",
            f"model: {model}",
            f"timestamp_utc: {timestamp_value}",
            "source_note: deterministic repository scan and code-facts extraction",
            "  are authoritative;",
            "  external references influence synthesis, not structural facts",
            "-->",
            "",
            "",
        ]
    )


def generate_sections(
    manifest: RepoManifest,
    theory_sources: list[TheorySource],
    config: AppConfig,
    code_facts_bundle: CodeFactsBundle | None = None,
    grounded_bundle: GroundedContextBundle | None = None,
    routed_alignment_bundle=None,
    llm_route_materials: RoutedLLMMaterialBundle | None = None,
    timestamp: datetime | None = None,
) -> dict[str, str]:
    """Generate markdown section files using deterministic or LLM mode."""

    active_grounded_bundle = grounded_bundle or build_grounded_context_bundle(theory_sources)
    if not config.enable_llm:
        return render_deterministic_sections(
            DeterministicContext(
                manifest=manifest,
                theory_sources=theory_sources,
                code_facts_bundle=code_facts_bundle or CodeFactsBundle(),
                grounded_bundle=active_grounded_bundle,
                routed_alignment=routed_alignment_bundle,
            ),
            generated_text_language=config.generated_text_language,
        )

    prompts = build_section_inputs(
        manifest,
        theory_sources,
        active_grounded_bundle,
        code_facts_bundle,
        llm_route_materials,
    )
    client, mode, model_name = _resolve_client(config)
    now = timestamp if timestamp is not None else (datetime.now(UTC) if mode == "llm" else None)

    rendered: dict[str, str] = {}
    transport_failures: list[LLMTransientFailure | LLMStreamInterruptedFailure] = []
    for section_key, prompt in prompts.items():
        if section_key == "theory_alignment":
            rendered["theory_alignment.md"] = prompt + "\n"
            continue
        filename = SECTION_TO_FILENAME[section_key]
        header = _build_header(mode=mode, model=model_name, section=section_key, timestamp=now)
        try:
            orchestration = orchestrate_llm_section(
                section_name=section_key,
                client=client,
                manifest=manifest,
                theory_sources=theory_sources,
                grounded_bundle=active_grounded_bundle,
                code_facts_bundle=code_facts_bundle,
                route_materials=(
                    llm_route_materials.reference_alignment if llm_route_materials else None
                )
                if section_key == "reference_alignment"
                else (
                    llm_route_materials.agent_instruction_alignment if llm_route_materials else None
                )
                if section_key == "agent_instruction_alignment"
                else (llm_route_materials.readme_claim_alignment if llm_route_materials else None)
                if section_key == "readme_claim_alignment"
                else None,
                generated_text_language=config.generated_text_language,
            )
            rendered[filename] = header + orchestration.final_markdown
        except LLMTransientFailure as exc:
            transport_failures.append(exc)
            logger.warning(
                "LLM section failed after transport retries and will be marked unavailable "
                "(section=%s, attempts=%s, timeouts=%s, final_error=%s: %s).",
                section_key,
                exc.attempt_count,
                list(exc.attempt_timeouts_seconds),
                exc.final_exception_type,
                exc.final_error_message,
            )
            rendered[filename] = header + _render_llm_transport_failure_section(
                section_name=section_key,
                failure=exc,
                theory_sources=theory_sources,
                grounded_bundle=active_grounded_bundle,
            )
        except LLMStreamInterruptedFailure as exc:
            transport_failures.append(exc)
            logger.warning(
                "LLM section stream interrupted and will be marked unavailable "
                "(section=%s, attempt=%s, meaningful_started=%s, content_received_chars=%s, "
                "final_error=%s: %s).",
                section_key,
                exc.attempt_count,
                exc.meaningful_response_started,
                exc.content_received_chars,
                exc.final_exception_type,
                exc.final_error_message,
            )
            rendered[filename] = header + _render_llm_transport_failure_section(
                section_name=section_key,
                failure=exc,
                theory_sources=theory_sources,
                grounded_bundle=active_grounded_bundle,
            )

    if transport_failures and len(transport_failures) >= len(LLM_SECTION_KEYS):
        summary = ", ".join(
            f"{failure.operation_label}({failure.final_exception_type})"
            for failure in transport_failures
        )
        raise LLMServiceError(
            f"LLM streaming transport unavailable for all LLM sections. Failures: {summary}."
        )

    return rendered


def _render_llm_transport_failure_section(
    *,
    section_name: str,
    failure: LLMTransientFailure | LLMStreamInterruptedFailure,
    theory_sources: list[TheorySource],
    grounded_bundle: GroundedContextBundle | None,
) -> str:
    contract = get_section_contract(section_name)
    section_blocks = {
        heading: (
            SectionBlock(
                kind="paragraph",
                text=(
                    "LLM transport was temporarily unavailable for this section. "
                    "This section could not be synthesized in this run."
                ),
            ),
        )
        for heading in contract.headings
    }
    provenance_note = "\n".join(
        [
            "> **Provenance note**",
            "> - Repository facts source: deterministic `scan_repository` manifest.",
            "> - Code facts source: deterministic `ast`-based structural extraction.",
            (
                "> - Methodology grounding: "
                f"{'present' if (grounded_bundle and grounded_bundle.chunks) else 'absent'} "
                f"(sources={len(theory_sources)}, "
                "selected_chunks_available="
                f"{len(grounded_bundle.chunks) if grounded_bundle else 0})."
            ),
        ]
    )
    diagnostics: list[StructuredDiagnostic] = [
        StructuredDiagnostic(
            code=(
                "rendering.llm_stream_interrupted_section_unavailable"
                if isinstance(failure, LLMStreamInterruptedFailure)
                else "rendering.llm_transient_exhausted_section_unavailable"
            ),
            severity=DiagnosticSeverity.ERROR,
            stage="rendering",
            summary=(
                "Section unavailable due to streaming interruption"
                if isinstance(failure, LLMStreamInterruptedFailure)
                else "Section unavailable due to transient LLM transport exhaustion"
            ),
            detail=(
                f"operation={failure.operation_label}; attempts={failure.attempt_count}; "
                f"exception={failure.final_exception_type}; error={failure.final_error_message}"
            ),
            location_ref=section_name,
        )
    ]
    if isinstance(failure, LLMTransientFailure):
        diagnostics.append(
            StructuredDiagnostic(
                code="rendering.llm_transient_attempt_timeouts",
                severity=DiagnosticSeverity.INFO,
                stage="rendering",
                summary="Transient retry timeouts recorded",
                detail=f"attempt_timeouts_seconds={list(failure.attempt_timeouts_seconds)}",
                location_ref=section_name,
            )
        )
    if isinstance(failure, LLMStreamInterruptedFailure):
        diagnostics.extend(
            (
                StructuredDiagnostic(
                    code="rendering.llm_stream_meaningful_response_started",
                    severity=DiagnosticSeverity.INFO,
                    stage="rendering",
                    summary="Meaningful response started before interruption",
                    detail=f"meaningful_response_started={failure.meaningful_response_started}",
                    location_ref=section_name,
                ),
                StructuredDiagnostic(
                    code="rendering.llm_stream_content_received_chars",
                    severity=DiagnosticSeverity.INFO,
                    stage="rendering",
                    summary="Partial stream content was received",
                    detail=f"content_received_chars={failure.content_received_chars}",
                    location_ref=section_name,
                ),
            )
        )
    return render_structured_section_page(
        section_name=section_name,
        section_blocks=section_blocks,
        provenance_note=provenance_note,
        diagnostics=tuple(diagnostics),
    )
