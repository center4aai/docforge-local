import json
from pathlib import Path

from repo_autodocs.models import (
    CodeFactsBundle,
    GroundedContextBundle,
    RepoManifest,
    RouteLLMMaterial,
)
from repo_autodocs.orchestration import (
    mapping_status_instruction_for_section,
    orchestrate_llm_section,
)
from repo_autodocs.rendering import get_section_contract


class FakeLLMClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._notes_calls = 0

    def generate_text(
        self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
    ) -> str:
        if "[STAGE: overview:notes]" in user_prompt:
            self._notes_calls += 1
            self.calls.append("overview:notes")
            if self._notes_calls == 1:
                return "short"
            return json.dumps(
                {
                    "notes_markdown": "- OBS: repo has CLI surface\n- UNCERTAINTY: runtime unclear",
                    "observations": ["repo has CLI surface"],
                    "uncertainty_flags": ["runtime unclear"],
                }
            )

        if "[STAGE: overview:final" in user_prompt:
            self.calls.append("overview:final")
            contract = get_section_contract("overview")
            return json.dumps(
                {
                    "title": contract.title,
                    "section_blocks": {
                        heading: [{"kind": "bullet", "text": f"synthesized {idx}"}]
                        for idx, heading in enumerate(contract.headings, start=1)
                    },
                }
            )

        if "[STAGE: architecture:notes]" in user_prompt:
            self.calls.append("architecture:notes")
            return json.dumps(
                {
                    "observations": ["modules suggest boundaries"],
                    "uncertainty_flags": ["integration depth uncertain"],
                }
            )

        if "[STAGE: architecture:final" in user_prompt:
            self.calls.append("architecture:final")
            contract = get_section_contract("architecture")
            return json.dumps(
                {
                    "section_blocks": {
                        heading: [{"kind": "bullet", "text": "architecture detail"}]
                        for heading in contract.headings
                    }
                }
            )

        if "[STAGE: code_structure:notes]" in user_prompt:
            self.calls.append("code_structure:notes")
            return json.dumps(
                {"notes_markdown": "- OBS: module inventory visible", "observations": ["modules"]}
            )

        if "[STAGE: code_structure:final" in user_prompt:
            self.calls.append("code_structure:final")
            contract = get_section_contract("code_structure")
            return json.dumps(
                {
                    "section_blocks": {
                        heading: [{"kind": "paragraph", "text": "structured code facts"}]
                        for heading in contract.headings
                    }
                }
            )

        if "[STAGE: runtime_entrypoints:notes]" in user_prompt:
            self.calls.append("runtime_entrypoints:notes")
            return json.dumps(
                {"notes_markdown": "- OBS: cli entrypoint", "observations": ["entrypoints"]}
            )

        if "[STAGE: runtime_entrypoints:final" in user_prompt:
            self.calls.append("runtime_entrypoints:final")
            contract = get_section_contract("runtime_entrypoints")
            return json.dumps(
                {
                    "section_blocks": {
                        heading: [{"kind": "bullet", "text": "runtime evidence"}]
                        for heading in contract.headings
                    }
                }
            )

        if "[STAGE: theory_alignment:notes]" in user_prompt:
            self.calls.append("theory_alignment:notes")
            return json.dumps(
                {
                    "notes_markdown": "- OBS: refs mention constraints",
                    "observations": ["refs mention constraints"],
                    "uncertainty_flags": ["some claims unmapped"],
                }
            )

        if "[STAGE: theory_alignment:reference-notes]" in user_prompt:
            self.calls.append("theory_alignment:reference-notes")
            return "- claim: explicit interfaces expected"

        if "[STAGE: theory_alignment:code-notes]" in user_prompt:
            self.calls.append("theory_alignment:code-notes")
            return "- anchor: src/repo_autodocs/cli.py exposes commands"

        if "[STAGE: theory_alignment:mapping]" in user_prompt:
            self.calls.append("theory_alignment:mapping")
            return json.dumps(
                {
                    "entries": [
                        {
                            "reference_claim": "explicit interfaces expected",
                            "code_anchor": "cli command surface",
                            "status": "partially_supported",
                            "evidence_note": "commands are explicit but contracts are evolving",
                            "uncertainty_note": "some interfaces are implicit",
                        }
                    ]
                }
            )

        if "[STAGE: theory_alignment:final" in user_prompt:
            self.calls.append("theory_alignment:final")
            contract = get_section_contract("theory_alignment")
            return json.dumps(
                {
                    "section_blocks": {
                        heading: [{"kind": "bullet", "text": "alignment synthesis"}]
                        for heading in contract.headings
                    }
                }
            )

        raise AssertionError(f"Unexpected prompt: {user_prompt[:120]}")


