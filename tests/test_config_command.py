from pathlib import Path

from conftest import copy_fixture_repo
from typer.testing import CliRunner

from repo_autodocs.cli import app


class _FakeKeyring:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.data.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.data[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.data.pop((service, username), None)


def test_config_help_and_show_effective(tmp_path: Path) -> None:
    repo = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    help_result = runner.invoke(app, ["config", "--help"])
    assert help_result.exit_code == 0

    show_result = runner.invoke(app, ["config", "--project-root", str(repo), "--show-effective"])
    assert show_result.exit_code == 0
    assert "docs_dir" in show_result.stdout


def test_config_show_effective_respects_cli_project_root_over_env(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cli_repo = copy_fixture_repo(workspace, "minimal_cli_repo")
    env_repo = copy_fixture_repo(workspace, "repo_with_methodology")
    monkeypatch.setenv("REPO_AUTODOCS_PROJECT_ROOT", str(env_repo))
    runner = CliRunner()

    show = runner.invoke(
        app,
        ["config", "--project-root", str(cli_repo), "--show-sources"],
    )

    assert show.exit_code == 0
    assert "project_root" in show.stdout
    assert "cli" in show.stdout
    assert "REPO_AUTODOCS_PROJECT_ROOT" not in show.stdout


def test_config_validate_respects_cli_project_root_over_env(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cli_repo = copy_fixture_repo(workspace, "minimal_cli_repo")
    env_repo = copy_fixture_repo(workspace, "repo_with_methodology")
    monkeypatch.setenv("REPO_AUTODOCS_PROJECT_ROOT", str(env_repo))
    runner = CliRunner()

    validate = runner.invoke(
        app,
        ["config", "--project-root", str(cli_repo), "--validate"],
    )

    assert validate.exit_code == 0
    assert "PASS: project_root exists:" in validate.stdout
    condensed = validate.stdout.replace("\n", "")
    assert str(cli_repo.resolve()).replace("\n", "") in condensed
    assert str(env_repo.resolve()).replace("\n", "") not in condensed


def test_config_set_and_reset_and_validate(tmp_path: Path) -> None:
    repo = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "config",
            "--project-root",
            str(repo),
            "--set",
            "docs_dir=.docforge-local/docs2",
            "--set",
            "output_dir=.docforge-local/docs2/generated",
            "--set",
            "site_dir=.docforge-local/site2",
            "--set",
            "generated_text_language=ru",
            "--set",
            "enable_llm=true",
            "--set",
            "temperature=0.4",
            "--set",
            "use_repo_gitignore=false",
            "--set",
            "reference_include_readme_default=false",
            "--show-sources",
            "--validate",
        ],
    )
    assert result.exit_code == 1
    assert "Source" in result.stdout
    assert "FAIL: llm model_name missing" in result.stdout

    reset = runner.invoke(
        app,
        [
            "config",
            "--project-root",
            str(repo),
            "--reset",
            "generated_text_language",
            "--show-effective",
        ],
    )
    assert reset.exit_code == 0


def test_config_interactive_flow(tmp_path: Path) -> None:
    repo = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()
    user_input = "2\n.docforge-local/docs-interactive\nvalidate\nquit\n"

    result = runner.invoke(app, ["config", "--project-root", str(repo)], input=user_input)

    assert result.exit_code == 0
    cfg = (repo / "docforge.toml").read_text(encoding="utf-8")
    assert "docs-interactive" in cfg
    assert "saves each edit immediately" in result.stdout
    assert "Validating current effective saved configuration state." in result.stdout


def test_config_interactive_save_command_is_informational(tmp_path: Path) -> None:
    repo = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["config", "--project-root", str(repo)],
        input="save\nquit\n",
    )

    assert result.exit_code == 0
    assert "No draft state: each edit is persisted immediately" in result.stdout


