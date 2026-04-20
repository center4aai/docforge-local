from repo_autodocs.rendering import render_structured_section_page
from repo_autodocs.structured_output import DiagnosticSeverity, SectionBlock, StructuredDiagnostic


def test_render_structured_section_page_preserves_missing_slots() -> None:
    rendered = render_structured_section_page(
        section_name="overview",
        section_blocks={
            "Observed Repository Evidence": (SectionBlock(kind="bullet", text="grounded fact"),)
        },
        provenance_note="> **Provenance note**\n> - test",
        diagnostics=(
            StructuredDiagnostic(
                code="final_output.unsupported_block_kind_normalized",
                severity=DiagnosticSeverity.WARNING,
                stage="final_parse",
                summary="Unsupported block kind was normalized",
                detail="Normalized block kind from unknown to paragraph.",
                operation_ref="block:0",
                location_ref="overview:Observed Repository Evidence",
            ),
            StructuredDiagnostic(
                code="final_output.unsupported_block_kind_normalized",
                severity=DiagnosticSeverity.WARNING,
                stage="final_parse",
                summary="Unsupported block kind was normalized",
                detail="Normalized block kind from unknown to paragraph.",
                operation_ref="block:0",
                location_ref="overview:Observed Repository Evidence",
            ),
            StructuredDiagnostic(
                code="final_output.unsupported_block_kind_normalized",
                severity=DiagnosticSeverity.WARNING,
                stage="final_parse",
                summary="Unsupported block kind was normalized",
                detail="Normalized block kind from invalid-x to paragraph.",
                operation_ref="block:1",
                location_ref="overview:Observed Repository Evidence",
            ),
        ),
    )

    assert rendered.startswith("# Overview")
    assert "## Structured Output Diagnostics" in rendered
    assert "### Summary" in rendered
    assert "<details>" in rendered
    assert "Open structured output diagnostic details" in rendered
    assert "Exact duplicate count: 2" in rendered
    assert "block:1" in rendered
    assert "## Observed Repository Evidence" in rendered
    assert "## Observed Repository Evidence\n\n- grounded fact" in rendered
    assert rendered.count("_Content unavailable after validation._") == 4


def test_render_structured_section_page_renders_all_block_kinds_deterministically() -> None:
    rendered = render_structured_section_page(
        section_name="runtime_entrypoints",
        section_blocks={
            "Detected Entrypoint Evidence": (
                SectionBlock(kind="paragraph", text="Paragraph."),
                SectionBlock(kind="bullet", text="Bullet."),
                SectionBlock(kind="labeled_bullet", label="Evidence", text="Labeled."),
                SectionBlock(kind="numbered_item", text="First"),
                SectionBlock(kind="numbered_item", text="Second"),
            )
        },
        provenance_note="> **Provenance note**\n> - test",
    )

    assert "Paragraph." in rendered
    assert "- Bullet." in rendered
    assert "- **Evidence:** Labeled." in rendered
    assert "1. First" in rendered
    assert "2. Second" in rendered
