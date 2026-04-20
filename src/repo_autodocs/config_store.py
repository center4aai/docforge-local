"""Canonical config read/modify/write store."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import tomlkit
from tomlkit.items import Table
from tomlkit.toml_document import TOMLDocument

from repo_autodocs.config import DEFAULT_CONFIG_FILE_NAME
from repo_autodocs.config_fields import FIELD_MAP, ConfigField
from repo_autodocs.config_paths import default_user_config_file

ConfigScope = Literal["project", "user"]


@dataclass(slots=True)
class ConfigStore:
    project_root: Path
    scope: ConfigScope
    config_file: Path | None = None

    @property
    def target_path(self) -> Path:
        if self.scope == "project":
            return (self.config_file or (self.project_root / DEFAULT_CONFIG_FILE_NAME)).resolve()
        return default_user_config_file()

    def load_document(self) -> TOMLDocument:
        path = self.target_path
        if not path.is_file():
            return tomlkit.document()
        return tomlkit.parse(path.read_text(encoding="utf-8"))

    def save_document(self, doc: TOMLDocument) -> None:
        path = self.target_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomlkit.dumps(doc), encoding="utf-8")

    def set_field(self, field_key: str, value: object) -> None:
        field = _require_field(field_key)
        self._ensure_scope(field)
        doc = self.load_document()
        _set_nested(doc, field.canonical_path, value)
        for alias_path in field.legacy_paths:
            _remove_nested(doc, alias_path)
        self.save_document(doc)

    def reset_field(self, field_key: str) -> None:
        field = _require_field(field_key)
        self._ensure_scope(field)
        doc = self.load_document()
        _remove_nested(doc, field.canonical_path)
        for alias_path in field.legacy_paths:
            _remove_nested(doc, alias_path)
        self.save_document(doc)

    def _ensure_scope(self, field: ConfigField) -> None:
        if not field.supports_scope(self.scope):
            raise ValueError(f"Field '{field.key}' is not editable in scope '{self.scope}'.")


def _require_field(field_key: str) -> ConfigField:
    if field_key not in FIELD_MAP:
        raise KeyError(f"Unknown field: {field_key}")
    return FIELD_MAP[field_key]


def _set_nested(doc: TOMLDocument, path: tuple[str, ...], value: object) -> None:
    if len(path) == 1:
        doc[path[0]] = value
        return

    node: TOMLDocument | Table = doc
    for key in path[:-1]:
        existing = node.get(key)
        if not isinstance(existing, Table):
            tbl = tomlkit.table()
            tbl.update({})
            node[key] = tbl
            existing = node[key]
        node = existing
    node[path[-1]] = value


def _remove_nested(doc: TOMLDocument, path: tuple[str, ...]) -> None:
    if not path:
        return
    node: TOMLDocument | Table = doc
    parents: list[tuple[TOMLDocument | Table, str]] = []
    for key in path[:-1]:
        child = node.get(key)
        if not isinstance(child, Table):
            return
        parents.append((node, key))
        node = child

    leaf = path[-1]
    if leaf in node:
        del node[leaf]

    for parent, key in reversed(parents):
        child = parent.get(key)
        if isinstance(child, Table) and len(child.value) == 0:
            del parent[key]
        else:
            break
