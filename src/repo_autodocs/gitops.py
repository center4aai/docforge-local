"""Small git subprocess helpers for update planning."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run_git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def is_git_repository(repo_root: Path) -> bool:
    """Return True when the path is an initialized git working tree."""

    result = _run_git(repo_root, ["rev-parse", "--is-inside-work-tree"])
    return result.returncode == 0 and result.stdout.strip() == "true"


def has_head_commit(repo_root: Path) -> bool:
    """Return True when repository has a resolvable HEAD commit."""

    result = _run_git(repo_root, ["rev-parse", "--verify", "HEAD"])
    return result.returncode == 0


def list_changed_files(repo_root: Path) -> list[str] | None:
    """List changed file paths relative to repository root.

    Returns None when git is unavailable/repo is invalid or git commands fail.
    """

    if not is_git_repository(repo_root):
        return None

    changed_paths: set[str] = set()

    if has_head_commit(repo_root):
        head_diff = _run_git(repo_root, ["diff", "--name-only", "HEAD", "--"])
        if head_diff.returncode != 0:
            return None
        changed_paths.update(path.strip() for path in head_diff.stdout.splitlines() if path.strip())
    else:
        staged_diff = _run_git(repo_root, ["diff", "--name-only", "--cached", "--"])
        unstaged_diff = _run_git(repo_root, ["diff", "--name-only", "--"])
        if staged_diff.returncode != 0 or unstaged_diff.returncode != 0:
            return None
        changed_paths.update(
            path.strip() for path in staged_diff.stdout.splitlines() if path.strip()
        )
        changed_paths.update(
            path.strip() for path in unstaged_diff.stdout.splitlines() if path.strip()
        )

    untracked = _run_git(repo_root, ["ls-files", "--others", "--exclude-standard"])
    if untracked.returncode != 0:
        return None

    changed_paths.update(path.strip() for path in untracked.stdout.splitlines() if path.strip())
    return sorted(changed_paths)
