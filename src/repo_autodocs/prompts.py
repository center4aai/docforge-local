"""Deterministic prompt builders for generated documentation sections."""

from __future__ import annotations

import json
from dataclasses import dataclass

from repo_autodocs.codefacts import select_code_facts_for_section
from repo_autodocs.grounding import render_methodology_chunks_for_prompt
from repo_autodocs.models import (
    CodeFactsBundle,
    GroundedContextBundle,
    MethodologyChunk,
    RepoManifest,
    RouteLLMMaterial,
    TheorySource,
)
from repo_autodocs.rendering import get_section_contract


@dataclass(frozen=True, slots=True)
class GroundingBudget:
    """Deterministic chunk/size limits for prompt grounding blocks."""

    max_chunks: int
    max_total_chars: int
    max_chars_per_chunk: int


SECTION_GROUNDING_BUDGETS: dict[str, GroundingBudget] = {
    "overview": GroundingBudget(max_chunks=4, max_total_chars=2600, max_chars_per_chunk=800),
    "architecture": GroundingBudget(max_chunks=6, max_total_chars=4200, max_chars_per_chunk=1000),
    "code_structure": GroundingBudget(max_chunks=6, max_total_chars=4200, max_chars_per_chunk=1000),
    "runtime_entrypoints": GroundingBudget(
        max_chunks=5, max_total_chars=3000, max_chars_per_chunk=900
    ),
    "theory_alignment": GroundingBudget(
        max_chunks=8, max_total_chars=5600, max_chars_per_chunk=1100
    ),
    "reference_alignment": GroundingBudget(
        max_chunks=8, max_total_chars=5600, max_chars_per_chunk=1100
    ),
    "agent_instruction_alignment": GroundingBudget(
        max_chunks=5, max_total_chars=3600, max_chars_per_chunk=900
    ),
    "readme_claim_alignment": GroundingBudget(
        max_chunks=5, max_total_chars=3600, max_chars_per_chunk=900
    ),
}


@dataclass(frozen=True, slots=True)
class SelectedGrounding:
    """Deterministically selected chunks for a specific section prompt."""

    section_name: str
    budget: GroundingBudget
    selected_chunk_count: int
    selected_total_chars: int
    selected_source_files: tuple[str, ...]
    selected_chunks: tuple[MethodologyChunk, ...]


EMPTY_BUNDLE = GroundedContextBundle()

_SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "overview": ("overview", "readme", "summary", "purpose", "goal", "intro"),
    "architecture": (
        "architecture",
        "module",
        "component",
        "boundary",
        "dependency",
        "integration",
        "entrypoint",
    ),
    "code_structure": (
        "structure",
        "module",
        "package",
        "symbol",
        "import",
        "dependency",
        "test",
    ),
    "runtime_entrypoints": (
        "entrypoint",
        "runtime",
        "cli",
        "command",
        "main",
        "typer",
        "argparse",
    ),
    "theory_alignment": (
        "theory",
        "alignment",
        "method",
        "principle",
        "assumption",
        "constraint",
        "mismatch",
    ),
    "reference_alignment": (
        "reference",
        "alignment",
        "claim",
        "supported",
        "contradicted",
        "missing",
    ),
    "agent_instruction_alignment": (
        "agent",
        "instruction",
        "workflow",
        "config",
        "command",
    ),
    "readme_claim_alignment": (
        "readme",
        "claim",
        "install",
        "command",
        "output",
        "llm",
    ),
}


def _chunk_relevance_score(section_name: str, chunk: MethodologyChunk) -> int:
    keywords = _SECTION_KEYWORDS[section_name]
    haystack = " ".join(
        [
            chunk.document_relative_path.lower(),
            (chunk.section_hint or "").lower(),
            chunk.text[:400].lower(),
        ]
    )
    score = 0
    for kw in keywords:
        if kw in haystack:
            score += 5
    if chunk.section_hint and section_name in chunk.section_hint.lower().replace("-", "_"):
        score += 6
    return score


