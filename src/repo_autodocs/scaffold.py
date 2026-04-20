"""Scaffolding helpers for MkDocs nav-first bootstrap behavior."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class NavScaffoldResult:
    """Result details for nav-target scaffolding."""

    docs_dir: Path
    required_markdown_paths: list[Path]
    created_paths: list[Path]


class NavScaffoldError(RuntimeError):
    """Raised when MkDocs nav scaffolding or validation fails."""


@dataclass(slots=True)
class EffectiveMkDocsConfig:
    """MkDocs config file selected or synthesized for a build run."""

    path: Path
    is_temporary: bool


_EXPLICIT_REASONS: dict[str, str] = {
    "index.md": "Home page was missing from the repository docs tree on first run.",
    "context/project_brief.md": "Project brief was not provided by the repository author.",
    "context/external_references.md": (
        "External reference materials are optional and were not provided for this run."
    ),
}

_DEFAULT_NAV: list[dict[str, Any]] = [
    {"Home": "index.md"},
    {
        "Context": [
            {"Project Brief": "context/project_brief.md"},
            {"External References": "context/external_references.md"},
        ]
    },
    {
        "Generated": [
            {"Project Snapshot": "generated/project_snapshot.md"},
            {"Overview": "generated/overview.md"},
            {"Architecture": "generated/architecture.md"},
            {"Code Structure": "generated/code_structure.md"},
            {"Runtime Entrypoints": "generated/runtime_entrypoints.md"},
            {"Reference Alignment": "generated/reference_alignment.md"},
            {"Agent Instruction Alignment": "generated/agent_instruction_alignment.md"},
            {"README Claim Alignment": "generated/readme_claim_alignment.md"},
            {"Theory Alignment (Deprecated Compatibility)": "generated/theory_alignment.md"},
        ]
    },
]


def scaffold_missing_nav_pages(
    project_root: Path, mkdocs_config_path: Path, docs_dir: Path | None = None
) -> NavScaffoldResult:
    """Create placeholder pages for missing markdown files referenced by MkDocs nav."""

    if not mkdocs_config_path.exists():
        raise NavScaffoldError(
            "Missing MkDocs config file at "
            f"{mkdocs_config_path}. Cannot build site without mkdocs.yml."
        )

    config_data = _load_mkdocs_config(mkdocs_config_path)
    docs_dir = _resolve_docs_dir(project_root, config_data, docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)

    nav_targets = _extract_nav_markdown_targets(config_data.get("nav"))
    nav_target_paths = {path.as_posix() for path, _ in nav_targets}
    if "index.md" not in nav_target_paths:
        nav_targets.insert(0, (Path("index.md"), "Home"))
    required_paths = [docs_dir / rel_path for rel_path, _ in nav_targets]

    created_paths: list[Path] = []
    for rel_path, nav_title in nav_targets:
        absolute_path = docs_dir / rel_path
        if absolute_path.exists():
            continue
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        placeholder_markdown = _render_placeholder_markdown(
            title=nav_title or _title_from_path(rel_path),
            reason=_placeholder_reason(rel_path),
            relative_path=rel_path,
        )
        absolute_path.write_text(placeholder_markdown, encoding="utf-8")
        created_paths.append(absolute_path)

    missing_paths = [path for path in required_paths if not path.exists()]
    if missing_paths:
        missing_text = ", ".join(str(path) for path in missing_paths)
        raise NavScaffoldError(
            f"MkDocs nav references missing markdown files after scaffolding: {missing_text}"
        )

    return NavScaffoldResult(
        docs_dir=docs_dir,
        required_markdown_paths=required_paths,
        created_paths=created_paths,
    )


def resolve_effective_mkdocs_config(project_root: Path, docs_dir: Path) -> EffectiveMkDocsConfig:
    """Resolve authored mkdocs.yml if present, otherwise create a fallback temporary config."""

    authored_config_path = project_root / "mkdocs.yml"
    if authored_config_path.exists():
        return EffectiveMkDocsConfig(path=authored_config_path, is_temporary=False)

    fallback_config = _build_fallback_mkdocs_config(project_root=project_root, docs_dir=docs_dir)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".yml",
        prefix="docforge-mkdocs-fallback-",
        dir=project_root,
        delete=False,
    ) as temp_file:
        temp_file.write(yaml.safe_dump(fallback_config, sort_keys=False))
        temp_config_path = Path(temp_file.name)
    return EffectiveMkDocsConfig(path=temp_config_path, is_temporary=True)


def create_local_filesystem_build_config(
    project_root: Path, mkdocs_config_path: Path, docs_dir: Path | None = None
) -> Path:
    """Create a temporary MkDocs config optimized for local filesystem browsing."""

    config_data = _load_mkdocs_config(mkdocs_config_path)
    resolved_docs_dir = _resolve_docs_dir(project_root, config_data, docs_dir)
    config_data["docs_dir"] = _to_mkdocs_docs_dir_value(project_root, resolved_docs_dir)
    config_data["use_directory_urls"] = False
    config_data["strict"] = True

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".yml",
        prefix="docforge-mkdocs-effective-",
        dir=project_root,
        delete=False,
    ) as temp_file:
        temp_file.write(yaml.safe_dump(config_data, sort_keys=False))
        temp_config_path = Path(temp_file.name)
    return temp_config_path


def _build_fallback_mkdocs_config(project_root: Path, docs_dir: Path) -> dict[str, Any]:
    return {
        "site_name": "DocForge Local Documentation",
        "docs_dir": _to_mkdocs_docs_dir_value(project_root, docs_dir.resolve()),
        "use_directory_urls": False,
        "strict": True,
        "nav": _DEFAULT_NAV,
    }


def _load_mkdocs_config(mkdocs_config_path: Path) -> dict[str, Any]:
    data = yaml.safe_load(mkdocs_config_path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise NavScaffoldError(f"Invalid MkDocs config format in {mkdocs_config_path}.")
    return data


def _resolve_docs_dir(
    project_root: Path, config_data: dict[str, Any], runtime_docs_dir: Path | None = None
) -> Path:
    if runtime_docs_dir is not None:
        return runtime_docs_dir.resolve()
    docs_dir_value = config_data.get("docs_dir", "docs")
    if not isinstance(docs_dir_value, str):
        raise NavScaffoldError("mkdocs.yml field 'docs_dir' must be a string path.")
    return (project_root / docs_dir_value).resolve()


def _to_mkdocs_docs_dir_value(project_root: Path, docs_dir: Path) -> str:
    try:
        return docs_dir.relative_to(project_root).as_posix()
    except ValueError:
        return docs_dir.as_posix()


def _extract_nav_markdown_targets(nav: Any) -> list[tuple[Path, str | None]]:
    targets: list[tuple[Path, str | None]] = []

    def _walk(node: Any, label_hint: str | None = None) -> None:
        if isinstance(node, str):
            normalized = node.strip()
            if normalized.lower().endswith(".md"):
                targets.append((Path(normalized), label_hint))
            return

        if isinstance(node, list):
            for item in node:
                _walk(item)
            return

        if isinstance(node, dict):
            for key, value in node.items():
                next_label = key if isinstance(key, str) else None
                if isinstance(value, str):
                    _walk(value, label_hint=next_label)
                else:
                    _walk(value)

    _walk(nav)

    deduplicated: list[tuple[Path, str | None]] = []
    seen: set[str] = set()
    for rel_path, label in targets:
        key = rel_path.as_posix()
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append((rel_path, label))

    return deduplicated


def _placeholder_reason(relative_path: Path) -> str:
    path_key = relative_path.as_posix()
    return _EXPLICIT_REASONS.get(
        path_key,
        "This page is referenced by mkdocs.yml navigation but no source markdown file exists yet.",
    )


def _title_from_path(relative_path: Path) -> str:
    if relative_path.name.lower() == "readme.md" and relative_path.parent.name:
        return relative_path.parent.name.replace("_", " ").replace("-", " ").title()
    stem = relative_path.stem.replace("_", " ").replace("-", " ")
    return stem.title() if stem else "Documentation"


def _render_placeholder_markdown(title: str, reason: str, relative_path: Path) -> str:
    return (
        f"# {title}\n\n"
        "**⚠️ AUTO-GENERATED PLACEHOLDER**\n\n"
        f"> **Reason:** {reason}\n\n"
        "This file was created automatically so the documentation site remains navigable "
        "without broken links.\n\n"
        "This page is a temporary placeholder and is **not authoritative "
        "project documentation**.\n\n"
        "## How to replace this page\n\n"
        "1. Replace this file with repository-authored documentation content.\n"
        "2. Keep the file path stable so MkDocs navigation continues to work.\n"
        "3. Remove this placeholder banner after adding real content.\n\n"
        f"_Auto-scaffolded for nav target: `{relative_path.as_posix()}`._\n"
    )