def _manifest() -> RepoManifest:
    return RepoManifest(project_root=Path("/tmp/repo"), top_level_directories=["src"])


def test_overview_orchestration_is_multi_step_and_retries_empty_notes() -> None:
    client = FakeLLMClient()

    result = orchestrate_llm_section(
        section_name="overview",
        client=client,
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
    )

    assert "overview:notes" in client.calls
    assert client.calls.count("overview:notes") == 2
    assert "overview:final" in client.calls
    assert result.notes.observations
    assert "# Overview" in result.final_markdown


def test_section_plans_are_section_aware_and_theory_alignment_has_mapping_stage() -> None:
    client = FakeLLMClient()

    architecture = orchestrate_llm_section(
        section_name="architecture",
        client=client,
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
    )
    theory = orchestrate_llm_section(
        section_name="theory_alignment",
        client=client,
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
    )

    assert architecture.mapping is None
    assert theory.mapping is not None
    assert len(theory.mapping.entries) == 1
    assert theory.mapping.entries[0].status == "missing_evidence"
    assert "theory_alignment:mapping" in theory.stages_run
    assert "architecture:final" in architecture.stages_run


def test_stage4_new_sections_orchestrate_successfully() -> None:
    client = FakeLLMClient()
    code_structure = orchestrate_llm_section(
        section_name="code_structure",
        client=client,
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
    )
    runtime = orchestrate_llm_section(
        section_name="runtime_entrypoints",
        client=client,
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
    )

    assert "code_structure:final" in code_structure.stages_run
    assert "runtime_entrypoints:final" in runtime.stages_run
    assert "# Code Structure" in code_structure.final_markdown
    assert "# Runtime Entrypoints" in runtime.final_markdown


def test_theory_alignment_mapping_has_fallback_when_entries_are_unparseable() -> None:
    class MappingFailClient(FakeLLMClient):
        def generate_text(
            self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
        ) -> str:
            if "[STAGE: theory_alignment:mapping]" in user_prompt:
                return "no structured mapping lines"
            return super().generate_text(system_prompt=system_prompt, user_prompt=user_prompt)

    result = orchestrate_llm_section(
        section_name="theory_alignment",
        client=MappingFailClient(),
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
    )

    assert result.mapping is not None
    assert result.mapping.entries[0].status == "missing_evidence"


def test_final_markdown_is_rendered_with_contract_headings() -> None:
    result = orchestrate_llm_section(
        section_name="architecture",
        client=FakeLLMClient(),
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
    )

    contract = get_section_contract("architecture")
    for heading in contract.headings:
        assert f"## {heading}" in result.final_markdown


def test_routed_alignment_prompt_includes_route_specific_material() -> None:
    class CaptureClient(FakeLLMClient):
        captured_prompt = ""

        def generate_text(
            self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
        ) -> str:
            if "[STAGE: readme_claim_alignment:notes]" in user_prompt:
                self.captured_prompt = user_prompt
                return json.dumps(
                    {
                        "notes_markdown": "- OBS: readme source included",
                        "observations": ["readme route evidence"],
                        "uncertainty_flags": [],
                    }
                )
            if "[STAGE: readme_claim_alignment:final" in user_prompt:
                contract = get_section_contract("readme_claim_alignment")
                return json.dumps(
                    {
                        "title": contract.title,
                        "section_blocks": {
                            heading: [{"kind": "paragraph", "text": "ok"}]
                            for heading in contract.headings
                        },
                    }
                )
            if "[STAGE: readme_claim_alignment:reference-notes]" in user_prompt:
                return "- claim: readme workflow"
            if "[STAGE: readme_claim_alignment:code-notes]" in user_prompt:
                return "- anchor: cli generate-docs command"
            if "[STAGE: readme_claim_alignment:mapping]" in user_prompt:
                return json.dumps(
                    {
                        "entries": [
                            {
                                "reference_claim": "readme workflow",
                                "code_anchor": "generate-docs command",
                                "status": "supported",
                                "evidence_note": "known command",
                                "uncertainty_note": "",
                            }
                        ]
                    }
                )
            return super().generate_text(system_prompt=system_prompt, user_prompt=user_prompt)

    client = CaptureClient()
    orchestrate_llm_section(
        section_name="readme_claim_alignment",
        client=client,
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
        route_materials=[
            RouteLLMMaterial(
                route="readme_claim_alignment",
                source_path="README.md",
                section_hint="Usage",
                excerpt="Use docforge-local generate-docs --project-root /repo.",
            )
        ],
    )

    assert (
        "[ROUTE-SPECIFIC SOURCE MATERIAL - AUTHORITATIVE FOR THIS ALIGNMENT ROUTE]"
        in client.captured_prompt
    )
    assert "source_path: README.md" in client.captured_prompt


