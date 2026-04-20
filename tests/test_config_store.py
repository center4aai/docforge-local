from pathlib import Path

from repo_autodocs.config_store import ConfigStore


def test_store_writes_canonical_and_removes_legacy(tmp_path: Path) -> None:
    cfg = tmp_path / "docforge.toml"
    cfg.write_text("docs_dir='legacy_docs'\n", encoding="utf-8")

    store = ConfigStore(project_root=tmp_path, scope="project")
    store.set_field("docs_dir", "managed_docs")

    text = cfg.read_text(encoding="utf-8")
    assert "[paths]" in text
    assert 'docs_dir = "managed_docs"' in text
    assert "docs_dir='legacy_docs'" not in text


def test_store_reset_removes_canonical_and_legacy(tmp_path: Path) -> None:
    cfg = tmp_path / "docforge.toml"
    cfg.write_text("[paths]\ndocs_dir='docs'\nreference_dir='refs'\n", encoding="utf-8")

    store = ConfigStore(project_root=tmp_path, scope="project")
    store.reset_field("docs_dir")

    text = cfg.read_text(encoding="utf-8")
    assert "docs_dir" not in text


def test_user_scope_writes_to_user_config_override(tmp_path: Path, monkeypatch) -> None:
    user_cfg = tmp_path / "user.toml"
    monkeypatch.setenv("REPO_AUTODOCS_USER_CONFIG_FILE", str(user_cfg))

    store = ConfigStore(project_root=tmp_path, scope="user")
    store.set_field("generated_text_language", "ru")

    text = user_cfg.read_text(encoding="utf-8")
    assert "[generation]" in text
    assert 'generated_text_language = "ru"' in text
