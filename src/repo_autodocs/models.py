"""Typed models for the repo-autodocs MVP pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(slots=True)
class ProjectPaths:
    """Resolved local paths used by the application."""

    project_root: Path
    docs_dir: Path
    reference_dir: Path | None
    output_dir: Path
    site_dir: Path


@dataclass(slots=True)
class RepositoryTextEvidence:
    """Deterministic textual evidence discovered from repository-owned files."""

    category: str
    relative_path: str
    excerpt: str
    line_count: int


@dataclass(slots=True)
class RepoManifest:
    """Deterministic summary of repository structure."""

    project_root: Path
    top_level_directories: list[str] = field(default_factory=list)
    top_level_files: list[str] = field(default_factory=list)
    has_git_dir: bool = False
    has_pyproject: bool = False
    has_mkdocs_config: bool = False
    has_docs_dir: bool = False
    has_src_dir: bool = False
    has_tests_dir: bool = False
    textual_evidence: list[RepositoryTextEvidence] = field(default_factory=list)


@dataclass(slots=True)
class PythonModuleInfo:
    """Deterministic metadata about a discovered Python module file."""

    module_path: Path
    relative_path: str
    module_name: str
    is_package: bool
    import_count: int
    defined_class_count: int
    defined_function_count: int
    is_test_module: bool = False
    module_importance_score: int = 0


@dataclass(slots=True)
class PythonSymbolInfo:
    """Deterministic top-level Python symbol metadata."""

    symbol_name: str
    symbol_type: str
    module_name: str
    relative_path: str
    lineno: int
    signature: str | None = None
    docstring: str | None = None
    is_public: bool = True


@dataclass(slots=True)
class ImportEdge:
    """Deterministic import relationship observed in Python source."""

    source_module: str
    imported_module: str
    relative: bool


@dataclass(slots=True)
class EntrypointEvidence:
    """Deterministic entrypoint evidence discovered in source code."""

    label: str
    module_name: str
    relative_path: str
    reason: str


@dataclass(slots=True)
class CodeExcerptEvidence:
    """Deterministic code excerpt from a selected high-value file/module."""

    module_name: str
    relative_path: str
    excerpt_kind: str
    start_line: int
    end_line: int
    excerpt: str


@dataclass(slots=True)
class CodeFactsBundle:
    """Deterministic structural code-facts extracted from repository code."""

    modules: list[PythonModuleInfo] = field(default_factory=list)
    symbols: list[PythonSymbolInfo] = field(default_factory=list)
    imports: list[ImportEdge] = field(default_factory=list)
    detected_entrypoints: list[str] = field(default_factory=list)
    entrypoint_evidence: list[EntrypointEvidence] = field(default_factory=list)
    code_excerpts: list[CodeExcerptEvidence] = field(default_factory=list)
    framework_hints: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TheorySource:
    """Discovered methodology/theory file metadata."""

    path: Path
    relative_path: str
    extension: str
    size_bytes: int


ReferenceSourceOrigin = Literal["explicit", "default"]
ReferenceSourceKind = Literal["general_reference", "agent_instruction", "readme_claims"]
ReferenceAnalysisRoute = Literal[
    "general_reference_alignment", "agent_instruction_alignment", "readme_claim_alignment"
]
ReferenceParseStatus = Literal["not_attempted", "parsed", "ingestible_unparsed", "not_ingestible"]


@dataclass(slots=True)
class ExternalReferenceSource:
    """Typed discovered external-reference metadata used for routing/inventory."""

    path: Path
    display_path: str
    extension: str
    size_bytes: int
    origin: ReferenceSourceOrigin
    kind: ReferenceSourceKind
    route: ReferenceAnalysisRoute
    selection_reason: str
    ingest_eligible: bool
    parse_status: ReferenceParseStatus = "not_attempted"
    participated_in_grounding: bool = False

    def to_theory_source(self) -> TheorySource:
        return TheorySource(
            path=self.path,
            relative_path=self.display_path,
            extension=self.extension,
            size_bytes=self.size_bytes,
        )


@dataclass(slots=True)
class MethodologyDocument:
    """Normalized text document from methodology ingestion."""

    source_path: Path
    relative_path: str
    extension: str
    title: str | None
    raw_text: str
    char_count: int


@dataclass(slots=True)
class MethodologyChunk:
    """Deterministic context chunk derived from a methodology document."""

    chunk_id: str
    document_relative_path: str
    index: int
    text: str
    char_count: int
    section_hint: str | None


@dataclass(slots=True)
class GroundedContextBundle:
    """Grounded methodology bundle used by downstream prompt assembly."""

    documents: list[MethodologyDocument] = field(default_factory=list)
    chunks: list[MethodologyChunk] = field(default_factory=list)
    discovered_source_count: int = 0
    unparsed_sources: list[TheorySource] = field(default_factory=list)


GeneralReferenceVerdict = Literal[
    "supported", "partially_supported", "missing_evidence", "contradicted"
]
AgentInstructionVerdict = Literal[
    "supported",
    "partially_supported",
    "not_evidenced",
    "contradicted",
    "out_of_scope_or_non_verifiable",
]
ReadmeClaimVerdict = Literal[
    "supported",
    "partially_supported",
    "not_evidenced",
    "contradicted",
    "not_statically_verifiable",
]


@dataclass(slots=True)
class AlignmentCandidate:
    route: ReferenceAnalysisRoute
    source_path: str
    claim_text: str
    claim_type: str
    verifiable: bool = True
    rationale: str = ""


@dataclass(slots=True)
class AlignmentVerdictEntry:
    route: ReferenceAnalysisRoute
    source_path: str
    claim_text: str
    claim_type: str
    verdict: str
    evidence_note: str
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class RouteAlignmentResult:
    route: ReferenceAnalysisRoute
    source_count: int = 0
    candidates: list[AlignmentCandidate] = field(default_factory=list)
    verdicts: list[AlignmentVerdictEntry] = field(default_factory=list)

    @property
    def verdict_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for verdict in self.verdicts:
            counts[verdict.verdict] = counts.get(verdict.verdict, 0) + 1
        return counts


@dataclass(slots=True)
class RoutedAlignmentBundle:
    reference_alignment: RouteAlignmentResult = field(
        default_factory=lambda: RouteAlignmentResult(route="general_reference_alignment")
    )
    agent_instruction_alignment: RouteAlignmentResult = field(
        default_factory=lambda: RouteAlignmentResult(route="agent_instruction_alignment")
    )
    readme_claim_alignment: RouteAlignmentResult = field(
        default_factory=lambda: RouteAlignmentResult(route="readme_claim_alignment")
    )


@dataclass(slots=True)
class RouteLLMMaterial:
    """Bounded route-specific source material for LLM alignment prompts."""

    route: ReferenceAnalysisRoute
    source_path: str
    section_hint: str
    excerpt: str


@dataclass(slots=True)
class RoutedLLMMaterialBundle:
    """Route-aware LLM grounding material derived from discovered reference sources."""

    reference_alignment: list[RouteLLMMaterial] = field(default_factory=list)
    agent_instruction_alignment: list[RouteLLMMaterial] = field(default_factory=list)
    readme_claim_alignment: list[RouteLLMMaterial] = field(default_factory=list)


@dataclass(slots=True)
class GenerationRequest:
    """Input contract for snapshot generation."""

    manifest: RepoManifest
    theory_sources: list[TheorySource] = field(default_factory=list)
    generated_text_language: Literal["en", "ru"] = "en"


@dataclass(slots=True)
class GenerationResult:
    """Output contract for snapshot generation."""

    markdown: str
    output_path: Path | None = None