def test_final_synthesis_preserves_partial_useful_structured_output() -> None:
    class PartialClient(FakeLLMClient):
        def generate_text(
            self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
        ) -> str:
            if "[STAGE: overview:final" in user_prompt:
                return json.dumps(
                    {
                        "sections": [
                            {"heading": "unknown section", "body": "kept useful body"},
                            {
                                "heading": "Observed Repository Evidence",
                                "blocks": [
                                    {
                                        "kind": "labeled_bullet",
                                        "label": "Evidence",
                                        "text": "known mapped body",
                                    }
                                ],
                            },
                            {
                                "heading": "Analytical Interpretation",
                                "blocks": [{"kind": "paragraph", "text": "known mapped body"}],
                            },
                        ]
                    }
                )
            return super().generate_text(system_prompt=system_prompt, user_prompt=user_prompt)

    result = orchestrate_llm_section(
        section_name="overview",
        client=PartialClient(),
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
    )

    assert "kept useful body" in result.final_markdown
    assert "Structured Output Diagnostics" in result.final_markdown


def test_notes_repair_includes_base_prompt_and_previous_invalid_response() -> None:
    class NotesRepairClient:
        def __init__(self) -> None:
            self.repair_prompt = ""

        def generate_text(
            self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
        ) -> str:
            if "[STAGE: overview:notes]" in user_prompt:
                return "{}"
            if "[STAGE: overview:notes-repair]" in user_prompt:
                self.repair_prompt = user_prompt
                return json.dumps(
                    {
                        "notes_markdown": "- repaired notes",
                        "observations": ["obs"],
                        "uncertainty_flags": [],
                    }
                )
            if "[STAGE: overview:final" in user_prompt:
                contract = get_section_contract("overview")
                return json.dumps(
                    {
                        "section_blocks": {
                            heading: [{"kind": "paragraph", "text": "ok"}]
                            for heading in contract.headings
                        }
                    }
                )
            raise AssertionError(f"Unexpected prompt: {user_prompt[:120]}")

    client = NotesRepairClient()
    orchestrate_llm_section(
        section_name="overview",
        client=client,
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
    )

    assert "[REPOSITORY FACTS - DETERMINISTIC SCAN - AUTHORITATIVE]" in client.repair_prompt
    assert "[PREVIOUS INVALID RESPONSE]" in client.repair_prompt
    assert "{}" in client.repair_prompt


