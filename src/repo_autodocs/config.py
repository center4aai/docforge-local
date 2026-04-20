"""Compatibility façade for configuration loading."""

from repo_autodocs.config_loader import DEFAULT_CONFIG_FILE_NAME, load_config
from repo_autodocs.config_models import AppConfig, ConfigValueSource

__all__ = ["DEFAULT_CONFIG_FILE_NAME", "AppConfig", "ConfigValueSource", "load_config"]
