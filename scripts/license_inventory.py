"""Local dependency/license inventory helper."""

from __future__ import annotations

import argparse
import csv
import importlib.metadata as metadata
import json
import re
import sys
import tomllib
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

LicenseMetadataQuality = Literal[
    "license_expression",
    "license_field_only",
    "classifier_only",
    "multiple_signals",
    "missing",
]
OutputFormat = Literal["markdown", "json", "csv"]
FailCondition = Literal["missing-license", "not-installed", "classifier-only"]


@dataclass(slots=True, frozen=True)
class DependencyDeclaration:
    normalized_name: str
    source: str
    requirement: str


@dataclass(slots=True)
class InventoryRow:
    normalized_name: str
    package_name: str
    source: str
    declared_requirement: str
    installed: bool
    version: str
    license_expression: str
    license_field: str
    license_classifiers: tuple[str, ...]
    license_metadata_summary: str
    license_metadata_quality: LicenseMetadataQuality
    summary: str
    homepage_url: str
    direct: bool
    transitive: bool
    transitive_parents: tuple[str, ...] = field(default_factory=tuple)


def _normalize_requirement_name(requirement: str) -> str:
    requirement = requirement.strip()
    if not requirement:
        return ""
    marker_free = requirement.split(";", maxsplit=1)[0].strip()
    match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", marker_free)
    if match:
        return match.group(1).lower().replace("_", "-")
    fallback = re.split(r"[<>=!~\s\[]", marker_free, maxsplit=1)[0]
    return fallback.strip().lower().replace("_", "-")


def _load_dependency_declarations(pyproject_path: Path) -> list[DependencyDeclaration]:
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    declarations: list[DependencyDeclaration] = []
    project = data.get("project", {})
    for requirement in project.get("dependencies", []):
        name = _normalize_requirement_name(str(requirement))
        if name:
            declarations.append(
                DependencyDeclaration(
                    normalized_name=name,
                    source="runtime",
                    requirement=str(requirement),
                )
            )

    for group_name, requirements in data.get("dependency-groups", {}).items():
        for requirement in requirements:
            name = _normalize_requirement_name(str(requirement))
            if name:
                declarations.append(
                    DependencyDeclaration(
                        normalized_name=name,
                        source=f"dev:{group_name}",
                        requirement=str(requirement),
                    )
                )

    for requirement in data.get("build-system", {}).get("requires", []):
        name = _normalize_requirement_name(str(requirement))
        if name:
            declarations.append(
                DependencyDeclaration(
                    normalized_name=name,
                    source="build-system",
                    requirement=str(requirement),
                )
            )

    return sorted(
        declarations,
        key=lambda item: (item.source, item.normalized_name, item.requirement),
    )


def _extract_license_classifiers(dist: metadata.Distribution) -> tuple[str, ...]:
    classifiers = dist.metadata.get_all("Classifier") or []
    return tuple(sorted(c for c in classifiers if c.startswith("License ::")))


def _classify_license_quality(
    *,
    license_expression: str,
    license_field: str,
    license_classifiers: tuple[str, ...],
) -> LicenseMetadataQuality:
    has_expression = bool(license_expression.strip())
    has_field = bool(license_field.strip())
    has_classifiers = bool(license_classifiers)

    signal_count = sum([has_expression, has_field, has_classifiers])
    if signal_count == 0:
        return "missing"
    if signal_count > 1:
        return "multiple_signals"
    if has_expression:
        return "license_expression"
    if has_field:
        return "license_field_only"
    return "classifier_only"


def _summarize_license_metadata(
    *,
    license_expression: str,
    license_field: str,
    license_classifiers: tuple[str, ...],
    quality: LicenseMetadataQuality,
) -> str:
    parts: list[str] = []
    if license_expression:
        parts.append(f"expr={license_expression}")
    if license_field:
        parts.append(f"license={license_field}")
    if license_classifiers:
        parts.append("classifiers=" + "; ".join(license_classifiers))
    if not parts:
        return "missing"
    return f"{quality}: " + " | ".join(parts)


def _get_distribution(name: str) -> metadata.Distribution | None:
    try:
        return metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return None


