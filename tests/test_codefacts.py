from pathlib import Path

from repo_autodocs.codefacts import (
    CODE_FACTS_SELECTION_BUDGETS,
    build_code_facts_bundle,
    render_code_facts_debug_markdown,
    select_code_facts_for_section,
    summarize_code_facts,
)
from repo_autodocs.repo_ignore import RepoIgnoreSpec


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_code_facts_bundle_discovers_richer_evidence_including_tests(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "sample" / "__init__.py", "from .module import Thing\n")
    _write(
        tmp_path / "src" / "sample" / "module.py",
        "import os\n"
        "from . import sub\n"
        "from sample import other\n"
        "import typer\n\n"
        "class Thing:\n"
        '    """Primary thing."""\n'
        "    pass\n\n"
        "def run(name: str) -> None:\n"
        '    """Run command."""\n'
        "    return None\n\n"
        "app = typer.Typer()\n\n"
        'if __name__ == "__main__":\n'
        "    run('x')\n",
    )
    _write(tmp_path / "src" / "sample" / "sub.py", "VALUE = 1\n")
    _write(
        tmp_path / "tests" / "test_module.py",
        "from sample.module import run\n\ndef test_run() -> None:\n    run('y')\n",
    )

    bundle = build_code_facts_bundle(tmp_path)

    module_names = [module.module_name for module in bundle.modules]
    assert "sample.module" in module_names
    assert "tests.test_module" in module_names

    run_symbol = next(symbol for symbol in bundle.symbols if symbol.symbol_name == "run")
    assert run_symbol.signature == "run(name) -> None"
    assert run_symbol.docstring == "Run command."
    assert run_symbol.is_public is True

    assert "sample.module:__main__" in bundle.detected_entrypoints
    assert any(item.reason for item in bundle.entrypoint_evidence)
    assert any(excerpt.excerpt_kind == "test" for excerpt in bundle.code_excerpts)
    assert "typer" in bundle.framework_hints


def test_build_code_facts_bundle_represents_star_imports_explicitly(tmp_path) -> None:
    _write(tmp_path / "src" / "sample" / "module.py", "from sample import *\nfrom .pkg import *\n")
    _write(tmp_path / "src" / "sample" / "pkg.py", "VALUE = 1\n")

    bundle = build_code_facts_bundle(tmp_path)
    imports = {(edge.source_module, edge.imported_module, edge.relative) for edge in bundle.imports}

    assert ("sample.module", "sample.*", False) in imports
    assert ("sample.module", ".pkg.*", True) in imports


def test_code_facts_selection_policy_is_deterministic_and_bounded(tmp_path) -> None:
    _write(tmp_path / "src" / "pkg" / "__init__.py", "from .module import Thing\n")
    _write(
        tmp_path / "src" / "pkg" / "module.py",
        "class Thing:\n    pass\n\ndef run() -> None:\n    return None\n",
    )
    _write(tmp_path / "tests" / "test_pkg.py", "def test_run():\n    assert True\n")
    bundle = build_code_facts_bundle(tmp_path)

    first = select_code_facts_for_section("architecture", bundle)
    second = select_code_facts_for_section("architecture", bundle)

    assert first == second
    budget = CODE_FACTS_SELECTION_BUDGETS["architecture"]
    assert len(first.modules) <= budget.max_modules
    assert len(first.code_excerpts) <= budget.max_excerpts


def test_code_facts_selection_supports_new_stage4_sections(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "pkg" / "cli.py", "import typer\napp = typer.Typer()\n")
    _write(tmp_path / "src" / "pkg" / "core.py", "def run() -> None:\n    return None\n")
    bundle = build_code_facts_bundle(tmp_path)

    code_structure = select_code_facts_for_section("code_structure", bundle)
    runtime = select_code_facts_for_section("runtime_entrypoints", bundle)

    assert len(code_structure.modules) <= CODE_FACTS_SELECTION_BUDGETS["code_structure"].max_modules
    assert (
        len(runtime.detected_entrypoints)
        <= CODE_FACTS_SELECTION_BUDGETS["runtime_entrypoints"].max_entrypoints
    )


def test_build_code_facts_bundle_applies_default_ignore_layer(tmp_path: Path) -> None:
    _write(tmp_path / ".gitignore", "src/pkg/ignored.py\n")
    _write(tmp_path / "src" / "pkg" / "keep.py", "def keep():\n    return 1\n")
    _write(tmp_path / "src" / "pkg" / "ignored.py", "def skip():\n    return 2\n")

    bundle = build_code_facts_bundle(tmp_path)
    module_names = {module.module_name for module in bundle.modules}
    assert "pkg.keep" in module_names
    assert "pkg.ignored" not in module_names


def test_build_code_facts_bundle_supports_explicit_ignore_opt_out(tmp_path: Path) -> None:
    _write(tmp_path / "README.md", "x")
    _write(tmp_path / "AGENTS.md", "x")
    _write(tmp_path / "src" / "pkg" / "mod.py", "def keep():\n    return 1\n")

    bundle = build_code_facts_bundle(tmp_path, apply_ignore_by_default=False)
    module_names = {module.module_name for module in bundle.modules}
    assert "pkg.mod" in module_names


def test_code_facts_summary_and_debug_markdown_render(tmp_path) -> None:
    _write(
        tmp_path / "src" / "sample" / "module.py",
        "import os\nfrom sample import other\nfrom .pkg import *\n",
    )
    _write(tmp_path / "src" / "sample" / "other.py", "VALUE = 2\n")
    _write(tmp_path / "src" / "sample" / "pkg.py", "VALUE = 1\n")
    bundle = build_code_facts_bundle(tmp_path)

    summary = summarize_code_facts(bundle)
    debug_markdown = render_code_facts_debug_markdown(bundle)

    assert "Code facts summary:" in summary
    assert "Framework hints:" in summary
    assert "# Code Facts Debug" in debug_markdown
    assert "## Public symbol signatures and docstrings (sample)" in debug_markdown
    assert "## Selected code excerpts" in debug_markdown
    assert "`sample.module` -> `sample.other` (absolute)" in debug_markdown
    assert "`sample.module` -> `.pkg.*` (relative)" in debug_markdown


def test_code_facts_bundle_safe_when_src_absent(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    _write(tmp_path / "tests" / "test_only.py", "def test_ok():\n    assert True\n")

    bundle = build_code_facts_bundle(tmp_path)

    assert bundle.modules
    assert any(module.is_test_module for module in bundle.modules)


def test_code_facts_respects_ignore_spec_for_files_and_dirs(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "pkg" / "keep.py", "def keep():\n    return 1\n")
    _write(tmp_path / "src" / "pkg" / "skip.py", "def skip():\n    return 2\n")
    _write(tmp_path / "src" / "ignored_dir" / "mod.py", "def nope():\n    return 3\n")

    ignore = RepoIgnoreSpec.build(
        repo_root=tmp_path,
        use_default_ignores=False,
        use_repo_gitignore=False,
        ignore_patterns=("src/pkg/skip.py", "src/ignored_dir/"),
    )
    bundle = build_code_facts_bundle(tmp_path, ignore_spec=ignore)

    module_names = {module.module_name for module in bundle.modules}
    assert "pkg.keep" in module_names
    assert "pkg.skip" not in module_names
    assert "ignored_dir.mod" not in module_names
