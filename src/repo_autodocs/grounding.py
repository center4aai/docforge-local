"""Grounded external-reference context bundle assembly helpers."""

from __future__ import annotations

from collections import Counter

from repo_autodocs.chunking import chunk_methodology_document
from repo_autodocs.ingest import ingest_methodology_sources
from repo_autodocs.models import GroundedContextBundle, MethodologyChunk, TheorySource


def build_grounded_context_bundle(theory_sources: list[TheorySource]) -> GroundedContextBundle:
    """Build deterministic document/chunk bundle from discovered reference sources."""

    ingestion = ingest_methodology_sources(theory_sources)
    chunks: list[MethodologyChunk] = []
    for document in ingestion.documents:
        chunks.extend(chunk_methodology_document(document))

    return GroundedContextBundle(
        documents=ingestion.documents,
        chunks=chunks,
        discovered_source_count=len(theory_sources),
        unparsed_sources=ingestion.unparsed_sources,
    )


def summarize_grounded_context(bundle: GroundedContextBundle) -> str:
    """Create a concise deterministic summary for logs/CLI output."""

    counts = Counter(chunk.document_relative_path for chunk in bundle.chunks)
    lines = [
        f"Discovered sources: {bundle.discovered_source_count}",
        f"Ingested documents: {len(bundle.documents)}",
        f"Total chunks: {len(bundle.chunks)}",
        f"Ingest-eligible but unparsed sources: {len(bundle.unparsed_sources)}",
    ]

    if bundle.documents:
        lines.append("Documents:")
        for document in sorted(bundle.documents, key=lambda item: item.relative_path):
            lines.append(f"  - {document.relative_path}: {counts[document.relative_path]} chunks")

    return "\n".join(lines)


def render_methodology_chunks_for_prompt(
    bundle: GroundedContextBundle,
    max_chunks: int = 5,
    max_chars_per_chunk: int = 800,
) -> str:
    """Render a deterministic prompt block from the first N grounded reference chunks."""

    lines = ["[GROUNDED EXTERNAL REFERENCE CHUNKS]"]
    selected = bundle.chunks[:max_chunks]
    if not selected:
        lines.append("No grounded external-reference chunks available.")
        return "\n".join(lines)

    for index, chunk in enumerate(selected, start=1):
        lines.extend(
            [
                f"[REFERENCE CHUNK {index}]",
                f"source: {chunk.document_relative_path}",
                f"section_hint: {chunk.section_hint or '(none)'}",
                chunk.text[:max_chars_per_chunk],
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_grounding_debug_markdown(
    theory_sources: list[TheorySource],
    bundle: GroundedContextBundle,
    preview_chunks: int = 5,
) -> str:
    """Render deterministic debug markdown for reference-grounding outputs."""

    chunk_counts = Counter(chunk.document_relative_path for chunk in bundle.chunks)
    lines = [
        "# Reference Grounding Debug",
        "",
        "This artifact is deterministic and intended for local inspection.",
        "",
        "## Summary",
        "",
        f"- Discovered sources: {len(theory_sources)}",
        f"- Ingested text documents: {len(bundle.documents)}",
        f"- Total chunks: {len(bundle.chunks)}",
        f"- Ingest-eligible but unparsed sources: {len(bundle.unparsed_sources)}",
        "",
        "## Discovered Sources",
        "",
    ]

    if theory_sources:
        for source in sorted(theory_sources, key=lambda item: item.relative_path):
            lines.append(
                f"- `{source.relative_path}` ({source.extension}, {source.size_bytes} bytes)"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Ingested Documents", ""])
    if bundle.documents:
        for document in sorted(bundle.documents, key=lambda item: item.relative_path):
            title = repr(document.title)
            lines.append(
                f"- `{document.relative_path}` title={title}, chars={document.char_count}, "
                f"chunks={chunk_counts[document.relative_path]}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Chunk Preview", ""])
    if bundle.chunks:
        for chunk in bundle.chunks[:preview_chunks]:
            preview = chunk.text[:220].replace("\n", " ")
            lines.extend(
                [
                    f"### `{chunk.chunk_id}`",
                    "",
                    f"- Source: `{chunk.document_relative_path}`",
                    f"- Index: {chunk.index}",
                    f"- Section hint: {chunk.section_hint or '(none)'}",
                    f"- Chars: {chunk.char_count}",
                    "",
                    preview,
                    "",
                ]
            )
    else:
        lines.append("- None")

    return "\n".join(lines).rstrip() + "\n"