def test_final_repair_includes_previous_output_and_intermediate_context() -> None:
    class FinalRepairClient:
        def __init__(self) -> None:
            self.final_repair_prompt = ""

        def generate_text(
            self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
        ) -> str:
            if "[STAGE: theory_alignment:notes]" in user_prompt:
                return json.dumps(
                    {
                        "notes_markdown": "- notes",
                        "observations": ["obs"],
                        "uncertainty_flags": ["uncertain"],
                    }
                )
            if "[STAGE: theory_alignment:reference-notes]" in user_prompt:
                return "- ref claim"
            if "[STAGE: theory_alignment:code-notes]" in user_prompt:
                return "- code anchor"
            if "[STAGE: theory_alignment:mapping]" in user_prompt:
                return json.dumps(
                    {
                        "reference_notes": "- ref claim",
                        "code_notes": "- code anchor",
                        "entries": [],
                    }
                )
            if "[STAGE: theory_alignment:final-repair]" in user_prompt:
                self.final_repair_prompt = user_prompt
                contract = get_section_contract("theory_alignment")
                return json.dumps(
                    {
                        "section_blocks": {
                            heading: [{"kind": "paragraph", "text": "repaired"}]
                            for heading in contract.headings
                        }
                    }
                )
            if "[STAGE: theory_alignment:final]" in user_prompt:
                return json.dumps(
                    {"section_blocks": {"wrong heading": [{"kind": "paragraph", "text": "bad"}]}}
                )
            raise AssertionError(f"Unexpected prompt: {user_prompt[:120]}")

    client = FinalRepairClient()
    orchestrate_llm_section(
        section_name="theory_alignment",
        client=client,
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
    )

    assert "[PREVIOUS INVALID RESPONSE]" in client.final_repair_prompt
    assert "wrong heading" in client.final_repair_prompt
    assert "[INTERMEDIATE ANALYTICAL NOTES]" in client.final_repair_prompt
    assert "[INTERMEDIATE MAPPING CONTEXT]" in client.final_repair_prompt
    assert "[OUTPUT CONTRACT: theory_alignment:final-repair]" in client.final_repair_prompt
    assert "[FINAL SECTION JSON SCHEMA]" in client.final_repair_prompt
    assert "Required keys inside section_blocks:" in client.final_repair_prompt
    assert "Block object keys:" in client.final_repair_prompt
    assert "Valid example JSON:" in client.final_repair_prompt


def test_orchestration_includes_language_directive_for_ru() -> None:
    class DirectiveClient(FakeLLMClient):
        def __init__(self) -> None:
            super().__init__()
            self.final_prompt = ""

        def generate_text(
            self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
        ) -> str:
            if "[STAGE: overview:final]" in user_prompt:
                self.final_prompt = user_prompt
                contract = get_section_contract("overview")
                return json.dumps(
                    {
                        "title": contract.title,
                        "section_blocks": {
                            heading: [{"kind": "paragraph", "text": "Это текст на русском."}]
                            for heading in contract.headings
                        },
                    }
                )
            return super().generate_text(system_prompt=system_prompt, user_prompt=user_prompt)

    client = DirectiveClient()
    orchestrate_llm_section(
        section_name="overview",
        client=client,
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
        generated_text_language="ru",
    )

    assert "Language directive: generate Russian prose for block text only." in client.final_prompt


def test_ru_language_repair_path_keeps_schema_and_applies_warning() -> None:
    class RepairClient:
        def __init__(self) -> None:
            self.repair_prompt = ""

        def generate_text(
            self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
        ) -> str:
            contract = get_section_contract("overview")
            if "[STAGE: overview:notes]" in user_prompt:
                return json.dumps({"notes_markdown": "- OBS: test", "observations": ["x"]})
            if "[STAGE: overview:final]" in user_prompt:
                return json.dumps(
                    {
                        "section_blocks": {
                            heading: [{"kind": "paragraph", "text": "This is English prose."}]
                            for heading in contract.headings
                        }
                    }
                )
            if "[STAGE: overview:language-repair]" in user_prompt:
                self.repair_prompt = user_prompt
                return json.dumps(
                    {
                        "section_blocks": {
                            heading: [{"kind": "paragraph", "text": "Это русский текст."}]
                            for heading in contract.headings
                        }
                    }
                )
            raise AssertionError(f"Unexpected prompt: {user_prompt[:120]}")

    client = RepairClient()
    result = orchestrate_llm_section(
        section_name="overview",
        client=client,
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
        generated_text_language="ru",
    )

    assert "# Overview" in result.final_markdown
    assert "Это русский текст." in result.final_markdown
    assert "Russian language repair pass applied" in result.final_markdown
    assert '"kind": "paragraph"' in client.repair_prompt
    assert "'kind': 'paragraph'" not in client.repair_prompt


def test_en_path_remains_backward_compatible_without_repair_warning() -> None:
    result = orchestrate_llm_section(
        section_name="overview",
        client=FakeLLMClient(),
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
        generated_text_language="en",
    )
    assert "Applied Russian language repair pass." not in result.final_markdown


def test_mapping_status_instruction_is_route_specific() -> None:
    assert (
        mapping_status_instruction_for_section("reference_alignment")
        == "supported, partially_supported, missing_evidence, contradicted"
    )
    assert (
        mapping_status_instruction_for_section("agent_instruction_alignment")
        == "supported, partially_supported, not_evidenced, contradicted, "
        "out_of_scope_or_non_verifiable"
    )
    assert (
        mapping_status_instruction_for_section("readme_claim_alignment")
        == "supported, partially_supported, not_evidenced, contradicted, "
        "not_statically_verifiable"
    )