def _build_row(
    *,
    normalized_name: str,
    source: str,
    declared_requirement: str,
    direct: bool,
    transitive: bool,
    transitive_parents: tuple[str, ...] = (),
) -> InventoryRow:
    dist = _get_distribution(normalized_name)
    if dist is None:
        return InventoryRow(
            normalized_name=normalized_name,
            package_name=normalized_name,
            source=source,
            declared_requirement=declared_requirement,
            installed=False,
            version="",
            license_expression="",
            license_field="",
            license_classifiers=(),
            license_metadata_summary="missing",
            license_metadata_quality="missing",
            summary="package not installed in current environment",
            homepage_url="",
            direct=direct,
            transitive=transitive,
            transitive_parents=transitive_parents,
        )

    license_expression = str(dist.metadata.get("License-Expression", "") or "").strip()
    license_field = str(dist.metadata.get("License", "") or "").strip()
    classifiers = _extract_license_classifiers(dist)
    quality = _classify_license_quality(
        license_expression=license_expression,
        license_field=license_field,
        license_classifiers=classifiers,
    )

    homepage_url = (
        str(dist.metadata.get("Home-page", "") or "").strip()
        or str(dist.metadata.get("Project-URL", "") or "").strip()
    )
    summary = str(dist.metadata.get("Summary", "") or "").strip()

    return InventoryRow(
        normalized_name=normalized_name,
        package_name=str(dist.metadata.get("Name", normalized_name) or normalized_name),
        source=source,
        declared_requirement=declared_requirement,
        installed=True,
        version=dist.version,
        license_expression=license_expression,
        license_field=license_field,
        license_classifiers=classifiers,
        license_metadata_summary=_summarize_license_metadata(
            license_expression=license_expression,
            license_field=license_field,
            license_classifiers=classifiers,
            quality=quality,
        ),
        license_metadata_quality=quality,
        summary=summary,
        homepage_url=homepage_url,
        direct=direct,
        transitive=transitive,
        transitive_parents=transitive_parents,
    )


def _parse_distribution_requirement_name(requirement: str) -> str:
    return _normalize_requirement_name(requirement)


def _discover_transitive_rows(direct_rows: list[InventoryRow]) -> list[InventoryRow]:
    roots = [row for row in direct_rows if row.installed]
    queue: deque[str] = deque(sorted({row.normalized_name for row in roots}))
    visited: set[str] = set(queue)
    discovered: dict[str, InventoryRow] = {}
    parents: dict[str, set[str]] = defaultdict(set)

    while queue:
        package_name = queue.popleft()
        dist = _get_distribution(package_name)
        if dist is None:
            continue
        requirements = dist.requires or []
        for req in requirements:
            child = _parse_distribution_requirement_name(req)
            if not child:
                continue
            parents[child].add(package_name)
            if child not in visited:
                visited.add(child)
                queue.append(child)

    direct_names = {row.normalized_name for row in direct_rows}
    for child_name in sorted(visited):
        if child_name in direct_names:
            continue
        transitive_parents = tuple(sorted(parents.get(child_name, set())))
        discovered[child_name] = _build_row(
            normalized_name=child_name,
            source="transitive",
            declared_requirement="",
            direct=False,
            transitive=True,
            transitive_parents=transitive_parents,
        )

    return sorted(discovered.values(), key=lambda row: (row.normalized_name, row.package_name))


def _deduplicate_direct_rows(rows: list[InventoryRow]) -> list[InventoryRow]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[InventoryRow] = []
    for row in rows:
        key = (row.normalized_name, row.source, row.declared_requirement)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def build_inventory(pyproject_path: Path, include_transitive: bool = False) -> dict[str, Any]:
    declarations = _load_dependency_declarations(pyproject_path)
    direct_rows = _deduplicate_direct_rows(
        [
            _build_row(
                normalized_name=decl.normalized_name,
                source=decl.source,
                declared_requirement=decl.requirement,
                direct=True,
                transitive=False,
            )
            for decl in declarations
        ]
    )

    transitive_rows: list[InventoryRow] = []
    if include_transitive:
        transitive_rows = _discover_transitive_rows(direct_rows)

    runtime_rows = [row for row in direct_rows if row.source == "runtime"]
    dev_rows = [row for row in direct_rows if row.source.startswith("dev:")]
    build_rows = [row for row in direct_rows if row.source == "build-system"]

    missing_license_count = sum(
        1 for row in [*direct_rows, *transitive_rows] if row.license_metadata_quality == "missing"
    )
    classifier_only_count = sum(
        1
        for row in [*direct_rows, *transitive_rows]
        if row.license_metadata_quality == "classifier_only"
    )

    summary = {
        "pyproject_path": str(pyproject_path),
        "direct_runtime_count": len(runtime_rows),
        "direct_dev_count": len(dev_rows),
        "build_system_count": len(build_rows),
        "installed_direct_count": sum(1 for row in direct_rows if row.installed),
        "missing_direct_count": sum(1 for row in direct_rows if not row.installed),
        "include_transitive": include_transitive,
        "transitive_count": len(transitive_rows),
        "missing_license_count": missing_license_count,
        "classifier_only_count": classifier_only_count,
    }

    return {
        "generated_from": str(pyproject_path),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "summary": summary,
        "direct_runtime": runtime_rows,
        "direct_dev": dev_rows,
        "build_system": build_rows,
        "transitive": transitive_rows,
        "limitations": [
            "Transitive discovery is best-effort from installed metadata requires fields.",
            (
                "Requirement markers/extras/version constraints are not fully resolved; "
                "only package names are normalized."
            ),
            "License signals are technical metadata quality hints, not legal conclusions.",
        ],
    }


