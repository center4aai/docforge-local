from pathlib import Path

from repo_autodocs.config import load_config
from repo_autodocs.shell_exports import emit_shell_env


def test_emit_shell_env_bash(tmp_path: Path) -> None:
    config = load_config(project_root=tmp_path)
    text = emit_shell_env(config, "bash")
    assert "export REPO_AUTODOCS_PROJECT_ROOT=" in text
    assert "your_api_key" not in text
    assert "never emitted" in text


def test_emit_shell_env_pwsh_and_cmd(tmp_path: Path) -> None:
    config = load_config(project_root=tmp_path)
    pwsh = emit_shell_env(config, "pwsh")
    cmd = emit_shell_env(config, "cmd")
    assert "$env:REPO_AUTODOCS_PROJECT_ROOT" in pwsh
    assert "set REPO_AUTODOCS_PROJECT_ROOT=" in cmd


def test_emit_shell_env_reference_paths_uses_platform_separator(
    tmp_path: Path, monkeypatch
) -> None:
    config = load_config(project_root=tmp_path, cli_overrides={"reference_paths": ["a", "b"]})
    monkeypatch.setattr("repo_autodocs.shell_exports.os.pathsep", ";")

    text = emit_shell_env(config, "pwsh")

    assert "REPO_AUTODOCS_REFERENCE_PATHS" in text
    assert ";" in text
