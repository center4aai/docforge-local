"""Interactive and non-interactive `docforge-local config` command."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from repo_autodocs import secrets
from repo_autodocs.config import load_config
from repo_autodocs.config_fields import FIELD_MAP, FIELDS, ConfigField, format_effective_value
from repo_autodocs.config_store import ConfigScope, ConfigStore
from repo_autodocs.config_validation import ValidationReport, validate_config
from repo_autodocs.shell_exports import emit_shell_env

console = Console()


def _load_effective_config(project_root: Path, config_file: Path | None):
    return load_config(
        project_root=project_root,
        config_file=config_file,
        cli_overrides={"project_root": str(project_root)},
    )


def register_config_command(app: typer.Typer) -> None:
    @app.command("config")
    def config_command(
        project_root: Annotated[Path, typer.Option("--project-root")] = Path("."),
        config_file: Annotated[Path | None, typer.Option("--config-file")] = None,
        scope: Annotated[ConfigScope, typer.Option("--scope")] = "project",
        show_effective: Annotated[bool, typer.Option("--show-effective")] = False,
        show_sources: Annotated[bool, typer.Option("--show-sources")] = False,
        validate: Annotated[bool, typer.Option("--validate")] = False,
        emit_shell_env: Annotated[str | None, typer.Option("--emit-shell-env")] = None,
        set_values: Annotated[list[str] | None, typer.Option("--set")] = None,
        reset_values: Annotated[list[str] | None, typer.Option("--reset")] = None,
        set_api_key_value: Annotated[str | None, typer.Option("--set-api-key")] = None,
        delete_api_key_flag: Annotated[bool, typer.Option("--delete-api-key")] = False,
    ) -> None:
        root = project_root.resolve()
        store = ConfigStore(project_root=root, scope=scope, config_file=config_file)
        pending_sets = set_values or []
        pending_resets = reset_values or []

        if pending_sets or pending_resets or set_api_key_value is not None or delete_api_key_flag:
            for item in pending_sets:
                key, value = _parse_set(item)
                field = _get_field(key)
                store.set_field(key, _coerce_value(field, value))
            for key in pending_resets:
                _get_field(key)
                store.reset_field(key)

            config = _load_effective_config(project_root=root, config_file=config_file)
            if set_api_key_value is not None:
                _set_api_key_for_config(config, set_api_key_value)
            if delete_api_key_flag:
                _delete_api_key_for_config(config)

        config = _load_effective_config(project_root=root, config_file=config_file)

        if show_effective or show_sources:
            _render_fields(config, include_sources=show_sources, scope=scope)
        if validate:
            report = validate_config(config)
            _render_validation(report)
            if report.failures:
                raise typer.Exit(code=1)
        if emit_shell_env:
            typer.echo(emit_shell_env_for_command(config, emit_shell_env))

        if not any(
            [
                show_effective,
                show_sources,
                validate,
                emit_shell_env is not None,
                bool(pending_sets),
                bool(pending_resets),
                set_api_key_value is not None,
                delete_api_key_flag,
            ]
        ):
            _interactive_wizard(root, config_file, scope)


def emit_shell_env_for_command(config, shell: str) -> str:
    if shell not in {"bash", "pwsh", "cmd"}:
        raise typer.BadParameter("--emit-shell-env must be one of: bash, pwsh, cmd")
    return emit_shell_env(config, shell)  # type: ignore[arg-type]


def _render_fields(config, *, include_sources: bool, scope: ConfigScope) -> None:
    table = Table(title=f"docforge-local config (scope={scope})")
    table.add_column("#", justify="right")
    table.add_column("Field")
    table.add_column("Value")
    if include_sources:
        table.add_column("Source")
        table.add_column("Source key")

    visible_fields = _visible_fields_for_scope(scope)
    for idx, field in enumerate(visible_fields, start=1):
        source = config.get_value_source(field.key)
        row = [str(idx), field.key, format_effective_value(config, field.key)]
        if include_sources:
            row.extend([source.source, source.source_key])
        table.add_row(*row)
    console.print(table)
    if include_sources:
        for field in visible_fields:
            source = config.get_value_source(field.key)
            if source.source == "env":
                console.print(
                    f"NOTE: {field.key} is currently overridden by env var {source.source_key}."
                )


def _render_validation(report: ValidationReport) -> None:
    for msg in report.passes:
        console.print(f"PASS: {msg}")
    for msg in report.warnings:
        console.print(f"WARN: {msg}")
    for msg in report.failures:
        console.print(f"FAIL: {msg}")


def _interactive_wizard(project_root: Path, config_file: Path | None, scope: ConfigScope) -> None:
    current_scope = scope

    console.print(
        "Interactive config manager saves each edit immediately. "
        "Validation checks the current effective saved configuration."
    )

    while True:
        cfg = _load_effective_config(project_root=project_root, config_file=config_file)
        _render_fields(cfg, include_sources=True, scope=current_scope)
        console.print(
            "Commands: [number]=edit, reset <number>, validate, save, scope, secret, quit"
        )
        command = typer.prompt("config>").strip()

        if command in {"quit", "q", "exit"}:
            return
        if command in {"save", "s"}:
            console.print(
                "No draft state: each edit is persisted immediately; save is informational only."
            )
            continue
        if command == "validate":
            console.print("Validating current effective saved configuration state.")
            _render_validation(validate_config(cfg))
            continue
        if command == "scope":
            next_scope = typer.prompt("Scope (project/user)", default=current_scope)
            if next_scope in {"project", "user"}:
                current_scope = next_scope  # type: ignore[assignment]
                console.print(f"Scope switched to '{current_scope}'.")
            else:
                console.print("Invalid scope.")
            continue
        if command == "secret":
            _interactive_secret(cfg)
            continue
        if command.startswith("reset "):
            _, _, index_txt = command.partition(" ")
            try:
                field = _field_by_index(index_txt, current_scope)
            except (ValueError, typer.BadParameter):
                console.print("Invalid field index for current scope.")
                continue
            try:
                ConfigStore(project_root, current_scope, config_file).reset_field(field.key)
            except ValueError as exc:
                console.print(f"Cannot reset field in scope '{current_scope}': {exc}")
            continue
        if command.isdigit():
            try:
                field = _field_by_index(command, current_scope)
            except (ValueError, typer.BadParameter):
                console.print("Invalid field index for current scope.")
                continue
            _interactive_edit_field(field, project_root, current_scope, config_file)
            continue
        console.print("Unrecognized command.")


def _interactive_secret(config) -> None:
    action = typer.prompt("Secret action (status/set/delete)", default="status").strip()
    if action == "status":
        if config.api_key_mode == "env":
            env_name = config.api_key_env_var
            env_present = bool(env_name and os.getenv(env_name))
            console.print(
                "api_key_mode=env, "
                f"env_var={env_name}, "
                f"api_key_present={'yes' if env_present else 'no'}"
            )
        elif config.api_key_mode == "keyring":
            keyring = secrets.keyring_status()
            keyring_ok = keyring.available
            key_present = secrets.api_key_present(config) if keyring_ok else False
            console.print(
                "api_key_mode=keyring, "
                f"secret_name={config.api_key_secret_name or '<unset>'}, "
                f"keyring_available={'yes' if keyring_ok else 'no'}, "
                f"api_key_present={'yes' if key_present else 'no'}"
            )
            if not keyring_ok:
                console.print(f"WARN: {keyring.reason}")
        else:
            console.print("api_key_mode=none, api_key_present=no")
        return
    if action == "set":
        secret = typer.prompt("API key", hide_input=True)
        _set_api_key_for_config(config, secret)
        return
    if action == "delete":
        _delete_api_key_for_config(config)
        return
    console.print("Unknown secret action.")


def _set_api_key_for_config(config, secret_value: str) -> None:
    if config.api_key_mode != "keyring":
        console.print("FAIL: set api_key_mode=keyring before storing API key.")
        raise typer.Exit(code=1)
    if not config.api_key_secret_name:
        console.print("FAIL: set api_key_secret_name before storing API key.")
        raise typer.Exit(code=1)
    keyring = secrets.keyring_status()
    if not keyring.available:
        console.print(f"{keyring.reason}. Install a usable backend or switch to api_key_mode=env.")
        raise typer.Exit(code=1)
    secrets.set_api_key(config.api_key_secret_name, secret_value)
    console.print("API key stored in keyring.")


def _delete_api_key_for_config(config) -> None:
    if config.api_key_mode == "env":
        env_var = config.api_key_env_var or "OPENAI_API_KEY"
        console.print(
            "INFO: api_key_mode=env stores the key in process/user environment variables. "
            f"Remove `{env_var}` manually in your shell/profile to delete it."
        )
        return
    if config.api_key_mode != "keyring":
        console.print("FAIL: delete is only supported when api_key_mode=keyring.")
        raise typer.Exit(code=1)
    if not config.api_key_secret_name:
        console.print("FAIL: api_key_secret_name is required to delete keyring secret.")
        raise typer.Exit(code=1)
    keyring = secrets.keyring_status()
    if not keyring.available:
        console.print(f"FAIL: {keyring.reason}.")
        raise typer.Exit(code=1)
    secrets.delete_api_key(config.api_key_secret_name)
    console.print("API key deleted from keyring (if it existed).")


def _interactive_edit_field(
    field: ConfigField, project_root: Path, scope: ConfigScope, config_file: Path | None
) -> None:
    store = ConfigStore(project_root=project_root, scope=scope, config_file=config_file)
    if not field.supports_scope(scope):
        console.print(
            f"Field '{field.key}' is not editable in scope '{scope}'. Switch scope and try again."
        )
        return
    if field.field_type == "bool":
        current_config = _load_effective_config(project_root=project_root, config_file=config_file)
        current_bool = bool(getattr(current_config, field.key))
        next_bool = not current_bool
        try:
            store.set_field(field.key, next_bool)
        except ValueError as exc:
            console.print(f"Cannot edit field in scope '{scope}': {exc}")
            return
        console.print(f"{field.key} toggled: {current_bool} -> {next_bool}")
        return

    prompt = f"{field.key} ({field.field_type})"
    current_config = _load_effective_config(project_root=project_root, config_file=config_file)
    current_val = format_effective_value(current_config, field.key)
    raw_value = typer.prompt(prompt, default=current_val)
    try:
        store.set_field(field.key, _coerce_value(field, raw_value))
    except ValueError as exc:
        console.print(f"Cannot edit field in scope '{scope}': {exc}")


def _visible_fields_for_scope(scope: ConfigScope) -> tuple[ConfigField, ...]:
    return tuple(field for field in FIELDS if field.supports_scope(scope))


def _field_by_index(index_txt: str, scope: ConfigScope) -> ConfigField:
    visible_fields = _visible_fields_for_scope(scope)
    index = int(index_txt)
    if index < 1 or index > len(visible_fields):
        raise typer.BadParameter("invalid field index")
    return visible_fields[index - 1]


def _parse_set(item: str) -> tuple[str, str]:
    key, sep, value = item.partition("=")
    if not sep:
        raise typer.BadParameter("--set expects key=value")
    return key.strip(), value.strip()


def _get_field(key: str) -> ConfigField:
    if key not in FIELD_MAP:
        raise typer.BadParameter(f"unknown config field: {key}")
    return FIELD_MAP[key]


def _coerce_value(field: ConfigField, raw: str) -> object:
    if field.field_type == "bool":
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    if field.field_type == "float":
        return float(raw)
    if field.field_type == "string_list":
        if raw.strip() == "":
            return []
        return [token.strip() for token in raw.split(",") if token.strip()]
    if field.field_type == "enum":
        if raw not in set(field.enum_values):
            raise typer.BadParameter(f"{field.key} must be one of: {', '.join(field.enum_values)}")
    return raw
