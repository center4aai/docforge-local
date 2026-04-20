from pathlib import Path

from repo_autodocs.models import (
    CodeFactsBundle,
    GroundedContextBundle,
    MethodologyChunk,
    PythonModuleInfo,
    PythonSymbolInfo,
    RepoManifest,
    RepositoryTextEvidence,
    RouteLLMMaterial,
    TheorySource,
)
from repo_autodocs.prompts import (
    SECTION_GROUNDING_BUDGETS,
    build_agent_instruction_alignment_prompt,
    build_architecture_prompt,
    build_code_structure_prompt,
    build_overview_prompt,
    build_readme_claim_alignment_prompt,
    build_reference_alignment_prompt,
    build_runtime_entrypoints_prompt,
    build_theory_alignment_prompt,
    render_prompt_grounding_debug_markdown,
    select_grounded_chunks_for_section,
)
from repo_autodocs.rendering import get_section_contract


def _manifest() -> RepoManifest:
    return RepoManifest(
        project_root=Path("/tmp/repo"),
        top_level_directories=["docs", "src", "tests"],
        top_level_files=["pyproject.toml", "mkdocs.yml"],
        has_pyproject=True,
        has_mkdocs_config=True,
        has_docs_dir=True,
        has_src_dir=True,
        has_tests_dir=True,
        textual_evidence=[
            RepositoryTextEvidence(
                category="readme",
                relative_path="README.md",
                excerpt="# Repo\nA CLI tool.",
                line_count=2,
            ),
            RepositoryTextEvidence(
                category="package_config",
                relative_path="pyproject.toml",
                excerpt="[project]\nname='repo'",
                line_count=2,
            ),
            RepositoryTextEvidence(
                category="test_file",
                relative_path="tests/test_cli.py",
                excerpt="def test_cli():\n    assert True",
                line_count=2,
            ),
        ],
    )


def _theory_sources() -> list[TheorySource]:
    return [
        TheorySource(
            path=Path("/tmp/repo/docs/context/methodology/README.md"),
            relative_path="README.md",
            extension=".md",
            size_bytes=120,
        )
    ]


def _bundle() -> GroundedContextBundle:
    return GroundedContextBundle(
        chunks=[
            MethodologyChunk(
                chunk_id="README.md:0:aaa111",
                document_relative_path="README.md",
                index=0,
                text="Intro and definitions.",
                char_count=22,
                section_hint="Intro",
            ),
            MethodologyChunk(
                chunk_id="README.md:1:bbb222",
                document_relative_path="README.md",
                index=1,
                text="Architecture interpretation details and component boundaries.",
                char_count=58,
                section_hint="Architecture",
            ),
            MethodologyChunk(
                chunk_id="README.md:2:ccc333",
                document_relative_path="README.md",
                index=2,
                text="Theory assumptions and mismatch handling.",
                char_count=40,
                section_hint="Theory Alignment",
            ),
        ]
    )


def _code_facts_bundle() -> CodeFactsBundle:
    return CodeFactsBundle(
        modules=[
            PythonModuleInfo(
                module_path=Path("/tmp/repo/src/sample/cli.py"),
                relative_path="src/sample/cli.py",
                module_name="sample.cli",
                is_package=False,
                import_count=3,
                defined_class_count=1,
                defined_function_count=2,
                module_importance_score=12,
            ),
            PythonModuleInfo(
                module_path=Path("/tmp/repo/tests/test_cli.py"),
                relative_path="tests/test_cli.py",
                module_name="tests.test_cli",
                is_package=False,
                import_count=1,
                defined_class_count=0,
                defined_function_count=1,
                is_test_module=True,
                module_importance_score=2,
            ),
        ],
        symbols=[
            PythonSymbolInfo(
                symbol_name="run",
                symbol_type="function",
                module_name="sample.cli",
                relative_path="src/sample/cli.py",
                lineno=10,
                signature="run() -> None",
                docstring="Run app.",
                is_public=True,
            )
        ],
        detected_entrypoints=["sample.cli:__main__"],
        framework_hints=["typer"],
    )


