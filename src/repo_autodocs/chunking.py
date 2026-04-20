"""Deterministic text chunking for ingested methodology documents."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1

from repo_autodocs.models import MethodologyChunk, MethodologyDocument


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    min_chars: int = 800
    target_chars: int = 1000
    max_chars: int = 1200


def chunk_methodology_document(
    document: MethodologyDocument,
    config: ChunkingConfig | None = None,
) -> list[MethodologyChunk]:
    """Chunk one methodology document by ordered paragraph blocks."""

    cfg = config or ChunkingConfig()
    blocks = _split_blocks(document)
    if not blocks:
        return []

    chunks: list[MethodologyChunk] = []
    current_texts: list[str] = []
    current_hint: str | None = None

    def flush() -> None:
        nonlocal current_texts, current_hint
        if not current_texts:
            return
        text = "\n\n".join(current_texts).strip()
        chunk_index = len(chunks)
        chunks.append(
            MethodologyChunk(
                chunk_id=_chunk_id(document.relative_path, chunk_index, text),
                document_relative_path=document.relative_path,
                index=chunk_index,
                text=text,
                char_count=len(text),
                section_hint=current_hint,
            )
        )
        current_texts = []
        current_hint = None

    for block in blocks:
        candidate_texts = current_texts + [block.text]
        candidate_text = "\n\n".join(candidate_texts)
        current_len = len("\n\n".join(current_texts)) if current_texts else 0

        should_flush_before_adding = (
            bool(current_texts)
            and len(candidate_text) > cfg.max_chars
            and current_len >= cfg.min_chars
        )
        if should_flush_before_adding:
            flush()

        if block.section_hint:
            current_hint = block.section_hint

        current_texts.append(block.text)
        if len("\n\n".join(current_texts)) >= cfg.target_chars:
            flush()

    flush()

    if len(chunks) >= 2 and chunks[-1].char_count < max(200, cfg.min_chars // 2):
        merged_text = f"{chunks[-2].text}\n\n{chunks[-1].text}".strip()
        prior_hint = chunks[-1].section_hint or chunks[-2].section_hint
        merged = MethodologyChunk(
            chunk_id=_chunk_id(document.relative_path, chunks[-2].index, merged_text),
            document_relative_path=document.relative_path,
            index=chunks[-2].index,
            text=merged_text,
            char_count=len(merged_text),
            section_hint=prior_hint,
        )
        chunks = chunks[:-2] + [merged]

    normalized: list[MethodologyChunk] = []
    for idx, chunk in enumerate(chunks):
        normalized.append(
            MethodologyChunk(
                chunk_id=_chunk_id(document.relative_path, idx, chunk.text),
                document_relative_path=chunk.document_relative_path,
                index=idx,
                text=chunk.text,
                char_count=chunk.char_count,
                section_hint=chunk.section_hint,
            )
        )

    return normalized


@dataclass(frozen=True, slots=True)
class _Block:
    text: str
    section_hint: str | None


def _split_blocks(document: MethodologyDocument) -> list[_Block]:
    if document.extension == ".md":
        return _split_markdown_blocks(document.raw_text)

    paragraphs = [
        paragraph.strip() for paragraph in document.raw_text.split("\n\n") if paragraph.strip()
    ]
    return [_Block(text=paragraph, section_hint=None) for paragraph in paragraphs]


def _split_markdown_blocks(text: str) -> list[_Block]:
    blocks: list[_Block] = []
    current_lines: list[str] = []
    current_heading: str | None = None

    def flush_current() -> None:
        if not current_lines:
            return
        block_text = "\n".join(current_lines).strip()
        if block_text:
            blocks.append(_Block(text=block_text, section_hint=current_heading))

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("#"):
            flush_current()
            current_lines = []
            heading_text = stripped.lstrip("#").strip()
            if heading_text:
                current_heading = heading_text
            continue

        if stripped == "":
            flush_current()
            current_lines = []
            continue

        current_lines.append(line)

    flush_current()
    return blocks


def _chunk_id(relative_path: str, index: int, text: str) -> str:
    digest = sha1(f"{relative_path}|{index}|{text[:120]}".encode()).hexdigest()[:12]
    return f"meth:{relative_path}:{index}:{digest}"
