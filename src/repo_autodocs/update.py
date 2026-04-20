"""Incremental update planning helpers for update-docs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class UpdatePlan:
    """Conservative update plan derived from changed paths."""

    changed_files: list[str] = field(default_factory=list)
    can_use_git_diff: bool = False
    full_regeneration: bool = True
    source_changed: bool = False
    reference_changed: bool = False
    docs_or_config_changed: bool = False
    out_of_repo_reference_paths: list[str] = field(default_factory=list)
    reason: str = ""


def _is_under(path: str, prefix: str) -> bool:
    normalized = path.replace("\\", "/")
    clean_prefix = prefix.strip("/")
    if not clean_prefix:
        return False
    return normalized == clean_prefix or normalized.startswith(f"{clean_prefix}/")


def build_update_plan(
    changed_files: list[str] | None,
    *,
    explicit_reference_roots_relative: list[str],
    explicit_reference_files_relative: list[str],
    default_reference_targets_relative: list[str],
    out_of_repo_reference_paths: list[str],
) -> UpdatePlan:
    """Build a readable conservative update plan from changed file list."""

    if changed_files is None:
        return UpdatePlan(
            changed_files=[],
            can_use_git_diff=False,
            full_regeneration=True,
            reason="Git diff unavailable; using full regeneration.",
        )

    source_changed = any(_is_under(path, "src") for path in changed_files)
    reference_changed = False
    for path in changed_files:
        if any(_is_under(path, prefix) for prefix in explicit_reference_roots_relative):
            reference_changed = True
            break
        if path in explicit_reference_files_relative or path in default_reference_targets_relative:
            reference_changed = True
            break
    docs_or_config_changed = any(
        (
            _is_under(path, "docs")
            and not any(_is_under(path, prefix) for prefix in explicit_reference_roots_relative)
            and path not in explicit_reference_files_relative
            and path not in default_reference_targets_relative
        )
        or path in {"mkdocs.yml", "docforge.toml", "pyproject.toml", ".env", ".env.example"}
        for path in changed_files
    )

    if not changed_files:
        reason = "No git-tracked changes detected; performing full regeneration for consistency."
    elif docs_or_config_changed:
        reason = "Docs/config files changed; forcing full regeneration."
    elif source_changed and reference_changed:
        reason = (
            "Source and external reference files changed; regenerating with both inputs refreshed."
        )
    elif source_changed:
        reason = "Source files changed under src/; regenerating code facts and documentation."
    elif reference_changed:
        reason = (
            "External reference files changed; "
            "regrounding references and regenerating documentation."
        )
    else:
        reason = (
            "Only unrelated files changed; update-docs still performs full regeneration "
            "to keep updates deterministic."
        )

    return UpdatePlan(
        changed_files=changed_files,
        can_use_git_diff=True,
        full_regeneration=True,
        source_changed=source_changed,
        reference_changed=reference_changed,
        docs_or_config_changed=docs_or_config_changed,
        out_of_repo_reference_paths=out_of_repo_reference_paths,
        reason=reason,
    )


def render_update_plan(plan: UpdatePlan) -> str:
    """Render update plan summary for CLI output."""

    lines = [
        "Update planning summary",
        "-----------------------",
        f"Git diff available: {'yes' if plan.can_use_git_diff else 'no'}",
        f"Changed files detected: {len(plan.changed_files)}",
        f"source_changed: {plan.source_changed}",
        f"reference_changed: {plan.reference_changed}",
        f"docs_or_config_changed: {plan.docs_or_config_changed}",
        f"full_regeneration: {plan.full_regeneration}",
        f"reason: {plan.reason}",
    ]

    if plan.changed_files:
        lines.append("changed_file_paths:")
        lines.extend(f"  - {path}" for path in plan.changed_files)
    if plan.out_of_repo_reference_paths:
        lines.append("reference_change_detection_limitations:")
        lines.extend(
            f"  - outside project root (git diff unavailable): {path}"
            for path in plan.out_of_repo_reference_paths
        )

    return "\n".join(lines)