def test_prompt_builders_include_authoritative_and_supporting_context() -> None:
    prompts = [
        build_overview_prompt(_manifest(), _theory_sources()),
        build_architecture_prompt(_manifest(), _theory_sources()),
        build_code_structure_prompt(_manifest(), _theory_sources()),
        build_runtime_entrypoints_prompt(_manifest(), _theory_sources()),
        build_reference_alignment_prompt(_manifest(), _theory_sources()),
        build_agent_instruction_alignment_prompt(_manifest(), _theory_sources()),
        build_readme_claim_alignment_prompt(_manifest(), _theory_sources()),
        build_theory_alignment_prompt(_manifest(), _theory_sources()),
    ]

    for prompt in prompts:
        assert "[REPOSITORY FACTS - DETERMINISTIC SCAN - AUTHORITATIVE]" in prompt
        assert "[AUTHORITATIVE REPOSITORY EVIDENCE]" in prompt
        assert "[AUTHORITATIVE CODE FACTS - DETERMINISTIC STRUCTURAL ANALYSIS]" in prompt
        assert "Repository scan facts are authoritative for code/system facts." in prompt
        assert (
            "Authoritative repository/code evidence must be treated as source of truth." in prompt
        )
        assert "External reference chunks are supporting explanatory context only." in prompt
        assert "Do NOT invent files, modules, APIs, tests, or runtime behavior." in prompt
        assert "Use this exact internal structure with H2 headings:" in prompt
        assert "Produce deep technical analysis for this section." in prompt
        assert "Required analytical dimensions:" in prompt
        assert "Required grounding behavior:" in prompt
        assert "Required uncertainty behavior:" in prompt
        assert "Label inference clearly" in prompt
        assert "Every major claim should identify concrete supporting evidence in prose." in prompt
        assert "[SUPPORTING EXTERNAL REFERENCE EVIDENCE - GROUNDED CHUNKS]" not in prompt
        assert "## readme: README.md" not in prompt


def test_prompt_builders_include_hardened_json_schema_contract() -> None:
    prompt = build_overview_prompt(_manifest(), _theory_sources(), _bundle(), _code_facts_bundle())

    assert "[JSON OUTPUT DISCIPLINE FOR SCHEMA-DRIVEN STAGES]" in prompt
    assert "[FINAL SECTION JSON SCHEMA REFERENCE - FOR JSON OUTPUT STAGES]" in prompt
    assert "Schema key explanations:" in prompt
    assert "Required keys inside section_blocks:" in prompt
    assert "Block object key explanations:" in prompt
    assert '- "kind": string enum.' in prompt
    assert '- "text": string.' in prompt
    assert '- "label": string.' in prompt
    assert "Valid example JSON:" in prompt
    assert '"section_blocks"' in prompt


def test_prompt_builders_require_page_specific_mismatch_expectations() -> None:
    overview_prompt = build_overview_prompt(_manifest(), _theory_sources())
    architecture_prompt = build_architecture_prompt(_manifest(), _theory_sources())
    theory_alignment_prompt = build_theory_alignment_prompt(_manifest(), _theory_sources())
    reference_alignment_prompt = build_reference_alignment_prompt(_manifest(), _theory_sources())

    assert "Mismatch analysis expectation: optional." in overview_prompt
    assert "Mismatch analysis expectation: conditional." in architecture_prompt
    assert "Mismatch analysis expectation: required." in theory_alignment_prompt
    assert "Mismatch analysis expectation: required." in reference_alignment_prompt


