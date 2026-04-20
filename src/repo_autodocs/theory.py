"""External reference discovery and compatibility helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from repo_autodocs.ingest import INGESTIBLE_EXTENSIONS
from repo_autodocs.models import (
    ExternalReferenceSource,
    GroundedContextBundle,
    TheorySource,
)

AGENT_INSTRUCTION_FILENAMES = {
    "AGENTS.md",
    "CLAUDE.md",
    "CODEX.md",
    "CURSOR.md",
    "AIDER.md",
    "CONTINUE.md",
    "GEMINI.md",
}


@dataclass(slots=True)
class DiscoveredMaterial:
    """Backward-compatible discovered material item for legacy consumers/tests."""

    path: Path
    relative_path: str
    extension: str
    size_bytes: int


@dataclass(slots=True)
class ReferenceDiscovery:
    """Canonical multi-input discovery inventory with compatibility aliases."""

    sources: list[ExternalReferenceSource] = field(default_factory=list)

    @property
    def discovered_materials(self) -> list[DiscoveredMaterial]:
        return [
            DiscoveredMaterial(
                path=source.path,
                relative_path=source.display_path,
                extension=source.extension,
                size_bytes=source.size_bytes,
            )
            for source in self.sources
        ]

    @property
    def ingest_eligible_materials(self) -> list[TheorySource]:
        return [source.to_theory_source() for source in self.sources if source.ingest_eligible]

    @property
    def grounding_sources(self) -> list[TheorySource]:
        return [
            source.to_theory_source()
            for source in self.sources
            if source.ingest_eligible and source.route == "general_reference_alignment"
        ]

    @property
    def parse_candidates(self) -> list[TheorySource]:
        """Deprecated alias kept for backwards-compatible callers/tests."""

        return self.ingest_eligible_materials

    @property
    def supported_sources(self) -> list[TheorySource]:
        """Deprecated alias kept for backwards-compatible callers/tests."""

        return self.ingest_eligible_materials

    @property
    def non_ingestible_materials(self) -> list[DiscoveredMaterial]:
        return [
            DiscoveredMaterial(
                path=source.path,
                relative_path=source.display_path,
                extension=source.extension,
                size_bytes=source.size_bytes,
            )
            for source in self.sources
            if not source.ingest_eligible
        ]

    @property
    def unsupported_sources(self) -> list[DiscoveredMaterial]:
        """Deprecated alias kept for backwards-compatible callers/tests."""

        return self.non_ingestible_materials


@dataclass(slots=True)
class DiscoveredReferencePath:
    input_path: Path
    origin: str
    exists: bool
    is_file: bool
    is_dir: bool
    in_project_root: bool


def _classify_kind(path: Path, *, explicit: bool) -> tuple[str, str, str]:
    name = path.name.upper()
    if name == "README.MD":
        return (
            "readme_claims",
            "readme_claim_alignment",
            "explicit input" if explicit else "default README target",
        )
    if name in AGENT_INSTRUCTION_FILENAMES:
        return (
            "agent_instruction",
            "agent_instruction_alignment",
            "default agent instruction target" if not explicit else "explicit input",
        )
    return (
        "general_reference",
        "general_reference_alignment",
        "explicit input" if explicit else "default target",
    )


def _discover_files_from_explicit_path(path: Path) -> list[Path]:
    if not path.exists():
        return []
    if path.is_file():
        return [path.resolve()]
    if path.is_dir():
        return sorted(
            (candidate.resolve() for candidate in path.rglob("*") if candidate.is_file()),
            key=lambda candidate: str(candidate),
        )
    return []


def _display_path(path: Path, project_root: Path) -> str:
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return str(path)


def discover_reference_materials(
    reference_dir: Path | None,
) -> ReferenceDiscovery:
    """Deprecated single-path shim for compatibility."""

    if reference_dir is None:
        return ReferenceDiscovery()
    resolved_root = reference_dir.resolve()
    return discover_external_references(
        project_root=resolved_root,
        explicit_reference_paths=(resolved_root,),
    )


def discover_external_references(
    *,
    project_root: Path,
    explicit_reference_paths: tuple[Path, ...] = (),
    include_readme_default: bool = False,
    include_agent_instructions_default: bool = False,
    default_readme_patterns: tuple[str, ...] = ("README.md",),
    default_agent_instruction_patterns: tuple[str, ...] = (
        "**/AGENTS.md",
        "**/CLAUDE.md",
        "**/CODEX.md",
        "**/CURSOR.md",
        "**/AIDER.md",
        "**/CONTINUE.md",
        "**/GEMINI.md",
    ),
) -> ReferenceDiscovery:
    """Discover external references from 0..N explicit paths plus optional defaults."""

    root = project_root.resolve()
    deduped: dict[Path, ExternalReferenceSource] = {}

    explicit_candidates = sorted({path.resolve() for path in explicit_reference_paths}, key=str)
    for explicit in explicit_candidates:
        for file_path in _discover_files_from_explicit_path(explicit):
            extension = file_path.suffix.lower()
            kind, route, reason = _classify_kind(file_path, explicit=True)
            deduped[file_path] = ExternalReferenceSource(
                path=file_path,
                display_path=_display_path(file_path, root),
                extension=extension,
                size_bytes=file_path.stat().st_size,
                origin="explicit",
                kind=kind,  # type: ignore[arg-type]
                route=route,  # type: ignore[arg-type]
                selection_reason=reason,
                ingest_eligible=extension in INGESTIBLE_EXTENSIONS,
            )

    if include_readme_default:
        patterns = default_readme_patterns or ("README.md",)
        for pattern in patterns:
            for candidate in sorted(root.glob(pattern), key=lambda p: str(p)):
                if not candidate.is_file():
                    continue
                resolved = candidate.resolve()
                if resolved in deduped:
                    continue
                extension = resolved.suffix.lower()
                deduped[resolved] = ExternalReferenceSource(
                    path=resolved,
                    display_path=_display_path(resolved, root),
                    extension=extension,
                    size_bytes=resolved.stat().st_size,
                    origin="default",
                    kind="readme_claims",
                    route="readme_claim_alignment",
                    selection_reason=f"default README target (pattern={pattern})",
                    ingest_eligible=extension in INGESTIBLE_EXTENSIONS,
                )

    if include_agent_instructions_default:
        patterns = default_agent_instruction_patterns or tuple(
            f"**/{name}" for name in sorted(AGENT_INSTRUCTION_FILENAMES)
        )
        for pattern in patterns:
            for candidate in sorted(root.glob(pattern), key=lambda p: str(p)):
                if not candidate.is_file():
                    continue
                resolved = candidate.resolve()
                if resolved in deduped:
                    continue
                extension = resolved.suffix.lower()
                deduped[resolved] = ExternalReferenceSource(
                    path=resolved,
                    display_path=_display_path(resolved, root),
                    extension=extension,
                    size_bytes=resolved.stat().st_size,
                    origin="default",
                    kind="agent_instruction",
                    route="agent_instruction_alignment",
                    selection_reason=f"default agent instruction target (pattern={pattern})",
                    ingest_eligible=extension in INGESTIBLE_EXTENSIONS,
                )

    ordered = sorted(
        deduped.values(),
        key=lambda source: (source.origin, source.kind, source.display_path),
    )
    return ReferenceDiscovery(sources=ordered)


def select_theory_grounding_sources(discovery: ReferenceDiscovery) -> list[TheorySource]:
    """Return only general-reference sources for current theory-alignment grounding flow."""

    return discovery.grounding_sources


def mark_reference_parse_statuses(
    discovery: ReferenceDiscovery,
    grounded_bundle: GroundedContextBundle,
) -> ReferenceDiscovery:
    """Apply parse/grounding status onto discovery inventory after grounding."""

    parsed_paths = {doc.source_path.resolve() for doc in grounded_bundle.documents}
    unparsed_paths = {source.path.resolve() for source in grounded_bundle.unparsed_sources}
    for source in discovery.sources:
        resolved = source.path.resolve()
        source.participated_in_grounding = source.route == "general_reference_alignment"
        if not source.ingest_eligible:
            source.parse_status = "not_ingestible"
        elif resolved in parsed_paths:
            source.parse_status = "parsed"
        elif resolved in unparsed_paths or source.participated_in_grounding:
            source.parse_status = "ingestible_unparsed"
        else:
            source.parse_status = "not_attempted"
    return discovery


def discover_theory_sources(methodology_dir: Path | None) -> list[TheorySource]:
    """Deprecated compatibility shim. Use discover_external_references()."""

    return discover_reference_materials(methodology_dir).ingest_eligible_materials


def supported_ingest_extensions() -> list[str]:
    return sorted(INGESTIBLE_EXTENSIONS)
