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
    """
    Remove a blog from tracking.

    Safe-delete ordering (see SECURITY_AUDIT_f3d3e2c.md / kanban t_8de0611b):

    cdaily shares a single SQLite DB with blogwatcher-cli. `blogwatcher-cli remove`
    deletes the `blogs` row AND its `articles` atomically. Because PRAGMA
    foreign_keys=ON is enabled per connection (bootstrap.py), that external delete
    FAILS with "FOREIGN KEY constraint failed" whenever cdaily's extension tables
    (cdaily_starred / cdaily_summaries / cdaily_article_images /
    cdaily_article_ratings) still reference the articles being removed.

    To guarantee an external CLI failure never leaves a blog orphaned (blog present
    while its articles are already gone), we therefore:
      1. delete ONLY cdaily_* rows first (releases the FK so the CLI can run; the
         blog + articles stay fully intact),
      2. invoke `blogwatcher-cli remove <name> -y` -> it owns the authoritative
         delete of the `blogs` + `articles` rows,
      3. if the CLI fails or times out -> return ok:0 with the DB otherwise UNTOUCHED:
         blog + articles remain intact (no orphan). The only data already gone is the
         recoverable cdaily_* user enrichment, which a rescan restores.
      4. if the CLI succeeds -> a DEFENSIVE DELETE of any `articles` it may have left
         behind (older CLI builds), so they never linger as orphans.

    We intentionally do NOT pre-delete `articles` ourselves: doing so before the CLI
    call would orphan the blog (blog present, articles gone) if the CLI later fails.
    """
    try:
        # 1) Fetch the blog name (blogwatcher-cli remove takes a name, not an id)
        #    and clear cdaily_* children to release the foreign key that would
        #    otherwise block the external CLI's own delete.
        with closing(get_connection()) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM blogs WHERE id = ?", (blog_id,))
            row = cur.fetchone()
            if not row:
                return {"ok": 0, "error": f"Blog with ID {blog_id} not found in database"}
            blog_name = row["name"]

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

        # 2) Hand the authoritative blogs + articles delete to blogwatcher-cli.
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
            # CLI never completed: blog + articles remain intact -> no orphan.
            return {"ok": 0, "error": "Remove operation timed out (>30s)"}

        if returncode != 0:
            # External CLI failed: blog + articles are untouched. The only data
            # already gone is the cdaily_* enrichment, which is recoverable on the
            # next scan. We do NOT roll forward and delete the blog ourselves.
            return {"ok": 0, "error": stderr.strip() or f"Process exited with {returncode}"}

        # 3) CLI succeeded. Defensive cleanup of any articles the CLI left behind
        #    (defensive only: a failure here must not flip a successful remove).
        deleted_articles = 0
        try:
            with closing(get_connection()) as conn:
                with conn:
                    cur = conn.cursor()
                    cur.execute("DELETE FROM articles WHERE blog_id = ?", (blog_id,))
                    deleted_articles = cur.rowcount
        except Exception:
            pass

        return {
            "ok": 1,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
            "deleted_articles": deleted_articles,
        }
    except FileNotFoundError:
        return {"ok": 0, "error": "blogwatcher-cli not found in PATH"}