def test_mapping_stage_prompt_enforces_route_specific_statuses() -> None:
    class CaptureMappingClient(FakeLLMClient):
        def __init__(self) -> None:
            super().__init__()
            self.mapping_prompt = ""

        def generate_text(
            self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
        ) -> str:
            if "[STAGE: readme_claim_alignment:notes]" in user_prompt:
                return json.dumps(
                    {"notes_markdown": "- OBS: x", "observations": ["x"], "uncertainty_flags": []}
                )
            if "[STAGE: readme_claim_alignment:reference-notes]" in user_prompt:
                return "- claim"
            if "[STAGE: readme_claim_alignment:code-notes]" in user_prompt:
                return "- anchor"
            if "[STAGE: readme_claim_alignment:mapping]" in user_prompt:
                self.mapping_prompt = user_prompt
                return json.dumps(
                    {
                        "entries": [
                            {
                                "reference_claim": "claim",
                                "code_anchor": "anchor",
                                "status": "not_statically_verifiable",
                                "evidence_note": "x",
                                "uncertainty_note": "",
                            }
                        ]
                    }
                )
            if "[STAGE: readme_claim_alignment:final]" in user_prompt:
                contract = get_section_contract("readme_claim_alignment")
                return json.dumps(
                    {
                        "section_blocks": {
                            heading: [{"kind": "paragraph", "text": "ok"}]
                            for heading in contract.headings
                        }
                    }
                )
            return super().generate_text(system_prompt=system_prompt, user_prompt=user_prompt)

    client = CaptureMappingClient()
    orchestrate_llm_section(
        section_name="readme_claim_alignment",
        client=client,
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
    )
    assert "Allowed status enum for this section:" in client.mapping_prompt
    assert "not_statically_verifiable" in client.mapping_prompt
    assert "missing_evidence" not in client.mapping_prompt


def test_routed_mapping_prompt_mentions_evidence_id_constraints() -> None:
    class CaptureClient(FakeLLMClient):
        prompt = ""

        def generate_text(
            self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
        ) -> str:
            if "[STAGE: reference_alignment:mapping]" in user_prompt:
                self.prompt = user_prompt
                return json.dumps(
                    {
                        "entries": [
                            {
                                "reference_claim": "claim",
                                "code_anchor": "anchor",
                                "status": "supported",
                                "evidence_note": "cli_subcommand:generate-docs",
                                "uncertainty_note": "",
                            }
                        ]
                    }
                )
            if "[STAGE: reference_alignment:notes]" in user_prompt:
                return json.dumps(
                    {"notes_markdown": "- OBS: x", "observations": ["x"], "uncertainty_flags": []}
                )
            if "[STAGE: reference_alignment:reference-notes]" in user_prompt:
                return "- claim"
            if "[STAGE: reference_alignment:code-notes]" in user_prompt:
                return "- anchor"
            if "[STAGE: reference_alignment:final" in user_prompt:
                contract = get_section_contract("reference_alignment")
                return json.dumps(
                    {
                        "title": contract.title,
                        "section_blocks": {
                            h: [{"kind": "paragraph", "text": "ok"}] for h in contract.headings
                        },
                    }
                )
            return super().generate_text(system_prompt=system_prompt, user_prompt=user_prompt)

    client = CaptureClient()
    orchestrate_llm_section(
        section_name="reference_alignment",
        client=client,
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
        route_materials=[
            RouteLLMMaterial(
                route="general_reference_alignment",
                source_path="deterministic_alignment_pack",
                section_hint="Deterministic claim/evidence pack",
                excerpt='{"deterministic_verdicts":[{"evidence_note":"evidence_ids=cli_subcommand:generate-docs"}]}',
            )
        ],
    )
    assert "Do not invent evidence IDs" in client.prompt
    assert "Allowed status enum for this section" in client.prompt


