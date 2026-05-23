"""CDaily MCP server — stdio transport.

Exposes the CDaily feed reader as MCP tools, resources, and prompts so
agents (Claude Code, Cursor, Codex CLI, Continue) can read, search, mark
and curate the feed without going through the FastAPI HTTP layer.

Run:
    python -m cdaily.mcp_server

Register in ~/.claude.json:
    {
      "mcpServers": {
        "cdaily": {
          "command": "python",
          "args": ["-m", "cdaily.mcp_server"],
          "cwd": "/home/gris/.hermes/workspace/repos/cdaily"
        }
      }
    }

Optional env: CDAILY_DB_PATH (default: ~/.blogwatcher-cli/blogwatcher-cli.db).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .mcp import register_prompts, register_resources, register_tools

mcp = FastMCP("cdaily")
register_tools(mcp)
register_resources(mcp)
register_prompts(mcp)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
