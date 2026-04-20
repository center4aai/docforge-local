import json

from repo_autodocs.rendering import get_section_contract
from repo_autodocs.structured_output import (
    DiagnosticSeverity,
    collapse_exact_duplicate_diagnostics,
    group_diagnostics_for_summary,
    parse_alignment_mapping_output,
    parse_final_section_output,
    parse_theory_mapping_output,
    summarize_diagnostics,
)


def test_theory_mapping_structured_parsing_and_status_normalization() -> None:
    parsed = parse_theory_mapping_output(
        json.dumps(
            {
                "entries": [
                    {
                        "reference_claim": "claim",
                        "code_anchor": "anchor",
                        "status": "unsupported_status",
                        "evidence_note": "note",
                        "uncertainty_note": "uncertain",
                    }
                ]
            }
        )
    )

    assert parsed.entries[0].status == "missing_evidence"


def test_route_aware_fallback_status_for_non_json_mapping_output() -> None:
    parsed = parse_alignment_mapping_output("agent_instruction_alignment", "not-json")
    assert parsed.entries[0].status == "not_evidenced"


def test_route_aware_status_normalization_uses_section_allowed_values() -> None:
    parsed = parse_alignment_mapping_output(
        "readme_claim_alignment",
        json.dumps(
            {
                "entries": [
                    {
                        "reference_claim": "claim",
                        "code_anchor": "anchor",
                        "status": "missing_evidence",
                    }
                ]
            }
        ),
    )
    assert parsed.entries[0].status == "not_evidenced"


def test_reference_alignment_fallback_can_use_missing_evidence() -> None:
    parsed = parse_alignment_mapping_output("reference_alignment", "not-json")
    assert parsed.entries[0].status == "missing_evidence"


def test_agent_and_readme_fallback_never_inject_missing_evidence() -> None:
    agent = parse_alignment_mapping_output(
        "agent_instruction_alignment",
        json.dumps(
            {
                "entries": [
                    {"reference_claim": "x", "code_anchor": "y", "status": "missing_evidence"}
                ]
            }
        ),
    )
    readme = parse_alignment_mapping_output(
        "readme_claim_alignment",
        json.dumps(
            {
                "entries": [
                    {"reference_claim": "x", "code_anchor": "y", "status": "missing_evidence"}
                ]
            }
        ),
    )
    assert agent.entries[0].status == "not_evidenced"
    assert readme.entries[0].status == "not_evidenced"


def test_final_section_output_parses_typed_block_schema() -> None:
    contract = get_section_contract("architecture")
    payload = parse_final_section_output(
        section_name="architecture",
        raw_text=json.dumps(
            {
                "section_blocks": {
                    contract.headings[0]: [
                        {"kind": "paragraph", "text": "p"},
                        {"kind": "bullet", "text": "b"},
                        {"kind": "labeled_bullet", "label": "Evidence", "text": "lb"},
                        {"kind": "numbered_item", "text": "n"},
                    ]
                }
            }
        ),
        section_title=contract.title,
        required_headings=contract.headings,
    )

    blocks = payload.section_blocks[contract.headings[0]]
    assert [block.kind for block in blocks] == [
        "paragraph",
        "bullet",
        "labeled_bullet",
        "numbered_item",
    ]


def test_final_section_output_legacy_section_bodies_becomes_paragraph_blocks() -> None:
    contract = get_section_contract("overview")
    payload = parse_final_section_output(
        section_name="overview",
        raw_text=json.dumps({"section_bodies": {contract.headings[0]: "legacy body"}}),
        section_title=contract.title,
        required_headings=contract.headings,
    )

    assert payload.section_blocks[contract.headings[0]][0].kind == "paragraph"
    assert payload.section_blocks[contract.headings[0]][0].text == "legacy body"


def test_final_section_output_recovers_unknown_sections_into_missing_slots() -> None:
    contract = get_section_contract("architecture")
    payload = parse_final_section_output(
        section_name="architecture",
        raw_text=json.dumps(
            {
                "sections": [
                    {"heading": "random", "body": "useful body"},
                    {"heading": contract.headings[1], "body": "exact body"},
                ]
            }
        ),
        section_title=contract.title,
        required_headings=contract.headings,
    )

    assert payload.section_blocks[contract.headings[0]][0].text == "useful body"
    assert payload.section_blocks[contract.headings[1]][0].text == "exact body"
    assert payload.diagnostics


def test_final_section_output_normalizes_invalid_blocks_with_warnings() -> None:
    contract = get_section_contract("runtime_entrypoints")
    payload = parse_final_section_output(
        section_name="runtime_entrypoints",
        raw_text=json.dumps(
            {
                "section_blocks": {
                    contract.headings[0]: [
                        {"kind": "unknown", "text": "kept"},
                        {"kind": "labeled_bullet", "text": "missing label"},
                        123,
                        {"kind": "bullet", "text": ""},
                    ]
                }
            }
        ),
        section_title=contract.title,
        required_headings=contract.headings,
    )

    blocks = payload.section_blocks[contract.headings[0]]
    assert blocks[0].kind == "paragraph"
    assert blocks[0].text == "kept"
    assert blocks[1].kind == "labeled_bullet"
    assert blocks[1].label == "Note"
    assert payload.diagnostics
    assert any(
        d.code == "final_output.unsupported_block_kind_normalized" for d in payload.diagnostics
    )
    assert any(
        d.code == "final_output.labeled_bullet_missing_label_normalized"
        for d in payload.diagnostics
    )
    assert any(d.code == "final_output.non_object_block_dropped" for d in payload.diagnostics)
    assert any(d.code == "final_output.empty_block_dropped" for d in payload.diagnostics)


def test_notes_non_json_recovery_emits_structured_diagnostic() -> None:
    from repo_autodocs.structured_output import parse_section_notes_output

    notes = parse_section_notes_output("overview", "- OBS: alpha\n- UNCERTAINTY: beta")

    assert notes.diagnostics
    diag = notes.diagnostics[0]
    assert diag.code == "notes.non_json_recovered_from_bullets"
    assert diag.stage == "notes"
    assert diag.severity == DiagnosticSeverity.WARNING


def test_diagnostic_aggregation_keeps_contextual_entries_distinct() -> None:
    contract = get_section_contract("overview")
    payload = parse_final_section_output(
        section_name="overview",
        raw_text=json.dumps(
            {
                "section_blocks": {
                    contract.headings[0]: [
                        {"kind": "unknown", "text": "a"},
                        {"kind": "unknown", "text": "b"},
                    ]
                }
            }
        ),
        section_title=contract.title,
        required_headings=contract.headings,
    )
    collapsed = collapse_exact_duplicate_diagnostics(payload.diagnostics)
    summary = summarize_diagnostics(payload.diagnostics)
    grouped = group_diagnostics_for_summary(payload.diagnostics)

    assert len(collapsed) == 2
    assert all(count == 1 for _, count in collapsed)
    assert summary["total"] >= 2
    assert grouped[0].code == "final_output.unsupported_block_kind_normalized"
