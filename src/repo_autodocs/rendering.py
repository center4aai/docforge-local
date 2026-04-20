"""Deterministic rendering helpers for structured generated section pages."""

from __future__ import annotations

from dataclasses import dataclass

from repo_autodocs.structured_output import (
    SectionBlock,
    StructuredDiagnostic,
    collapse_exact_duplicate_diagnostics,
    summarize_diagnostics,
)


@dataclass(frozen=True, slots=True)
class SectionContract:
    """Stable markdown analysis contract for a generated LLM section page."""

    title: str
    purpose: str
    analytical_dimensions: tuple[str, ...]
    grounding_requirements: tuple[str, ...]
    uncertainty_requirements: tuple[str, ...]
    mismatch_expectation: str
    prohibited_behaviors: tuple[str, ...]
    headings: tuple[str, ...]


SECTION_CONTRACTS: dict[str, SectionContract] = {
    "overview": SectionContract(
        title="Overview",
        purpose=(
            "Explain what the project appears to be by combining deterministic repository "
            "evidence with cautious technical interpretation."
        ),
        analytical_dimensions=(
            "project identity and scope signals",
            "major subsystem surfaces",
            "observable implications for maintainers/operators",
        ),
        grounding_requirements=(
            "Anchor observations to concrete repository/code evidence such as file paths, "
            "module names, symbols, tests, or entrypoints.",
            "Keep observed evidence separate from interpretive inferences.",
        ),
        uncertainty_requirements=(
            "State confidence limits and explicitly call out missing evidence.",
            "Mark inferences as hypotheses when evidence is partial.",
        ),
        mismatch_expectation="optional",
        prohibited_behaviors=(
            "Inventing repository facts, files, APIs, modules, or runtime behavior.",
            "Presenting inference as directly observed evidence.",
        ),
        headings=(
            "Observed Repository Evidence",
            "Analytical Interpretation",
            "Subsystem Surfaces and Implications",
            "Uncertainty and Evidence Limits",
            "Potential Mismatches",
        ),
    ),
    "architecture": SectionContract(
        title="Architecture",
        purpose=(
            "Analyze structural organization, responsibility boundaries, and integration signals "
            "grounded in deterministic repository/code evidence."
        ),
        analytical_dimensions=(
            "component and module boundaries",
            "responsibility allocation",
            "integration pathways and architectural implications",
        ),
        grounding_requirements=(
            "Tie architecture claims to concrete code evidence (modules, imports, signatures, "
            "entrypoints, config, and tests when relevant).",
            "Separate what is observed from inferred boundary/interaction interpretation.",
        ),
        uncertainty_requirements=(
            "Explicitly note uncertain boundaries and unknown runtime behavior.",
            "Identify where the repository lacks enough evidence for a confident "
            "architectural claim.",
        ),
        mismatch_expectation="conditional",
        prohibited_behaviors=(
            "Claiming runtime/deployment behavior that is not evidenced.",
            "Flattening all modules into a single undifferentiated summary.",
        ),
        headings=(
            "Observed Structural Evidence",
            "Component Boundaries and Responsibilities",
            "Integration Signals and Architectural Implications",
            "Uncertainty and Missing Evidence",
            "Documented vs Implemented Mismatches",
        ),
    ),
    "theory_alignment": SectionContract(
        title="Theory Alignment",
        purpose=(
            "Evaluate how external/reference theory aligns or diverges from observed repository "
            "and code evidence."
        ),
        analytical_dimensions=(
            "areas of alignment between reference materials and implementation evidence",
            "areas of divergence or contradiction",
            "missing implementation evidence for theoretical claims",
        ),
        grounding_requirements=(
            "Reference both concrete repository/code evidence and grounded external "
            "chunk/source identities.",
            "Separate observed evidence statements from interpretive alignment conclusions.",
        ),
        uncertainty_requirements=(
            "State when evidence is insufficient to confirm or reject a theoretical claim.",
            "Flag ambiguous mapping between theory terms and code artifacts.",
        ),
        mismatch_expectation="required",
        prohibited_behaviors=(
            "Treating external reference claims as implementation facts without code evidence.",
            "Declaring full alignment when key claims lack repository evidence.",
        ),
        headings=(
            "Observed Evidence From Repository and References",
            "Alignment Analysis",
            "Mismatch and Divergence Analysis",
            "Missing Evidence and Open Questions",
            "Confidence and Uncertainty Statement",
        ),
    ),
    "code_structure": SectionContract(
        title="Code Structure",
        purpose=(
            "Describe repository code organization from deterministic "
            "module/symbol/import evidence, "
            "explicitly separating observed structure from interpretation."
        ),
        analytical_dimensions=(
            "module/package inventory and organization patterns",
            "representative symbols and import/dependency signals",
            "tests and quality-surface coverage signals",
        ),
        grounding_requirements=(
            "Ground structural claims in module lists, symbols, imports, excerpts, "
            "and test evidence.",
            "Distinguish direct observations from inferred architectural interpretation.",
        ),
        uncertainty_requirements=(
            "Flag uncertain structural boundaries and missing module context.",
            "Call out where inferred organization exceeds direct evidence.",
        ),
        mismatch_expectation="conditional",
        prohibited_behaviors=(
            "Inventing modules, symbols, dependencies, or test coverage.",
            "Treating inferred layering as directly observed fact.",
        ),
        headings=(
            "Observed Module and Package Inventory",
            "Observed Symbol and Dependency Signals",
            "Interpretation of Structural Grouping",
            "Tests and Quality Surface Signals",
            "Uncertainty and Evidence Limits",
        ),
    ),
    "runtime_entrypoints": SectionContract(
        title="Runtime Entrypoints",
        purpose=(
            "Analyze detected runtime/CLI surfaces and invocation evidence without speculating "
            "beyond deterministic entrypoint and code-facts signals."
        ),
        analytical_dimensions=(
            "detected entrypoint surfaces and invocation patterns",
            "framework/runtime hints and control-surface cues",
            "operational caveats and unknown runtime behavior",
        ),
        grounding_requirements=(
            "Prioritize deterministic entrypoint evidence, module facts, and code excerpts.",
            "Treat runtime behavior as unknown unless directly evidenced.",
        ),
        uncertainty_requirements=(
            "Explicitly note missing startup/runtime flow evidence.",
            "Identify assumptions as hypotheses when invocation semantics are incomplete.",
        ),
        mismatch_expectation="conditional",
        prohibited_behaviors=(
            "Inventing commands, flags, APIs, or runtime topology.",
            "Claiming runtime behavior that is not anchored in explicit entrypoint evidence.",
        ),
        headings=(
            "Detected Entrypoint Evidence",
            "Invocation and Framework Signals",
            "Interpretation of Runtime Surfaces",
            "Operational Caveats and Unknowns",
            "Uncertainty and Evidence Limits",
        ),
    ),
    "reference_alignment": SectionContract(
        title="Reference Alignment",
        purpose="Evaluate general external reference claims against implementation evidence.",
        analytical_dimensions=(
            "supported claims",
            "partial support",
            "missing evidence or contradiction",
        ),
        grounding_requirements=(
            "Use authoritative repository/code evidence for verdicting.",
            "Reference grounded source/chunk identities when available.",
        ),
        uncertainty_requirements=("Call out uncertain mappings explicitly.",),
        mismatch_expectation="required",
        prohibited_behaviors=("Treating reference text as implementation truth without evidence.",),
        headings=(
            "Observed Evidence",
            "Supported and Partially Supported Claims",
            "Missing Evidence and Contradictions",
            "Route Verdict Summary",
            "Confidence and Uncertainty",
        ),
    ),
    "agent_instruction_alignment": SectionContract(
        title="Agent Instruction Alignment",
        purpose="Evaluate AI-agent instruction claims against implementation evidence.",
        analytical_dimensions=("verifiable claims", "out-of-scope instructions", "mismatches"),
        grounding_requirements=(
            "Only verifiable implementation claims should be evidence-mapped.",
        ),
        uncertainty_requirements=(
            "Mark process/style guidance as out_of_scope_or_non_verifiable.",
        ),
        mismatch_expectation="required",
        prohibited_behaviors=("Treating style/process advice as code behavior.",),
        headings=(
            "Observed Instruction Evidence",
            "Verifiable Instruction Claims",
            "Out-of-Scope or Non-Verifiable Instructions",
            "Mismatch and Not-Evidenced Findings",
            "Confidence and Uncertainty",
        ),
    ),
    "readme_claim_alignment": SectionContract(
        title="README Claim Alignment",
        purpose="Evaluate README claims against deterministic implementation evidence.",
        analytical_dimensions=(
            "supported claims",
            "contradictions",
            "not statically verifiable claims",
        ),
        grounding_requirements=("Use deterministic implementation evidence only.",),
        uncertainty_requirements=("Use not_statically_verifiable where appropriate.",),
        mismatch_expectation="required",
        prohibited_behaviors=("Claiming runtime guarantees from static evidence alone.",),
        headings=(
            "Observed README Evidence",
            "Supported and Partially Supported Claims",
            "Not Evidenced or Contradicted Claims",
            "Not Statically Verifiable Claims",
            "Confidence and Uncertainty",
        ),
    ),
}