def select_grounded_chunks_for_section(
    section_name: str,
    grounded_bundle: GroundedContextBundle | None,
) -> SelectedGrounding:
    """Select methodology chunks deterministically under section-specific budgets."""

    budget = SECTION_GROUNDING_BUDGETS[section_name]
    bundle = grounded_bundle or EMPTY_BUNDLE
    if not bundle.chunks:
        return SelectedGrounding(
            section_name=section_name,
            budget=budget,
            selected_chunk_count=0,
            selected_total_chars=0,
            selected_source_files=tuple(),
            selected_chunks=tuple(),
        )

    ranked_chunks = sorted(
        bundle.chunks,
        key=lambda chunk: (
            -_chunk_relevance_score(section_name, chunk),
            chunk.document_relative_path,
            chunk.index,
            chunk.chunk_id,
        ),
    )

    total_chars = 0
    source_files: list[str] = []
    selected_chunks: list[MethodologyChunk] = []

    for chunk in ranked_chunks:
        if len(selected_chunks) >= budget.max_chunks:
            break

        chunk_chars = min(len(chunk.text), budget.max_chars_per_chunk)
        if total_chars + chunk_chars > budget.max_total_chars:
            continue

        total_chars += chunk_chars
        source_files.append(chunk.document_relative_path)
        selected_chunks.append(chunk)

    return SelectedGrounding(
        section_name=section_name,
        budget=budget,
        selected_chunk_count=len(selected_chunks),
        selected_total_chars=total_chars,
        selected_source_files=tuple(dict.fromkeys(source_files)),
        selected_chunks=tuple(selected_chunks),
    )


def _render_repo_facts(manifest: RepoManifest) -> str:
    lines = [
        "[REPOSITORY FACTS - DETERMINISTIC SCAN - AUTHORITATIVE]",
        f"project_root: {manifest.project_root}",
        f"top_level_directories: {', '.join(manifest.top_level_directories) or '(none)'}",
        f"top_level_files: {', '.join(manifest.top_level_files) or '(none)'}",
        f"has_pyproject: {manifest.has_pyproject}",
        f"has_mkdocs_config: {manifest.has_mkdocs_config}",
        f"has_docs_dir: {manifest.has_docs_dir}",
        f"has_src_dir: {manifest.has_src_dir}",
        f"has_tests_dir: {manifest.has_tests_dir}",
    ]
    return "\n".join(lines)


def _render_theory_context(theory_sources: list[TheorySource]) -> str:
    lines = ["[EXTERNAL REFERENCE SOURCES - DISCOVERED METADATA ONLY]"]
    if not theory_sources:
        lines.append("No external reference source files were discovered.")
        return "\n".join(lines)

    lines.append("Discovered external reference source files:")
    for source in theory_sources:
        lines.append(f"- {source.relative_path} ({source.extension}, {source.size_bytes} bytes)")
    return "\n".join(lines)