def _row_to_json(row: InventoryRow) -> dict[str, Any]:
    return {
        "normalized_name": row.normalized_name,
        "package_name": row.package_name,
        "source": row.source,
        "declared_requirement": row.declared_requirement,
        "installed": row.installed,
        "version": row.version,
        "license_expression": row.license_expression,
        "license_field": row.license_field,
        "license_classifiers": list(row.license_classifiers),
        "license_metadata_summary": row.license_metadata_summary,
        "license_metadata_quality": row.license_metadata_quality,
        "summary": row.summary,
        "homepage_url": row.homepage_url,
        "direct": row.direct,
        "transitive": row.transitive,
        "transitive_parents": list(row.transitive_parents),
    }


def _row_to_csv(row: InventoryRow) -> dict[str, str]:
    return {
        "normalized_name": row.normalized_name,
        "package_name": row.package_name,
        "source": row.source,
        "declared_requirement": row.declared_requirement,
        "installed": "yes" if row.installed else "no",
        "version": row.version,
        "direct": "yes" if row.direct else "no",
        "transitive": "yes" if row.transitive else "no",
        "transitive_parents": ";".join(row.transitive_parents),
        "license_expression": row.license_expression,
        "license_field": row.license_field,
        "license_classifiers": "; ".join(row.license_classifiers),
        "license_metadata_summary": row.license_metadata_summary,
        "license_metadata_quality": row.license_metadata_quality,
        "summary": row.summary,
        "homepage_url": row.homepage_url,
    }


