from pathlib import Path

from repo_autodocs.config import load_config
from repo_autodocs.repo_ignore import RepoIgnoreSpec
from repo_autodocs.scanner import scan_repository, scan_repository_with_code_facts


def test_scan_repository_detects_expected_structure(tmp_path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'sample'\n", encoding="utf-8")
    (tmp_path / "mkdocs.yml").write_text("site_name: Sample\n", encoding="utf-8")

    manifest = scan_repository(tmp_path)

    assert manifest.has_git_dir is True
    assert manifest.has_pyproject is True
    assert manifest.has_mkdocs_config is True
    assert manifest.has_docs_dir is True
    assert manifest.has_src_dir is True
    assert manifest.has_tests_dir is True
    assert "src" in manifest.top_level_directories
    assert "tests" in manifest.top_level_directories
    assert "pyproject.toml" in manifest.top_level_files


def test_scan_repository_without_ignore_spec_applies_default_ignore_layer(tmp_path: Path) -> None:
    (tmp_path / ".venv").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("x", encoding="utf-8")
    (tmp_path / "docforge.toml").write_text("[paths]\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("x=1\n", encoding="utf-8")

    manifest = scan_repository(tmp_path)

    assert ".venv" not in manifest.top_level_directories
    assert "README.md" not in manifest.top_level_files
    assert "AGENTS.md" not in manifest.top_level_files
    assert "docforge.toml" not in manifest.top_level_files
    assert "ignored.py" not in manifest.top_level_files


def test_scan_repository_supports_explicit_opt_out_for_raw_behavior(tmp_path: Path) -> None:
    (tmp_path / ".venv").mkdir()
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("x", encoding="utf-8")

    manifest = scan_repository(tmp_path, apply_ignore_by_default=False)

    assert ".venv" in manifest.top_level_directories
    assert "README.md" in manifest.top_level_files
    assert "AGENTS.md" in manifest.top_level_files


def test_scan_repository_with_code_facts_returns_bundle(tmp_path: Path) -> None:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "mod.py").write_text("def fn():\n    return 1\n", encoding="utf-8")

    manifest, bundle = scan_repository_with_code_facts(tmp_path)

    assert manifest.project_root == tmp_path.resolve()
    assert [module.module_name for module in bundle.modules] == ["pkg.mod"]


def test_scan_repository_with_code_facts_applies_default_ignore_layer(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("src/pkg/ignored.py\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("ignored", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("ignored", encoding="utf-8")
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "keep.py").write_text(
        "def keep():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "src" / "pkg" / "ignored.py").write_text(
        "def bad():\n    return 2\n", encoding="utf-8"
    )

    manifest, bundle = scan_repository_with_code_facts(tmp_path)
    module_names = {module.module_name for module in bundle.modules}

    assert "README.md" not in manifest.top_level_files
    assert "AGENTS.md" not in manifest.top_level_files
    assert "pkg.keep" in module_names
    assert "pkg.ignored" not in module_names


def test_scan_repository_collects_textual_evidence_with_default_ignore_layer(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text("# Sample\n\nOverview", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname="sample"', encoding="utf-8")
    (tmp_path / "docforge.toml").write_text("[paths]\ndocs_dir='docs'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_core.py").write_text(
        "def test_a():\n    assert True\n", encoding="utf-8"
    )

    manifest = scan_repository(tmp_path)
    categories = {(item.category, item.relative_path) for item in manifest.textual_evidence}

    assert ("readme", "README.md") not in categories
    assert ("package_config", "pyproject.toml") in categories
    assert ("runtime_config", "docforge.toml") not in categories
    assert ("test_file", "tests/test_core.py") in categories


def test_scan_repository_config_applies_default_ignore_layer(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# hidden", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("hidden", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "CLAUDE.md").write_text("hidden", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")

    config = load_config(project_root=tmp_path)
    manifest = scan_repository(tmp_path, config=config)
    evidence_paths = {item.relative_path for item in manifest.textual_evidence}

    assert "README.md" not in manifest.top_level_files
    assert "AGENTS.md" not in manifest.top_level_files
    assert "README.md" not in evidence_paths
    assert "pyproject.toml" in evidence_paths


def test_scan_repository_respects_gitignore_toggle(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("x = 1\n", encoding="utf-8")

    with_gitignore = RepoIgnoreSpec.build(repo_root=tmp_path, use_repo_gitignore=True)
    without_gitignore = RepoIgnoreSpec.build(repo_root=tmp_path, use_repo_gitignore=False)

    manifest_with = scan_repository(tmp_path, ignore_spec=with_gitignore)
    manifest_without = scan_repository(tmp_path, ignore_spec=without_gitignore)

    assert "ignored.py" not in manifest_with.top_level_files
    assert "ignored.py" in manifest_without.top_level_files


def test_scan_repository_with_config_excludes_custom_tool_output_dirs(tmp_path: Path) -> None:
    (tmp_path / "generated-docs" / "pages").mkdir(parents=True)
    (tmp_path / "generated-site").mkdir(parents=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "generated-docs" / "pages" / "overview.md").write_text(
        "# generated\n", encoding="utf-8"
    )
    (tmp_path / "generated-site" / "index.html").write_text("<html></html>\n", encoding="utf-8")
    (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")

    config = load_config(
        project_root=tmp_path,
        cli_overrides={
            "docs_dir": str(tmp_path / "generated-docs"),
            "output_dir": str(tmp_path / "generated-docs" / "pages"),
            "site_dir": str(tmp_path / "generated-site"),
        },
    )
    manifest = scan_repository(tmp_path, config=config)

    assert "generated-docs" not in manifest.top_level_directories
    assert "generated-site" not in manifest.top_level_directories
    assert "src" in manifest.top_level_directories
