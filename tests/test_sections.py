from datetime import UTC, datetime
from pathlib import Path

import pytest

import repo_autodocs.sections as sections_module
from repo_autodocs.config import AppConfig
from repo_autodocs.llm import LLMServiceError, LLMStreamInterruptedFailure, LLMTransientFailure
from repo_autodocs.models import CodeFactsBundle, GroundedContextBundle, ProjectPaths, RepoManifest
from repo_autodocs.sections import build_section_inputs, generate_sections


def _config_stub() -> AppConfig:
    root = Path("/tmp/repo")
    paths = ProjectPaths(
        project_root=root,
        docs_dir=root / "docs",
        reference_dir=root / "docs/context/methodology",
        output_dir=root / "docs/generated",
        site_dir=root / "site",
    )
    return AppConfig(project_paths=paths, enable_llm=False)


def _manifest() -> RepoManifest:
    return RepoManifest(project_root=Path("/tmp/repo"), top_level_directories=["src"])


def test_generate_sections_stub_mode_returns_expected_files() -> None:
    sections = generate_sections(
        manifest=_manifest(),
        theory_sources=[],
        config=_config_stub(),
        code_facts_bundle=CodeFactsBundle(),
        grounded_bundle=GroundedContextBundle(),
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert set(sections) == {
        "overview.md",
        "architecture.md",
        "reference_alignment.md",
        "agent_instruction_alignment.md",
        "readme_claim_alignment.md",
        "theory_alignment.md",
        "code_structure.md",
        "runtime_entrypoints.md",
    }
    assert "# Overview" in sections["overview.md"]
    assert "## What This Project Appears To Be" in sections["overview.md"]
    assert "# Architecture" in sections["architecture.md"]
    assert "## Structural Organization" in sections["architecture.md"]
    assert "# Reference Alignment" in sections["reference_alignment.md"]
    assert "# Agent Instruction Alignment" in sections["agent_instruction_alignment.md"]
    assert "# README Claim Alignment" in sections["readme_claim_alignment.md"]
    assert "# Theory Alignment" in sections["theory_alignment.md"]
    assert "Deprecated compatibility page" in sections["theory_alignment.md"]
    assert "# Code Structure" in sections["code_structure.md"]
    assert "# Runtime Entrypoints" in sections["runtime_entrypoints.md"]


def test_generate_sections_deterministic_mode_is_stable_without_timestamp() -> None:
    first = generate_sections(
        manifest=_manifest(),
        theory_sources=[],
        config=_config_stub(),
    )
    second = generate_sections(
        manifest=_manifest(),
        theory_sources=[],
        config=_config_stub(),
    )

    assert first == second
    assert "deterministic and based on scanned repository/code evidence" in first["overview.md"]


def test_generate_sections_deterministic_mode_has_no_llm_metadata_header() -> None:
    sections = generate_sections(
        manifest=_manifest(),
        theory_sources=[],
        config=_config_stub(),
    )
    body = sections["overview.md"]

    assert body.startswith("# Overview")
    assert "Generated section artifact" not in body


def test_generate_sections_stub_mode_is_structurally_stable() -> None:
    sections = generate_sections(
        manifest=_manifest(),
        theory_sources=[],
        config=_config_stub(),
    )
    overview = sections["overview.md"]
    expected_order = [
        "## What This Project Appears To Be",
        "## Deterministic Observations",
        "## Major Structural Signals",
        "## Known Uncertainty",
    ]

    positions = [overview.index(heading) for heading in expected_order]
    assert positions == sorted(positions)


def test_build_section_inputs_includes_code_facts_block() -> None:
    prompts = build_section_inputs(
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
    )

    assert "[AUTHORITATIVE CODE FACTS - DETERMINISTIC STRUCTURAL ANALYSIS]" in prompts["overview"]
    assert set(prompts) == {
        "overview",
        "architecture",
        "code_structure",
        "runtime_entrypoints",
        "reference_alignment",
        "agent_instruction_alignment",
        "readme_claim_alignment",
        "theory_alignment",
    }


def test_build_section_inputs_reflect_llm_analysis_semantics() -> None:
    prompts = build_section_inputs(
        manifest=_manifest(),
        theory_sources=[],
        grounded_bundle=GroundedContextBundle(),
        code_facts_bundle=CodeFactsBundle(),
    )

    assert "Produce deep technical analysis for this section." in prompts["overview"]
    assert "Label inference clearly" in prompts["architecture"]
    assert "module inventory" in prompts["code_structure"]
    assert "entrypoint detection evidence" in prompts["runtime_entrypoints"]
    assert "Mismatch analysis expectation: required." in prompts["reference_alignment"]


def test_generate_sections_builds_grounded_bundle(monkeypatch) -> None:
    called = {"count": 0}

    def _fake_bundle(theory_sources):
        called["count"] += 1
        return GroundedContextBundle()

    monkeypatch.setattr("repo_autodocs.sections.build_grounded_context_bundle", _fake_bundle)

    generate_sections(
        manifest=_manifest(),
        theory_sources=[],
        config=_config_stub(),
    )

    assert called["count"] == 1


def test_generate_sections_uses_provided_grounded_bundle_without_rebuild(monkeypatch) -> None:
    def _fail_bundle(theory_sources):  # pragma: no cover - should not execute
        raise AssertionError("grounded bundle builder should not be called")

    monkeypatch.setattr("repo_autodocs.sections.build_grounded_context_bundle", _fail_bundle)

    generate_sections(
        manifest=_manifest(),
        theory_sources=[],
        config=_config_stub(),
        grounded_bundle=GroundedContextBundle(),
    )


def test_generate_sections_stub_mode_does_not_instantiate_openai_client(monkeypatch) -> None:
    def _fail_openai(*args, **kwargs):  # pragma: no cover - should not execute
        raise AssertionError("OpenAI client should not be instantiated in stub mode")

    monkeypatch.setattr("repo_autodocs.llm.OpenAI", _fail_openai)

    sections = generate_sections(
        manifest=_manifest(),
        theory_sources=[],
        config=_config_stub(),
        grounded_bundle=GroundedContextBundle(),
    )

    assert "overview.md" in sections


def test_generate_sections_llm_mode_uses_orchestration(monkeypatch) -> None:
    config = _config_stub()
    config.enable_llm = True
    config.model_name = "gpt-test"
    config.base_url = "http://localhost/v1"

    class _FakeClient:
        pass

    monkeypatch.setattr(
        "repo_autodocs.sections.OpenAICompatibleLLMClient.from_config",
        lambda _config: _FakeClient(),
    )

    calls: list[str] = []

    def _fake_orchestrate(**kwargs):
        calls.append(kwargs["section_name"])
        return type(
            "_Result",
            (),
            {"final_markdown": "# Overview\n\n## Observed Repository Evidence\n\n- ok\n"},
        )()

    monkeypatch.setattr("repo_autodocs.sections.orchestrate_llm_section", _fake_orchestrate)

    sections = generate_sections(
        manifest=_manifest(),
        theory_sources=[],
        config=config,
        grounded_bundle=GroundedContextBundle(),
    )

    assert set(calls) == {
        "overview",
        "architecture",
        "code_structure",
        "runtime_entrypoints",
        "reference_alignment",
        "agent_instruction_alignment",
        "readme_claim_alignment",
    }
    assert "Generated section artifact" in sections["overview.md"]


def test_generate_sections_llm_mode_no_longer_uses_single_generate_markdown(monkeypatch) -> None:
    config = _config_stub()
    config.enable_llm = True
    config.model_name = "gpt-test"
    config.base_url = "http://localhost/v1"

    class _FailClient:
        def generate_markdown(self, prompt: str) -> str:  # pragma: no cover - should not execute
            raise AssertionError("single-shot generate_markdown should not be used")

        def generate_text(
            self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
        ) -> str:
            return "unused"

    monkeypatch.setattr(
        "repo_autodocs.sections.OpenAICompatibleLLMClient.from_config",
        lambda _config: _FailClient(),
    )

    monkeypatch.setattr(
        "repo_autodocs.sections.orchestrate_llm_section",
        lambda **kwargs: type("_Result", (), {"final_markdown": "# Page\n"})(),
    )

    generate_sections(
        manifest=_manifest(),
        theory_sources=[],
        config=config,
        grounded_bundle=GroundedContextBundle(),
    )


def test_generate_sections_continues_when_one_llm_unit_exhausts_retries(monkeypatch) -> None:
    config = _config_stub()
    config.enable_llm = True
    config.model_name = "gpt-test"
    config.base_url = "http://localhost/v1"

    monkeypatch.setattr(
        "repo_autodocs.sections.OpenAICompatibleLLMClient.from_config",
        lambda _config: object(),
    )

    def _fake_orchestrate(**kwargs):
        if kwargs["section_name"] == "architecture":
            raise LLMTransientFailure(
                operation_label="architecture:notes",
                attempt_count=5,
                attempt_timeouts_seconds=(5, 10, 20, 40, 60),
                final_exception_type="APITimeoutError",
                final_error_message="timed out",
            )
        return type("_Result", (), {"final_markdown": "# OK\n"})()

    monkeypatch.setattr("repo_autodocs.sections.orchestrate_llm_section", _fake_orchestrate)

    sections = generate_sections(
        manifest=_manifest(),
        theory_sources=[],
        config=config,
        grounded_bundle=GroundedContextBundle(),
    )

    assert "# OK" in sections["overview.md"]
    assert "Structured Output Diagnostics" in sections["architecture.md"]
    assert (
        "Section unavailable due to transient LLM transport exhaustion"
        in sections["architecture.md"]
    )
    assert "attempt_timeouts_seconds=[5, 10, 20, 40, 60]" in sections["architecture.md"]
    assert "# OK" in sections["runtime_entrypoints.md"]


def test_generate_sections_raises_clean_summary_when_all_llm_units_fail(monkeypatch) -> None:
    config = _config_stub()
    config.enable_llm = True
    config.model_name = "gpt-test"
    config.base_url = "http://localhost/v1"

    monkeypatch.setattr(
        "repo_autodocs.sections.OpenAICompatibleLLMClient.from_config",
        lambda _config: object(),
    )

    def _always_fail(**kwargs):
        raise LLMTransientFailure(
            operation_label=f"{kwargs['section_name']}:notes",
            attempt_count=4,
            attempt_timeouts_seconds=(5, 10, 20, 30),
            final_exception_type="APIConnectionError",
            final_error_message="connection dropped",
        )

    monkeypatch.setattr("repo_autodocs.sections.orchestrate_llm_section", _always_fail)

    with pytest.raises(LLMServiceError, match="LLM streaming transport unavailable"):
        generate_sections(
            manifest=_manifest(),
            theory_sources=[],
            config=config,
            grounded_bundle=GroundedContextBundle(),
        )


def test_generate_sections_all_llm_failure_check_is_independent_of_filename_mapping_size(
    monkeypatch,
) -> None:
    config = _config_stub()
    config.enable_llm = True
    config.model_name = "gpt-test"
    config.base_url = "http://localhost/v1"

    monkeypatch.setattr(
        "repo_autodocs.sections.OpenAICompatibleLLMClient.from_config",
        lambda _config: object(),
    )
    monkeypatch.setitem(
        sections_module.SECTION_TO_FILENAME,
        "compatibility_only_page",
        "compatibility_only_page.md",
    )

    def _always_fail(**kwargs):
        raise LLMTransientFailure(
            operation_label=f"{kwargs['section_name']}:notes",
            attempt_count=4,
            attempt_timeouts_seconds=(5, 10, 20, 30),
            final_exception_type="APIConnectionError",
            final_error_message="connection dropped",
        )

    monkeypatch.setattr("repo_autodocs.sections.orchestrate_llm_section", _always_fail)

    with pytest.raises(LLMServiceError, match="LLM streaming transport unavailable"):
        generate_sections(
            manifest=_manifest(),
            theory_sources=[],
            config=config,
            grounded_bundle=GroundedContextBundle(),
        )


def test_generate_sections_marks_mid_stream_interruption_unavailable_and_continues(
    monkeypatch,
) -> None:
    config = _config_stub()
    config.enable_llm = True
    config.model_name = "gpt-test"
    config.base_url = "http://localhost/v1"

    monkeypatch.setattr(
        "repo_autodocs.sections.OpenAICompatibleLLMClient.from_config",
        lambda _config: object(),
    )

    def _fake_orchestrate(**kwargs):
        if kwargs["section_name"] == "runtime_entrypoints":
            raise LLMStreamInterruptedFailure(
                operation_label="runtime_entrypoints:final",
                meaningful_response_started=True,
                attempt_count=1,
                final_exception_type="ConnectionResetError",
                final_error_message="stream dropped",
                content_received_chars=82,
            )
        return type("_Result", (), {"final_markdown": "# OK\n"})()

    monkeypatch.setattr("repo_autodocs.sections.orchestrate_llm_section", _fake_orchestrate)

    sections = generate_sections(
        manifest=_manifest(),
        theory_sources=[],
        config=config,
        grounded_bundle=GroundedContextBundle(),
    )

    assert "# OK" in sections["overview.md"]
    assert "Section unavailable due to streaming interruption" in sections["runtime_entrypoints.md"]
    assert "content_received_chars=82" in sections["runtime_entrypoints.md"]
    assert "# OK" in sections["architecture.md"]
