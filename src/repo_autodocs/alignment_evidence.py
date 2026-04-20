"""Deterministic typed evidence atom inventory for routed alignment."""

from __future__ import annotations

from collections.abc import Iterable

from repo_autodocs.config_fields import FIELDS
from repo_autodocs.config_loader import DEFAULT_CONFIG_FILE_NAME
from repo_autodocs.models import CodeFactsBundle, RepoManifest
from repo_autodocs.repo_ignore import DEFAULT_REPO_ANALYSIS_IGNORE_PATTERNS
from repo_autodocs.sections import SECTION_TO_FILENAME

from .alignment_models import EvidenceAtom

_ENV_COMPAT_ALIASES: tuple[str, ...] = (
    "REPO_AUTODOCS_REFERENCE_DIR",
    "REPO_AUTODOCS_METHODOLOGY_DIR",
    "REPO_AUTODOCS_GENERATED_DOCS_DIR",
)


def _iter_cli_commands() -> tuple[str, ...]:
    from repo_autodocs.cli import app

    commands: list[str] = []
    for command in app.registered_commands:
        if command.name:
            commands.append(command.name)
    return tuple(sorted(set(commands)))


def _iter_route_names() -> tuple[str, ...]:
    return (
        "reference_alignment",
        "agent_instruction_alignment",
        "readme_claim_alignment",
    )


def _iter_ignore_targets() -> tuple[str, ...]:
    return tuple(pattern for pattern in DEFAULT_REPO_ANALYSIS_IGNORE_PATTERNS if pattern)


def build_evidence_atoms(
    manifest: RepoManifest, code_facts_bundle: CodeFactsBundle
) -> list[EvidenceAtom]:
    items: list[EvidenceAtom] = []

    def add(
        kind: str, value: str, source: str, category: str, excerpt: str, **metadata: object
    ) -> None:
        evidence_id = f"{kind}:{value}".replace(" ", "_").lower()
        items.append(
            EvidenceAtom(
                evidence_id=evidence_id,
                evidence_kind=kind,
                source_path=source,
                source_category=category,
                display_anchor=value,
                normalized_value=value.lower(),
                raw_excerpt=excerpt,
                metadata=metadata,
            )
        )

    for command in _iter_cli_commands():
        add("cli_command", command, "src/repo_autodocs/cli.py", "cli", f"docforge-local {command}")
        add(
            "cli_subcommand",
            command,
            "src/repo_autodocs/cli.py",
            "cli",
            f"docforge-local {command}",
        )

    for field in FIELDS:
        add(
            "config_field",
            field.key,
            "src/repo_autodocs/config_fields.py",
            "config",
            field.description,
        )
        for enum in field.enum_values:
            add(
                "config_enum_value",
                f"{field.key}:{enum}",
                "src/repo_autodocs/config_fields.py",
                "config",
                f"{field.key} supports {enum}",
                field_key=field.key,
                enum_value=enum,
            )
        for alias_path in field.legacy_paths:
            alias = ".".join(alias_path)
            add(
                "config_alias",
                alias,
                "src/repo_autodocs/config_fields.py",
                "config",
                f"legacy alias for {field.key}",
                canonical=field.key,
            )
            add(
                "config_alias_maps_to_field",
                f"{alias}->{field.key}",
                "src/repo_autodocs/config_fields.py",
                "config",
                f"legacy alias {alias} maps to {field.key}",
                alias=alias,
                canonical=field.key,
            )
            if alias in {"reference_dir", "methodology_dir"}:
                add(
                    "compatibility_alias",
                    alias,
                    "src/repo_autodocs/config_fields.py",
                    "compatibility",
                    f"deprecated compatibility alias: {alias}",
                )
        add(
            "env_var",
            f"REPO_AUTODOCS_{field.key.upper()}",
            "src/repo_autodocs/config_loader.py",
            "config_env",
            f"Environment variable for {field.key}",
            canonical=field.key,
        )

    for env_name in _ENV_COMPAT_ALIASES:
        add(
            "env_var",
            env_name,
            "src/repo_autodocs/config_loader.py",
            "config_env",
            f"compatibility environment variable {env_name}",
            compatibility=True,
        )

    for _, filename in SECTION_TO_FILENAME.items():
        add(
            "generated_page",
            filename.removesuffix(".md"),
            "src/repo_autodocs/sections.py",
            "generated_output",
            f"generated/{filename}",
        )

    for route in _iter_route_names():
        add("route_name", route, "src/repo_autodocs/alignment.py", "routing", route)

    for target in _iter_ignore_targets():
        add(
            "ignore_policy_excludes_target",
            target,
            "src/repo_autodocs/repo_ignore.py",
            "policy",
            f"default repo-analysis ignore pattern: {target}",
        )

    add(
        "ignore_policy_reference_selection",
        "explicit_reference_paths_independent",
        "src/repo_autodocs/theory.py",
        "policy",
        "Explicit reference path selection is independent from repo-analysis ignores.",
        relation="explicit_reference_paths_independent",
    )
    add(
        "ignore_policy_reference_selection",
        "default_reference_targets_independent",
        "src/repo_autodocs/theory.py",
        "policy",
        "Default README/agent target selection is independent from repo-analysis ignores.",
        relation="default_reference_targets_independent",
    )
    for alias in ("reference_dir", "methodology_dir"):
        add(
            "compatibility_alias_maps_to_first_reference_path",
            f"{alias}->first_explicit_reference_path",
            "src/repo_autodocs/config_loader.py",
            "compatibility",
            f"Compatibility alias {alias} maps to first explicit reference path.",
            alias=alias,
            target="first_explicit_reference_path",
        )

    for d in manifest.top_level_directories:
        add(
            "repo_scan_fact",
            d,
            str(manifest.project_root),
            "repo_scan",
            f"top-level directory: {d}",
        )
    for f in manifest.top_level_files:
        add("repo_scan_fact", f, str(manifest.project_root), "repo_scan", f"top-level file: {f}")
    for item in manifest.textual_evidence:
        add(
            "module_fact", item.relative_path, item.relative_path, item.category, item.excerpt[:220]
        )

    for ep in _dedupe_values(code_facts_bundle.detected_entrypoints):
        add("entrypoint", ep, "code_facts", "runtime", ep)
    for hint in _dedupe_values(code_facts_bundle.framework_hints):
        add("framework_hint", hint, "code_facts", "runtime", hint)
    for module in code_facts_bundle.modules:
        add("module_fact", module.module_name, module.relative_path, "module", module.module_name)

    add(
        "compatibility_alias",
        "ground-methodology",
        "src/repo_autodocs/cli.py",
        "compatibility",
        "deprecated command alias ground-methodology",
    )
    add(
        "config_alias",
        DEFAULT_CONFIG_FILE_NAME,
        "src/repo_autodocs/config_loader.py",
        "config",
        "default project config filename",
    )

    return _dedupe_atoms(items)


def _dedupe_values(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in items:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return tuple(out)


def _dedupe_atoms(items: list[EvidenceAtom]) -> list[EvidenceAtom]:
    seen: set[str] = set()
    out: list[EvidenceAtom] = []
    for item in items:
        if item.evidence_id in seen:
            continue
        seen.add(item.evidence_id)
        out.append(item)
    return out
