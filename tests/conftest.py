from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def copy_fixture_repo(tmp_path: Path, fixture_name: str) -> Path:
    fixtures_root = Path(__file__).parent / "fixtures" / "repos"
    source = fixtures_root / fixture_name
    target = tmp_path / fixture_name
    shutil.copytree(source, target)
    return target


def init_git_repo(repo_root: Path) -> None:
    subprocess.run(["git", "-C", str(repo_root), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "user.name", "Test User"],
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "-C", str(repo_root), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_root), "commit", "-m", "initial commit"],
        check=True,
        capture_output=True,
    )
