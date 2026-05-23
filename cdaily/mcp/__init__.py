"""CDaily MCP server — agent-native exposure of feed reader operations."""

from .prompts import register_prompts
from .resources import register_resources
from .tools import register_tools

__all__ = ["register_tools", "register_resources", "register_prompts"]
