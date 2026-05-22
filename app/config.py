"""
config.py — Load and validate config.yaml.
Database existence is NOT checked at import time; bootstrap does that.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

import yaml

# Default configurations
DEFAULT_BLOG_CATEGORIES: Dict[str, str] = {
    "CIPER Chile": "news",
    "BioBioChile": "news",
    "Cambio21": "news",
    "El Clarin": "news",
    "The Clinic": "culture",
    "BBC Mundo": "news",
    "The Guardian Mundo": "news",
    "Ars Technica": "tech",
    "Science Daily": "science",
    "Diario Financiero": "business",
    "The Onion": "culture",
    "CyberScoop": "security",
    "Dark Reading": "security",
    "Help Net Security": "security",
    "Infosecurity Magazine": "security",
    "Krebs on Security": "security",
    "MIT Tech Review AI": "tech",
    "SANS ISC": "security",
    "Schneier on Security": "security",
    "Talos Intelligence": "security",
    "The Hacker News": "security",
    "The Verge AI": "tech",
    "Unit 42 Palo Alto": "security",
    "We Live Security": "security",
}

DEFAULT_CATEGORY_EMOJI: Dict[str, str] = {
    "news": "📰",
    "tech": "💻",
    "science": "🔬",
    "business": "💼",
    "culture": "🎭",
    "security": "🔐",
    "default": "📰",
}


def _resolve_path(path: str) -> Path:
    """Expand ~ and environment variables in paths."""
    return Path(os.path.expandvars(os.path.expanduser(path)))


def _validate_schema(raw: dict) -> None:
    """Validate required keys and types only (no DB existence check)."""
    required_keys = ["host", "port", "db_path", "scan_interval_minutes", "refresh_interval_seconds", "log_level"]
    for key in required_keys:
        if key not in raw:
            raise ValueError(f"Missing required config key: {key}")

    if not isinstance(raw["port"], int) or raw["port"] <= 0:
        raise ValueError("port must be a positive integer")


def load_config(config_path: str | None = None) -> dict:
    """Load and validate config."""
    if config_path is None:
        config_path = os.environ.get("CDAILY_CONFIG", str(Path(__file__).parent.parent / "config.yaml"))
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # Resolve paths and allow safe env overrides
    env_db_path = os.environ.get("CDAILY_DB_PATH")
    if env_db_path:
        raw["db_path"] = env_db_path
    raw["db_path"] = _resolve_path(str(raw["db_path"]))

    ai_prefs = raw.setdefault("ai_preferences", {})
    env_endpoint = os.environ.get("CDAILY_AI_ENDPOINT")
    if env_endpoint:
        ai_prefs["endpoint"] = env_endpoint
    env_api_key = os.environ.get("CDAILY_AI_API_KEY")
    if env_api_key:
        ai_prefs["api_key"] = env_api_key

    _validate_schema(raw)
    return raw


def save_ai_preferences(new_prefs: dict) -> None:
    """Updates ai_preferences in config.yaml and reloads CONFIG in-place."""
    config_path = os.environ.get("CDAILY_CONFIG", str(Path(__file__).parent.parent / "config.yaml"))
    
    raw = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            try:
                raw = yaml.safe_load(f) or {}
            except Exception:
                raw = {}

    raw["ai_preferences"] = {
        "enabled": bool(new_prefs.get("enabled")),
        "endpoint": str(new_prefs.get("endpoint", "")).strip(),
        "api_key": str(new_prefs.get("api_key", "")).strip(),
        "auth_type": str(new_prefs.get("auth_type", "none")).strip(),
        "auth_header_name": str(new_prefs.get("auth_header_name", "")).strip(),
        "model": str(new_prefs.get("model", "")).strip(),
        "system_prompt": str(new_prefs.get("system_prompt", "Summarize this.")).strip(),
        "max_content_chars": int(new_prefs.get("max_content_chars", 12000)),
    }

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(raw, f, allow_unicode=True, sort_keys=False)

    # Reload global CONFIG dictionary in-place
    loaded = load_config(config_path)
    CONFIG.clear()
    CONFIG.update(loaded)


CONFIG = load_config()
DB_PATH: Path = CONFIG["db_path"]
BLOG_CATEGORIES: Dict[str, str] = CONFIG.get("blog_categories", DEFAULT_BLOG_CATEGORIES)
CATEGORY_EMOJI: Dict[str, str] = CONFIG.get("category_emoji", DEFAULT_CATEGORY_EMOJI)
DEFAULT_EMOJI = CATEGORY_EMOJI.get("default", "📰")
