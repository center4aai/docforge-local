from pathlib import Path

from repo_autodocs.codefacts import build_code_facts_bundle
from repo_autodocs.config import load_config
from repo_autodocs.repo_ignore import RepoIgnoreSpec
from repo_autodocs.scanner import scan_repository
from repo_autodocs.theory import discover_reference_materials


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_repo_ignore_user_ignore_and_unignore_patterns(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "pkg" / "keep.py", "def keep():\n    return 1\n")
    _write(tmp_path / "src" / "pkg" / "drop.py", "def drop():\n    return 1\n")

    ignore = RepoIgnoreSpec.build(
        repo_root=tmp_path,
        use_default_ignores=False,
        use_repo_gitignore=False,
        ignore_patterns=("src/pkg/*.py",),
        unignore_patterns=("src/pkg/keep.py",),
    )

    manifest = scan_repository(tmp_path, ignore_spec=ignore)
    bundle = build_code_facts_bundle(tmp_path, ignore_spec=ignore)

    assert manifest.has_src_dir is True
    assert {module.module_name for module in bundle.modules} == {"pkg.keep"}


def test_repo_ignore_does_not_affect_explicit_external_references(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "pkg" / "README.md", "# impl\n")
    refs = tmp_path / "refs"
    _write(refs / "README.md", "# ref\n")

    ignore = RepoIgnoreSpec.build(
        repo_root=tmp_path,
        use_default_ignores=False,
        use_repo_gitignore=False,
        ignore_patterns=("refs/README.md",),
    )
    manifest = scan_repository(tmp_path, ignore_spec=ignore)
    discovery = discover_reference_materials(refs)

    assert "refs" in manifest.top_level_directories
    assert any(item.relative_path == "README.md" for item in discovery.discovered_materials)


def test_repo_ignore_defaults_include_docforge_toml(tmp_path: Path) -> None:
    _write(tmp_path / "docforge.toml", "[paths]\ndocs_dir='docs'\n")

    manifest = scan_repository(tmp_path)

    assert "docforge.toml" not in manifest.top_level_files


def test_repo_ignore_from_config_excludes_tool_owned_paths_inside_repo(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "pkg" / "__init__.py", "")
    _write(tmp_path / "generated-docs" / "index.md", "# generated\n")
    _write(tmp_path / "generated-docs" / "pages" / "overview.md", "# generated\n")
    _write(tmp_path / "generated-site" / "index.html", "<html></html>\n")

    config = load_config(
        project_root=tmp_path,
        cli_overrides={
            "docs_dir": str(tmp_path / "generated-docs"),
            "output_dir": str(tmp_path / "generated-docs" / "pages"),
            "site_dir": str(tmp_path / "generated-site"),
        },
    )

    ignore = RepoIgnoreSpec.from_config(config)
    manifest = scan_repository(tmp_path, ignore_spec=ignore)

    assert "generated-docs" not in manifest.top_level_directories
    assert "generated-site" not in manifest.top_level_directories
    assert "src" in manifest.top_level_directories


def test_config_derived_repo_ignore_does_not_affect_external_reference_discovery(
    tmp_path: Path,
) -> None:
    refs = tmp_path / "generated-docs"
    _write(refs / "README.md", "# reference\n")
    config = load_config(
        project_root=tmp_path,
        cli_overrides={"docs_dir": str(refs)},
    )

    ignore = RepoIgnoreSpec.from_config(config)
    manifest = scan_repository(tmp_path, ignore_spec=ignore)
    discovery = discover_reference_materials(refs)

    assert "generated-docs" not in manifest.top_level_directories
    assert any(item.relative_path == "README.md" for item in discovery.discovered_materials)