def _render_authoritative_repo_evidence(section_name: str, manifest: RepoManifest) -> str:
    selected = _select_authoritative_repo_evidence(section_name, manifest)
    lines = ["[AUTHORITATIVE REPOSITORY EVIDENCE]"]
    if not selected:
        lines.append("No repository text evidence discovered.")
        return "\n".join(lines)

    lines.append(f"selected_items: {len(selected)}")
    for item in selected:
        lines.extend(
            [
                f"## {item.category}: {item.relative_path}",
                f"lines_in_excerpt: {item.line_count}",
                item.excerpt,
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _select_authoritative_repo_evidence(section_name: str, manifest: RepoManifest):
    evidence = [
        item
        for item in manifest.textual_evidence
        if item.category not in {"readme", "runtime_config"}
    ]
    if section_name == "overview":
        ordered = sorted(
            evidence,
            key=lambda item: (
                item.category != "package_config",
                item.relative_path,
            ),
        )
        selected = ordered[:4]
    elif section_name == "architecture":
        ordered = sorted(
            evidence,
            key=lambda item: (
                item.category == "test_file",
                item.category,
                item.relative_path,
            ),
        )
        selected = ordered[:6]
    elif section_name == "code_structure":
        ordered = sorted(
            evidence,
            key=lambda item: (
                item.category != "package_config",
                item.category == "test_file",
                item.relative_path,
            ),
        )
        selected = ordered[:7]
    elif section_name == "runtime_entrypoints":
        ordered = sorted(
            evidence,
            key=lambda item: (
                item.category == "test_file",
                item.category,
                item.relative_path,
            ),
        )
        selected = ordered[:6]
    else:
        selected = sorted(evidence, key=lambda item: (item.category, item.relative_path))[:6]
    return selected


def _render_code_facts_block(section_name: str, code_facts_bundle: CodeFactsBundle | None) -> str:
    selected = select_code_facts_for_section(section_name, code_facts_bundle)
    lines = ["[AUTHORITATIVE CODE FACTS - DETERMINISTIC STRUCTURAL ANALYSIS]"]
    lines.append(
        "module_count="
        f"{len(selected.modules)}, symbol_count={len(selected.symbols)}, "
        f"import_edge_count={len(selected.imports)}, "
        f"entrypoint_count={len(selected.detected_entrypoints)}, "
        f"excerpt_count={len(selected.code_excerpts)}"
    )
    lines.append("framework_hints: " + (", ".join(selected.framework_hints) or "(none)"))

    lines.append("Top modules:")
    if not selected.modules:
        lines.append("- None")
    else:
        for module in selected.modules:
            symbol_count = module.defined_class_count + module.defined_function_count
            lines.append(
                f"- {module.module_name} ({module.relative_path}, "
                f"score={module.module_importance_score}, symbols={symbol_count}, "
                f"imports={module.import_count}, test_module={module.is_test_module})"
            )

    lines.append("Selected public symbol signatures/docstrings:")
    if not selected.symbols:
        lines.append("- None")
    else:
        for symbol in selected.symbols:
            if not symbol.is_public:
                continue
            doc = (symbol.docstring or "(none)").splitlines()[0][:90]
            signature = symbol.signature or "(unknown)"
            lines.append(
                f"- {symbol.module_name}:{symbol.symbol_name} signature={signature} "
                f"docstring={doc!r} line={symbol.lineno}"
            )

    lines.append("Selected import relations:")
    if not selected.imports:
        lines.append("- None")
    else:
        for edge in selected.imports:
            qualifier = "relative" if edge.relative else "absolute"
            lines.append(f"- {edge.source_module} -> {edge.imported_module} ({qualifier})")

    lines.append("Entrypoint evidence:")
    if not selected.entrypoint_evidence:
        lines.append("- None")
    else:
        for entrypoint in selected.entrypoint_evidence:
            lines.append(
                f"- {entrypoint.label} ({entrypoint.relative_path}) reason={entrypoint.reason}"
            )

    lines.append("Code excerpts:")
    if not selected.code_excerpts:
        lines.append("- None")
    else:
        for excerpt in selected.code_excerpts:
            preview = excerpt.excerpt.replace("\n", " ")[:180]
            lines.append(
                f"- {excerpt.module_name} [{excerpt.excerpt_kind}] {excerpt.relative_path}:"
                f"{excerpt.start_line}-{excerpt.end_line} :: {preview}"
            )

    return "\n".join(lines)


def _json_only_stage_notice() -> str:
    return "\n".join(
        [
            "[JSON OUTPUT DISCIPLINE FOR SCHEMA-DRIVEN STAGES]",
            "If the current stage asks for JSON, return ONLY one valid JSON object and nothing else.",
            "Do not wrap JSON in markdown fences.",
            "Do not add explanations, comments, prose, bullet lists, or text before or after the JSON object.",
            "Do not rename keys, translate keys, or add extra top-level keys.",
            "When a stage-specific schema is provided later in the prompt, follow that schema exactly.",
        ]
    )


def _render_required_heading_key_explanations(section_name: str) -> str:
    contract = get_section_contract(section_name)
    lines = ["Required keys inside section_blocks:"]
    for heading in contract.headings:
        lines.append(
            f'- "{heading}": array of block objects for the required H2 heading "{heading}". '
            "The key must appear exactly as written, even when evidence is limited."
        )
    return "\n".join(lines)


def _build_final_section_example(section_name: str) -> dict[str, object]:
    contract = get_section_contract(section_name)
    section_blocks: dict[str, list[dict[str, str]]] = {}

    for idx, heading in enumerate(contract.headings):
        if idx == 0:
            section_blocks[heading] = [
                {
                    "kind": "paragraph",
                    "text": "Observed repository evidence is summarized here with concise, grounded prose.",
                },
                {
                    "kind": "bullet",
                    "text": "Key implementation fact or repository signal.",
                },
                {
                    "kind": "labeled_bullet",
                    "label": "Inference",
                    "text": "Interpretation that is clearly separated from direct evidence.",
                },
                {
                    "kind": "numbered_item",
                    "text": "Ordered analytical step or consequence supported by the evidence.",
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


def _render_final_output_schema_block(section_name: str) -> str:
    contract = get_section_contract(section_name)
    example_json = json.dumps(
        _build_final_section_example(section_name),
        ensure_ascii=False,
        indent=2,
    )
    return "\n\n".join(
        [
            "[FINAL SECTION JSON SCHEMA REFERENCE - FOR JSON OUTPUT STAGES]",
            (
                "When a stage asks for the final structured section payload, the valid top-level "
                "JSON object must follow the schema below exactly."
            ),
            "Schema key explanations:",
            '- "title": string. Use the canonical section title exactly as required for this page.',
            (
                '- "section_blocks": object. Maps each required heading key to an array of block '
                "objects. Every required heading key must be present."
            ),
            _render_required_heading_key_explanations(section_name),
            "Block object key explanations:",
            (
                '- "kind": string enum. Allowed values are exactly: "paragraph", "bullet", '
                '"labeled_bullet", "numbered_item".'
            ),
            (
                '- "text": string. Human-readable analytical content for the block. Do not put '
                "markdown headings inside this text."
            ),
            (
                '- "label": string. Use this key only when kind == "labeled_bullet". '
                'Omit "label" for all other block kinds.'
            ),
            "Hard constraints:",
            f'- "title" must equal "{contract.title}".',
            '- "section_blocks" must be a JSON object, not an array and not a string.',
            "- Every required heading key must appear exactly once.",
            "- Each heading value must be an array of JSON objects.",
            "- Do not emit unsupported block kinds.",
            "- Do not emit extra top-level keys.",
            "Valid example JSON:",
            example_json,
        ]
    )


def _instruction_block(section_name: str) -> str:
    contract = get_section_contract(section_name)
    heading_lines = "\n".join(f"- {heading}" for heading in contract.headings)
    analysis_dimensions = "\n".join(
        f"- {dimension}" for dimension in contract.analytical_dimensions
    )
    grounding_requirements = "\n".join(
        f"- {requirement}" for requirement in contract.grounding_requirements
    )
    uncertainty_requirements = "\n".join(
        f"- {requirement}" for requirement in contract.uncertainty_requirements
    )
    prohibited_behaviors = "\n".join(f"- {behavior}" for behavior in contract.prohibited_behaviors)
    return "\n".join(
        [
            f"[TASK: {section_name}]",
            _json_only_stage_notice(),
            "Produce deep technical analysis for this section.",
            f"Page purpose: {contract.purpose}",
            "Required analytical dimensions:",
            analysis_dimensions,
            "Required grounding behavior:",
            grounding_requirements,
            "Required uncertainty behavior:",
            uncertainty_requirements,
            f"Mismatch analysis expectation: {contract.mismatch_expectation}.",
            "Prohibited behaviors:",
            prohibited_behaviors,
            "Use this exact internal structure with H2 headings:",
            heading_lines,
            "Repository scan facts are authoritative for code/system facts.",
            "Authoritative repository/code evidence must be treated as source of truth.",
            "External reference chunks are supporting explanatory context only.",
            "Do NOT invent files, modules, APIs, tests, or runtime behavior.",
            "Separate observed evidence statements from inferred explanations.",
            (
                "Label inference clearly (for example using wording like "
                "'Inference:' or 'Interpretation:') when moving beyond direct evidence."
            ),
            (
                "Reference influence should use grounded external-reference "
                "context only when present."
            ),
            (
                "When relevant, perform mismatch analysis between docs/reference claims and "
                "repository implementation signals."
            ),
            "Every major claim should identify concrete supporting evidence in prose.",
            "If evidence is insufficient, explicitly say so.",
        ]
    )


def _render_grounded_chunks_block(selection: SelectedGrounding) -> str:
    if not selection.selected_chunk_count:
        return ""

    selected_bundle = GroundedContextBundle(
        chunks=list(selection.selected_chunks),
        discovered_source_count=len(selection.selected_source_files),
    )
    rendered_chunks = render_methodology_chunks_for_prompt(
        selected_bundle,
        max_chunks=selection.selected_chunk_count,
        max_chars_per_chunk=selection.budget.max_chars_per_chunk,
    )
    chunk_id_lines = "\n".join(
        f"- chunk_{idx}_id: {chunk.chunk_id} (source={chunk.document_relative_path})"
        for idx, chunk in enumerate(selection.selected_chunks, start=1)
    )
    return "\n\n".join(
        [
            (
                "[SUPPORTING EXTERNAL REFERENCE EVIDENCE - GROUNDED CHUNKS]\n"
                f"selected_chunks: {selection.selected_chunk_count}\n"
                f"selected_total_chars: {selection.selected_total_chars}\n"
                f"budget_max_chunks: {selection.budget.max_chunks}\n"
                f"budget_max_total_chars: {selection.budget.max_total_chars}\n"
                f"budget_max_chars_per_chunk: {selection.budget.max_chars_per_chunk}"
            ),
            "[REFERENCE CHUNK IDS]\n" + chunk_id_lines,
            rendered_chunks,
        ]
    )


def _render_route_material_block(
    route: str, materials: list[RouteLLMMaterial] | None, *, max_items: int = 10
) -> str:
    selected = [item for item in (materials or []) if item.route == route][:max_items]
    if not selected:
        return ""
    lines = [
        "[ROUTE-SPECIFIC SOURCE MATERIAL - AUTHORITATIVE FOR THIS ALIGNMENT ROUTE]",
        f"route: {route}",
        f"selected_items: {len(selected)}",
    ]
    for idx, item in enumerate(selected, start=1):
        lines.extend(
            [
                f"## route_item_{idx}",
                f"source_path: {item.source_path}",
                f"section_hint: {item.section_hint}",
                item.excerpt,
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def build_overview_prompt(
    manifest: RepoManifest,
    theory_sources: list[TheorySource],
    grounded_bundle: GroundedContextBundle | None = None,
    code_facts_bundle: CodeFactsBundle | None = None,
) -> str:
    selection = select_grounded_chunks_for_section("overview", grounded_bundle)
    parts = [
        _instruction_block("overview"),
        _render_repo_facts(manifest),
        _render_authoritative_repo_evidence("overview", manifest),
        _render_theory_context(theory_sources),
        _render_code_facts_block("overview", code_facts_bundle),
        _render_final_output_schema_block("overview"),
    ]
    grounded = _render_grounded_chunks_block(selection)
    if grounded:
        parts.append(grounded)
    return "\n\n".join(parts)


def build_architecture_prompt(
    manifest: RepoManifest,
    theory_sources: list[TheorySource],
    grounded_bundle: GroundedContextBundle | None = None,
    code_facts_bundle: CodeFactsBundle | None = None,
) -> str:
    selection = select_grounded_chunks_for_section("architecture", grounded_bundle)
    parts = [
        _instruction_block("architecture"),
        "Focus on repository structure and responsibility boundaries visible from evidence.",
        _render_repo_facts(manifest),
        _render_authoritative_repo_evidence("architecture", manifest),
        _render_theory_context(theory_sources),
        _render_code_facts_block("architecture", code_facts_bundle),
        _render_final_output_schema_block("architecture"),
    ]
    grounded = _render_grounded_chunks_block(selection)
    if grounded:
        parts.append(grounded)
    return "\n\n".join(parts)


def build_theory_alignment_prompt(
    manifest: RepoManifest,
    theory_sources: list[TheorySource],
    grounded_bundle: GroundedContextBundle | None = None,
    code_facts_bundle: CodeFactsBundle | None = None,
) -> str:
    selection = select_grounded_chunks_for_section("theory_alignment", grounded_bundle)
    parts = [
        _instruction_block("theory_alignment"),
        "Highlight where alignment is clear versus where evidence is missing.",
        _render_repo_facts(manifest),
        _render_authoritative_repo_evidence("theory_alignment", manifest),
        _render_theory_context(theory_sources),
        _render_code_facts_block("theory_alignment", code_facts_bundle),
        _render_final_output_schema_block("theory_alignment"),
    ]
    grounded = _render_grounded_chunks_block(selection)
    if grounded:
        parts.append(grounded)
    return "\n\n".join(parts)


def build_reference_alignment_prompt(
    manifest: RepoManifest,
    theory_sources: list[TheorySource],
    grounded_bundle: GroundedContextBundle | None = None,
    code_facts_bundle: CodeFactsBundle | None = None,
    route_materials: list[RouteLLMMaterial] | None = None,
) -> str:
    selection = select_grounded_chunks_for_section("reference_alignment", grounded_bundle)
    parts = [
        _instruction_block("reference_alignment"),
        "Focus on supported/partially-supported/missing-evidence/contradicted reference claims.",
        "Allowed statuses: supported, partially_supported, missing_evidence, contradicted.",
        "Use only provided deterministic evidence IDs and do not invent evidence.",
        "Advisory mapping must stay conservative when no valid deterministic evidence ID applies.",
        _render_repo_facts(manifest),
        _render_authoritative_repo_evidence("reference_alignment", manifest),
        _render_theory_context(theory_sources),
        _render_code_facts_block("reference_alignment", code_facts_bundle),
        _render_final_output_schema_block("reference_alignment"),
    ]
    grounded = _render_grounded_chunks_block(selection)
    if grounded:
        parts.append(grounded)
    route_material_block = _render_route_material_block(
        "general_reference_alignment", route_materials
    )
    if route_material_block:
        parts.append(route_material_block)
    return "\n\n".join(parts)


def build_agent_instruction_alignment_prompt(
    manifest: RepoManifest,
    theory_sources: list[TheorySource],
    grounded_bundle: GroundedContextBundle | None = None,
    code_facts_bundle: CodeFactsBundle | None = None,
    route_materials: list[RouteLLMMaterial] | None = None,
) -> str:
    selection = select_grounded_chunks_for_section("agent_instruction_alignment", grounded_bundle)
    parts = [
        _instruction_block("agent_instruction_alignment"),
        "Classify instructions as verifiable vs out_of_scope_or_non_verifiable.",
        (
            "Allowed statuses: supported, partially_supported, not_evidenced, "
            "contradicted, out_of_scope_or_non_verifiable."
        ),
        "Use only provided deterministic evidence IDs and do not invent evidence.",
        "Advisory mapping must stay conservative when no valid deterministic evidence ID applies.",
        _render_repo_facts(manifest),
        _render_authoritative_repo_evidence("agent_instruction_alignment", manifest),
        _render_theory_context(theory_sources),
        _render_code_facts_block("agent_instruction_alignment", code_facts_bundle),
        _render_final_output_schema_block("agent_instruction_alignment"),
    ]
    grounded = _render_grounded_chunks_block(selection)
    if grounded:
        parts.append(grounded)
    route_material_block = _render_route_material_block(
        "agent_instruction_alignment", route_materials
    )
    if route_material_block:
        parts.append(route_material_block)
    return "\n\n".join(parts)


def build_readme_claim_alignment_prompt(
    manifest: RepoManifest,
    theory_sources: list[TheorySource],
    grounded_bundle: GroundedContextBundle | None = None,
    code_facts_bundle: CodeFactsBundle | None = None,
    route_materials: list[RouteLLMMaterial] | None = None,
) -> str:
    selection = select_grounded_chunks_for_section("readme_claim_alignment", grounded_bundle)
    parts = [
        _instruction_block("readme_claim_alignment"),
        (
            "Use not_statically_verifiable when static evidence cannot reliably validate "
            "README claims."
        ),
        (
            "Allowed statuses: supported, partially_supported, not_evidenced, "
            "contradicted, not_statically_verifiable."
        ),
        "Use only provided deterministic evidence IDs and do not invent evidence.",
        "Advisory mapping must stay conservative when no valid deterministic evidence ID applies.",
        _render_repo_facts(manifest),
        _render_authoritative_repo_evidence("readme_claim_alignment", manifest),
        _render_theory_context(theory_sources),
        _render_code_facts_block("readme_claim_alignment", code_facts_bundle),
        _render_final_output_schema_block("readme_claim_alignment"),
    ]
    grounded = _render_grounded_chunks_block(selection)
    if grounded:
        parts.append(grounded)
    route_material_block = _render_route_material_block("readme_claim_alignment", route_materials)
    if route_material_block:
        parts.append(route_material_block)
    return "\n\n".join(parts)


def build_code_structure_prompt(
    manifest: RepoManifest,
    theory_sources: list[TheorySource],
    grounded_bundle: GroundedContextBundle | None = None,
    code_facts_bundle: CodeFactsBundle | None = None,
) -> str:
    selection = select_grounded_chunks_for_section("code_structure", grounded_bundle)
    parts = [
        _instruction_block("code_structure"),
        "Focus on observed module inventory and structural grouping evidence.",
        _render_repo_facts(manifest),
        _render_authoritative_repo_evidence("code_structure", manifest),
        _render_theory_context(theory_sources),
        _render_code_facts_block("code_structure", code_facts_bundle),
        _render_final_output_schema_block("code_structure"),
    ]
    grounded = _render_grounded_chunks_block(selection)
    if grounded:
        parts.append(grounded)
    return "\n\n".join(parts)


def build_runtime_entrypoints_prompt(
    manifest: RepoManifest,
    theory_sources: list[TheorySource],
    grounded_bundle: GroundedContextBundle | None = None,
    code_facts_bundle: CodeFactsBundle | None = None,
) -> str:
    selection = select_grounded_chunks_for_section("runtime_entrypoints", grounded_bundle)
    parts = [
        _instruction_block("runtime_entrypoints"),
        "Focus on entrypoint detection evidence and invocation caveats.",
        _render_repo_facts(manifest),
        _render_authoritative_repo_evidence("runtime_entrypoints", manifest),
        _render_theory_context(theory_sources),
        _render_code_facts_block("runtime_entrypoints", code_facts_bundle),
        _render_final_output_schema_block("runtime_entrypoints"),
    ]
    grounded = _render_grounded_chunks_block(selection)
    if grounded:
        parts.append(grounded)
    return "\n\n".join(parts)


def render_prompt_grounding_debug_markdown(
    grounded_bundle: GroundedContextBundle | None,
    manifest: RepoManifest | None = None,
    code_facts_bundle: CodeFactsBundle | None = None,
) -> str:
    """Render deterministic per-section evidence-selection debug information."""

    lines = [
        "# Prompt Grounding Debug",
        "",
        "Deterministic prompt evidence selection summary per section.",
        "",
        "Repository/code evidence is authoritative. External chunks are supporting context.",
        "",
    ]

    for section_name in (
        "overview",
        "architecture",
        "code_structure",
        "runtime_entrypoints",
        "reference_alignment",
        "agent_instruction_alignment",
        "readme_claim_alignment",
        "theory_alignment",
    ):
        selection = select_grounded_chunks_for_section(section_name, grounded_bundle)
        selected_code = select_code_facts_for_section(section_name, code_facts_bundle)
        repo_items = 0
        repo_sources: list[str] = []
        if manifest is not None:
            selected_repo_evidence = _select_authoritative_repo_evidence(section_name, manifest)
            repo_items = len(selected_repo_evidence)
            repo_sources = sorted({item.relative_path for item in selected_repo_evidence})

        lines.extend(
            [
                f"## {section_name}",
                "",
                "### Evidence categories",
                "",
                "- authoritative_repository_text",
                "- authoritative_code_facts",
                "- supporting_external_reference_chunks",
                "",
                "### Budgets",
                "",
                (
                    "- external_chunk_budget: "
                    f"max_chunks={selection.budget.max_chunks}, "
                    f"max_total_chars={selection.budget.max_total_chars}, "
                    f"max_chars_per_chunk={selection.budget.max_chars_per_chunk}"
                ),
                (
                    "- code_facts_budget: "
                    f"max_modules={len(selected_code.modules)}, "
                    f"max_symbols={len(selected_code.symbols)}, "
                    f"max_import_edges={len(selected_code.imports)}, "
                    f"max_entrypoints={len(selected_code.detected_entrypoints)}, "
                    f"max_excerpts={len(selected_code.code_excerpts)}"
                ),
                "",
                "### Selected authoritative repository evidence",
                "",
                f"- selected_items: {repo_items}",
                (
                    "- selected_sources: "
                    + (", ".join(sorted(repo_sources)) if repo_sources else "None")
                ),
                "",
                "### Selected authoritative code evidence",
                "",
                f"- modules: {len(selected_code.modules)}",
                f"- symbols: {len(selected_code.symbols)}",
                f"- imports: {len(selected_code.imports)}",
                f"- entrypoints: {len(selected_code.detected_entrypoints)}",
                f"- code_excerpts: {len(selected_code.code_excerpts)}",
                (
                    "- code_sources: "
                    + (
                        ", ".join(
                            sorted({module.relative_path for module in selected_code.modules})
                        )
                        if selected_code.modules
                        else "None"
                    )
                ),
                "",
                "### Selected supporting external chunks",
                "",
                f"- selected_chunks: {selection.selected_chunk_count}",
                f"- selected_total_chars: {selection.selected_total_chars}",
                (
                    "- selected_source_files: "
                    + (
                        ", ".join(selection.selected_source_files)
                        if selection.selected_source_files
                        else "None"
                    )
                ),
                "",
                "Chunk previews:",
            ]
        )
        if not selection.selected_chunks:
            lines.extend(["- None", ""])
            continue

        for idx, chunk in enumerate(selection.selected_chunks, start=1):
            chunk_id = chunk.chunk_id
            section_hint = chunk.section_hint or "(none)"
            lines.append(f"- {idx}. {chunk_id} (section_hint={section_hint})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
