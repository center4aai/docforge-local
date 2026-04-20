from __future__ import annotations

import builtins
from types import SimpleNamespace

from repo_autodocs.secrets import keyring_status


def _backend(*, name: str, module: str, priority: float):
    backend_type = type(name, (), {"__module__": module})
    backend = backend_type()
    backend.priority = priority
    return backend


def test_keyring_status_when_package_missing(monkeypatch) -> None:
    original_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name == "keyring":
            raise ModuleNotFoundError("no module")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    status = keyring_status()
    assert status.available is False
    assert "not installed" in status.reason


def test_keyring_status_when_backend_unusable(monkeypatch) -> None:
    keyring_module = SimpleNamespace(
        get_keyring=lambda: _backend(
            name="FailKeyring", module="keyring.backends.fail", priority=0.0
        )
    )
    original_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name == "keyring":
            return keyring_module
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    status = keyring_status()

    assert status.available is False
    assert "no usable backend" in status.reason or "disabled/unusable" in status.reason


def test_keyring_status_when_backend_usable(monkeypatch) -> None:
    keyring_module = SimpleNamespace(
        get_keyring=lambda: _backend(
            name="SecureBackend", module="keyring.backends.secure", priority=5.0
        )
    )
    original_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name == "keyring":
            return keyring_module
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    status = keyring_status()

    assert status.available is True
    assert "usable" in status.reason
