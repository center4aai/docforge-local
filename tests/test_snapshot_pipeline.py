from pathlib import Path

from repo_autodocs.generator import generate_project_snapshot
from repo_autodocs.models import GenerationRequest
from repo_autodocs.publisher import write_project_snapshot
from repo_autodocs.scanner import scan_repository
from repo_autodocs.theory import discover_theory_sources


def test_generate_snapshot_writes_markdown_file(tmp_path: Path) -> None:
    manifest = scan_repository(Path.cwd())
    theory_sources = discover_theory_sources(Path("docs/context/methodology"))
    result = generate_project_snapshot(
        GenerationRequest(manifest=manifest, theory_sources=theory_sources)
    )

    output_path = write_project_snapshot(result.markdown, tmp_path / "project_snapshot.md")

    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "# Project Snapshot" in content
    assert "deterministic repository snapshot" in content
    assert "**Project root label:**" in content
    assert str(Path.cwd()) not in content