def test_config_interactive_boolean_toggle(tmp_path: Path) -> None:
    repo = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()
    user_input = "15\nquit\n"

    result = runner.invoke(app, ["config", "--project-root", str(repo)], input=user_input)

    assert result.exit_code == 0
    cfg = (repo / "docforge.toml").read_text(encoding="utf-8")
    assert "enable_llm = true" in cfg


def test_config_interactive_scope_switch_uses_scope_filtered_indexes(tmp_path: Path) -> None:
    repo = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()
    user_input = "scope\nuser\n999\nreset 999\nquit\n"

    result = runner.invoke(app, ["config", "--project-root", str(repo)], input=user_input)

    assert result.exit_code == 0
    assert "Scope switched to 'user'." in result.stdout
    assert result.stdout.count("Invalid field index for current scope.") >= 2


def test_config_set_project_root_field(tmp_path: Path) -> None:
    repo = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["config", "--project-root", str(repo), "--set", "project_root=.", "--show-sources"],
    )

    assert result.exit_code == 0
    assert "project_root" in result.stdout


def test_scope_user_and_env_override_explained(tmp_path: Path, monkeypatch) -> None:
    repo = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    user_cfg = tmp_path / "user-config.toml"
    monkeypatch.setenv("REPO_AUTODOCS_USER_CONFIG_FILE", str(user_cfg))
    monkeypatch.setenv("REPO_AUTODOCS_DOCS_DIR", "env_docs")
    runner = CliRunner()

    save_user = runner.invoke(
        app,
        ["config", "--project-root", str(repo), "--scope", "user", "--set", "docs_dir=user_docs"],
    )
    assert save_user.exit_code == 0

    show = runner.invoke(
        app,
        ["config", "--project-root", str(repo), "--show-sources"],
    )
    assert show.exit_code == 0
    assert "env" in show.stdout
    assert "REPO_AUTODOCS_DOCS_DIR" in show.stdout


def test_emit_shell_env_modes(tmp_path: Path) -> None:
    repo = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    bash = runner.invoke(app, ["config", "--project-root", str(repo), "--emit-shell-env", "bash"])
    pwsh = runner.invoke(app, ["config", "--project-root", str(repo), "--emit-shell-env", "pwsh"])
    cmd = runner.invoke(app, ["config", "--project-root", str(repo), "--emit-shell-env", "cmd"])
    assert bash.exit_code == 0
    assert pwsh.exit_code == 0
    assert cmd.exit_code == 0


def test_api_key_keyring_flow_and_no_plaintext_in_config(tmp_path: Path, monkeypatch) -> None:
    repo = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    fake = _FakeKeyring()
    monkeypatch.setattr("repo_autodocs.secrets.keyring_available", lambda: True)
    monkeypatch.setattr(
        "repo_autodocs.secrets.keyring_status",
        lambda: type("S", (), {"available": True, "reason": "keyring is available and usable"})(),
    )
    monkeypatch.setattr(
        "repo_autodocs.secrets.set_api_key",
        lambda name, value: fake.set_password("docforge-local", name, value),
    )
    monkeypatch.setattr(
        "repo_autodocs.secrets.delete_api_key",
        lambda name: fake.delete_password("docforge-local", name),
    )
    monkeypatch.setattr(
        "repo_autodocs.secrets.resolve_api_key",
        lambda config: fake.get_password("docforge-local", config.api_key_secret_name or ""),
    )

    runner = CliRunner()
    set_cfg = runner.invoke(
        app,
        [
            "config",
            "--project-root",
            str(repo),
            "--set",
            "api_key_mode=keyring",
            "--set",
            "api_key_secret_name=test-secret",
            "--set-api-key",
            "super-secret",
        ],
    )
    assert set_cfg.exit_code == 0
    assert fake.get_password("docforge-local", "test-secret") == "super-secret"

    cfg_text = (repo / "docforge.toml").read_text(encoding="utf-8")
    assert "super-secret" not in cfg_text

    delete = runner.invoke(
        app,
        ["config", "--project-root", str(repo), "--delete-api-key"],
    )
    assert delete.exit_code == 0


