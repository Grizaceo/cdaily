"""
config.py — Load and validate config.yaml
All settings must be here, zero hardcoding.
"""

import os
from pathlib import Path
from typing import Dict

import yaml


def _resolve_path(path: str) -> Path:
    """Expand ~ and environment variables in paths."""
    return Path(os.path.expandvars(os.path.expanduser(path)))


def load_config(config_path: str | None = None) -> dict:
    if config_path is None:
        config_path = os.environ.get(
            "CDAILY_CONFIG",
            Path(__file__).parent.parent / "config.yaml"
        )
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    # Resolve paths
    raw["db_path"] = _resolve_path(raw["db_path"])

    return raw


CONFIG = load_config()
DB_PATH = CONFIG["db_path"]
BLOG_CATEGORIES: Dict[str, str] = CONFIG.get("blog_categories", {})
CATEGORY_EMOJI: Dict[str, str] = CONFIG.get("category_emoji", {})
DEFAULT_EMOJI = CATEGORY_EMOJI.get("default", "📰")
