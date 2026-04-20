"""Path helpers for configuration discovery."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "docforge-local"
USER_CONFIG_FILE_ENV = "REPO_AUTODOCS_USER_CONFIG_FILE"


def default_user_config_file() -> Path:
    override = os.getenv(USER_CONFIG_FILE_ENV)
    if override:
        return Path(override).expanduser().resolve()

    try:
        from platformdirs import user_config_dir

        base = Path(user_config_dir(APP_NAME, appauthor=False))
    except Exception:  # pragma: no cover - fallback path
        base = Path.home() / ".config" / APP_NAME
    return (base / "config.toml").resolve()
