"""Deterministic ingestion of discovered methodology sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import docx2txt
from pypdf import PdfReader

from repo_autodocs.models import MethodologyDocument, TheorySource

INGESTIBLE_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}


@dataclass(slots=True)
class IngestionOutcome:
    """Result of methodology source ingestion."""

    documents: list[MethodologyDocument] = field(default_factory=list)
    unparsed_sources: list[TheorySource] = field(default_factory=list)


def ingest_methodology_sources(theory_sources: list[TheorySource]) -> IngestionOutcome:
    """Ingest eligible reference files and report unparsed files explicitly."""

    documents: list[MethodologyDocument] = []
    unparsed_sources: list[TheorySource] = []

    for source in sorted(theory_sources, key=lambda item: item.relative_path):
        if source.extension not in INGESTIBLE_EXTENSIONS:
            unparsed_sources.append(source)
            continue

        raw_text = _read_source_text(source)
        if raw_text is None:
            unparsed_sources.append(source)
            continue
        documents.append(
            MethodologyDocument(
                source_path=source.path,
                relative_path=source.relative_path,
                extension=source.extension,
                title=_derive_title(
                    raw_text=raw_text, extension=source.extension, source_path=source.path
                ),
                raw_text=raw_text,
                char_count=len(raw_text),
            )
        )

    return IngestionOutcome(documents=documents, unparsed_sources=unparsed_sources)


def _read_text_safe(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def _read_source_text(source: TheorySource) -> str | None:
    if source.extension in {".md", ".txt"}:
        return _read_text_safe(source.path)
    if source.extension == ".pdf":
        return _read_pdf_text_safe(source.path)
    if source.extension == ".docx":
        return _read_docx_text_safe(source.path)
    return None


def _read_pdf_text_safe(path: Path) -> str | None:
    try:
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
    except Exception:
        return None


def _read_docx_text_safe(path: Path) -> str | None:
    try:
        return docx2txt.process(str(path)).strip()
    except Exception:
        return None


def _derive_title(raw_text: str, extension: str, source_path: Path) -> str:
    if extension == ".md":
        for line in raw_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip() or source_path.stem

    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped

    return source_path.stem
