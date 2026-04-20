from pathlib import Path

from repo_autodocs.config import AppConfig
from repo_autodocs.models import ProjectPaths
from repo_autodocs.privacy import build_privacy_report, validate_llm_egress_config


def _paths() -> ProjectPaths:
    root = Path("/tmp/repo")
    return ProjectPaths(
        project_root=root,
        docs_dir=root / "docs",
        reference_dir=root / "docs/context/methodology",
        output_dir=root / "docs/generated",
        site_dir=root / "site",
    )


def test_privacy_report_local_only() -> None:
    report = build_privacy_report(
        AppConfig(project_paths=_paths(), enable_llm=False),
        use_llm=False,
    )
    assert report.mode == "local-only"
    assert report.allowed_egress_endpoints == []


def test_privacy_report_llm_endpoint_mode() -> None:
    report = build_privacy_report(
        AppConfig(
            project_paths=_paths(),
            enable_llm=True,
            model_name="gpt-test",
            base_url="https://llm.example/v1",
        ),
        use_llm=True,
    )
    assert report.mode == "llm-endpoint-enabled"
    assert report.allowed_egress_endpoints == ["https://llm.example/v1"]


def test_validate_llm_egress_requires_base_url_when_enabled() -> None:
    failures = validate_llm_egress_config(
        AppConfig(project_paths=_paths(), enable_llm=True, model_name="gpt-test", base_url=None)
    )
    assert "llm base_url missing" in failures


def test_privacy_report_marks_invalid_llm_configuration() -> None:
    report = build_privacy_report(
        AppConfig(project_paths=_paths(), enable_llm=True, model_name="gpt-test", base_url=None),
        use_llm=True,
    )
    assert report.mode == "llm-config-invalid"
