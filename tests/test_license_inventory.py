from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "license_inventory.py"


spec = importlib.util.spec_from_file_location("license_inventory", SCRIPT_PATH)
assert spec and spec.loader
license_inventory = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = license_inventory
spec.loader.exec_module(license_inventory)


class FakeMetadata:
    def __init__(self, values: dict[str, str], classifiers: list[str] | None = None):
        self._values = values
        self._classifiers = classifiers or []

    def get(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)

    def get_all(self, key: str):
        if key == "Classifier":
            return list(self._classifiers)
        return []


class FakeDistribution:
    def __init__(
        self,
        *,
        name: str,
        version: str,
        requires: list[str] | None = None,
        metadata_values: dict[str, str] | None = None,
        classifiers: list[str] | None = None,
    ):
        values = {
            "Name": name,
            "Summary": f"{name} summary",
            **(metadata_values or {}),
        }
        self.metadata = FakeMetadata(values, classifiers)
        self.version = version
        self.requires = requires or []


def _write_pyproject(path: Path) -> None:
    path.write_text(
        """
[project]
dependencies = ["alpha>=1", "beta", "missingpkg>=0.1"]

[dependency-groups]
test = ["gamma>=2"]

[build-system]
requires = ["setuptools>=65"]
build-backend = "setuptools.build_meta"
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _fake_distribution_lookup():
    fake = {
        "alpha": FakeDistribution(
            name="alpha",
            version="1.0.0",
            requires=["child>=0.2", "leaf; python_version > '3.10'"],
            metadata_values={"License-Expression": "MIT", "Home-page": "https://alpha.example"},
        ),
        "beta": FakeDistribution(
            name="beta",
            version="2.0.0",
            metadata_values={"License": "BSD-3-Clause"},
        ),
        "gamma": FakeDistribution(
            name="gamma",
            version="3.0.0",
            classifiers=["License :: OSI Approved :: Apache Software License"],
        ),
        "setuptools": FakeDistribution(
            name="setuptools",
            version="70.0.0",
            metadata_values={"License-Expression": "MIT"},
        ),
        "child": FakeDistribution(
            name="child",
            version="0.3.0",
            requires=["leaf>=0.1"],
            metadata_values={"License": "Apache-2.0"},
        ),
        "leaf": FakeDistribution(
            name="leaf",
            version="0.4.0",
            classifiers=["License :: OSI Approved :: MIT License"],
        ),
    }

    def _lookup(name: str):
        if name in fake:
            return fake[name]
        raise license_inventory.metadata.PackageNotFoundError

    return _lookup


def _build_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, include_transitive: bool = False
):
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject)
    monkeypatch.setattr(license_inventory.metadata, "distribution", _fake_distribution_lookup())
    return license_inventory.build_inventory(pyproject, include_transitive=include_transitive)


def test_direct_dependency_parsing(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject)
    declarations = license_inventory._load_dependency_declarations(pyproject)
    sources = {(decl.normalized_name, decl.source) for decl in declarations}
    assert ("alpha", "runtime") in sources
    assert ("gamma", "dev:test") in sources
    assert ("setuptools", "build-system") in sources


def test_default_markdown_output_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inventory = _build_inventory(tmp_path, monkeypatch)
    output = license_inventory._render_report(inventory, fmt="markdown", failure_conditions=[])
    assert "# Local License Inventory" in output
    assert "## Summary" in output
    assert "## Direct runtime dependencies" in output
    assert "## Direct dev dependencies" in output
    assert "## Build-system dependencies" in output


def test_json_output_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inventory = _build_inventory(tmp_path, monkeypatch, include_transitive=True)
    output = license_inventory._render_report(
        inventory,
        fmt="json",
        failure_conditions=["missing-license"],
    )
    payload = json.loads(output)
    assert payload["generated_from"].endswith("pyproject.toml")
    assert "summary" in payload
    assert "direct_runtime" in payload
    assert "transitive" in payload
    assert payload["failure_conditions"] == ["missing-license"]


def test_csv_output_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inventory = _build_inventory(tmp_path, monkeypatch, include_transitive=True)
    output = license_inventory._render_report(inventory, fmt="csv", failure_conditions=[])
    rows = list(csv.DictReader(output.splitlines()))
    assert rows
    assert "normalized_name" in rows[0]
    assert "license_metadata_quality" in rows[0]


def test_missing_package_handling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inventory = _build_inventory(tmp_path, monkeypatch)
    all_direct = [
        *inventory["direct_runtime"],
        *inventory["direct_dev"],
        *inventory["build_system"],
    ]
    missing = [row for row in all_direct if row.normalized_name == "missingpkg"]
    assert missing
    assert missing[0].installed is False


def test_license_metadata_quality_classification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inventory = _build_inventory(tmp_path, monkeypatch, include_transitive=True)
    rows = [
        *inventory["direct_runtime"],
        *inventory["direct_dev"],
        *inventory["build_system"],
        *inventory["transitive"],
    ]
    by_name = {row.normalized_name: row for row in rows}
    assert by_name["alpha"].license_metadata_quality == "license_expression"
    assert by_name["beta"].license_metadata_quality == "license_field_only"
    assert by_name["gamma"].license_metadata_quality == "classifier_only"
    assert by_name["missingpkg"].license_metadata_quality == "missing"


def test_transitive_discovery_best_effort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inventory = _build_inventory(tmp_path, monkeypatch, include_transitive=True)
    transitive_names = {row.normalized_name for row in inventory["transitive"]}
    assert "child" in transitive_names
    assert "leaf" in transitive_names
    leaf = next(row for row in inventory["transitive"] if row.normalized_name == "leaf")
    assert "alpha" in leaf.transitive_parents or "child" in leaf.transitive_parents


def test_fail_on_missing_license(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject)
    monkeypatch.setattr(license_inventory.metadata, "distribution", _fake_distribution_lookup())
    exit_code = license_inventory.main(
        ["--pyproject", str(pyproject), "--fail-on", "missing-license"]
    )
    stderr = capsys.readouterr().err
    assert exit_code == 1
    assert "missing-license" in stderr


def test_fail_on_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject)
    monkeypatch.setattr(license_inventory.metadata, "distribution", _fake_distribution_lookup())
    exit_code = license_inventory.main(
        ["--pyproject", str(pyproject), "--fail-on", "not-installed"]
    )
    stderr = capsys.readouterr().err
    assert exit_code == 1
    assert "not-installed" in stderr


def test_fail_on_classifier_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject)
    monkeypatch.setattr(license_inventory.metadata, "distribution", _fake_distribution_lookup())
    exit_code = license_inventory.main(
        ["--pyproject", str(pyproject), "--fail-on", "classifier-only"]
    )
    stderr = capsys.readouterr().err
    assert exit_code == 1
    assert "classifier-only" in stderr
