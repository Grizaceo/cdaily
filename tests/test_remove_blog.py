"""
Integration tests for services.blogs.remove_blog.

These exercise remove_blog WITHOUT mocking the function (the gap flagged in
qa_report_f3d3e2c.md t_8de0611b). blogwatcher-cli is mocked at the
subprocess boundary so the tests are deterministic and have no external side
effects, while still proving the safe-delete ordering:

  * cdaily only clears its cdaily_* extension rows before calling the CLI; the
    blog + articles stay intact until the external CLI reports success.
  * If the CLI fails / times out, the blog + articles remain in the DB (no
    orphan), which is the bug this card fixes.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

import cdaily.config as cfg_mod
import cdaily.services.blogs as blogs_svc


class _FakeProc:
    """Stand-in for asyncio.subprocess.Process controlled by the test."""

    def __init__(self, *, returncode, stdout=b"", stderr=b"", raise_timeout=False, db_path=None):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._raise_timeout = raise_timeout
        self._db_path = db_path
        self.articles_at_cli_call: int | None = None
        self.captured_args: tuple | None = None

    async def communicate(self):
        if self._raise_timeout:
            raise asyncio.TimeoutError()
        if self._db_path is not None:
            conn = sqlite3.connect(self._db_path)
            self.articles_at_cli_call = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            conn.close()
        return self._stdout, self._stderr

    def kill(self):
        pass


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Fresh temp DB with the shared blogwatcher-cli + cdaily schema."""
    path = tmp_path / "blogwatcher-cli.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE blogs (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            feed_url TEXT,
            scrape_selector TEXT,
            last_scanned TIMESTAMP
        );
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            blog_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            published_date TIMESTAMP,
            discovered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_read BOOLEAN DEFAULT FALSE,
            FOREIGN KEY(blog_id) REFERENCES blogs(id)
        );
        CREATE TABLE cdaily_starred (
            id INTEGER PRIMARY KEY,
            article_id INTEGER REFERENCES articles(id),
            starred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(article_id)
        );
        CREATE TABLE cdaily_summaries (
            id INTEGER PRIMARY KEY,
            article_id INTEGER REFERENCES articles(id) UNIQUE,
            ai_summary TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE cdaily_article_images (
            id INTEGER PRIMARY KEY,
            article_id INTEGER REFERENCES articles(id) UNIQUE,
            image_url TEXT,
            fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE cdaily_article_ratings (
            id INTEGER PRIMARY KEY,
            article_id INTEGER REFERENCES articles(id) UNIQUE,
            rating INTEGER NOT NULL,
            rated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("CDAILY_DB_PATH", str(path))
    monkeypatch.setattr(cfg_mod, "DB_PATH", Path(str(path)))
    return str(path)


def _seed(db_path: str, with_enrichment: bool = True) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        INSERT INTO blogs (id, name, url, feed_url) VALUES
            (1, 'Ars Technica', 'https://arstechnica.com', 'https://feeds.arstechnica.com');
        INSERT INTO articles (id, blog_id, title, url) VALUES
            (1, 1, 'Rust in Linux', 'https://arstechnica.com/rust'),
            (2, 1, 'Copper strike', 'https://arstechnica.com/copper');
        """
    )
    if with_enrichment:
        conn.execute("INSERT INTO cdaily_starred (id, article_id) VALUES (1, 1)")
        conn.execute("INSERT INTO cdaily_summaries (id, article_id, ai_summary) VALUES (1, 2, 'summary')")
        conn.execute("INSERT INTO cdaily_article_images (id, article_id, image_url) VALUES (1, 1, 'https://img/x.jpg')")
        conn.execute("INSERT INTO cdaily_article_ratings (id, article_id, rating) VALUES (1, 1, 5)")
    conn.commit()
    conn.close()


def _counts(db_path: str) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    out = {
        "blogs": conn.execute("SELECT COUNT(*) FROM blogs").fetchone()[0],
        "articles": conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0],
        "starred": conn.execute("SELECT COUNT(*) FROM cdaily_starred").fetchone()[0],
        "summaries": conn.execute("SELECT COUNT(*) FROM cdaily_summaries").fetchone()[0],
        "images": conn.execute("SELECT COUNT(*) FROM cdaily_article_images").fetchone()[0],
        "ratings": conn.execute("SELECT COUNT(*) FROM cdaily_article_ratings").fetchone()[0],
    }
    conn.close()
    return out


def _patch_cli(monkeypatch, *, returncode=0, stdout=b"Removed blog\n", stderr=b"", raise_timeout=False, db_path=None):
    """Replace the subprocess CLI with a controllable fake and return the proc."""
    fake = _FakeProc(returncode=returncode, stdout=stdout, stderr=stderr, raise_timeout=raise_timeout, db_path=db_path)

    async def _fake_create_subprocess_exec(*args, **kwargs):
        fake.captured_args = args
        return fake

    monkeypatch.setattr(blogs_svc.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)
    return fake


def test_remove_blog_cli_success_deletes_articles_and_reports_ok(db_path, monkeypatch):
    _seed(db_path)
    fake = _patch_cli(monkeypatch, returncode=0, stdout=b"Removed blog\n", db_path=db_path)

    res = asyncio.run(blogs_svc.remove_blog(1))

    assert res.get("ok") == 1, res
    # articles present at CLI call time -> service did NOT pre-delete them (the fix).
    assert fake.articles_at_cli_call == 2
    assert fake.captured_args == ("blogwatcher-cli", "remove", "Ars Technica", "-y")
    # defensive cleanup removes the articles the (mocked) CLI left behind.
    counts = _counts(db_path)
    assert counts["articles"] == 0
    assert counts["starred"] == 0 and counts["summaries"] == 0
    assert counts["images"] == 0 and counts["ratings"] == 0


def test_remove_blog_cli_failure_keeps_blog_and_articles_intact(db_path, monkeypatch):
    _seed(db_path)
    _patch_cli(monkeypatch, returncode=1, stderr=b"boom", db_path=db_path)

    res = asyncio.run(blogs_svc.remove_blog(1))

    assert res.get("ok") == 0, res
    assert "boom" in (res.get("error") or "")
    counts = _counts(db_path)
    # No orphan: blog + articles survive an external CLI failure.
    assert counts["blogs"] == 1
    assert counts["articles"] == 2
    # Only the recoverable cdaily_* enrichment was cleared.
    assert counts["starred"] == 0 and counts["summaries"] == 0
    assert counts["images"] == 0 and counts["ratings"] == 0


def test_remove_blog_cli_timeout_keeps_blog_and_articles_intact(db_path, monkeypatch):
    _seed(db_path)
    _patch_cli(monkeypatch, raise_timeout=True, db_path=db_path)

    res = asyncio.run(blogs_svc.remove_blog(1))

    assert res.get("ok") == 0, res
    assert "timed out" in (res.get("error") or "").lower()
    counts = _counts(db_path)
    assert counts["blogs"] == 1
    assert counts["articles"] == 2


def test_remove_blog_unknown_id_reports_error(db_path, monkeypatch):
    _seed(db_path)
    _patch_cli(monkeypatch, returncode=0, db_path=db_path)

    res = asyncio.run(blogs_svc.remove_blog(999))

    assert res.get("ok") == 0, res
    assert "not found" in (res.get("error") or "").lower()
    # DB untouched.
    counts = _counts(db_path)
    assert counts["blogs"] == 1 and counts["articles"] == 2