def test_unknown_evidence_ids_are_sanitized_from_mapping_output() -> None:
    class UnknownEvidenceClient(FakeLLMClient):
        def generate_text(
            self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
        ) -> str:
            if "[STAGE: reference_alignment:notes]" in user_prompt:
                return json.dumps(
                    {"notes_markdown": "- OBS: x", "observations": ["x"], "uncertainty_flags": []}
                )
            if "[STAGE: reference_alignment:reference-notes]" in user_prompt:
                return "- claim"
            if "[STAGE: reference_alignment:code-notes]" in user_prompt:
                return "- anchor"
            if "[STAGE: reference_alignment:mapping]" in user_prompt:
                return json.dumps(
                    {
                        "entries": [
                            {
                                "reference_claim": "claim",
                                "code_anchor": "anchor",
                                "status": "supported",
                                "evidence_note": "unknown_kind:foo",
                                "uncertainty_note": "",
                            }
                        ]
                    }
                )
            if "[STAGE: reference_alignment:final" in user_prompt:
                contract = get_section_contract("reference_alignment")
                return json.dumps(
                    {
                        "title": contract.title,
                        "section_blocks": {
                            h: [{"kind": "paragraph", "text": "ok"}] for h in contract.headings
                        },
                    }
                )
            return super().generate_text(system_prompt=system_prompt, user_prompt=user_prompt)

    result = orchestrate_llm_section(
        section_name="reference_alignment",
        client=UnknownEvidenceClient(),
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
        route_materials=[
            RouteLLMMaterial(
                route="general_reference_alignment",
                source_path="deterministic_alignment_pack",
                section_hint="Deterministic claim/evidence pack",
                excerpt="evidence_ids=cli_subcommand:generate-docs",
            )
        ],
    )
    assert result.mapping is not None
    assert "unknown_kind:foo" not in result.mapping.entries[0].evidence_note
    assert result.mapping.entries[0].status == "missing_evidence"
    assert any(
        diag.code == "mapping.no_valid_ids_status_downgraded"
        and "status transitioned supported -> missing_evidence" in diag.detail
        for diag in result.mapping.diagnostics
    )
    assert any(
        diag.code == "mapping.unknown_evidence_ids_dropped" and "unknown_kind:foo" in diag.detail
        for diag in result.mapping.diagnostics
    )


def test_mapping_uses_allowed_ids_from_structured_alignment_pack_not_note_format() -> None:
    class StructuredAllowedIdsClient(FakeLLMClient):
        def generate_text(
            self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
        ) -> str:
            if "[STAGE: reference_alignment:notes]" in user_prompt:
                return json.dumps(
                    {"notes_markdown": "- OBS: x", "observations": ["x"], "uncertainty_flags": []}
                )
            if "[STAGE: reference_alignment:reference-notes]" in user_prompt:
                return "- claim"
            if "[STAGE: reference_alignment:code-notes]" in user_prompt:
                return "- anchor"
            if "[STAGE: reference_alignment:mapping]" in user_prompt:
                return json.dumps(
                    {
                        "entries": [
                            {
                                "reference_claim": "claim",
                                "code_anchor": "anchor",
                                "status": "supported",
                                "evidence_note": "cli_subcommand:generate-docs",
                                "uncertainty_note": "",
                            }
                        ]
                    }
                )
            if "[STAGE: reference_alignment:final" in user_prompt:
                contract = get_section_contract("reference_alignment")
                return json.dumps(
                    {
                        "title": contract.title,
                        "section_blocks": {
                            h: [{"kind": "paragraph", "text": "ok"}] for h in contract.headings
                        },
                    }
                )
            return super().generate_text(system_prompt=system_prompt, user_prompt=user_prompt)

    result = orchestrate_llm_section(
        section_name="reference_alignment",
        client=StructuredAllowedIdsClient(),
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
        route_materials=[
            RouteLLMMaterial(
                route="general_reference_alignment",
                source_path="deterministic_alignment_pack",
                section_hint="Deterministic claim/evidence pack",
                excerpt=json.dumps(
                    {
                        "allowed_evidence_ids": ["cli_subcommand:generate-docs"],
                        "deterministic_verdicts": [
                            {
                                "claim_text": "claim",
                                "status": "supported",
                                "evidence_note": "free text",
                            }
                        ],
                    }
                ),
            )
        ],
    )
    assert result.mapping is not None
    assert result.mapping.entries[0].status == "supported"
    assert not any(
        diag.code == "mapping.no_valid_ids_status_downgraded" for diag in result.mapping.diagnostics
    )


