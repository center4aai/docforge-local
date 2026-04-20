from pathlib import Path


def test_console_script_entrypoint_exists() -> None:
    content = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "[project.scripts]" in content
    assert 'docforge-local = "repo_autodocs.cli:app"' in content


def test_release_version_surfaces_match_v0_1_3() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    package_init = Path("src/repo_autodocs/__init__.py").read_text(encoding="utf-8")

    assert 'version = "0.1.3"' in pyproject
    assert '__version__ = "0.1.3"' in package_init
