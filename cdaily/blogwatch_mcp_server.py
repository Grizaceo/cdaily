"""MCP server wrapping blogwatcher-cli subprocess.

Agent-native bridge: tools mimic the CLI commands with structured output.
Follows cdaily conventions: _apply suffix for mutations, slim responses,
agent-oriented descriptions.
"""

from __future__ import annotations

import json
import os
import subprocess

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("blogwatcher-cli")

_BW_BIN = os.environ.get("BLOGWATCHER_CLI_BIN", "blogwatcher-cli")


def _db_args() -> list[str]:
    db = os.environ.get("CDAILY_DB_PATH", "")
    if db:
        return ["--db", os.path.expanduser(db)]
    return []


def _run(*args: str, timeout: int = 120) -> dict[str, object]:
    """Run blogwatcher-cli and return {ok, stdout, stderr, returncode}."""
    try:
        r = subprocess.run(
            [_BW_BIN, *_db_args(), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": r.returncode == 0,
            "stdout": r.stdout.strip(),
            "stderr": r.stderr.strip(),
            "returncode": r.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "Timeout expired", "returncode": -1}
    except FileNotFoundError:
        return {"ok": False, "stdout": "", "stderr": f"'{_BW_BIN}' not found. pip install blogwatcher-cli", "returncode": -1}


# ─── Read tools ────────────────────────────────────────────────────────────────


@mcp.tool()
def blogwatch_list() -> dict[str, object]:
    """List all tracked blog sources.

    Use to discover what feeds are configured. Returns {ok, blogs[]}
    with name, url, feed_url, last_scanned per blog.
    """
    result = _run("blogs")
    if not result["ok"]:
        return {"ok": False, "error": result["stderr"]}

    lines = result["stdout"].split("\n")
    blogs: list[dict] = []
    # Blog list output format: columns with headers
    current: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line:
            if current:
                blogs.append(current)
                current = {}
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip().lower().replace(" ", "_")
            current[key] = val.strip()
    if current:
        blogs.append(current)

    return {"ok": True, "count": len(blogs), "blogs": blogs}


@mcp.tool()
def blogwatch_articles(filter: str = "unread", limit: int = 20) -> dict[str, object]:
    """List articles. Use filter='unread' (default) or 'all'.

    Returns {ok, count, articles[]}.
    """
    args = ["articles"]
    if filter == "all":
        args.append("--all")
    if limit:
        args.extend(["--limit", str(limit)])
    result = _run(*args)
    return {
        "ok": result["ok"],
        "count": 0,
        "stdout": result["stdout"],
        "error": result.get("stderr") if not result["ok"] else None,
    }


# ─── Mutating tools (_apply suffix) ────────────────────────────────────────────


@mcp.tool()
def blogwatch_add_apply(
    name: str,
    url: str,
    feed_url: str | None = None,
    scrape_selector: str | None = None,
) -> dict[str, object]:
    """[MUTATES] Add a new blog source.

    Args:
        name: Display name for the blog.
        url: Website URL.
        feed_url: Optional direct RSS/Atom feed URL.
        scrape_selector: Optional CSS selector for scraping articles.
    """
    args = ["add", name, url]
    if feed_url:
        args.extend(["--feed-url", feed_url])
    if scrape_selector:
        args.extend(["--selector", scrape_selector])
    return _run(*args)


@mcp.tool()
def blogwatch_remove_apply(name: str) -> dict[str, object]:
    """[MUTATES] Remove a tracked blog by name.

    Use blogwatch_list first to find the exact name.
    """
    return _run("remove", name)


@mcp.tool()
def blogwatch_scan_apply(name: str | None = None, silent: bool = True, workers: int = 8) -> dict[str, object]:
    """[MUTATES, SLOW 30s-2min] Scan blogs for new articles.

    Args:
        name: Optional blog name to scan. Omit to scan ALL tracked blogs.
        silent: Suppress progress output (default True, agent-friendly).
        workers: Concurrent workers for full scan (default 8).
    """
    args = ["scan"]
    if silent:
        args.append("--silent")
    if workers:
        args.extend(["--workers", str(workers)])
    if name:
        args.append(name)
    return _run(*args, timeout=180)


@mcp.tool()
def blogwatch_read_apply(article_id: int) -> dict[str, object]:
    """[MUTATES] Mark a single article as read.

    Args:
        article_id: The article ID (from blogwatch_articles output).
    """
    return _run("read", str(article_id))


@mcp.tool()
def blogwatch_read_all_apply() -> dict[str, object]:
    """[MUTATES] Mark ALL unread articles as read.

    Use with caution — this clears the entire unread queue.
    """
    return _run("read-all")


@mcp.tool()
def blogwatch_unread_apply(article_id: int) -> dict[str, object]:
    """[MUTATES] Mark an article as unread.

    Args:
        article_id: The article ID to revert to unread.
    """
    return _run("unread", str(article_id))


@mcp.tool()
def blogwatch_import_apply(opml_path: str) -> dict[str, object]:
    """[MUTATES] Import blogs from an OPML file.

    Args:
        opml_path: Absolute path to the .opml file.
    """
    return _run("import", opml_path)


# ─── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
