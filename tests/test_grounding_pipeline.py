from pathlib import Path

from reference_fixtures import write_minimal_docx, write_minimal_pdf

from repo_autodocs.chunking import ChunkingConfig, chunk_methodology_document
from repo_autodocs.grounding import (
    build_grounded_context_bundle,
    render_methodology_chunks_for_prompt,
    summarize_grounded_context,
)
from repo_autodocs.ingest import ingest_methodology_sources
from repo_autodocs.models import MethodologyDocument
from repo_autodocs.theory import discover_theory_sources


def test_ingest_md_and_txt_and_title_extraction(tmp_path: Path) -> None:
    methodology_dir = tmp_path / "methodology"
    methodology_dir.mkdir()

    md_path = methodology_dir / "guide.md"
    md_path.write_text("# Grounding Guide\n\nBody paragraph.", encoding="utf-8")

    txt_path = methodology_dir / "notes.txt"
    txt_path.write_text("First line title\n\nMore details.", encoding="utf-8")
    untitled_path = methodology_dir / "untitled.txt"
    untitled_path.write_text("", encoding="utf-8")

    sources = discover_theory_sources(methodology_dir)
    outcome = ingest_methodology_sources(sources)

    assert len(outcome.documents) == 3
    by_path = {doc.relative_path: doc for doc in outcome.documents}
    assert by_path["guide.md"].title == "Grounding Guide"
    assert by_path["notes.txt"].title == "First line title"
    assert by_path["untitled.txt"].title == "untitled"
    assert outcome.unparsed_sources == []


def test_chunk_generation_is_stable_and_tracks_markdown_heading() -> None:
    raw_text = (
        "# Intro\n\n"
        "This is intro paragraph one.\n\n"
        "This is intro paragraph two.\n\n"
        "## Design\n\n"
        "Design details paragraph one.\n\n"
        "Design details paragraph two."
    )
    doc = MethodologyDocument(
        source_path=Path("/tmp/method.md"),
        relative_path="method.md",
        extension=".md",
        title="Method",
        raw_text=raw_text,
        char_count=len(raw_text),
    )

    config = ChunkingConfig(min_chars=20, target_chars=40, max_chars=60)
    first = chunk_methodology_document(doc, config=config)
    second = chunk_methodology_document(doc, config=config)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert any(chunk.section_hint in {"Intro", "Design"} for chunk in first)


def test_bundle_assembly_with_mixed_formats(tmp_path: Path) -> None:
    methodology_dir = tmp_path / "methodology"
    methodology_dir.mkdir()

    (methodology_dir / "a.md").write_text("# A\n\nAlpha text.", encoding="utf-8")
    (methodology_dir / "b.txt").write_text("Beta title\n\nBeta text.", encoding="utf-8")
    write_minimal_pdf(methodology_dir / "paper.pdf")
    write_minimal_docx(methodology_dir / "spec.docx")
    (methodology_dir / "legacy.rst").write_text("not ingestible", encoding="utf-8")

    sources = discover_theory_sources(methodology_dir)
    bundle = build_grounded_context_bundle(sources)

    assert bundle.discovered_source_count == 4
    assert len(bundle.documents) == 4
    assert bundle.unparsed_sources == []
    assert {document.extension for document in bundle.documents} == {".md", ".txt", ".pdf", ".docx"}
    assert bundle.chunks

    summary = summarize_grounded_context(bundle)
    assert "Discovered sources: 4" in summary
    assert "Ingested documents: 4" in summary
    assert "Ingest-eligible but unparsed sources: 0" in summary

    prompt_block = render_methodology_chunks_for_prompt(bundle, max_chunks=1)
    assert "[REFERENCE CHUNK 1]" in prompt_block


def test_ingest_corrupt_binary_formats_degrade_gracefully(tmp_path: Path) -> None:
    methodology_dir = tmp_path / "methodology"
    methodology_dir.mkdir()
    (methodology_dir / "broken.pdf").write_bytes(b"%PDF-1.4 broken")
    (methodology_dir / "broken.docx").write_bytes(b"not-a-zip")

    sources = discover_theory_sources(methodology_dir)
    outcome = ingest_methodology_sources(sources)

    assert outcome.documents == []
    assert sorted(source.relative_path for source in outcome.unparsed_sources) == [
        "broken.docx",
        "broken.pdf",
    ]
