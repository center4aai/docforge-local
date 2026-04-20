from pathlib import Path

from repo_autodocs.theory import discover_reference_materials, discover_theory_sources


def test_discover_theory_sources_from_methodology_dir(tmp_path: Path) -> None:
    methodology_dir = tmp_path / "methodology"
    methodology_dir.mkdir()
    (methodology_dir / "README.md").write_text("# Ref", encoding="utf-8")
    sources = discover_theory_sources(methodology_dir)

    assert sources
    assert any(source.relative_path.endswith("README.md") for source in sources)


def test_discover_reference_materials_distinguishes_discovered_vs_ingest_eligibility(
    tmp_path: Path,
) -> None:
    (tmp_path / "notes.md").write_text("# Notes", encoding="utf-8")
    (tmp_path / "paper.pdf").write_bytes(b"%PDF-1.4 fake")
    (tmp_path / "spec.docx").write_bytes(b"PK fake")
    (tmp_path / "legacy.rst").write_text("unsupported", encoding="utf-8")

    discovery = discover_reference_materials(tmp_path)

    assert len(discovery.discovered_materials) == 4
    assert sorted(item.relative_path for item in discovery.ingest_eligible_materials) == [
        "notes.md",
        "paper.pdf",
        "spec.docx",
    ]
    assert [item.relative_path for item in discovery.non_ingestible_materials] == ["legacy.rst"]
