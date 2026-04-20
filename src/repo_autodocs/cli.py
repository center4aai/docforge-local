"""CLI entrypoints for DocForge Local commands."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

import click
import typer
from click.core import ParameterSource
from typer._completion_shared import _get_shell_name, get_completion_script
from typer._completion_shared import install as typer_install

from repo_autodocs.alignment import build_routed_alignment_bundle, build_routed_llm_material_bundle
from repo_autodocs.codefacts import render_code_facts_debug_markdown, summarize_code_facts
from repo_autodocs.config import DEFAULT_CONFIG_FILE_NAME, AppConfig, load_config
from repo_autodocs.config_command import register_config_command
from repo_autodocs.deterministic import (
    DeterministicContext,
    render_external_references_page,
    render_home_page,
    render_project_brief_page,
    should_overwrite_managed_page,
)
from repo_autodocs.generator import generate_project_snapshot
from repo_autodocs.gitops import list_changed_files
from repo_autodocs.grounding import (
    build_grounded_context_bundle,
    render_grounding_debug_markdown,
    summarize_grounded_context,
)
from repo_autodocs.llm import LLMServiceError
from repo_autodocs.models import GenerationRequest
from repo_autodocs.privacy import build_privacy_report, validate_llm_egress_config
from repo_autodocs.prompts import render_prompt_grounding_debug_markdown
from repo_autodocs.publisher import build_mkdocs_site, write_project_snapshot
from repo_autodocs.scaffold import NavScaffoldError
from repo_autodocs.scanner import scan_repository, scan_repository_with_code_facts
from repo_autodocs.secrets import api_key_present
from repo_autodocs.sections import generate_sections
from repo_autodocs.theory import (
    discover_external_references,
    mark_reference_parse_statuses,
    select_theory_grounding_sources,
    supported_ingest_extensions,
)
from repo_autodocs.update import build_update_plan, render_update_plan
from repo_autodocs.writer import (
    write_code_facts_debug_artifact,
    write_generated_readme,
    write_generated_sections,
    write_markdown_artifact,
    write_prompt_grounding_debug_artifact,
)

app = typer.Typer(
    help=(
        "DocForge Local: local-first repository documentation CLI. "
        "Use `docforge-local config` as the primary configuration UX."
    ),
    add_completion=False,
)
register_config_command(app)

POWERSHELL_COMPLETION_BLOCK_START = "# >>> docforge-local completion >>>"
POWERSHELL_COMPLETION_BLOCK_END = "# <<< docforge-local completion <<<"


def _detect_newline_style(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    return "\n"


def _upsert_managed_block(
    existing_text: str, block_text: str, start_marker: str, end_marker: str
) -> str:
    start = existing_text.find(start_marker)
    if start != -1:
        end = existing_text.find(end_marker, start)
        if end != -1:
            end += len(end_marker)
            remainder = existing_text[end:]
            if remainder.startswith("\r\n"):
                remainder = remainder[2:]
            elif remainder.startswith("\n"):
                remainder = remainder[1:]
            preserved_prefix = existing_text[:start].rstrip("\r\n")
            if preserved_prefix:
                return f"{preserved_prefix}\n{block_text}\n{remainder}"
            return f"{block_text}\n{remainder}"

    if not existing_text:
        return f"{block_text}\n"
    if existing_text.endswith(("\n", "\r\n")):
        return f"{existing_text}{block_text}\n"
    return f"{existing_text}\n{block_text}\n"


def _write_text_atomic(path: Path, content: str, newline: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline=newline,
        dir=path.parent,
        delete=False,
    ) as temp_file:
        temp_file.write(content)
        temp_path = Path(temp_file.name)
    try:
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "cp1252"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _resolve_powershell_profile_path(shell: str) -> Path:
    result = subprocess.run(
        [shell, "-NoProfile", "-Command", "$PROFILE"],
        check=True,
        stdout=subprocess.PIPE,
    )
    return Path(result.stdout.decode("utf-8").strip())


def _install_powershell_completion(*, prog_name: str, complete_var: str, shell: str) -> Path:
    profile_path = _resolve_powershell_profile_path(shell)
    existing_profile = _read_text_if_exists(profile_path)
    newline = _detect_newline_style(existing_profile)
    script_content = get_completion_script(
        prog_name=prog_name,
        complete_var=complete_var,
        shell=shell,
    ).strip()
    block = (
        f"{POWERSHELL_COMPLETION_BLOCK_START}\n{script_content}\n{POWERSHELL_COMPLETION_BLOCK_END}"
    )
    updated_profile = _upsert_managed_block(
        existing_text=existing_profile,
        block_text=block,
        start_marker=POWERSHELL_COMPLETION_BLOCK_START,
        end_marker=POWERSHELL_COMPLETION_BLOCK_END,
    )
    _write_text_atomic(profile_path, updated_profile, newline=newline)
    return profile_path


def _install_completion(shell: str | None = None) -> tuple[str, Path]:
    ctx = click.get_current_context()
    prog_name = ctx.find_root().info_name
    assert prog_name
    complete_var = f"_{prog_name.replace('-', '_').upper()}_COMPLETE"
    resolved_shell = shell or _get_shell_name()
    if resolved_shell in {"powershell", "pwsh"}:
        return resolved_shell, _install_powershell_completion(
            prog_name=prog_name,
            complete_var=complete_var,
            shell=resolved_shell,
        )
    installed_shell, path = typer_install(
        shell=resolved_shell,
        prog_name=prog_name,
        complete_var=complete_var,
    )
    return installed_shell, path


def _show_completion(shell: str | None = None) -> str:
    ctx = click.get_current_context()
    prog_name = ctx.find_root().info_name
    assert prog_name
    complete_var = f"_{prog_name.replace('-', '_').upper()}_COMPLETE"
    resolved_shell = shell or _get_shell_name() or ""
    return get_completion_script(
        prog_name=prog_name,
        complete_var=complete_var,
        shell=resolved_shell,
    )


@app.callback(invoke_without_command=True)
def main(
    install_completion: Annotated[
        bool,
        typer.Option(
            "--install-completion",
            help="Install completion for the current shell.",
            is_eager=True,
        ),
    ] = False,
    show_completion: Annotated[
        bool,
        typer.Option(
            "--show-completion",
            help="Show completion for the current shell, to copy or customize installation.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    if show_completion:
        typer.echo(_show_completion())
        raise typer.Exit(code=0)
    if install_completion:
        shell, path = _install_completion()
        typer.echo(f"{shell} completion installed in {path}")
        typer.echo("Completion will take effect once you restart the terminal")
        raise typer.Exit(code=0)


@app.command("scan", hidden=True)
def scan_command(project_root: Path = Path(".")) -> None:
    """Advanced/internal: scan a repository root and print deterministic summary."""

    config = load_config(project_root=project_root)
    manifest = scan_repository(config.project_root, config=config)
    typer.echo(f"Project root: {manifest.project_root}")
    typer.echo(f"Top-level directories ({len(manifest.top_level_directories)}):")
    for name in manifest.top_level_directories:
        typer.echo(f"  - {name}")

    typer.echo(f"Top-level files ({len(manifest.top_level_files)}):")
    for name in manifest.top_level_files:
        typer.echo(f"  - {name}")

    typer.echo("Flags:")
    typer.echo(f"  - has .git: {manifest.has_git_dir}")
    typer.echo(f"  - has pyproject.toml: {manifest.has_pyproject}")
    typer.echo(f"  - has mkdocs.yml: {manifest.has_mkdocs_config}")
    typer.echo(f"  - has docs/: {manifest.has_docs_dir}")
    typer.echo(f"  - has src/: {manifest.has_src_dir}")
    typer.echo(f"  - has tests/: {manifest.has_tests_dir}")


@app.command("discover-theory", hidden=True)
def discover_theory_command(project_root: Path = Path(".")) -> None:
    """Advanced/internal deprecated alias: discover external reference sources and print them."""

    config = load_config(project_root=project_root)
    discovery = discover_external_references(
        project_root=config.project_root,
        explicit_reference_paths=config.reference_paths,
        include_readme_default=config.reference_include_readme_default,
        include_agent_instructions_default=config.reference_include_agent_instructions_default,
        default_readme_patterns=config.reference_default_readme_patterns,
        default_agent_instruction_patterns=config.reference_default_agent_instruction_patterns,
    )
    sources = select_theory_grounding_sources(discovery)
    typer.echo(f"Reference input count: {len(config.reference_paths)}")
    typer.echo(f"Discovered files: {len(discovery.sources)}")
    typer.echo(f"Ingest-eligible files: {len(sources)}")
    for source in sources:
        typer.echo(f"  - {source.relative_path} ({source.extension}, {source.size_bytes} bytes)")


@app.command("discover-references", hidden=True)
def discover_references_command(project_root: Path = Path(".")) -> None:
    """Advanced/internal: discover external reference sources and print them."""

    discover_theory_command(project_root=project_root)


@app.command("generate-snapshot", hidden=True)
def generate_snapshot_command(project_root: Path = Path(".")) -> None:
    """Advanced/internal: generate and write deterministic markdown project snapshot."""

    config = load_config(project_root=project_root)
    manifest = scan_repository(config.project_root, config=config)
    discovery = discover_external_references(
        project_root=config.project_root,
        explicit_reference_paths=config.reference_paths,
        include_readme_default=config.reference_include_readme_default,
        include_agent_instructions_default=config.reference_include_agent_instructions_default,
        default_readme_patterns=config.reference_default_readme_patterns,
        default_agent_instruction_patterns=config.reference_default_agent_instruction_patterns,
    )
    theory_sources = select_theory_grounding_sources(discovery)

    request = GenerationRequest(
        manifest=manifest,
        theory_sources=theory_sources,
        generated_text_language=config.generated_text_language,
    )
    result = generate_project_snapshot(request)
    output_path = write_project_snapshot(result.markdown, config.output_dir / "project_snapshot.md")

    typer.echo(f"Generated snapshot: {output_path}")


def _resolve_runtime_config(
    project_root: Path,
    config_file: Path | None,
    docs_dir: Path | None,
    reference_paths: list[Path] | None,
    reference_dir: Path | None,
    methodology_dir: Path | None,
    output_dir: Path | None,
    site_dir: Path | None,
    use_llm: bool | None,
    debug_artifacts: bool | None,
) -> AppConfig:
    overrides = {
        "project_root": str(project_root.resolve()),
        "docs_dir": str(docs_dir) if docs_dir else None,
        "reference_paths": [str(path) for path in (reference_paths or [])] or None,
        "reference_dir": str(reference_dir) if reference_dir else None,
        "methodology_dir": str(methodology_dir) if methodology_dir else None,
        "output_dir": str(output_dir) if output_dir else None,
        "site_dir": str(site_dir) if site_dir else None,
        "enable_llm": use_llm,
        "debug_artifacts": debug_artifacts,
    }
    return load_config(project_root=project_root, config_file=config_file, cli_overrides=overrides)


def _cli_bool_override(ctx: typer.Context, option_name: str, value: bool | None) -> bool | None:
    """Return a CLI boolean override only when the flag was explicitly provided."""

    source = ctx.get_parameter_source(option_name)
    if source is ParameterSource.COMMANDLINE:
        return value
    return None


def _run_doctor_checks(
    config: AppConfig, use_llm: bool, bootstrap_outputs: bool = False
) -> tuple[list[str], list[str], list[str]]:
    def _is_creatable_under_project_root(path: Path) -> bool:
        if not project_root_valid:
            return False
        try:
            path.resolve().relative_to(config.project_root.resolve())
        except ValueError:
            return False
        return True

    passes: list[str] = []
    warnings: list[str] = []
    failures: list[str] = []
    project_root_valid = config.project_root.exists() and config.project_root.is_dir()
    bootstrap_allowed = bootstrap_outputs and project_root_valid

    if project_root_valid:
        passes.append(f"project_root exists: {config.project_root}")
    else:
        failures.append(f"project_root missing or not a directory: {config.project_root}")

    if config.docs_dir.exists() and config.docs_dir.is_dir():
        passes.append(f"docs_dir exists: {config.docs_dir}")
    elif _is_creatable_under_project_root(config.docs_dir):
        passes.append(f"docs_dir creatable: {config.docs_dir}")
    elif bootstrap_allowed:
        try:
            config.docs_dir.mkdir(parents=True, exist_ok=True)
            passes.append(f"docs_dir created: {config.docs_dir}")
        except OSError as exc:
            failures.append(f"docs_dir missing and could not be created: {config.docs_dir} ({exc})")
    else:
        failures.append(f"docs_dir missing or not a directory: {config.docs_dir}")

    if not config.reference_paths:
        passes.append(
            "reference inputs not explicitly provided (optional explicit inputs disabled)"
        )
    else:
        missing_inputs = 0
        for path in config.reference_paths:
            if path.exists() and (path.is_dir() or path.is_file()):
                passes.append(f"reference input exists: {path}")
            else:
                missing_inputs += 1
                warnings.append(
                    f"reference input missing or unsupported; it will be skipped: {path}"
                )
        if missing_inputs == len(config.reference_paths):
            warnings.append("all explicit reference inputs are unavailable")

    if config.output_dir.parent.exists():
        passes.append(f"output_dir parent exists: {config.output_dir.parent}")
    elif _is_creatable_under_project_root(config.output_dir.parent):
        passes.append(f"output_dir parent creatable: {config.output_dir.parent}")
    elif bootstrap_allowed:
        try:
            config.output_dir.parent.mkdir(parents=True, exist_ok=True)
            passes.append(f"output_dir parent created: {config.output_dir.parent}")
        except OSError as exc:
            message = "output_dir parent missing and could not be created: "
            failures.append(f"{message}{config.output_dir.parent} ({exc})")
    else:
        failures.append(f"output_dir parent missing: {config.output_dir.parent}")

    if config.site_dir.parent.exists():
        passes.append(f"site_dir parent exists: {config.site_dir.parent}")
    elif _is_creatable_under_project_root(config.site_dir.parent):
        passes.append(f"site_dir parent creatable: {config.site_dir.parent}")
    elif bootstrap_allowed:
        try:
            config.site_dir.parent.mkdir(parents=True, exist_ok=True)
            passes.append(f"site_dir parent created: {config.site_dir.parent}")
        except OSError as exc:
            message = "site_dir parent missing and could not be created: "
            failures.append(f"{message}{config.site_dir.parent} ({exc})")
    else:
        failures.append(f"site_dir parent missing: {config.site_dir.parent}")

    if use_llm:
        llm_validation_failures = validate_llm_egress_config(config)
        if llm_validation_failures:
            failures.extend(llm_validation_failures)
        else:
            passes.append("llm model_name configured")
            passes.append("llm base_url configured")

        if config.api_key_mode == "none":
            warnings.append("llm api_key_mode=none; requests will be sent without authentication")
        elif config.api_key_mode == "keyring":
            passes.append("llm api_key_mode=keyring")
            if not config.api_key_secret_name:
                warnings.append("llm keyring mode enabled but api_key_secret_name is not set")
            elif api_key_present(config):
                passes.append("llm keyring secret present")
            else:
                warnings.append("llm keyring secret not present for configured secret name")
        elif config.api_key_env_var:
            passes.append(f"llm api_key_env_var configured: {config.api_key_env_var} (optional)")
            if os.getenv(config.api_key_env_var):
                passes.append(f"llm api key env var present: {config.api_key_env_var}")
            else:
                warnings.append(
                    "llm api key env var not present; requests will be sent "
                    f"without authentication: {config.api_key_env_var}"
                )
        else:
            warnings.append(
                "llm api_key_env_var unset; requests will be sent without authentication unless "
                "your endpoint requires credentials"
            )

    return passes, warnings, failures


def _cleanup_debug_artifacts(output_dir: Path) -> list[Path]:
    removed: list[Path] = []
    for filename in ("prompt_grounding_debug.md", "code_facts_debug.md"):
        path = output_dir / filename
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed


def _run_generation_pipeline(config: AppConfig, mode_label: str) -> None:
    manifest, code_facts_bundle = scan_repository_with_code_facts(
        config.project_root, config=config
    )
    reference_discovery = discover_external_references(
        project_root=config.project_root,
        explicit_reference_paths=config.reference_paths,
        include_readme_default=config.reference_include_readme_default,
        include_agent_instructions_default=config.reference_include_agent_instructions_default,
        default_readme_patterns=config.reference_default_readme_patterns,
        default_agent_instruction_patterns=config.reference_default_agent_instruction_patterns,
    )
    theory_sources = select_theory_grounding_sources(reference_discovery)
    grounded_bundle = build_grounded_context_bundle(theory_sources)
    reference_discovery = mark_reference_parse_statuses(reference_discovery, grounded_bundle)
    routed_alignment_bundle = build_routed_alignment_bundle(
        discovery=reference_discovery,
        manifest=manifest,
        code_facts_bundle=code_facts_bundle,
        grounded_bundle=grounded_bundle,
    )
    llm_route_materials = build_routed_llm_material_bundle(
        discovery=reference_discovery,
        grounded_bundle=grounded_bundle,
        routed_alignment=routed_alignment_bundle,
    )

    snapshot = generate_project_snapshot(
        GenerationRequest(
            manifest=manifest,
            theory_sources=theory_sources,
            generated_text_language=config.generated_text_language,
        )
    )
    snapshot_path = write_project_snapshot(
        snapshot.markdown, config.output_dir / "project_snapshot.md"
    )

    try:
        sections = generate_sections(
            manifest=manifest,
            theory_sources=theory_sources,
            config=config,
            code_facts_bundle=code_facts_bundle,
            grounded_bundle=grounded_bundle,
            routed_alignment_bundle=routed_alignment_bundle,
            llm_route_materials=llm_route_materials,
        )
    except LLMServiceError as exc:
        typer.echo(f"FAIL: {exc}")
        raise typer.Exit(code=1) from exc

    written_paths = write_generated_sections(sections=sections, output_dir=config.output_dir)
    deterministic_context = DeterministicContext(
        manifest=manifest,
        theory_sources=theory_sources,
        code_facts_bundle=code_facts_bundle,
        grounded_bundle=grounded_bundle,
        routed_alignment=routed_alignment_bundle,
    )
    home_path = config.docs_dir / "index.md"
    existing_home = home_path.read_text(encoding="utf-8") if home_path.exists() else None
    if should_overwrite_managed_page(existing_home):
        home_path.parent.mkdir(parents=True, exist_ok=True)
        home_path.write_text(
            render_home_page(
                project_root=config.project_root,
                ctx=deterministic_context,
                generated_text_language=config.generated_text_language,
            ),
            encoding="utf-8",
        )

    project_brief_path = config.docs_dir / "context" / "project_brief.md"
    existing_brief = (
        project_brief_path.read_text(encoding="utf-8") if project_brief_path.exists() else None
    )
    if should_overwrite_managed_page(existing_brief):
        project_brief_path.parent.mkdir(parents=True, exist_ok=True)
        project_brief_path.write_text(
            render_project_brief_page(
                project_root=config.project_root,
                ctx=deterministic_context,
                generated_text_language=config.generated_text_language,
            ),
            encoding="utf-8",
        )
    external_references_path = config.docs_dir / "context" / "external_references.md"
    existing_external_references = (
        external_references_path.read_text(encoding="utf-8")
        if external_references_path.exists()
        else None
    )
    if should_overwrite_managed_page(existing_external_references):
        external_references_path.parent.mkdir(parents=True, exist_ok=True)
        external_references_path.write_text(
            render_external_references_page(
                discovery=reference_discovery,
                grounded_bundle=grounded_bundle,
                routed_alignment=routed_alignment_bundle,
                supported_ingest_extensions=supported_ingest_extensions(),
                generated_text_language=config.generated_text_language,
            ),
            encoding="utf-8",
        )

    readme_path = write_generated_readme(
        output_dir=config.output_dir,
        include_debug_artifacts=config.debug_artifacts,
        generated_text_language=config.generated_text_language,
    )
    removed_debug_artifacts: list[Path] = []
    prompt_debug_path: Path | None = None
    code_facts_debug_path: Path | None = None
    if config.debug_artifacts:
        prompt_debug_path = write_prompt_grounding_debug_artifact(
            markdown=render_prompt_grounding_debug_markdown(
                grounded_bundle, manifest=manifest, code_facts_bundle=code_facts_bundle
            ),
            output_dir=config.output_dir,
        )
        code_facts_debug_path = write_code_facts_debug_artifact(
            markdown=render_code_facts_debug_markdown(code_facts_bundle),
            output_dir=config.output_dir,
        )
    else:
        removed_debug_artifacts = _cleanup_debug_artifacts(config.output_dir)
    try:
        site_path = build_mkdocs_site(
            config.project_root,
            config.site_dir,
            docs_dir=config.docs_dir,
            output_dir=config.output_dir,
        )
    except (NavScaffoldError, RuntimeError, FileNotFoundError) as exc:
        typer.echo(f"FAIL: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo("Documentation generation complete")
    typer.echo("-------------------------------")
    typer.echo(f"Workflow mode: {mode_label}")
    typer.echo(f"Repo path: {config.project_root}")
    typer.echo(f"Output docs path: {config.output_dir}")
    typer.echo(f"Generated site path: {site_path}")
    typer.echo(f"LLM mode: {'enabled' if config.enable_llm else 'deterministic-offline'}")
    typer.echo(f"Debug artifacts: {'enabled' if config.debug_artifacts else 'disabled'}")
    unparsed_count = len(
        [item for item in reference_discovery.sources if item.parse_status == "ingestible_unparsed"]
    )
    typer.echo(
        "External references summary: "
        f"explicit_inputs={len(config.reference_paths)}, "
        f"discovered={len(reference_discovery.sources)}, "
        f"parsed={len(grounded_bundle.documents)}, "
        f"unparsed={unparsed_count}"
    )
    typer.echo(
        "Code facts summary: "
        f"modules={len(code_facts_bundle.modules)}, symbols={len(code_facts_bundle.symbols)}, "
        f"imports={len(code_facts_bundle.imports)}, "
        f"entrypoints={len(code_facts_bundle.detected_entrypoints)}"
    )
    typer.echo("Artifacts:")
    typer.echo(f"  - {snapshot_path}")
    for path in written_paths:
        typer.echo(f"  - {path}")
    typer.echo(f"  - {readme_path}")
    typer.echo(f"  - {home_path}")
    typer.echo(f"  - {project_brief_path}")
    typer.echo(f"  - {external_references_path}")
    if prompt_debug_path and code_facts_debug_path:
        typer.echo(f"  - {prompt_debug_path}")
        typer.echo(f"  - {code_facts_debug_path}")
    elif removed_debug_artifacts:
        typer.echo("Debug cleanup:")
        for path in removed_debug_artifacts:
            typer.echo(f"  - removed stale debug artifact: {path}")


@app.command("doctor")
def doctor_command(
    ctx: typer.Context,
    project_root: Path = Path("."),
    config_file: Annotated[
        Path | None,
        typer.Option(
            "--config-file", help=f"Path to config file (default: {DEFAULT_CONFIG_FILE_NAME})."
        ),
    ] = None,
    docs_dir: Annotated[Path | None, typer.Option("--docs-dir", help="Override docs dir.")] = None,
    reference_path: Annotated[
        list[Path] | None,
        typer.Option(
            "--reference-path",
            help="Explicit external reference path (file or directory). Repeatable.",
        ),
    ] = None,
    reference_dir: Annotated[
        Path | None,
        typer.Option("--reference-dir", help="Optional directory of external reference materials."),
    ] = None,
    methodology_dir: Annotated[
        Path | None,
        typer.Option("--methodology-dir", help="Deprecated alias for --reference-dir."),
    ] = None,
    output_dir: Annotated[
        Path | None, typer.Option("--output-dir", help="Override output dir.")
    ] = None,
    site_dir: Annotated[Path | None, typer.Option("--site-dir", help="Override site dir.")] = None,
    use_llm: Annotated[
        bool | None,
        typer.Option("--use-llm", help="Enable LLM checks (model/base URL; API key is optional)."),
    ] = None,
    privacy: Annotated[
        bool,
        typer.Option("--privacy", help="Print privacy/egress summary lines."),
    ] = False,
) -> None:
    """Validate workflow configuration, external references, and required paths."""

    config = _resolve_runtime_config(
        project_root=project_root,
        config_file=config_file,
        docs_dir=docs_dir,
        reference_paths=reference_path,
        reference_dir=reference_dir,
        methodology_dir=methodology_dir,
        output_dir=output_dir,
        site_dir=site_dir,
        use_llm=_cli_bool_override(ctx, "use_llm", use_llm),
        debug_artifacts=None,
    )
    for warning in config.deprecation_warnings:
        typer.echo(f"WARN: {warning}")

    passes, warnings, failures = _run_doctor_checks(config, config.enable_llm)

    typer.echo("Doctor report")
    typer.echo("-------------")
    for line in passes:
        typer.echo(f"PASS: {line}")
    for line in warnings:
        typer.echo(f"WARN: {line}")
    for line in failures:
        typer.echo(f"FAIL: {line}")

    if privacy:
        report = build_privacy_report(config, config.enable_llm)
        typer.echo("Privacy")
        typer.echo("-------")
        typer.echo(f"MODE: {report.mode}")
        typer.echo(f"GUARANTEE: {report.guarantee}")
        if report.allowed_egress_endpoints:
            for endpoint in report.allowed_egress_endpoints:
                typer.echo(f"ALLOWED_EGRESS_ENDPOINT: {endpoint}")
        else:
            typer.echo("ALLOWED_EGRESS_ENDPOINT: none")

    if failures:
        raise typer.Exit(code=1)


@app.command("generate-sections", hidden=True)
def generate_sections_command(
    ctx: typer.Context,
    project_root: Path = Path("."),
    use_llm: Annotated[
        bool | None, typer.Option("--use-llm", help="Enable OpenAI-compatible LLM mode.")
    ] = None,
    reference_path: Annotated[
        list[Path] | None,
        typer.Option(
            "--reference-path",
            help="Explicit external reference path (file or directory). Repeatable.",
        ),
    ] = None,
    reference_dir: Annotated[
        Path | None,
        typer.Option("--reference-dir", help="Optional directory of external reference materials."),
    ] = None,
    methodology_dir: Annotated[
        Path | None,
        typer.Option("--methodology-dir", help="Deprecated alias for --reference-dir."),
    ] = None,
    output_dir: Annotated[
        Path | None, typer.Option("--output-dir", help="Override generated docs dir.")
    ] = None,
    debug_artifacts: Annotated[
        bool | None,
        typer.Option(
            "--debug-artifacts/--no-debug-artifacts",
            help="Write or skip debug artifact pages under generated output.",
        ),
    ] = None,
) -> None:
    """Advanced/internal: generate markdown sections using deterministic or LLM mode."""

    config = _resolve_runtime_config(
        project_root=project_root,
        config_file=None,
        docs_dir=None,
        reference_paths=reference_path,
        reference_dir=reference_dir,
        methodology_dir=methodology_dir,
        output_dir=output_dir,
        site_dir=None,
        use_llm=_cli_bool_override(ctx, "use_llm", use_llm),
        debug_artifacts=_cli_bool_override(ctx, "debug_artifacts", debug_artifacts),
    )
    for warning in config.deprecation_warnings:
        typer.echo(f"WARN: {warning}")

    if config.enable_llm:
        passes, warnings, failures = _run_doctor_checks(config, config.enable_llm)
        for line in passes:
            typer.echo(f"PASS: {line}")
        for line in warnings:
            typer.echo(f"WARN: {line}")
        for line in failures:
            typer.echo(f"FAIL: {line}")
        if failures:
            raise typer.Exit(code=1)

    manifest, code_facts_bundle = scan_repository_with_code_facts(
        config.project_root, config=config
    )
    discovery = discover_external_references(
        project_root=config.project_root,
        explicit_reference_paths=config.reference_paths,
        include_readme_default=config.reference_include_readme_default,
        include_agent_instructions_default=config.reference_include_agent_instructions_default,
        default_readme_patterns=config.reference_default_readme_patterns,
        default_agent_instruction_patterns=config.reference_default_agent_instruction_patterns,
    )
    theory_sources = select_theory_grounding_sources(discovery)
    grounded_bundle = build_grounded_context_bundle(theory_sources)
    discovery = mark_reference_parse_statuses(discovery, grounded_bundle)
    routed_alignment_bundle = build_routed_alignment_bundle(
        discovery=discovery,
        manifest=manifest,
        code_facts_bundle=code_facts_bundle,
        grounded_bundle=grounded_bundle,
    )
    llm_route_materials = build_routed_llm_material_bundle(
        discovery=discovery,
        grounded_bundle=grounded_bundle,
        routed_alignment=routed_alignment_bundle,
    )

    try:
        sections = generate_sections(
            manifest=manifest,
            theory_sources=theory_sources,
            config=config,
            code_facts_bundle=code_facts_bundle,
            grounded_bundle=grounded_bundle,
            routed_alignment_bundle=routed_alignment_bundle,
            llm_route_materials=llm_route_materials,
        )
    except LLMServiceError as exc:
        typer.echo(f"FAIL: {exc}")
        raise typer.Exit(code=1) from exc

    written_paths = write_generated_sections(sections=sections, output_dir=config.output_dir)
    readme_path = write_generated_readme(
        output_dir=config.output_dir,
        include_debug_artifacts=config.debug_artifacts,
        generated_text_language=config.generated_text_language,
    )
    prompt_debug_path: Path | None = None
    code_facts_debug_path: Path | None = None
    removed_debug_artifacts: list[Path] = []
    if config.debug_artifacts:
        prompt_debug_path = write_prompt_grounding_debug_artifact(
            markdown=render_prompt_grounding_debug_markdown(
                grounded_bundle, manifest=manifest, code_facts_bundle=code_facts_bundle
            ),
            output_dir=config.output_dir,
        )
        code_facts_debug_path = write_code_facts_debug_artifact(
            markdown=render_code_facts_debug_markdown(code_facts_bundle),
            output_dir=config.output_dir,
        )
    else:
        removed_debug_artifacts = _cleanup_debug_artifacts(config.output_dir)

    typer.echo(f"Generated sections mode: {'llm' if config.enable_llm else 'deterministic'}")
    typer.echo(
        "Grounded external reference context: "
        f"documents={len(grounded_bundle.documents)}, chunks={len(grounded_bundle.chunks)}, "
        f"unparsed={len(grounded_bundle.unparsed_sources)}"
    )
    typer.echo(summarize_code_facts(code_facts_bundle))
    typer.echo(f"Debug artifacts: {'enabled' if config.debug_artifacts else 'disabled'}")
    for path in written_paths:
        typer.echo(f"  - {path}")
    typer.echo(f"  - {readme_path}")
    if prompt_debug_path and code_facts_debug_path:
        typer.echo(f"  - {prompt_debug_path}")
        typer.echo(f"  - {code_facts_debug_path}")
    for path in removed_debug_artifacts:
        typer.echo(f"  - removed stale debug artifact: {path}")


@app.command("generate-docs")
def generate_docs_command(
    ctx: typer.Context,
    project_root: Path = Path("."),
    config_file: Annotated[
        Path | None,
        typer.Option(
            "--config-file", help=f"Path to config file (default: {DEFAULT_CONFIG_FILE_NAME})."
        ),
    ] = None,
    docs_dir: Annotated[Path | None, typer.Option("--docs-dir", help="Override docs dir.")] = None,
    reference_path: Annotated[
        list[Path] | None,
        typer.Option(
            "--reference-path",
            help="Explicit external reference path (file or directory). Repeatable.",
        ),
    ] = None,
    reference_dir: Annotated[
        Path | None,
        typer.Option("--reference-dir", help="Optional directory of external reference materials."),
    ] = None,
    methodology_dir: Annotated[
        Path | None,
        typer.Option("--methodology-dir", help="Deprecated alias for --reference-dir."),
    ] = None,
    output_dir: Annotated[
        Path | None, typer.Option("--output-dir", help="Override output dir.")
    ] = None,
    site_dir: Annotated[Path | None, typer.Option("--site-dir", help="Override site dir.")] = None,
    use_llm: Annotated[
        bool | None, typer.Option("--use-llm", help="Enable OpenAI-compatible LLM mode.")
    ] = None,
    debug_artifacts: Annotated[
        bool | None,
        typer.Option(
            "--debug-artifacts/--no-debug-artifacts",
            help="Write or skip debug artifact pages under generated output.",
        ),
    ] = None,
) -> None:
    """Preferred workflow: deterministic docs/site generation with optional LLM mode."""

    config = _resolve_runtime_config(
        project_root=project_root,
        config_file=config_file,
        docs_dir=docs_dir,
        reference_paths=reference_path,
        reference_dir=reference_dir,
        methodology_dir=methodology_dir,
        output_dir=output_dir,
        site_dir=site_dir,
        use_llm=_cli_bool_override(ctx, "use_llm", use_llm),
        debug_artifacts=_cli_bool_override(ctx, "debug_artifacts", debug_artifacts),
    )
    for warning in config.deprecation_warnings:
        typer.echo(f"WARN: {warning}")

    passes, warnings, failures = _run_doctor_checks(
        config, config.enable_llm, bootstrap_outputs=True
    )
    for line in passes:
        typer.echo(f"PASS: {line}")
    for line in warnings:
        typer.echo(f"WARN: {line}")
    for line in failures:
        typer.echo(f"FAIL: {line}")
    if failures:
        raise typer.Exit(code=1)

    _run_generation_pipeline(config=config, mode_label="full-generate-docs")


@app.command("update-docs")
def update_docs_command(
    ctx: typer.Context,
    project_root: Path = Path("."),
    config_file: Annotated[
        Path | None,
        typer.Option(
            "--config-file", help=f"Path to config file (default: {DEFAULT_CONFIG_FILE_NAME})."
        ),
    ] = None,
    docs_dir: Annotated[Path | None, typer.Option("--docs-dir", help="Override docs dir.")] = None,
    reference_path: Annotated[
        list[Path] | None,
        typer.Option(
            "--reference-path",
            help="Explicit external reference path (file or directory). Repeatable.",
        ),
    ] = None,
    reference_dir: Annotated[
        Path | None,
        typer.Option("--reference-dir", help="Optional directory of external reference materials."),
    ] = None,
    methodology_dir: Annotated[
        Path | None,
        typer.Option("--methodology-dir", help="Deprecated alias for --reference-dir."),
    ] = None,
    output_dir: Annotated[
        Path | None, typer.Option("--output-dir", help="Override output dir.")
    ] = None,
    site_dir: Annotated[Path | None, typer.Option("--site-dir", help="Override site dir.")] = None,
    use_llm: Annotated[
        bool | None, typer.Option("--use-llm", help="Enable OpenAI-compatible LLM mode.")
    ] = None,
    debug_artifacts: Annotated[
        bool | None,
        typer.Option(
            "--debug-artifacts/--no-debug-artifacts",
            help="Write or skip debug artifact pages under generated output.",
        ),
    ] = None,
) -> None:
    """Conservative update workflow with deterministic git-diff planning summary."""

    config = _resolve_runtime_config(
        project_root=project_root,
        config_file=config_file,
        docs_dir=docs_dir,
        reference_paths=reference_path,
        reference_dir=reference_dir,
        methodology_dir=methodology_dir,
        output_dir=output_dir,
        site_dir=site_dir,
        use_llm=_cli_bool_override(ctx, "use_llm", use_llm),
        debug_artifacts=_cli_bool_override(ctx, "debug_artifacts", debug_artifacts),
    )
    for warning in config.deprecation_warnings:
        typer.echo(f"WARN: {warning}")

    passes, warnings, failures = _run_doctor_checks(
        config, config.enable_llm, bootstrap_outputs=True
    )
    for line in passes:
        typer.echo(f"PASS: {line}")
    for line in warnings:
        typer.echo(f"WARN: {line}")
    for line in failures:
        typer.echo(f"FAIL: {line}")
    if failures:
        raise typer.Exit(code=1)

    explicit_dirs_relative: list[str] = []
    explicit_files_relative: list[str] = []
    out_of_repo_paths: list[str] = []
    for path in config.reference_paths:
        try:
            relative = str(path.relative_to(config.project_root))
        except ValueError:
            out_of_repo_paths.append(str(path))
            continue
        if path.is_dir():
            explicit_dirs_relative.append(relative)
        elif path.is_file():
            explicit_files_relative.append(relative)
    default_targets_relative: list[str] = []
    default_discovery = discover_external_references(
        project_root=config.project_root,
        explicit_reference_paths=config.reference_paths,
        include_readme_default=config.reference_include_readme_default,
        include_agent_instructions_default=config.reference_include_agent_instructions_default,
        default_readme_patterns=config.reference_default_readme_patterns,
        default_agent_instruction_patterns=config.reference_default_agent_instruction_patterns,
    )
    for source in default_discovery.sources:
        if source.origin != "default":
            continue
        try:
            relative = str(source.path.relative_to(config.project_root))
        except ValueError:
            continue
        default_targets_relative.append(relative)

    changed_files = list_changed_files(config.project_root)
    plan = build_update_plan(
        changed_files=changed_files,
        explicit_reference_roots_relative=sorted(set(explicit_dirs_relative)),
        explicit_reference_files_relative=sorted(set(explicit_files_relative)),
        default_reference_targets_relative=sorted(set(default_targets_relative)),
        out_of_repo_reference_paths=sorted(set(out_of_repo_paths)),
    )

    typer.echo(render_update_plan(plan))
    _run_generation_pipeline(config=config, mode_label="update-docs")


@app.command("ground-reference", hidden=True)
def ground_reference_command(
    project_root: Path = Path("."),
    reference_path: Annotated[
        list[Path] | None,
        typer.Option(
            "--reference-path",
            help="Explicit external reference path (file or directory). Repeatable.",
        ),
    ] = None,
    reference_dir: Annotated[
        Path | None,
        typer.Option("--reference-dir", help="Optional directory of external reference materials."),
    ] = None,
    methodology_dir: Annotated[
        Path | None,
        typer.Option("--methodology-dir", help="Deprecated alias for --reference-dir."),
    ] = None,
    write_debug_artifact: Annotated[
        bool,
        typer.Option(
            "--write-debug-artifact/--no-write-debug-artifact",
            help="Write docs/generated/reference_grounding.md debug artifact.",
        ),
    ] = True,
) -> None:
    """Advanced/internal: ingest/chunk external reference files into grounded context."""

    config = load_config(
        project_root=project_root,
        cli_overrides={
            "reference_paths": [str(path) for path in (reference_path or [])] or None,
            "reference_dir": str(reference_dir) if reference_dir else None,
            "methodology_dir": str(methodology_dir) if methodology_dir else None,
        },
    )
    for warning in config.deprecation_warnings:
        typer.echo(f"WARN: {warning}")
    discovery = discover_external_references(
        project_root=config.project_root,
        explicit_reference_paths=config.reference_paths,
        include_readme_default=config.reference_include_readme_default,
        include_agent_instructions_default=config.reference_include_agent_instructions_default,
        default_readme_patterns=config.reference_default_readme_patterns,
        default_agent_instruction_patterns=config.reference_default_agent_instruction_patterns,
    )
    theory_sources = select_theory_grounding_sources(discovery)
    bundle = build_grounded_context_bundle(theory_sources)
    discovery = mark_reference_parse_statuses(discovery, bundle)

    typer.echo(f"Discovered files: {len(discovery.sources)}")
    typer.echo(f"Ingest-eligible files: {len(discovery.ingest_eligible_materials)}")
    typer.echo(summarize_grounded_context(bundle))

    if write_debug_artifact:
        debug_markdown = render_grounding_debug_markdown(theory_sources, bundle)
        debug_path = write_markdown_artifact(
            markdown=debug_markdown,
            output_path=config.output_dir / "reference_grounding.md",
        )
        typer.echo(f"Debug artifact: {debug_path}")


@app.command("ground-methodology", hidden=True, deprecated=True)
def ground_methodology_command(
    project_root: Path = Path("."),
    reference_path: Annotated[
        list[Path] | None,
        typer.Option(
            "--reference-path",
            help="Explicit external reference path (file or directory). Repeatable.",
        ),
    ] = None,
    reference_dir: Annotated[
        Path | None,
        typer.Option("--reference-dir", help="Optional directory of external reference materials."),
    ] = None,
    methodology_dir: Annotated[
        Path | None,
        typer.Option("--methodology-dir", help="Deprecated alias for --reference-dir."),
    ] = None,
    write_debug_artifact: Annotated[
        bool,
        typer.Option(
            "--write-debug-artifact/--no-write-debug-artifact",
            help="Write docs/generated/reference_grounding.md debug artifact.",
        ),
    ] = True,
) -> None:
    """Deprecated alias for `ground-reference`."""

    typer.echo("WARN: `ground-methodology` is deprecated. Use `ground-reference`.")
    ground_reference_command(
        project_root=project_root,
        reference_path=reference_path,
        reference_dir=reference_dir,
        methodology_dir=methodology_dir,
        write_debug_artifact=write_debug_artifact,
    )


if __name__ == "__main__":
    app()
