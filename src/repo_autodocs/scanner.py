"""Deterministic repository scanning utilities."""

from __future__ import annotations

from pathlib import Path

from repo_autodocs.codefacts import build_code_facts_bundle
from repo_autodocs.config_models import AppConfig
from repo_autodocs.models import CodeFactsBundle, RepoManifest, RepositoryTextEvidence
from repo_autodocs.repo_ignore import RepoIgnoreSpec

_REPO_EVIDENCE_FILES: tuple[tuple[str, str], ...] = (
    ("README.md", "readme"),
    ("pyproject.toml", "package_config"),
    ("mkdocs.yml", "publishing_config"),
)


def _read_text_excerpt(
    path: Path, max_lines: int = 40, max_chars: int = 2400
) -> tuple[str, int] | None:
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    lines = raw.splitlines()
    clipped_lines = lines[:max_lines]
    excerpt = "\n".join(clipped_lines)
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rstrip() + "\n..."
    return excerpt, len(clipped_lines)


def _collect_repository_textual_evidence(
    root: Path, ignore_spec: RepoIgnoreSpec | None
) -> list[RepositoryTextEvidence]:
    evidence: list[RepositoryTextEvidence] = []

    for relative_name, category in _REPO_EVIDENCE_FILES:
        if ignore_spec and ignore_spec.is_ignored(relative_name):
            continue
        excerpt = _read_text_excerpt(root / relative_name)
        if excerpt is None:
            continue
        text, line_count = excerpt
        evidence.append(
            RepositoryTextEvidence(
                category=category,
                relative_path=relative_name,
                excerpt=text,
                line_count=line_count,
            )
        )

    tests_root = root / "tests"
    if tests_root.is_dir() and not (ignore_spec and ignore_spec.is_ignored("tests", is_dir=True)):
        test_evidence_count = 0
        for test_file in sorted(tests_root.rglob("test_*.py")):
            relative = test_file.relative_to(root).as_posix()
            if ignore_spec and ignore_spec.is_ignored(relative):
                continue
            excerpt = _read_text_excerpt(test_file, max_lines=24, max_chars=1600)
            if excerpt is None:
                continue
            text, line_count = excerpt
            evidence.append(
                RepositoryTextEvidence(
                    category="test_file",
                    relative_path=relative,
                    excerpt=text,
                    line_count=line_count,
                )
            )
            test_evidence_count += 1
            if test_evidence_count >= 6:
                break

    return evidence


def _resolve_ignore_spec(
    repo_root: Path,
    *,
    ignore_spec: RepoIgnoreSpec | None,
    config: AppConfig | None,
    apply_ignore_by_default: bool,
) -> RepoIgnoreSpec | None:
    if ignore_spec is not None:
        return ignore_spec
    if config is not None:
        return RepoIgnoreSpec.from_config(config)
    if apply_ignore_by_default:
        return RepoIgnoreSpec.build(repo_root=repo_root)
    return None


def scan_repository(
    repo_root: Path,
    *,
    ignore_spec: RepoIgnoreSpec | None = None,
    config: AppConfig | None = None,
    apply_ignore_by_default: bool = True,
) -> RepoManifest:
    """Scan top-level repository facts deterministically.

    Repo-analysis ignores are applied by default. Set ``apply_ignore_by_default=False``
    as an explicit opt-out for raw legacy scanning behavior.
    """

    root = repo_root.resolve()
    active_ignore_spec = _resolve_ignore_spec(
        root,
        ignore_spec=ignore_spec,
        config=config,
        apply_ignore_by_default=apply_ignore_by_default,
    )

    top_level_directories: list[str] = []
    top_level_files: list[str] = []

    for item in sorted(root.iterdir(), key=lambda p: p.name):
        if active_ignore_spec and active_ignore_spec.is_ignored(
            item.relative_to(root).as_posix(), is_dir=item.is_dir()
        ):
            continue
        if item.is_dir():
            top_level_directories.append(item.name)
        elif item.is_file():
            top_level_files.append(item.name)

    return RepoManifest(
        project_root=root,
        top_level_directories=top_level_directories,
        top_level_files=top_level_files,
        has_git_dir=(root / ".git").is_dir()
        and not (active_ignore_spec and active_ignore_spec.is_ignored(".git", is_dir=True)),
        has_pyproject=(root / "pyproject.toml").is_file(),
        has_mkdocs_config=(root / "mkdocs.yml").is_file()
        and not (active_ignore_spec and active_ignore_spec.is_ignored("mkdocs.yml")),
        has_docs_dir=(root / "docs").is_dir()
        and not (active_ignore_spec and active_ignore_spec.is_ignored("docs", is_dir=True)),
        has_src_dir=(root / "src").is_dir()
        and not (active_ignore_spec and active_ignore_spec.is_ignored("src", is_dir=True)),
        has_tests_dir=(root / "tests").is_dir()
        and not (active_ignore_spec and active_ignore_spec.is_ignored("tests", is_dir=True)),
        textual_evidence=_collect_repository_textual_evidence(root, active_ignore_spec),
    )


def scan_repository_with_code_facts(
    repo_root: Path,
    *,
    ignore_spec: RepoIgnoreSpec | None = None,
    config: AppConfig | None = None,
    apply_ignore_by_default: bool = True,
) -> tuple[RepoManifest, CodeFactsBundle]:
    """Return top-level manifest and deterministic Python code facts."""

    active_ignore_spec = _resolve_ignore_spec(
        repo_root.resolve(),
        ignore_spec=ignore_spec,
        config=config,
        apply_ignore_by_default=apply_ignore_by_default,
    )
    manifest = scan_repository(
        repo_root,
        ignore_spec=active_ignore_spec,
        apply_ignore_by_default=apply_ignore_by_default,
    )
    code_facts = build_code_facts_bundle(
        manifest.project_root,
        ignore_spec=active_ignore_spec,
        apply_ignore_by_default=apply_ignore_by_default,
    )
    return manifest, code_facts
