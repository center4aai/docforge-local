from pathlib import Path

from repo_autodocs.deterministic import (
    DeterministicContext,
    render_home_page,
    render_project_brief_page,
)
from repo_autodocs.models import CodeFactsBundle, GroundedContextBundle, RepoManifest


def test_render_deterministic_pages_do_not_depend_on_readme(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_bytes(b"\xff\xfe\x00bad-encoding")
    ctx = DeterministicContext(
        manifest=RepoManifest(project_root=tmp_path, top_level_directories=["src"]),
        theory_sources=[],
        code_facts_bundle=CodeFactsBundle(),
        grounded_bundle=GroundedContextBundle(),
    )

    home = render_home_page(tmp_path, ctx, generated_text_language="en")
    rendered = render_project_brief_page(tmp_path, ctx, generated_text_language="en")

    assert "Documentation" in home
    assert "# Project Brief" in rendered
    assert "README" not in rendered