def test_section_contracts_are_richer_and_differentiated() -> None:
    overview_contract = get_section_contract("overview")
    architecture_contract = get_section_contract("architecture")
    theory_contract = get_section_contract("theory_alignment")
    code_structure_contract = get_section_contract("code_structure")
    runtime_contract = get_section_contract("runtime_entrypoints")
    reference_contract = get_section_contract("reference_alignment")

    assert overview_contract.purpose
    assert overview_contract.analytical_dimensions
    assert overview_contract.grounding_requirements
    assert overview_contract.uncertainty_requirements
    assert overview_contract.mismatch_expectation == "optional"

    assert architecture_contract.mismatch_expectation == "conditional"
    assert theory_contract.mismatch_expectation == "required"
    assert code_structure_contract.mismatch_expectation == "conditional"
    assert runtime_contract.mismatch_expectation == "conditional"
    assert reference_contract.mismatch_expectation == "required"
    assert overview_contract.headings != architecture_contract.headings
    assert architecture_contract.headings != theory_contract.headings
    assert code_structure_contract.headings != runtime_contract.headings


def test_prompt_builders_include_section_specific_grounded_chunks() -> None:
    prompt = build_architecture_prompt(_manifest(), _theory_sources(), _bundle())

    assert "[SUPPORTING EXTERNAL REFERENCE EVIDENCE - GROUNDED CHUNKS]" in prompt
    assert "selected_chunks:" in prompt
    assert "chunk_1_id:" in prompt


def test_route_specific_materials_are_included_for_routed_alignment_prompts() -> None:
    route_materials = [
        RouteLLMMaterial(
            route="agent_instruction_alignment",
            source_path="AGENTS.md",
            section_hint="Workflow",
            excerpt="Use docforge-local generate-docs for main workflow.",
        ),
        RouteLLMMaterial(
            route="readme_claim_alignment",
            source_path="README.md",
            section_hint="Usage",
            excerpt="README claims generated pages include reference_alignment.",
        ),
    ]

    agent_prompt = build_agent_instruction_alignment_prompt(
        _manifest(), _theory_sources(), _bundle(), _code_facts_bundle(), route_materials
    )
    readme_prompt = build_readme_claim_alignment_prompt(
        _manifest(), _theory_sources(), _bundle(), _code_facts_bundle(), route_materials
    )

    assert (
        "[ROUTE-SPECIFIC SOURCE MATERIAL - AUTHORITATIVE FOR THIS ALIGNMENT ROUTE]" in agent_prompt
    )
    assert "source_path: AGENTS.md" in agent_prompt
    assert "section_hint: Workflow" in agent_prompt
    assert "source_path: README.md" in readme_prompt


def test_prompt_builder_includes_selected_code_facts_when_bundle_present() -> None:
    prompt = build_architecture_prompt(
        _manifest(),
        _theory_sources(),
        grounded_bundle=None,
        code_facts_bundle=_code_facts_bundle(),
    )

    assert "framework_hints: typer" in prompt
    assert "sample.cli (src/sample/cli.py" in prompt
    assert "sample.cli:run signature=run() -> None" in prompt


def test_chunk_selection_is_deterministic_and_section_budgets_apply() -> None:
    bundle = GroundedContextBundle(
        chunks=[
            MethodologyChunk(
                chunk_id=f"doc.md:{idx}:id{idx}",
                document_relative_path="doc.md",
                index=idx,
                text=("architecture " if idx % 2 == 0 else "theory ") + ("x" * 450),
                char_count=460,
                section_hint="Architecture" if idx % 2 == 0 else "Theory Alignment",
            )
            for idx in range(12)
        ]
    )

    overview = select_grounded_chunks_for_section("overview", bundle)
    overview_again = select_grounded_chunks_for_section("overview", bundle)
    architecture = select_grounded_chunks_for_section("architecture", bundle)
    theory_alignment = select_grounded_chunks_for_section("theory_alignment", bundle)

    assert overview == overview_again
    assert overview.selected_chunk_count <= SECTION_GROUNDING_BUDGETS["overview"].max_chunks
    assert architecture.selected_chunk_count <= SECTION_GROUNDING_BUDGETS["architecture"].max_chunks
    assert (
        theory_alignment.selected_chunk_count
        <= SECTION_GROUNDING_BUDGETS["theory_alignment"].max_chunks
    )


