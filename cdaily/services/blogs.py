"""Blogwatcher sources (blogs) service."""

from __future__ import annotations

import asyncio
from contextlib import closing

from ..database import get_connection


async def add_blog(
    name: str,
    url: str,
    feed_url: str | None = None,
    scrape_selector: str | None = None,
) -> dict[str, int | str]:
    try:
        args = ["add", name, url]
        if feed_url:
            args.extend(["--feed-url", feed_url])
        if scrape_selector:
            args.extend(["--scrape-selector", scrape_selector])

        proc = await asyncio.create_subprocess_exec(
            "blogwatcher-cli",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            stdout = stdout_bytes.decode() if stdout_bytes else ""
            stderr = stderr_bytes.decode() if stderr_bytes else ""
            returncode = proc.returncode
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return {"ok": 0, "error": "Add operation timed out (>30s)"}

        if returncode != 0:
            return {"ok": 0, "error": stderr.strip() or f"Process exited with {returncode}"}

        return {"ok": 1, "stdout": stdout, "stderr": stderr, "returncode": returncode}
    except FileNotFoundError:
        return {"ok": 0, "error": "blogwatcher-cli not found in PATH"}


async def remove_blog(blog_id: int) -> dict[str, int | str]:
    try:
        # Retrieve the blog name from the SQLite database first,
        # as blogwatcher-cli remove requires the name instead of the ID.
        try:
            with closing(get_connection()) as conn:
                cur = conn.cursor()
                cur.execute("SELECT name FROM blogs WHERE id = ?", (blog_id,))
                row = cur.fetchone()
                if not row:
                    return {"ok": 0, "error": f"Blog with ID {blog_id} not found in database"}
                blog_name = row["name"]

                # Delete in FK order inside one transaction.
                # We enabled PRAGMA foreign_keys=ON in bootstrap; none of the
                # relevant FKs cascade, so we must clear children explicitly:
                #   1. cdaily_* rows reference articles(id)  -> delete first
                #   2. articles rows reference blogs(id)     -> delete next
                #   3. the blog row itself is removed by blogwatcher-cli (separate process)
                with conn:
                    cur.execute(
                        "DELETE FROM cdaily_starred WHERE article_id IN (SELECT id FROM articles WHERE blog_id = ?)",
                        (blog_id,),
                    )
                    cur.execute(
                        "DELETE FROM cdaily_summaries WHERE article_id IN (SELECT id FROM articles WHERE blog_id = ?)",
                        (blog_id,),
                    )
                    cur.execute(
                        "DELETE FROM cdaily_article_images WHERE article_id IN (SELECT id FROM articles WHERE blog_id = ?)",
                        (blog_id,),
                    )
                    cur.execute(
                        "DELETE FROM cdaily_article_ratings WHERE article_id IN (SELECT id FROM articles WHERE blog_id = ?)",
                        (blog_id,),
                    )
                    cur.execute("DELETE FROM articles WHERE blog_id = ?", (blog_id,))
                    deleted_articles = cur.rowcount
        except Exception as db_err:
            return {"ok": 0, "error": f"Failed to delete blog data from database: {str(db_err)}"}

        # Invoke blogwatcher-cli remove <name> -y (non-interactive)
        proc = await asyncio.create_subprocess_exec(
            "blogwatcher-cli",
            "remove",
            blog_name,
            "-y",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            stdout = stdout_bytes.decode() if stdout_bytes else ""
            stderr = stderr_bytes.decode() if stderr_bytes else ""
            returncode = proc.returncode
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return {"ok": 0, "error": "Remove operation timed out (>30s)"}

        if returncode != 0:
            return {"ok": 0, "error": stderr.strip() or f"Process exited with {returncode}"}

        return {"ok": 1, "stdout": stdout, "stderr": stderr, "returncode": returncode, "deleted_articles": deleted_articles}
    except FileNotFoundError:
        return {"ok": 0, "error": "blogwatcher-cli not found in PATH"}
