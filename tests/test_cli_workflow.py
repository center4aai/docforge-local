from pathlib import Path

from conftest import copy_fixture_repo
from reference_fixtures import write_minimal_docx, write_minimal_pdf
from typer.testing import CliRunner

from repo_autodocs.cli import app
from repo_autodocs.llm import LLMServiceError


def test_doctor_success_with_optional_methodology_missing(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    result = runner.invoke(app, ["doctor", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert "PASS:" in result.stdout
    assert "PASS: reference inputs not explicitly provided" in result.stdout
    assert "FAIL:" not in result.stdout


def test_doctor_use_llm_fails_when_required_settings_missing(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "repo_with_methodology")
    runner = CliRunner()

    result = runner.invoke(app, ["doctor", "--project-root", str(repo_path), "--use-llm"])

    assert result.exit_code == 1
    assert "FAIL: llm model_name missing" in result.stdout
    assert "FAIL: llm base_url missing" in result.stdout


def test_doctor_use_llm_succeeds_without_api_key_when_endpoint_configured(
    tmp_path: Path, monkeypatch
) -> None:
    repo_path = copy_fixture_repo(tmp_path, "repo_with_methodology")
    runner = CliRunner()
    monkeypatch.setenv("REPO_AUTODOCS_MODEL_NAME", "gpt-test")
    monkeypatch.setenv("REPO_AUTODOCS_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("REPO_AUTODOCS_API_KEY_ENV_VAR", "UNSET_OPTIONAL_KEY")
    monkeypatch.delenv("UNSET_OPTIONAL_KEY", raising=False)

    result = runner.invoke(app, ["doctor", "--project-root", str(repo_path), "--use-llm"])

    assert result.exit_code == 0
    assert "PASS: llm model_name configured" in result.stdout
    assert "PASS: llm base_url configured" in result.stdout
    assert (
        "WARN: llm api key env var not present; requests will be sent without authentication"
        in result.stdout
    )


def test_doctor_uses_env_llm_when_cli_flag_not_explicit(tmp_path: Path, monkeypatch) -> None:
    repo_path = copy_fixture_repo(tmp_path, "repo_with_methodology")
    runner = CliRunner()
    monkeypatch.setenv("REPO_AUTODOCS_ENABLE_LLM", "true")
    monkeypatch.setenv("REPO_AUTODOCS_MODEL_NAME", "gpt-test")
    monkeypatch.setenv("REPO_AUTODOCS_BASE_URL", "http://127.0.0.1:11434/v1")

    result = runner.invoke(app, ["doctor", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert "PASS: llm model_name configured" in result.stdout
    assert "PASS: llm base_url configured" in result.stdout


def test_doctor_cli_use_llm_flag_overrides_env_false(tmp_path: Path, monkeypatch) -> None:
    repo_path = copy_fixture_repo(tmp_path, "repo_with_methodology")
    runner = CliRunner()
    monkeypatch.setenv("REPO_AUTODOCS_ENABLE_LLM", "false")
    monkeypatch.delenv("REPO_AUTODOCS_MODEL_NAME", raising=False)
    monkeypatch.delenv("REPO_AUTODOCS_BASE_URL", raising=False)

    result = runner.invoke(app, ["doctor", "--project-root", str(repo_path), "--use-llm"])

    assert result.exit_code == 1
    assert "FAIL: llm model_name missing" in result.stdout


def test_generate_docs_deterministic_mode_builds_docs_and_site_without_methodology(
    tmp_path: Path,
) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert "PASS: reference inputs not explicitly provided" in result.stdout
    assert "Documentation generation complete" in result.stdout
    assert "LLM mode: deterministic-offline" in result.stdout
    assert "External references summary: explicit_inputs=0" in result.stdout
    assert (repo_path / ".docforge-local" / "docs" / "generated" / "overview.md").exists()
    assert (repo_path / ".docforge-local" / "docs" / "generated" / "architecture.md").exists()
    assert (repo_path / ".docforge-local" / "docs" / "generated" / "code_structure.md").exists()
    assert (
        repo_path / ".docforge-local" / "docs" / "generated" / "runtime_entrypoints.md"
    ).exists()
    assert (repo_path / ".docforge-local" / "docs" / "generated" / "theory_alignment.md").exists()
    assert (repo_path / ".docforge-local" / "docs" / "index.md").exists()
    assert (repo_path / ".docforge-local" / "docs" / "context" / "project_brief.md").exists()
    assert (repo_path / ".docforge-local" / "site" / "index.html").exists()
    assert not (
        repo_path / ".docforge-local" / "docs" / "generated" / "prompt_grounding_debug.md"
    ).exists()
    assert not (
        repo_path / ".docforge-local" / "docs" / "generated" / "code_facts_debug.md"
    ).exists()


def test_generate_docs_ru_from_env_localizes_prose_but_keeps_canonical_surfaces(
    tmp_path: Path, monkeypatch
) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    monkeypatch.setenv("REPO_AUTODOCS_GENERATED_TEXT_LANGUAGE", "ru")
    runner = CliRunner()

    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    generated_root = repo_path / ".docforge-local" / "docs"
    home = (generated_root / "index.md").read_text(encoding="utf-8")
    brief = (generated_root / "context" / "project_brief.md").read_text(encoding="utf-8")
    external_refs = (generated_root / "context" / "external_references.md").read_text(
        encoding="utf-8"
    )
    snapshot = (generated_root / "generated" / "project_snapshot.md").read_text(encoding="utf-8")
    generated_readme = (generated_root / "generated" / "README.md").read_text(encoding="utf-8")
    overview = (generated_root / "generated" / "overview.md").read_text(encoding="utf-8")

    assert "Этот сайт был сгенерирован" in home
    assert "Этот обзор строится только на детерминированных признаках" in brief
    assert "Статус-отчёт по опциональным внешним reference-материалам." in external_refs
    assert "Эта страница — детерминированный снимок репозитория." in snapshot
    assert "сгенерированными артефактами" in generated_readme
    assert "Этот обзор детерминированный" in overview

    assert "# Overview" in overview
    assert "## Discovered external reference files" in snapshot
    assert "# Generated Documentation" in generated_readme
    assert (generated_root / "generated" / "reference_alignment.md").exists()


def test_doctor_privacy_reports_local_only_mode(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    result = runner.invoke(app, ["doctor", "--project-root", str(repo_path), "--privacy"])

    assert result.exit_code == 0
    assert "MODE: local-only" in result.stdout
    assert "ALLOWED_EGRESS_ENDPOINT: none" in result.stdout


def test_generate_docs_deterministic_mode_does_not_touch_openai_client(
    tmp_path: Path, monkeypatch
) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    def _fail_openai(*args, **kwargs):  # pragma: no cover - should not execute
        raise AssertionError("OpenAI client should not be initialized in stub mode")

    monkeypatch.setattr("repo_autodocs.llm.OpenAI", _fail_openai)

    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert "LLM mode: deterministic-offline" in result.stdout


def test_doctor_privacy_reports_configured_llm_endpoint_mode(tmp_path: Path, monkeypatch) -> None:
    repo_path = copy_fixture_repo(tmp_path, "repo_with_methodology")
    runner = CliRunner()

    monkeypatch.setenv("REPO_AUTODOCS_MODEL_NAME", "gpt-test")
    monkeypatch.setenv("REPO_AUTODOCS_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("REPO_AUTODOCS_API_KEY_ENV_VAR", "TEST_LLM_API_KEY")
    monkeypatch.setenv("TEST_LLM_API_KEY", "test-key")

    result = runner.invoke(
        app,
        ["doctor", "--project-root", str(repo_path), "--use-llm", "--privacy"],
    )

    assert result.exit_code == 0
    assert "MODE: llm-endpoint-enabled" in result.stdout
    assert "ALLOWED_EGRESS_ENDPOINT: https://llm.example/v1" in result.stdout


def test_doctor_privacy_reports_invalid_llm_configuration(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "repo_with_methodology")
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["doctor", "--project-root", str(repo_path), "--use-llm", "--privacy"],
    )

    assert result.exit_code == 1
    assert "MODE: llm-config-invalid" in result.stdout
    assert "ALLOWED_EGRESS_ENDPOINT: <missing>" in result.stdout


def test_generate_docs_deterministic_mode_never_calls_llm_constructor(
    tmp_path: Path, monkeypatch
) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    def _fail_from_config(*args, **kwargs):  # pragma: no cover - should not execute
        raise AssertionError("LLM constructor should not be called in stub mode")

    monkeypatch.setattr(
        "repo_autodocs.sections.OpenAICompatibleLLMClient.from_config", _fail_from_config
    )

    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert "LLM mode: deterministic-offline" in result.stdout


def test_generate_docs_deterministic_pages_do_not_contain_stub_artifacts(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    overview = (repo_path / ".docforge-local" / "docs" / "generated" / "overview.md").read_text(
        encoding="utf-8"
    )
    architecture = (
        repo_path / ".docforge-local" / "docs" / "generated" / "architecture.md"
    ).read_text(encoding="utf-8")
    assert "Stub synthesis" not in overview
    assert "Prompt digest" not in overview
    assert "stub-local" not in architecture
    assert "generation_mode: stub" not in architecture


def test_generate_docs_use_llm_generates_substantive_stage4_pages(
    tmp_path: Path, monkeypatch
) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()
    monkeypatch.setenv("REPO_AUTODOCS_MODEL_NAME", "gpt-test")
    monkeypatch.setenv("REPO_AUTODOCS_BASE_URL", "http://127.0.0.1:11434/v1")

    class _FakeClient:
        pass

    monkeypatch.setattr(
        "repo_autodocs.sections.OpenAICompatibleLLMClient.from_config",
        lambda _config: _FakeClient(),
    )

    def _fake_orchestrate(**kwargs):
        section = kwargs["section_name"]
        title = section.replace("_", " ").title()
        body = f"# {title}\n\n## Structured\n\n- Substantive {section} content.\n"
        return type("_Result", (), {"final_markdown": body})()

    monkeypatch.setattr("repo_autodocs.sections.orchestrate_llm_section", _fake_orchestrate)

    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path), "--use-llm"])

    assert result.exit_code == 0
    code_structure = (
        repo_path / ".docforge-local" / "docs" / "generated" / "code_structure.md"
    ).read_text(encoding="utf-8")
    runtime_entrypoints = (
        repo_path / ".docforge-local" / "docs" / "generated" / "runtime_entrypoints.md"
    ).read_text(encoding="utf-8")
    assert "Substantive code_structure content." in code_structure
    assert "Substantive runtime_entrypoints content." in runtime_entrypoints
    assert "AUTO-GENERATED PLACEHOLDER" not in code_structure
    assert "AUTO-GENERATED PLACEHOLDER" not in runtime_entrypoints


def test_generate_docs_use_llm_auth_failure_prints_friendly_fail(
    tmp_path: Path, monkeypatch
) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()
    monkeypatch.setenv("REPO_AUTODOCS_MODEL_NAME", "gpt-test")
    monkeypatch.setenv("REPO_AUTODOCS_BASE_URL", "http://127.0.0.1:11434/v1")

    def _raise_auth(*args, **kwargs):
        raise LLMServiceError("LLM endpoint authentication failed: endpoint rejected request.")

    monkeypatch.setattr("repo_autodocs.cli.generate_sections", _raise_auth)

    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path), "--use-llm"])

    assert result.exit_code == 1
    assert "FAIL: LLM endpoint authentication failed" in result.stdout
    assert "Traceback" not in result.stdout


def test_generate_sections_use_llm_connection_failure_prints_friendly_fail(
    tmp_path: Path, monkeypatch
) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()
    monkeypatch.setenv("REPO_AUTODOCS_MODEL_NAME", "gpt-test")
    monkeypatch.setenv("REPO_AUTODOCS_BASE_URL", "http://127.0.0.1:11434/v1")

    def _raise_conn(*args, **kwargs):
        raise LLMServiceError("Could not connect to the LLM endpoint at http://127.0.0.1:11434/v1.")

    monkeypatch.setattr("repo_autodocs.cli.generate_sections", _raise_conn)

    result = runner.invoke(
        app, ["generate-sections", "--project-root", str(repo_path), "--use-llm"]
    )

    assert result.exit_code == 1
    assert "FAIL: Could not connect to the LLM endpoint" in result.stdout
    assert "Traceback" not in result.stdout


def test_generate_sections_use_llm_fails_when_model_name_missing(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    result = runner.invoke(
        app, ["generate-sections", "--project-root", str(repo_path), "--use-llm"]
    )

    assert result.exit_code == 1
    assert "FAIL: llm model_name missing" in result.stdout
    assert "Traceback" not in result.stdout


def test_generate_sections_use_llm_fails_when_base_url_missing(tmp_path: Path, monkeypatch) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()
    monkeypatch.setenv("REPO_AUTODOCS_MODEL_NAME", "gpt-test")
    monkeypatch.delenv("REPO_AUTODOCS_BASE_URL", raising=False)

    result = runner.invoke(
        app, ["generate-sections", "--project-root", str(repo_path), "--use-llm"]
    )

    assert result.exit_code == 1
    assert "FAIL: llm base_url missing" in result.stdout
    assert "Traceback" not in result.stdout


def test_doctor_supports_relative_project_root_from_controlled_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    copy_fixture_repo(workspace, "minimal_cli_repo")
    monkeypatch.chdir(workspace)
    runner = CliRunner()

    result = runner.invoke(app, ["doctor", "--project-root", "minimal_cli_repo"])

    assert result.exit_code == 0
    assert "PASS: project_root exists:" in result.stdout


def test_doctor_cli_project_root_overrides_env_project_root(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cli_repo = copy_fixture_repo(workspace, "minimal_cli_repo")
    env_repo = copy_fixture_repo(workspace, "repo_with_methodology")
    monkeypatch.setenv("REPO_AUTODOCS_PROJECT_ROOT", str(env_repo))
    runner = CliRunner()

    result = runner.invoke(app, ["doctor", "--project-root", str(cli_repo)])

    assert result.exit_code == 0
    assert f"PASS: project_root exists: {cli_repo.resolve()}" in result.stdout
    assert str(env_repo.resolve()) not in result.stdout


def test_generate_docs_cli_project_root_overrides_env_project_root(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cli_repo = copy_fixture_repo(workspace, "minimal_cli_repo")
    env_repo = copy_fixture_repo(workspace, "repo_with_methodology")
    monkeypatch.setenv("REPO_AUTODOCS_PROJECT_ROOT", str(env_repo))
    runner = CliRunner()

    result = runner.invoke(app, ["generate-docs", "--project-root", str(cli_repo)])

    assert result.exit_code == 0
    assert f"Repo path: {cli_repo.resolve()}" in result.stdout
    assert (cli_repo / ".docforge-local" / "docs" / "generated" / "overview.md").exists()
    assert not (env_repo / ".docforge-local" / "docs" / "generated" / "overview.md").exists()


def test_generate_docs_reports_external_references_when_directory_provided(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    refs = tmp_path / "refs"
    (refs / "nested").mkdir(parents=True)
    (refs / "guide.md").write_text("# Guide\n\nalpha", encoding="utf-8")
    (refs / "nested" / "notes.txt").write_text("Notes\n\nbeta", encoding="utf-8")
    write_minimal_pdf(refs / "nested" / "paper.pdf")
    write_minimal_docx(refs / "nested" / "spec.docx")
    (refs / "nested" / "legacy.rst").write_text("unsupported", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "generate-docs",
            "--project-root",
            str(repo_path),
            "--reference-dir",
            str(refs),
        ],
    )

    assert result.exit_code == 0
    assert "External references summary: explicit_inputs=1, discovered=5" in result.stdout
    page = repo_path / ".docforge-local" / "docs" / "context" / "external_references.md"
    assert page.exists()
    content = page.read_text(encoding="utf-8")
    assert "| Path | Origin | Kind | Route | Extension | Size (bytes) | Parse status |" in content
    assert "legacy.rst" in content
    assert "paper.pdf" in content
    assert "spec.docx" in content
    assert "guide.md" in content
    assert "Ingest-eligible files: 4" in content
    assert "not_ingestible" in content


def test_generate_docs_accepts_deprecated_methodology_dir_alias(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "guide.md").write_text("# Guide\n\nalpha", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "generate-docs",
            "--project-root",
            str(repo_path),
            "--methodology-dir",
            str(refs),
        ],
    )

    assert result.exit_code == 0
    assert "`methodology_dir` is deprecated" in result.stdout


def test_generate_docs_writes_debug_artifacts_when_enabled(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["generate-docs", "--project-root", str(repo_path), "--debug-artifacts"],
    )

    assert result.exit_code == 0
    assert (
        repo_path / ".docforge-local" / "docs" / "generated" / "prompt_grounding_debug.md"
    ).exists()
    assert (repo_path / ".docforge-local" / "docs" / "generated" / "code_facts_debug.md").exists()


def test_generate_docs_uses_env_debug_artifacts_when_cli_not_explicit(
    tmp_path: Path, monkeypatch
) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    monkeypatch.setenv("REPO_AUTODOCS_DEBUG_ARTIFACTS", "true")
    runner = CliRunner()

    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert (
        repo_path / ".docforge-local" / "docs" / "generated" / "prompt_grounding_debug.md"
    ).exists()


def test_generate_docs_cli_debug_artifacts_overrides_env_false(tmp_path: Path, monkeypatch) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    monkeypatch.setenv("REPO_AUTODOCS_DEBUG_ARTIFACTS", "false")
    runner = CliRunner()

    result = runner.invoke(
        app, ["generate-docs", "--project-root", str(repo_path), "--debug-artifacts"]
    )

    assert result.exit_code == 0
    assert (
        repo_path / ".docforge-local" / "docs" / "generated" / "prompt_grounding_debug.md"
    ).exists()


def test_generate_docs_cleans_stale_debug_artifacts_when_disabled(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    first = runner.invoke(
        app,
        ["generate-docs", "--project-root", str(repo_path), "--debug-artifacts"],
    )
    second = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert not (
        repo_path / ".docforge-local" / "docs" / "generated" / "prompt_grounding_debug.md"
    ).exists()
    assert not (
        repo_path / ".docforge-local" / "docs" / "generated" / "code_facts_debug.md"
    ).exists()


def test_generate_docs_does_not_delete_reference_grounding_artifact(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    output_dir = repo_path / ".docforge-local" / "docs" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    grounding = output_dir / "reference_grounding.md"
    grounding.write_text("# Existing grounding\n", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    assert grounding.exists()


def test_generate_docs_ignores_root_readme_for_implementation_analysis(tmp_path: Path) -> None:
    repo_path = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    (repo_path / "README.md").write_text("# Project\n\nDo not use me.\n", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(app, ["generate-docs", "--project-root", str(repo_path)])

    assert result.exit_code == 0
    brief = (repo_path / ".docforge-local" / "docs" / "context" / "project_brief.md").read_text(
        encoding="utf-8"
    )
    assert "README title" not in brief