def render_markdown_report(inventory: dict[str, Any]) -> str:
    summary = inventory["summary"]

    lines: list[str] = [
        "# Local License Inventory",
        "",
        "Generated from local package metadata via `importlib.metadata`.",
        "",
        "## Summary",
        "",
        f"- Pyproject: `{summary['pyproject_path']}`",
        f"- Direct runtime dependencies: {summary['direct_runtime_count']}",
        f"- Direct dev dependencies: {summary['direct_dev_count']}",
        f"- Build-system dependencies: {summary['build_system_count']}",
        f"- Installed direct dependencies: {summary['installed_direct_count']}",
        f"- Missing direct dependencies: {summary['missing_direct_count']}",
        f"- Include transitive: {summary['include_transitive']}",
        f"- Transitive dependency count: {summary['transitive_count']}",
        f"- Missing license metadata count: {summary['missing_license_count']}",
        f"- Classifier-only license metadata count: {summary['classifier_only_count']}",
        "",
    ]

    def add_table(title: str, rows: list[InventoryRow]) -> None:
        lines.extend(
            [
                f"## {title}",
                "",
                (
                    "| Package | Source | Installed | Version | License metadata summary | "
                    "License metadata quality | Notes |"
                ),
                "|---|---|---|---|---|---|---|",
            ]
        )
        if not rows:
            lines.append("| _none_ | - | - | - | - | - | - |")
        for row in rows:
            installed_label = "installed" if row.installed else "not-installed"
            package_cell = f"`{row.package_name or row.normalized_name}`"
            if row.declared_requirement:
                package_cell += f" (`{row.declared_requirement}`)"
            if row.transitive_parents:
                parent_list = ", ".join(row.transitive_parents)
                package_cell += f" (parents: `{parent_list}`)"
            lines.append(
                "| "
                f"{package_cell} | {row.source} | {installed_label} | {row.version or '-'} | "
                f"{row.license_metadata_summary} | {row.license_metadata_quality} | "
                f"{row.summary or '-'} |"
            )
        lines.append("")

    add_table("Direct runtime dependencies", inventory["direct_runtime"])
    add_table("Direct dev dependencies", inventory["direct_dev"])
    add_table("Build-system dependencies", inventory["build_system"])
    if inventory["summary"]["include_transitive"]:
        add_table("Transitive dependencies (best-effort)", inventory["transitive"])

    lines.extend(
        [
            "## Uncertainty and limitations",
            "",
            "- Transitive dependency discovery is best-effort based on installed package metadata.",
            (
                "- Requirement markers/extras are not fully evaluated; "
                "only requirement names are normalized."
            ),
            "- License metadata quality is a technical signal only and not legal advice.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_json_report(inventory: dict[str, Any], failure_conditions: list[FailCondition]) -> str:
    payload = {
        "generated_from": inventory["generated_from"],
        "generated_at_utc": inventory["generated_at_utc"],
        "summary": inventory["summary"],
        "direct_runtime": [_row_to_json(row) for row in inventory["direct_runtime"]],
        "direct_dev": [_row_to_json(row) for row in inventory["direct_dev"]],
        "build_system": [_row_to_json(row) for row in inventory["build_system"]],
        "transitive": [_row_to_json(row) for row in inventory["transitive"]],
        "failure_conditions": list(failure_conditions),
        "limitations": inventory["limitations"],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _render_report(
    inventory: dict[str, Any],
    *,
    fmt: OutputFormat,
    failure_conditions: list[FailCondition],
) -> str:
    if fmt == "json":
        return render_json_report(inventory, failure_conditions)
    if fmt == "csv":
        import io

        buffer = io.StringIO()
        columns = [
            "normalized_name",
            "package_name",
            "source",
            "declared_requirement",
            "installed",
            "version",
            "direct",
            "transitive",
            "transitive_parents",
            "license_expression",
            "license_field",
            "license_classifiers",
            "license_metadata_summary",
            "license_metadata_quality",
            "summary",
            "homepage_url",
        ]
        rows = [
            *inventory["direct_runtime"],
            *inventory["direct_dev"],
            *inventory["build_system"],
            *inventory["transitive"],
        ]
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        for row in sorted(
            rows, key=lambda row: (row.source, row.normalized_name, row.package_name)
        ):
            writer.writerow(_row_to_csv(row))
        return buffer.getvalue()
    return render_markdown_report(inventory)


def _evaluate_fail_conditions(
    inventory: dict[str, Any], fail_conditions: list[FailCondition]
) -> list[str]:
    direct_rows = [
        *inventory["direct_runtime"],
        *inventory["direct_dev"],
        *inventory["build_system"],
    ]
    all_rows = [*direct_rows, *inventory["transitive"]]

    failures: list[str] = []
    if "not-installed" in fail_conditions:
        missing = [row.normalized_name for row in direct_rows if not row.installed]
        if missing:
            failures.append(
                "Fail condition 'not-installed' matched missing direct packages: "
                + ", ".join(sorted(missing))
            )

    if "missing-license" in fail_conditions:
        missing_license = [
            row.normalized_name for row in all_rows if row.license_metadata_quality == "missing"
        ]
        if missing_license:
            failures.append(
                "Fail condition 'missing-license' matched packages: "
                + ", ".join(sorted(missing_license))
            )

    if "classifier-only" in fail_conditions:
        classifier_only = [
            row.normalized_name
            for row in all_rows
            if row.license_metadata_quality == "classifier_only"
        ]
        if classifier_only:
            failures.append(
                "Fail condition 'classifier-only' matched packages: "
                + ", ".join(sorted(classifier_only))
            )

    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate local dependency/license inventory.")
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "csv"],
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--include-transitive",
        action="store_true",
        help="Include best-effort transitive installed dependencies.",
    )
    parser.add_argument(
        "--fail-on",
        choices=["missing-license", "not-installed", "classifier-only"],
        action="append",
        default=[],
        help="Exit non-zero when selected condition is present.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    inventory = build_inventory(
        pyproject_path=args.pyproject,
        include_transitive=bool(args.include_transitive),
    )
    report = _render_report(
        inventory,
        fmt=args.format,
        failure_conditions=args.fail_on,
    )

    if args.output:
        args.output.write_text(report, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(report, end="")

    failures = _evaluate_fail_conditions(inventory, args.fail_on)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
