"""Deterministic Python code-facts extraction for local repositories."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

from repo_autodocs.models import (
    CodeExcerptEvidence,
    CodeFactsBundle,
    EntrypointEvidence,
    ImportEdge,
    PythonModuleInfo,
    PythonSymbolInfo,
)
from repo_autodocs.repo_ignore import RepoIgnoreSpec


@dataclass(frozen=True, slots=True)
class CodeFactsSelectionBudget:
    """Deterministic prompt selection budgets for code facts."""

    max_modules: int
    max_symbols: int
    max_import_edges: int
    max_entrypoints: int
    max_excerpts: int


CODE_FACTS_SELECTION_BUDGETS: dict[str, CodeFactsSelectionBudget] = {
    "overview": CodeFactsSelectionBudget(
        max_modules=6,
        max_symbols=10,
        max_import_edges=8,
        max_entrypoints=4,
        max_excerpts=4,
    ),
    "architecture": CodeFactsSelectionBudget(
        max_modules=14,
        max_symbols=24,
        max_import_edges=24,
        max_entrypoints=8,
        max_excerpts=10,
    ),
    "theory_alignment": CodeFactsSelectionBudget(
        max_modules=10,
        max_symbols=18,
        max_import_edges=16,
        max_entrypoints=6,
        max_excerpts=8,
    ),
    "code_structure": CodeFactsSelectionBudget(
        max_modules=16,
        max_symbols=28,
        max_import_edges=26,
        max_entrypoints=8,
        max_excerpts=12,
    ),
    "runtime_entrypoints": CodeFactsSelectionBudget(
        max_modules=10,
        max_symbols=14,
        max_import_edges=14,
        max_entrypoints=10,
        max_excerpts=8,
    ),
    "reference_alignment": CodeFactsSelectionBudget(
        max_modules=10,
        max_symbols=18,
        max_import_edges=16,
        max_entrypoints=6,
        max_excerpts=8,
    ),
    "agent_instruction_alignment": CodeFactsSelectionBudget(
        max_modules=10,
        max_symbols=18,
        max_import_edges=16,
        max_entrypoints=6,
        max_excerpts=8,
    ),
    "readme_claim_alignment": CodeFactsSelectionBudget(
        max_modules=10,
        max_symbols=18,
        max_import_edges=16,
        max_entrypoints=6,
        max_excerpts=8,
    ),
}


def _module_name_from_relative_path(relative_path: Path) -> str:
    parts = list(relative_path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _parse_ast(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _format_signature(name: str, args: ast.arguments, returns: ast.expr | None) -> str:
    parts: list[str] = []
    for arg in args.posonlyargs:
        parts.append(arg.arg)
    if args.posonlyargs:
        parts.append("/")
    for arg in args.args:
        parts.append(arg.arg)
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")
    for arg in args.kwonlyargs:
        parts.append(arg.arg)
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")

    rendered = f"{name}({', '.join(parts)})"
    if returns is not None:
        try:
            rendered += f" -> {ast.unparse(returns)}"
        except Exception:
            pass
    return rendered


def _extract_symbols(module_name: str, relative_path: str, tree: ast.AST) -> list[PythonSymbolInfo]:
    symbols: list[PythonSymbolInfo] = []
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.ClassDef):
            symbols.append(
                PythonSymbolInfo(
                    symbol_name=node.name,
                    symbol_type="class",
                    module_name=module_name,
                    relative_path=relative_path,
                    lineno=node.lineno,
                    signature=f"class {node.name}",
                    docstring=ast.get_docstring(node),
                    is_public=not node.name.startswith("_"),
                )
            )
        elif isinstance(node, ast.FunctionDef):
            symbols.append(
                PythonSymbolInfo(
                    symbol_name=node.name,
                    symbol_type="function",
                    module_name=module_name,
                    relative_path=relative_path,
                    lineno=node.lineno,
                    signature=_format_signature(node.name, node.args, node.returns),
                    docstring=ast.get_docstring(node),
                    is_public=not node.name.startswith("_"),
                )
            )
        elif isinstance(node, ast.AsyncFunctionDef):
            symbols.append(
                PythonSymbolInfo(
                    symbol_name=node.name,
                    symbol_type="async_function",
                    module_name=module_name,
                    relative_path=relative_path,
                    lineno=node.lineno,
                    signature=f"async {_format_signature(node.name, node.args, node.returns)}",
                    docstring=ast.get_docstring(node),
                    is_public=not node.name.startswith("_"),
                )
            )
    return symbols


def _extract_imports(source_module: str, tree: ast.AST) -> list[ImportEdge]:
    imports: list[ImportEdge] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(
                    ImportEdge(
                        source_module=source_module,
                        imported_module=alias.name,
                        relative=False,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            dot_prefix = "." * node.level
            base = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    if base:
                        imported_module = f"{dot_prefix}{base}.*"
                    else:
                        imported_module = f"{dot_prefix}*"
                else:
                    if base:
                        imported_module = f"{dot_prefix}{base}.{alias.name}"
                    else:
                        imported_module = f"{dot_prefix}{alias.name}"
                imports.append(
                    ImportEdge(
                        source_module=source_module,
                        imported_module=imported_module,
                        relative=node.level > 0,
                    )
                )
    return imports


def _is_main_guard(node: ast.If) -> bool:
    left = node.test.left if isinstance(node.test, ast.Compare) else None
    comparators = node.test.comparators if isinstance(node.test, ast.Compare) else []
    if not (isinstance(left, ast.Name) and left.id == "__name__"):
        return False
    if len(comparators) != 1:
        return False
    target = comparators[0]
    return isinstance(target, ast.Constant) and target.value == "__main__"


def _detect_entrypoints(
    module_name: str,
    relative_path: str,
    tree: ast.AST,
    source_text: str,
) -> list[EntrypointEvidence]:
    evidence: list[EntrypointEvidence] = []
    has_typer_import = False
    has_typer_class_import = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "typer" for alias in node.names):
                has_typer_import = True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "typer" and any(alias.name == "Typer" for alias in node.names):
                has_typer_class_import = True

    if "argparse" in source_text:
        evidence.append(
            EntrypointEvidence(
                label=f"{module_name}:argparse",
                module_name=module_name,
                relative_path=relative_path,
                reason="argparse usage detected",
            )
        )

    if relative_path.endswith(("/cli.py", "/main.py", "/__main__.py")):
        evidence.append(
            EntrypointEvidence(
                label=f"{module_name}:filename_hint",
                module_name=module_name,
                relative_path=relative_path,
                reason="entrypoint filename convention matched",
            )
        )

    for node in getattr(tree, "body", []):
        if isinstance(node, ast.If) and _is_main_guard(node):
            evidence.append(
                EntrypointEvidence(
                    label=f"{module_name}:__main__",
                    module_name=module_name,
                    relative_path=relative_path,
                    reason="__name__ == '__main__' guard",
                )
            )
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                called = node.value.func
                if (
                    isinstance(called, ast.Attribute)
                    and isinstance(called.value, ast.Name)
                    and called.value.id == "typer"
                    and called.attr == "Typer"
                    and has_typer_import
                ):
                    evidence.append(
                        EntrypointEvidence(
                            label=f"{module_name}:typer_app:{target.id}",
                            module_name=module_name,
                            relative_path=relative_path,
                            reason="typer.Typer app instance",
                        )
                    )
                if isinstance(called, ast.Name) and called.id == "Typer" and has_typer_class_import:
                    evidence.append(
                        EntrypointEvidence(
                            label=f"{module_name}:typer_app:{target.id}",
                            module_name=module_name,
                            relative_path=relative_path,
                            reason="Typer app instance",
                        )
                    )

    return evidence


def _discover_python_files(
    project_root: Path, ignore_spec: RepoIgnoreSpec | None = None
) -> list[tuple[Path, str]]:
    discovered: list[tuple[Path, str]] = []
    for base_name in ("src", "tests"):
        base = project_root / base_name
        if not base.is_dir() or (ignore_spec and ignore_spec.is_ignored(base_name, is_dir=True)):
            continue
        for current_root, dir_names, file_names in os.walk(base):
            current_path = Path(current_root)
            dir_names[:] = sorted(
                [
                    name
                    for name in dir_names
                    if not (
                        ignore_spec
                        and ignore_spec.is_ignored(
                            (current_path / name).relative_to(project_root).as_posix(),
                            is_dir=True,
                        )
                    )
                ]
            )
            for file_name in sorted(file_names):
                if not file_name.endswith(".py"):
                    continue
                file_path = current_path / file_name
                if ignore_spec and ignore_spec.is_ignored(
                    file_path.relative_to(project_root).as_posix()
                ):
                    continue
                discovered.append((file_path, base_name))
    return discovered


def _score_module(module: PythonModuleInfo) -> int:
    score = (
        (module.defined_class_count * 4) + (module.defined_function_count * 3) + module.import_count
    )
    if any(
        module.relative_path.endswith(suffix) for suffix in ("/cli.py", "/main.py", "/__main__.py")
    ):
        score += 8
    if module.is_test_module:
        score -= 2
    return score


def _build_excerpt(
    file_path: Path,
    module_name: str,
    relative_path: str,
    kind: str,
    max_lines: int = 18,
) -> CodeExcerptEvidence | None:
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("def ", "class ", "async def ")):
            start = idx + 1
            end = min(len(lines), start + max_lines - 1)
            excerpt = "\n".join(lines[start - 1 : end])
            return CodeExcerptEvidence(
                module_name=module_name,
                relative_path=relative_path,
                excerpt_kind=kind,
                start_line=start,
                end_line=end,
                excerpt=excerpt,
            )

    end = min(len(lines), max_lines)
    excerpt = "\n".join(lines[:end])
    return CodeExcerptEvidence(
        module_name=module_name,
        relative_path=relative_path,
        excerpt_kind=kind,
        start_line=1,
        end_line=end,
        excerpt=excerpt,
    )


def build_code_facts_bundle(
    project_root: Path,
    *,
    ignore_spec: RepoIgnoreSpec | None = None,
    apply_ignore_by_default: bool = True,
) -> CodeFactsBundle:
    """Extract deterministic Python code facts from files under ``src/`` and ``tests/``."""

    root = project_root.resolve()
    active_ignore_spec = ignore_spec
    if active_ignore_spec is None and apply_ignore_by_default:
        active_ignore_spec = RepoIgnoreSpec.build(repo_root=root)

    modules: list[PythonModuleInfo] = []
    symbols: list[PythonSymbolInfo] = []
    imports: list[ImportEdge] = []
    entrypoint_evidence: list[EntrypointEvidence] = []
    framework_hints: set[str] = set()

    excerpts: list[CodeExcerptEvidence] = []

    for file_path, base_name in _discover_python_files(root, ignore_spec=active_ignore_spec):
        relative_to_base = file_path.relative_to(root / base_name)
        module_name = _module_name_from_relative_path(relative_to_base)
        if not module_name:
            continue
        if base_name == "tests":
            module_name = f"tests.{module_name}"

        tree = _parse_ast(file_path)
        if tree is None:
            continue

        relative_path = file_path.relative_to(root).as_posix()
        source_text = file_path.read_text(encoding="utf-8", errors="ignore")

        module_symbols = _extract_symbols(module_name, relative_path, tree)
        module_imports = _extract_imports(module_name, tree)

        module = PythonModuleInfo(
            module_path=file_path,
            relative_path=relative_path,
            module_name=module_name,
            is_package=file_path.name == "__init__.py",
            import_count=len(module_imports),
            defined_class_count=sum(
                1 for symbol in module_symbols if symbol.symbol_type == "class"
            ),
            defined_function_count=sum(
                1
                for symbol in module_symbols
                if symbol.symbol_type in {"function", "async_function"}
            ),
            is_test_module=base_name == "tests",
        )
        module.module_importance_score = _score_module(module)
        modules.append(module)

        symbols.extend(module_symbols)
        imports.extend(module_imports)
        entrypoint_evidence.extend(
            _detect_entrypoints(module_name, relative_path, tree, source_text)
        )

        lowered = source_text.lower()
        if "typer" in lowered:
            framework_hints.add("typer")
        if "click" in lowered:
            framework_hints.add("click")
        if "fastapi" in lowered:
            framework_hints.add("fastapi")
        if "pytest" in lowered:
            framework_hints.add("pytest")
        if "argparse" in lowered:
            framework_hints.add("argparse")

    modules.sort(
        key=lambda item: (
            -item.module_importance_score,
            item.is_test_module,
            item.module_name,
        )
    )
    symbols.sort(
        key=lambda item: (
            not item.is_public,
            item.module_name,
            item.lineno,
            item.symbol_name,
        )
    )
    imports.sort(key=lambda item: (item.source_module, item.imported_module, item.relative))

    for module in modules[:12]:
        kind = "test" if module.is_test_module else "module"
        excerpt = _build_excerpt(
            module.module_path,
            module.module_name,
            module.relative_path,
            kind,
        )
        if excerpt:
            excerpts.append(excerpt)

    dedup_entrypoints: dict[str, EntrypointEvidence] = {}
    for evidence in entrypoint_evidence:
        dedup_entrypoints[evidence.label] = evidence

    sorted_entrypoints = sorted(dedup_entrypoints.values(), key=lambda item: item.label)

    return CodeFactsBundle(
        modules=modules,
        symbols=symbols,
        imports=imports,
        detected_entrypoints=[item.label for item in sorted_entrypoints],
        entrypoint_evidence=sorted_entrypoints,
        code_excerpts=excerpts,
        framework_hints=sorted(framework_hints),
    )


def summarize_code_facts(bundle: CodeFactsBundle) -> str:
    """Create a concise deterministic text summary for extracted code facts."""

    class_count = sum(1 for symbol in bundle.symbols if symbol.symbol_type == "class")
    function_count = sum(
        1 for symbol in bundle.symbols if symbol.symbol_type in {"function", "async_function"}
    )
    test_module_count = sum(1 for module in bundle.modules if module.is_test_module)

    lines = [
        "Code facts summary:",
        f"- Modules: {len(bundle.modules)} (tests={test_module_count})",
        f"- Symbols: {len(bundle.symbols)} (classes={class_count}, functions={function_count})",
        f"- Import edges: {len(bundle.imports)}",
        f"- Entrypoints: {len(bundle.detected_entrypoints)}",
        f"- Code excerpts: {len(bundle.code_excerpts)}",
        f"- Framework hints: {', '.join(bundle.framework_hints) or '(none)'}",
    ]
    if bundle.detected_entrypoints:
        lines.append("- Entrypoint labels: " + ", ".join(bundle.detected_entrypoints[:8]))
    if bundle.modules:
        lines.append("- Top modules by importance:")
        for module in bundle.modules[:6]:
            symbol_count = module.defined_class_count + module.defined_function_count
            lines.append(
                f"  - {module.module_name} (score={module.module_importance_score}, "
                f"symbols={symbol_count}, imports={module.import_count})"
            )

    return "\n".join(lines)


def render_code_facts_debug_markdown(bundle: CodeFactsBundle) -> str:
    """Render compact code-facts debug markdown for generated artifacts."""

    lines = [
        "# Code Facts Debug",
        "",
        "Deterministic structural analysis over Python files under `src/` and `tests/`.",
        "",
        summarize_code_facts(bundle),
        "",
        "## Modules",
    ]

    if not bundle.modules:
        lines.extend(["", "- None"])
    else:
        for module in bundle.modules:
            symbol_count = module.defined_class_count + module.defined_function_count
            lines.append(
                "- "
                f"`{module.module_name}` ({module.relative_path}) "
                f"score={module.module_importance_score}, "
                f"symbols={symbol_count}, imports={module.import_count}, "
                f"test_module={module.is_test_module}"
            )

    lines.extend(["", "## Public symbol signatures and docstrings (sample)"])
    public_symbols = [symbol for symbol in bundle.symbols if symbol.is_public][:40]
    if not public_symbols:
        lines.extend(["", "- None"])
    else:
        for symbol in public_symbols:
            doc = (symbol.docstring or "(none)").splitlines()[0][:120]
            sig = symbol.signature or "(unknown)"
            lines.append(
                f"- `{symbol.module_name}:{symbol.symbol_name}` signature=`{sig}` docstring={doc!r}"
            )

    lines.extend(["", "## Entrypoints"])
    if not bundle.entrypoint_evidence:
        lines.extend(["", "- None"])
    else:
        for item in bundle.entrypoint_evidence:
            lines.append(f"- `{item.label}` ({item.relative_path}) reason={item.reason}")

    lines.extend(["", "## Import edges (sample)"])
    if not bundle.imports:
        lines.extend(["", "- None"])
    else:
        for edge in bundle.imports[:60]:
            qualifier = "relative" if edge.relative else "absolute"
            lines.append(f"- `{edge.source_module}` -> `{edge.imported_module}` ({qualifier})")

    lines.extend(["", "## Selected code excerpts"])
    if not bundle.code_excerpts:
        lines.extend(["", "- None"])
    else:
        for excerpt in bundle.code_excerpts[:16]:
            lines.extend(
                [
                    f"### `{excerpt.module_name}` ({excerpt.excerpt_kind})",
                    "",
                    f"- Source: `{excerpt.relative_path}`",
                    f"- Lines: {excerpt.start_line}-{excerpt.end_line}",
                    "",
                    "```python",
                    excerpt.excerpt,
                    "```",
                    "",
                ]
            )

    return "\n".join(lines).rstrip() + "\n"


def select_code_facts_for_section(
    section_name: str,
    bundle: CodeFactsBundle | None,
) -> CodeFactsBundle:
    """Select bounded deterministic code facts for a section prompt."""

    if bundle is None:
        return CodeFactsBundle()

    budget = CODE_FACTS_SELECTION_BUDGETS[section_name]

    if section_name == "overview":
        modules = [module for module in bundle.modules if not module.is_test_module][
            : budget.max_modules
        ]
    elif section_name == "runtime_entrypoints":
        modules = sorted(
            bundle.modules,
            key=lambda module: (
                not any(
                    module.module_name == item.module_name for item in bundle.entrypoint_evidence
                ),
                module.is_test_module,
                -module.module_importance_score,
                module.module_name,
            ),
        )[: budget.max_modules]
    elif section_name == "architecture":
        modules = bundle.modules[: budget.max_modules]
    elif section_name == "code_structure":
        modules = sorted(
            bundle.modules,
            key=lambda module: (
                module.is_test_module,
                -module.module_importance_score,
                module.module_name,
            ),
        )[: budget.max_modules]
    else:
        modules = bundle.modules[: budget.max_modules]

    module_names = {module.module_name for module in modules}

    candidate_symbols = [
        symbol
        for symbol in bundle.symbols
        if symbol.module_name in module_names and symbol.is_public
    ]
    if len(candidate_symbols) < budget.max_symbols:
        candidate_symbols.extend(
            symbol
            for symbol in bundle.symbols
            if symbol.module_name in module_names and symbol not in candidate_symbols
        )
    symbols = candidate_symbols[: budget.max_symbols]

    imports = [edge for edge in bundle.imports if edge.source_module in module_names]
    imports = imports[: budget.max_import_edges]

    entrypoint_evidence = [
        item for item in bundle.entrypoint_evidence if item.module_name in module_names
    ][: budget.max_entrypoints]
    if section_name == "runtime_entrypoints":
        entrypoint_evidence = sorted(
            entrypoint_evidence,
            key=lambda item: (
                "typer_app" not in item.label,
                "__main__" not in item.label,
                item.relative_path,
                item.label,
            ),
        )[: budget.max_entrypoints]

    excerpt_candidates = [
        excerpt for excerpt in bundle.code_excerpts if excerpt.module_name in module_names
    ]
    if section_name == "overview":
        excerpt_candidates = [e for e in excerpt_candidates if e.excerpt_kind != "test"] + [
            e for e in excerpt_candidates if e.excerpt_kind == "test"
        ]
    elif section_name == "architecture":
        excerpt_candidates = [e for e in excerpt_candidates if e.excerpt_kind == "module"] + [
            e for e in excerpt_candidates if e.excerpt_kind == "test"
        ]
    elif section_name == "runtime_entrypoints":
        entrypoint_modules = {item.module_name for item in bundle.entrypoint_evidence}
        excerpt_candidates = sorted(
            excerpt_candidates,
            key=lambda e: (
                e.module_name not in entrypoint_modules,
                e.excerpt_kind != "module",
                e.excerpt_kind == "test",
                e.relative_path,
                e.start_line,
            ),
        )

    return CodeFactsBundle(
        modules=modules,
        symbols=symbols,
        imports=imports,
        detected_entrypoints=[item.label for item in entrypoint_evidence],
        entrypoint_evidence=entrypoint_evidence,
        code_excerpts=excerpt_candidates[: budget.max_excerpts],
        framework_hints=bundle.framework_hints,
    )