def get_section_contract(section_name: str) -> SectionContract:
    """Return the section contract for a known section name."""

    return SECTION_CONTRACTS[section_name]


def render_structured_section_page(
    section_name: str,
    section_blocks: dict[str, tuple[SectionBlock, ...]],
    provenance_note: str,
    diagnostics: tuple[StructuredDiagnostic, ...] = (),
) -> str:
    """Render a section page with deterministic title, provenance, and stable headings."""

    contract = get_section_contract(section_name)
    lines = [f"# {contract.title}", "", provenance_note, ""]

    if diagnostics:
        lines.extend(_render_diagnostics(diagnostics))

    for heading in contract.headings:
        lines.extend([f"## {heading}", ""])
        blocks = section_blocks.get(heading, ())
        if not blocks:
            lines.extend(["_Content unavailable after validation._", ""])
            continue
        lines.extend(_render_blocks(blocks))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_diagnostics(diagnostics: tuple[StructuredDiagnostic, ...]) -> list[str]:
    summary = summarize_diagnostics(diagnostics)
    pattern_lines = [
        f"- `{item.code}` ({item.severity.value}/{item.stage}): {item.count}"
        for item in summary["patterns"][:5]
    ]
    stage_counts = ", ".join(f"{k}={v}" for k, v in summary["by_stage"].items())
    severity_counts = ", ".join(f"{k}={v}" for k, v in summary["by_severity"].items())

    lines = ["## Structured Output Diagnostics", "", "### Summary", ""]
    lines.append(f"- Total diagnostics: {summary['total']}")
    lines.append(f"- Severity counts: {severity_counts or 'none'}")
    lines.append(f"- Stage counts: {stage_counts or 'none'}")
    lines.append("- Top diagnostic patterns:")
    if pattern_lines:
        lines.extend(pattern_lines)
    else:
        lines.append("  - none")
    lines.extend(
        [
            "",
            "<details>",
            "<summary>Open structured output diagnostic details</summary>",
            "",
            "### Detailed events",
            "",
        ]
    )
    for item, count in collapse_exact_duplicate_diagnostics(diagnostics):
        parts = [
            f"- **{item.severity.value.upper()}** `{item.code}` ({item.stage})",
            f"  - Summary: {item.summary}",
            f"  - Detail: {item.detail}",
        ]
        if item.operation_ref:
            parts.append(f"  - Operation ref: {item.operation_ref}")
        if item.location_ref:
            parts.append(f"  - Location ref: {item.location_ref}")
        if count > 1:
            parts.append(f"  - Exact duplicate count: {count}")
        lines.extend(parts)
    lines.extend(["", "</details>", ""])
    return lines


def _render_blocks(blocks: tuple[SectionBlock, ...]) -> list[str]:
    lines: list[str] = []
    ordered_number = 1
    for block in blocks:
        if block.kind == "paragraph":
            lines.extend([block.text, ""])
            continue
        if block.kind == "bullet":
            lines.append(f"- {block.text}")
            continue
        if block.kind == "labeled_bullet":
            lines.append(f"- **{block.label}:** {block.text}")
            continue
        if block.kind == "numbered_item":
            lines.append(f"{ordered_number}. {block.text}")
            ordered_number += 1
            continue
        lines.extend([block.text, ""])
    if lines and lines[-1] != "":
        lines.append("")
    return lines