def test_overview_and_architecture_receive_different_evidence_priority() -> None:
    prompt_overview = build_overview_prompt(
        _manifest(), _theory_sources(), _bundle(), _code_facts_bundle()
    )
    prompt_architecture = build_architecture_prompt(
        _manifest(), _theory_sources(), _bundle(), _code_facts_bundle()
    )

    assert "test_module=True" not in prompt_overview
    assert "test_module=True" in prompt_architecture


def test_prompt_grounding_debug_contains_category_counts_and_sources() -> None:
    markdown = render_prompt_grounding_debug_markdown(
        _bundle(), manifest=_manifest(), code_facts_bundle=_code_facts_bundle()
    )

    assert "### Evidence categories" in markdown
    assert "authoritative_repository_text" in markdown
    assert "### Budgets" in markdown
    assert "### Selected authoritative repository evidence" in markdown
    assert "### Selected supporting external chunks" in markdown
    assert "## code_structure" in markdown
    assert "## runtime_entrypoints" in markdown


def test_prompt_grounding_debug_reports_only_section_selected_repo_sources() -> None:
    markdown = render_prompt_grounding_debug_markdown(
        _bundle(), manifest=_manifest(), code_facts_bundle=_code_facts_bundle()
    )

    overview_block = markdown.split("## overview", maxsplit=1)[1].split(
        "## architecture", maxsplit=1
    )[0]
    assert "selected_items: 2" in overview_block
    assert "selected_sources: pyproject.toml, tests/test_cli.py" in overview_block


def test_authoritative_repo_evidence_never_treats_runtime_config_as_authoritative() -> None:
    manifest = _manifest()
    manifest.textual_evidence.append(
        RepositoryTextEvidence(
            category="runtime_config",
            relative_path="docforge.toml",
            excerpt="[paths]\ndocs_dir='generated-docs'",
            line_count=2,
        )
    )

    prompt = build_overview_prompt(manifest, _theory_sources(), _bundle(), _code_facts_bundle())
    debug_markdown = render_prompt_grounding_debug_markdown(
        _bundle(), manifest=manifest, code_facts_bundle=_code_facts_bundle()
    )

    assert "## runtime_config: docforge.toml" not in prompt
    assert "docforge.toml" not in debug_markdown


def test_prompt_grounding_debug_code_sources_are_deterministically_sorted() -> None:
    markdown = render_prompt_grounding_debug_markdown(
        _bundle(), manifest=_manifest(), code_facts_bundle=_code_facts_bundle()
    )

    assert "code_sources: src/sample/cli.py, tests/test_cli.py" in markdown


def test_routed_alignment_prompts_include_status_contract_and_no_invent_evidence() -> None:
    reference_prompt = build_reference_alignment_prompt(_manifest(), _theory_sources())
    agent_prompt = build_agent_instruction_alignment_prompt(_manifest(), _theory_sources())
    readme_prompt = build_readme_claim_alignment_prompt(_manifest(), _theory_sources())

    assert (
        "Allowed statuses: supported, partially_supported, missing_evidence, contradicted."
        in reference_prompt
    )
    assert (
        "Allowed statuses: supported, partially_supported, not_evidenced, "
        "contradicted, out_of_scope_or_non_verifiable." in agent_prompt
    )
    assert (
        "Allowed statuses: supported, partially_supported, not_evidenced, "
        "contradicted, not_statically_verifiable." in readme_prompt
    )
    assert "do not invent evidence" in reference_prompt.lower()
    assert "do not invent evidence" in agent_prompt.lower()
    assert "do not invent evidence" in readme_prompt.lower()
