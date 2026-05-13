"""
config.py — Load and validate config.yaml
All settings must be here, zero hardcoding.
"""

import os
from pathlib import Path
from typing import Dict

import yaml

# Default configurations
DEFAULT_BLOG_CATEGORIES: Dict[str, str] = {
    "CIPER Chile": "politica",
    "BioBioChile": "politica",
    "Cambio21": "politica",
    "El Clarin": "politica",
    "The Clinic": "humor",
    "BBC Mundo": "internacional",
    "The Guardian Mundo": "internacional",
    "Ars Technica": "ciencia",
    "Science Daily": "ciencia",
    "Diario Financiero": "economia",
    "The Onion": "humor",
    "CyberScoop": "ciberseguridad",
    "Dark Reading": "ciberseguridad",
    "Help Net Security": "ciberseguridad",
    "Infosecurity Magazine": "ciberseguridad",
    "Krebs on Security": "ciberseguridad",
    "MIT Tech Review AI": "ciencia",
    "SANS ISC": "ciberseguridad",
    "Schneier on Security": "ciberseguridad",
    "Talos Intelligence": "ciberseguridad",
    "The Hacker News": "ciberseguridad",
    "The Verge AI": "ciencia",
    "Unit 42 Palo Alto": "ciberseguridad",
    "We Live Security": "ciberseguridad",
}

DEFAULT_CATEGORY_EMOJI: Dict[str, str] = {
    "politica": "🏛️",
    "internacional": "🌎",
    "ciencia": "🔬",
    "economia": "💰",
    "humor": "😂",
    "ciberseguridad": "🔐",
    "default": "📰",
}


def _resolve_path(path: str) -> Path:
    """Expand ~ and environment variables in paths."""
    return Path(os.path.expandvars(os.path.expanduser(path)))


def validate_config(config: dict) -> None:
    """Validate required config keys and types."""
    required_keys = ["host", "port", "db_path", "scan_interval_minutes", "refresh_interval_seconds", "log_level"]
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing required config key: {key}")

    if not isinstance(config["port"], int) or config["port"] <= 0:
        raise ValueError("port must be a positive integer")

    if not config["db_path"].exists():
        raise FileNotFoundError(f"Database path does not exist: {config['db_path']}")


def load_config(config_path: str | None = None) -> dict:
    if config_path is None:
        config_path = os.environ.get("CDAILY_CONFIG", Path(__file__).parent.parent / "config.yaml")
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    # Resolve paths and allow safe env overrides for public sharing
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

    # Validate config
    validate_config(raw)

    return raw


CONFIG = load_config()
DB_PATH = CONFIG["db_path"]
BLOG_CATEGORIES: Dict[str, str] = CONFIG.get("blog_categories", DEFAULT_BLOG_CATEGORIES)
CATEGORY_EMOJI: Dict[str, str] = CONFIG.get("category_emoji", DEFAULT_CATEGORY_EMOJI)
DEFAULT_EMOJI = CATEGORY_EMOJI.get("default", "📰")
