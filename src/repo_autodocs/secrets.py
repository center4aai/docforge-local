"""Secret resolution helpers for LLM credentials."""

from __future__ import annotations

import os
from dataclasses import dataclass

from repo_autodocs.config_models import AppConfig

KEYRING_SERVICE_NAME = "docforge-local"


@dataclass(frozen=True, slots=True)
class KeyringAvailability:
    available: bool
    reason: str


def keyring_status() -> KeyringAvailability:
    try:
        import keyring  # type: ignore
    except Exception:
        return KeyringAvailability(available=False, reason="keyring package not installed")

    try:
        backend = keyring.get_keyring()
    except Exception:
        return KeyringAvailability(
            available=False, reason="keyring installed but backend lookup failed"
        )

    backend_name = backend.__class__.__name__.lower()
    backend_module = backend.__class__.__module__.lower()
    priority = getattr(backend, "priority", None)
    try:
        priority_value = float(priority) if priority is not None else None
    except Exception:
        priority_value = None

    if "fail" in backend_name or "fail" in backend_module:
        return KeyringAvailability(
            available=False, reason="keyring installed but no usable backend is available"
        )
    if priority_value is not None and priority_value <= 0:
        return KeyringAvailability(
            available=False, reason="keyring installed but backend is disabled/unusable"
        )

    return KeyringAvailability(available=True, reason="keyring is available and usable")


def keyring_available() -> bool:
    return keyring_status().available


def api_key_present(config: AppConfig) -> bool:
    return resolve_api_key(config) is not None


def set_api_key(secret_name: str, secret_value: str) -> None:
    try:
        import keyring  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("keyring backend unavailable") from exc
    keyring.set_password(KEYRING_SERVICE_NAME, secret_name, secret_value)


def delete_api_key(secret_name: str) -> None:
    try:
        import keyring  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("keyring backend unavailable") from exc
    try:
        keyring.delete_password(KEYRING_SERVICE_NAME, secret_name)
    except Exception:
        pass


def resolve_api_key(config: AppConfig) -> str | None:
    """Resolve API key using configured mode."""

    if config.api_key_mode == "none":
        return None
    if config.api_key_mode == "env":
        return os.getenv(config.api_key_env_var) or None
    if config.api_key_mode == "keyring":
        if not config.api_key_secret_name:
            return None
        try:
            import keyring  # type: ignore
        except Exception:  # pragma: no cover - optional dependency
            return None
        return keyring.get_password(KEYRING_SERVICE_NAME, config.api_key_secret_name)
    return None
