"""Repo-analysis ignore rules for implementation analysis surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pathspec import PathSpec

from repo_autodocs.config_models import AppConfig

DEFAULT_REPO_ANALYSIS_IGNORE_PATTERNS: tuple[str, ...] = (
    ".docforge-local/",
    "docforge.toml",
    ".git/",
    ".venv/",
    "venv/",
    "env/",
    "__pycache__/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
    ".tox/",
    ".nox/",
    ".coverage",
    ".coverage.*",
    "htmlcov/",
    "build/",
    "dist/",
    "*.egg-info/",
    ".eggs/",
    "*.sqlite",
    "*.sqlite3",
    "*.db",
    "*.db-*",
    "*.db3",
    "*.mdb",
    "*.parquet",
    "*.duckdb",
    ".claude/",
    ".cursor/",
    ".codex/",
    ".aider/",
    ".continue/",
    "README.md",
    "**/AGENTS.md",
    "**/CLAUDE.md",
    "**/CODEX.md",
    "**/CURSOR.md",
    "**/AIDER.md",
    "**/CONTINUE.md",
    "**/GEMINI.md",
)


def _normalize_pattern(pattern: str) -> str:
    return pattern.strip().replace("\\", "/")


def _load_repo_gitignore_patterns(repo_root: Path) -> list[str]:
    gitignore = repo_root / ".gitignore"
    if not gitignore.is_file():
        return []
    patterns: list[str] = []
    for raw_line in gitignore.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(_normalize_pattern(line))
    return patterns


def _to_posix_relative(path: Path, repo_root: Path) -> str:
    relative = path.resolve().relative_to(repo_root.resolve())
    return PurePosixPath(relative.as_posix()).as_posix()


def _derive_tool_owned_ignore_patterns(config: AppConfig) -> tuple[str, ...]:
    repo_root = config.project_root.resolve()
    candidates = (
        config.docs_dir,
        config.output_dir,
        config.site_dir,
        config.artifact_root,
    )
    deduped: dict[str, None] = {}

    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            relative = resolved.relative_to(repo_root)
        except ValueError:
            continue
        if relative == Path("."):
            continue
        relative_posix = PurePosixPath(relative.as_posix()).as_posix()
        is_file = resolved.exists() and resolved.is_file()
        pattern = relative_posix if is_file else f"{relative_posix}/"
        deduped[pattern] = None

    return tuple(sorted(deduped))


@dataclass(frozen=True, slots=True)
class RepoIgnoreSpec:
    """Compiled gitignore-like matcher for repository implementation analysis."""

    repo_root: Path
    patterns: tuple[str, ...]
    matcher: PathSpec

    @classmethod
    def build(
        cls,
        *,
        repo_root: Path,
        use_default_ignores: bool = True,
        use_repo_gitignore: bool = True,
        ignore_patterns: tuple[str, ...] = (),
        unignore_patterns: tuple[str, ...] = (),
    ) -> RepoIgnoreSpec:
        merged_patterns: list[str] = []
        if use_default_ignores:
            merged_patterns.extend(DEFAULT_REPO_ANALYSIS_IGNORE_PATTERNS)
        if use_repo_gitignore:
            merged_patterns.extend(_load_repo_gitignore_patterns(repo_root))
        merged_patterns.extend(
            _normalize_pattern(pattern) for pattern in ignore_patterns if pattern
        )
        merged_patterns.extend(
            f"!{_normalize_pattern(pattern).lstrip('!')}"
            for pattern in unignore_patterns
            if pattern
        )
        matcher = PathSpec.from_lines("gitignore", merged_patterns)
        return cls(
            repo_root=repo_root.resolve(),
            patterns=tuple(merged_patterns),
            matcher=matcher,
        )

    @classmethod
    def from_config(cls, config: AppConfig) -> RepoIgnoreSpec:
        dynamic_tool_owned_patterns = _derive_tool_owned_ignore_patterns(config)
        return cls.build(
            repo_root=config.project_root,
            use_default_ignores=config.use_repo_analysis_default_ignores,
            use_repo_gitignore=config.use_repo_gitignore,
            ignore_patterns=config.repo_analysis_ignore_patterns + dynamic_tool_owned_patterns,
            unignore_patterns=config.repo_analysis_unignore_patterns,
        )

    def is_ignored(self, relative_path: str, *, is_dir: bool = False) -> bool:
        normalized = PurePosixPath(relative_path).as_posix().lstrip("./")
        if not normalized:
            return False
        candidate = f"{normalized}/" if is_dir else normalized
        return self.matcher.match_file(candidate)

    def is_ignored_path(self, path: Path, *, is_dir: bool | None = None) -> bool:
        relative = _to_posix_relative(path, self.repo_root)
        directory = path.is_dir() if is_dir is None else is_dir
        return self.is_ignored(relative, is_dir=directory)