def test_mapping_diagnostic_summary_counts_and_contextual_details_are_preserved() -> None:
    class MultiEntryClient(FakeLLMClient):
        def generate_text(
            self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
        ) -> str:
            if "[STAGE: reference_alignment:notes]" in user_prompt:
                return json.dumps(
                    {"notes_markdown": "- OBS: x", "observations": ["x"], "uncertainty_flags": []}
                )
            if "[STAGE: reference_alignment:reference-notes]" in user_prompt:
                return "- claim"
            if "[STAGE: reference_alignment:code-notes]" in user_prompt:
                return "- anchor"
            if "[STAGE: reference_alignment:mapping]" in user_prompt:
                return json.dumps(
                    {
                        "entries": [
                            {
                                "reference_claim": "claim 1",
                                "code_anchor": "anchor 1",
                                "status": "supported",
                                "evidence_note": "unknown_kind:first",
                                "uncertainty_note": "",
                            },
                            {
                                "reference_claim": "claim 2",
                                "code_anchor": "anchor 2",
                                "status": "supported",
                                "evidence_note": "unknown_kind:second",
                                "uncertainty_note": "",
                            },
                        ]
                    }
                )
            if "[STAGE: reference_alignment:final" in user_prompt:
                contract = get_section_contract("reference_alignment")
                return json.dumps(
                    {
                        "title": contract.title,
                        "section_blocks": {
                            h: [{"kind": "paragraph", "text": "ok"}] for h in contract.headings
                        },
                    }
                )
            return super().generate_text(system_prompt=system_prompt, user_prompt=user_prompt)

    result = orchestrate_llm_section(
        section_name="reference_alignment",
        client=MultiEntryClient(),
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
        route_materials=[
            RouteLLMMaterial(
                route="general_reference_alignment",
                source_path="deterministic_alignment_pack",
                section_hint="Deterministic claim/evidence pack",
                excerpt=json.dumps({"allowed_evidence_ids": ["cli_subcommand:generate-docs"]}),
            )
        ],
    )

    assert "Total diagnostics:" in result.final_markdown
    assert "mapping.unknown_evidence_ids_dropped" in result.final_markdown
    assert "mapping.no_valid_ids_status_downgraded" in result.final_markdown
    assert "entry:0" in result.final_markdown
    assert "entry:1" in result.final_markdown


def test_no_fallback_retained_diagnostic_for_fallback_status_without_valid_ids() -> None:
    class AlreadyFallbackClient(FakeLLMClient):
        def generate_text(
            self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
        ) -> str:
            if "[STAGE: readme_claim_alignment:notes]" in user_prompt:
                return json.dumps(
                    {"notes_markdown": "- OBS: x", "observations": ["x"], "uncertainty_flags": []}
                )
            if "[STAGE: readme_claim_alignment:reference-notes]" in user_prompt:
                return "- claim"
            if "[STAGE: readme_claim_alignment:code-notes]" in user_prompt:
                return "- anchor"
            if "[STAGE: readme_claim_alignment:mapping]" in user_prompt:
                return json.dumps(
                    {
                        "entries": [
                            {
                                "reference_claim": "claim",
                                "code_anchor": "anchor",
                                "status": "not_evidenced",
                                "evidence_note": "fake:missing",
                                "uncertainty_note": "",
                            }
                        ]
                    }
                )
            if "[STAGE: readme_claim_alignment:final" in user_prompt:
                contract = get_section_contract("readme_claim_alignment")
                return json.dumps(
                    {
                        "title": contract.title,
                        "section_blocks": {
                            h: [{"kind": "paragraph", "text": "ok"}] for h in contract.headings
                        },
                    }
                )
            return super().generate_text(system_prompt=system_prompt, user_prompt=user_prompt)

    result = orchestrate_llm_section(
        section_name="readme_claim_alignment",
        client=AlreadyFallbackClient(),
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
        route_materials=[
            RouteLLMMaterial(
                route="readme_claim_alignment",
                source_path="deterministic_alignment_pack",
                section_hint="Deterministic claim/evidence pack",
                excerpt=json.dumps({"allowed_evidence_ids": ["cli_subcommand:generate-docs"]}),
            )
        ],
    )

    assert result.mapping is not None
    assert result.mapping.entries[0].status == "not_evidenced"
    assert not any(
        diag.code == "mapping.no_valid_ids_fallback_retained" for diag in result.mapping.diagnostics
    )
    assert any(
        diag.code == "mapping.unknown_evidence_ids_dropped" for diag in result.mapping.diagnostics
    )


