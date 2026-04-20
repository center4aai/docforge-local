"""Lightweight localization helpers for generated explanatory prose."""

from __future__ import annotations

from typing import Literal

GeneratedTextLanguage = Literal["en", "ru"]

_RU_CATALOG: dict[str, str] = {
    "home.generated_with_mode": (
        "Этот сайт был сгенерирован **DocForge Local** в **детерминированном режиме** (без LLM)."
    ),
    "home.observed_summary_fallback": (
        "- В метаданных `pyproject.toml` не найдено краткого описания проекта."
    ),
    "home.key_structural_fallback": "- Под `src/` не обнаружена структура Python-модулей.",
    "project_brief.interpretation_limited": (
        "- Доступные детерминированные признаки ограничены; "
        "назначение проекта нельзя уверенно вывести."
    ),
    "project_brief.known_uncertainty": (
        "- Этот обзор строится только на детерминированных признаках "
        "репозитория/кода; он не выводит неявный продуктовый замысел "
        "или архитектуру развертывания."
    ),
    "project_brief.no_theory_sources": (
        "- Для дополнительного контекста не обнаружены файлы внешних reference-материалов."
    ),
    "external_refs.status_intro": "Статус-отчёт по опциональным внешним reference-материалам.",
    "external_refs.none_supplied": (
        "Для этого запуска внешние reference-материалы не были переданы."
    ),
    "external_refs.none_analysis": "Дополнительный reference-анализ не выполнялся.",
    "external_refs.enable_hint": "Чтобы включить эту возможность, укажите один из вариантов:",
    "external_refs.no_discovered_files": "Для выбранных reference-входов файлы не обнаружены.",
    "overview.deterministic_notice": (
        "Этот обзор детерминированный и основан только на "
        "просканированных признаках репозитория/кода."
    ),
    "overview.no_ranked_modules": "- Ранжированные Python-модули не обнаружены.",
    "overview.no_llm_uncertainty": "- В этом запуске не использовался LLM-синтез.",
    "architecture.no_boundaries": (
        "- Детерминированно вывести компонентные границы из Python-модулей не удалось."
    ),
    "architecture.no_import_edges": "- Рёбра импортов не были извлечены.",
    "code_structure.inventory_intro": (
        "Детерминированный инвентарь Python-модулей и репрезентативных символов."
    ),
    "code_structure.no_modules": "- Под `src/` Python-модули не обнаружены.",
    "code_structure.no_symbols": "- Топ-уровневые классы/функции не обнаружены.",
    "runtime_entrypoints.page_intro": (
        "Эта страница перечисляет детерминированно обнаруженные "
        "runtime/CLI-поверхности из code facts."
    ),
    "runtime_entrypoints.none_detected": (
        "- Явные entrypoint-поверхности не обнаружены (`__main__`/Typer-шаблоны)."
    ),
    "runtime_entrypoints.notes": (
        "- Entrypoint-поверхности определяются по шаблонам и могут покрывать не все runtime-пути."
    ),
    "reference_alignment.page_intro": (
        "Детерминированные вердикты для общих внешних reference-материалов."
    ),
    "agent_alignment.page_intro": "Детерминированные вердикты для файлов AI-agent инструкций.",
    "readme_alignment.page_intro": "Детерминированные вердикты для README-утверждений.",
    "route_summary.empty_general": "- Общие reference-источники не обнаружены.",
    "route_summary.empty_agent": "- Источники AI-agent инструкций не обнаружены.",
    "route_summary.empty_readme": "- README-источники не обнаружены.",
    "writer.generated_notice": (
        "Эти файлы являются сгенерированными артефактами "
        "и могут быть перегенерированы в любой момент."
    ),
    "writer.reference_notice": (
        "Опциональные внешние reference-материалы анализируются из явно настроенных путей и"
    ),
    "writer.reference_notice_cont": (
        "из default-выбранных целей (README/файлы agent-инструкций), если они включены."
    ),
    "generator.methodology_heading": "## Discovered external reference files",
    "generator.scope_note": (
        "Эта страница — детерминированный снимок репозитория. "
        "Это не полная архитектурная документация."
    ),
}


def localize(language: GeneratedTextLanguage, key: str, fallback_english: str) -> str:
    """Return localized explanatory prose while preserving English fallback."""

    if language == "ru":
        return _RU_CATALOG.get(key, fallback_english)
    return fallback_english