def test_api_key_delete_env_mode_is_informational_only(tmp_path: Path) -> None:
    repo = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "config",
            "--project-root",
            str(repo),
            "--set",
            "api_key_mode=env",
            "--set",
            "api_key_env_var=MY_DOCFORGE_KEY",
            "--delete-api-key",
        ],
    )

    assert result.exit_code == 0
    assert "INFO: api_key_mode=env stores the key" in result.stdout
    assert "Remove `MY_DOCFORGE_KEY` manually" in result.stdout


def test_keyring_unavailable_is_graceful(tmp_path: Path, monkeypatch) -> None:
    repo = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    monkeypatch.setattr("repo_autodocs.secrets.keyring_available", lambda: False)
    monkeypatch.setattr(
        "repo_autodocs.secrets.keyring_status",
        lambda: type("S", (), {"available": False, "reason": "keyring package not installed"})(),
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "config",
            "--project-root",
            str(repo),
            "--set",
            "api_key_mode=keyring",
            "--set",
            "api_key_secret_name=test-secret",
            "--set-api-key",
            "secret",
        ],
    )
    assert result.exit_code != 0
    assert "keyring package not installed" in result.stdout


def test_keyring_secret_status_reports_unusable_backend_reason(tmp_path: Path, monkeypatch) -> None:
    repo = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()
    monkeypatch.setattr(
        "repo_autodocs.secrets.keyring_status",
        lambda: type(
            "S",
            (),
            {"available": False, "reason": "keyring installed but no usable backend is available"},
        )(),
    )
    runner.invoke(
        app,
        [
            "config",
            "--project-root",
            str(repo),
            "--set",
            "api_key_mode=keyring",
            "--set",
            "api_key_secret_name=test-secret",
        ],
    )
    result = runner.invoke(
        app, ["config", "--project-root", str(repo)], input="secret\nstatus\nquit\n"
    )
    assert result.exit_code == 0
    assert "no usable backend is available" in result.stdout


def test_secret_status_reports_env_presence(tmp_path: Path, monkeypatch) -> None:
    repo = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    runner = CliRunner()
    user_input = "secret\nstatus\nquit\n"

    result = runner.invoke(app, ["config", "--project-root", str(repo)], input=user_input)

    assert result.exit_code == 0
    assert "api_key_mode=env" in result.stdout
    assert "api_key_present=yes" in result.stdout


def test_saved_config_is_consumed_by_workflows(tmp_path: Path, monkeypatch) -> None:
    repo = copy_fixture_repo(tmp_path, "minimal_cli_repo")
    runner = CliRunner()
    user_cfg = tmp_path / "user.toml"
    monkeypatch.setenv("REPO_AUTODOCS_USER_CONFIG_FILE", str(user_cfg))

    runner.invoke(
        app,
        [
            "config",
            "--project-root",
            str(repo),
            "--scope",
            "user",
            "--set",
            "docs_dir=.docforge-local/docs-user",
        ],
    )
    doctor = runner.invoke(app, ["doctor", "--project-root", str(repo)])
    assert doctor.exit_code == 0
    assert "docs-user" in doctor.stdout

    runner.invoke(
        app,
        ["config", "--project-root", str(repo), "--set", "site_dir=.docforge-local/site-proj"],
    )
    upd = runner.invoke(app, ["update-docs", "--project-root", str(repo)])
    assert upd.exit_code == 0

    cli_override = runner.invoke(
        app,
        ["doctor", "--project-root", str(repo), "--docs-dir", ".docforge-local/docs-cli"],
    )
    assert cli_override.exit_code == 0
    assert "docs-cli" in cli_override.stdout

    monkeypatch.setenv("REPO_AUTODOCS_DOCS_DIR", "env-docs")
    env_override = runner.invoke(app, ["doctor", "--project-root", str(repo)])
    assert env_override.exit_code == 0
    assert "env-docs" in env_override.stdout
