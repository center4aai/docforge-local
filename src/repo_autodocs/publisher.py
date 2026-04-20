"""Publishing helpers for generated markdown artifacts."""

from __future__ import annotations

from pathlib import Path

from mkdocs.commands.build import build
from mkdocs.config import load_config

from repo_autodocs.scaffold import (
    NavScaffoldError,
    create_local_filesystem_build_config,
    resolve_effective_mkdocs_config,
    scaffold_missing_nav_pages,
)


def write_project_snapshot(markdown: str, output_path: Path) -> Path:
    """Write snapshot markdown to disk, creating parent directories if needed."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def build_mkdocs_site(project_root: Path, site_dir: Path, docs_dir: Path, output_dir: Path) -> Path:
    """Build MkDocs HTML output to a deterministic output directory."""

    resolved_docs_dir = docs_dir.resolve()
    resolved_output_dir = output_dir.resolve()
    if not resolved_output_dir.is_relative_to(resolved_docs_dir):
        raise RuntimeError(
            "Configured output_dir must be inside docs_dir for a consistent MkDocs build. "
            f"output_dir={resolved_output_dir}, docs_dir={resolved_docs_dir}"
        )

    mkdocs_config = resolve_effective_mkdocs_config(
        project_root=project_root, docs_dir=resolved_docs_dir
    )

    try:
        scaffold_result = scaffold_missing_nav_pages(
            project_root=project_root,
            mkdocs_config_path=mkdocs_config.path,
            docs_dir=resolved_docs_dir,
        )
        if scaffold_result.docs_dir != resolved_docs_dir:
            raise RuntimeError(
                "Internal docs root mismatch during nav scaffolding. "
                f"resolved={resolved_docs_dir}, scaffold={scaffold_result.docs_dir}"
            )
        effective_config_path = create_local_filesystem_build_config(
            project_root=project_root,
            mkdocs_config_path=mkdocs_config.path,
            docs_dir=resolved_docs_dir,
        )
        config = load_config(config_file=str(effective_config_path), site_dir=str(site_dir))
        config.use_directory_urls = False
        config.strict = True
        build(config)
    except NavScaffoldError:
        raise
    except Exception as exc:  # pragma: no cover - depends on mkdocs internals
        raise RuntimeError(f"MkDocs build failed: {exc}") from exc
    finally:
        if "effective_config_path" in locals():
            effective_config_path.unlink(missing_ok=True)
        if mkdocs_config.is_temporary:
            mkdocs_config.path.unlink(missing_ok=True)

    site_index_path = site_dir / "index.html"
    if not site_index_path.exists():
        raise RuntimeError(
            f"MkDocs build completed without a usable home page: missing {site_index_path}."
        )

    return site_dir