def test_mapping_entries_without_valid_ids_downgrade_even_for_contradicted_status() -> None:
    class UnsupportedContradictionClient(FakeLLMClient):
        def generate_text(
            self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
        ) -> str:
            if "[STAGE: readme_claim_alignment:notes]" in user_prompt:
                return json.dumps(
                    {"notes_markdown": "- OBS: x", "observations": ["x"], "uncertainty_flags": []}
                )
            if "[STAGE: readme_claim_alignment:reference-notes]" in user_prompt:
                return "- claim"
            if "[STAGE: readme_claim_alignment:code-notes]" in user_prompt:
                return "- anchor"
            if "[STAGE: readme_claim_alignment:mapping]" in user_prompt:
                return json.dumps(
                    {
                        "entries": [
                            {
                                "reference_claim": "claim",
                                "code_anchor": "anchor",
                                "status": "contradicted",
                                "evidence_note": "fake:missing",
                                "uncertainty_note": "",
                            }
                        ]
                    }
                )
            if "[STAGE: readme_claim_alignment:final" in user_prompt:
                contract = get_section_contract("readme_claim_alignment")
                return json.dumps(
                    {
                        "title": contract.title,
                        "section_blocks": {
                            h: [{"kind": "paragraph", "text": "ok"}] for h in contract.headings
                        },
                    }
                )
            return super().generate_text(system_prompt=system_prompt, user_prompt=user_prompt)

    result = orchestrate_llm_section(
        section_name="readme_claim_alignment",
        client=UnsupportedContradictionClient(),
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
        route_materials=[
            RouteLLMMaterial(
                route="readme_claim_alignment",
                source_path="deterministic_alignment_pack",
                section_hint="Deterministic claim/evidence pack",
                excerpt=json.dumps({"allowed_evidence_ids": ["cli_subcommand:generate-docs"]}),
            )
        ],
    )
    assert result.mapping is not None
    assert result.mapping.entries[0].status == "not_evidenced"


def test_deterministic_contradiction_status_is_not_overridden() -> None:
    class ContradictionClient(FakeLLMClient):
        def generate_text(
            self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
        ) -> str:
            if "[STAGE: reference_alignment:notes]" in user_prompt:
                return json.dumps(
                    {"notes_markdown": "- OBS: x", "observations": ["x"], "uncertainty_flags": []}
                )
            if "[STAGE: reference_alignment:reference-notes]" in user_prompt:
                return "- made-up-command claim"
            if "[STAGE: reference_alignment:code-notes]" in user_prompt:
                return "- anchor"
            if "[STAGE: reference_alignment:mapping]" in user_prompt:
                return json.dumps(
                    {
                        "entries": [
                            {
                                "reference_claim": "made-up-command claim",
                                "code_anchor": "anchor",
                                "status": "supported",
                                "evidence_note": "cli_subcommand:generate-docs",
                                "uncertainty_note": "",
                            }
                        ]
                    }
                )
            if "[STAGE: reference_alignment:final" in user_prompt:
                contract = get_section_contract("reference_alignment")
                return json.dumps(
                    {
                        "title": contract.title,
                        "section_blocks": {
                            h: [{"kind": "paragraph", "text": "ok"}] for h in contract.headings
                        },
                    }
                )
            return super().generate_text(system_prompt=system_prompt, user_prompt=user_prompt)

    result = orchestrate_llm_section(
        section_name="reference_alignment",
        client=ContradictionClient(),
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
        route_materials=[
            RouteLLMMaterial(
                route="general_reference_alignment",
                source_path="deterministic_alignment_pack",
                section_hint="Deterministic claim/evidence pack",
                excerpt=(
                    '{"deterministic_verdicts":[{"claim_text":"made-up-command claim",'
                    '"status":"contradicted",'
                    '"evidence_note":"evidence_ids=cli_subcommand:generate-docs"}]}'
                ),
            )
        ],
    )
    assert result.mapping is not None
    assert result.mapping.entries[0].status == "contradicted"
    assert any(
        diag.code == "mapping.deterministic_contradiction_preserved"
        for diag in result.mapping.diagnostics
    )
