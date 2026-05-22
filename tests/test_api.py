from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient backed by a fresh temp DB + config.yaml."""
    db_path = _tmp_db()

    # Create blogwatcher-cli shared schema in the temp DB
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE blogs (id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL, feed_url TEXT);
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            blog_id INTEGER REFERENCES blogs(id),
            title TEXT,
            url TEXT NOT NULL,
            content TEXT,
            summary TEXT,
            author TEXT,
            categories TEXT,
            published_date TEXT,
            guid TEXT,
            is_read INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
    conn.commit()
    conn.close()

    # Write minimal config.yaml that points to our temp DB
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        yaml.safe_dump(
            {
                "host": "127.0.0.1",
                "port": 7890,
                "db_path": db_path,
                "scan_interval_minutes": 30,
                "refresh_interval_seconds": 60,
                "log_level": "INFO",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CDAILY_CONFIG", str(cfg_file))
    monkeypatch.setenv("CDAILY_DB_PATH", db_path)

    # Patch config.DB_PATH so that get_connection() sees our temp DB
    import app.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "DB_PATH", Path(db_path))

    # Need to ensure that app.repositories.bootstrap uses the patched DB_PATH.
    # bootstrap imports DB_PATH at module load; but it uses a dynamic get from config now.
    # Still, import after patching.
    from app.main import app

    with TestClient(app) as tc:
        yield tc

    Path(db_path).unlink(missing_ok=True)


def _seed(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        DELETE FROM articles; DELETE FROM blogs;
        INSERT INTO blogs (id, name, url, feed_url) VALUES
            (1, 'Ars Technica', 'https://arstechnica.com', 'https://feeds.arstechnica.com'),
            (2, 'News Chile',   'https://example.cl',      'https://example.cl/rss');
        INSERT INTO articles (id, blog_id, title, url, published_date, is_read, categories) VALUES
            (1, 1, 'Rust in Linux 6.15', 'https://arstechnica.com/rust', '2026-05-18', 0, '["tech"]'),
            (2, 2, 'Copper strike ends', 'https://example.cl/copper',      '2026-05-17', 1, '["news"]');
        """)
    conn.commit()
    conn.close()


# Tests


def test_homepage(client):
    assert client.get("/").status_code == 200
    assert "CDaily" in client.get("/").text


def test_api_articles_empty(client):
    data = client.get("/api/articles").json()
    assert data["count"] == 0


def test_api_articles_with_data(client):
    db = os.environ["CDAILY_DB_PATH"]
    _seed(db)
    data = client.get("/api/articles").json()
    assert data["count"] == 2
    assert any(a["title"] == "Rust in Linux 6.15" for a in data["articles"])


def test_api_articles_filter_category(client):
    db = os.environ["CDAILY_DB_PATH"]
    _seed(db)
    data = client.get("/api/articles?cat=tech").json()
    assert all(a["category"] == "tech" for a in data["articles"])


def test_api_mark_read(client):
    db = os.environ["CDAILY_DB_PATH"]
    _seed(db)
    assert client.post("/api/articles/1/read").json()["ok"] is True
    cur = sqlite3.connect(db).execute("SELECT is_read FROM articles WHERE id = 1")
    assert cur.fetchone()[0] == 1


def test_api_mark_unread(client):
    db = os.environ["CDAILY_DB_PATH"]
    _seed(db)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE articles SET is_read = 1 WHERE id = 2")
        conn.commit()
    assert client.post("/api/articles/2/unread").json()["ok"] is True
    with sqlite3.connect(db) as conn:
        cur = conn.execute("SELECT is_read FROM articles WHERE id = 2")
        assert cur.fetchone()[0] == 0


def test_api_toggle_star(client):
    db = os.environ["CDAILY_DB_PATH"]
    _seed(db)
    js = client.post("/api/articles/1/star").json()
    assert js["ok"] is True and js["starred"] is True
    js = client.post("/api/articles/1/star").json()
    assert js["starred"] is False


def test_api_mark_all_read(client):
    db = os.environ["CDAILY_DB_PATH"]
    _seed(db)
    js = client.post("/api/articles/read-all").json()
    assert js["ok"] is True and js["count"] == 1


def test_api_rate_article(client):
    db = os.environ["CDAILY_DB_PATH"]
    _seed(db)
    js = client.post("/api/articles/1/rate", json={"rating": 5}).json()
    assert js["ok"] is True and js["rating"] == 5
    js = client.post("/api/articles/1/rate", json={"rating": None}).json()
    assert js["rating"] is None


def test_api_rate_article_bad_value(client):
    db = os.environ["CDAILY_DB_PATH"]
    _seed(db)
    assert client.post("/api/articles/1/rate", json={"rating": 6}).status_code == 422


def test_api_stats(client):
    db = os.environ["CDAILY_DB_PATH"]
    _seed(db)
    data = client.get("/api/stats").json()
    assert data["total"] == 1
    assert "by_category" in data


def test_api_scan_disabled(client, monkeypatch):
    db = os.environ["CDAILY_DB_PATH"]
    _seed(db)

    async def mock_fail():
        return {"ok": 0, "error": "blogwatcher-cli not found in PATH"}

    monkeypatch.setattr("app.routes.system.run_scan", mock_fail)
    data = client.post("/api/scan").json()
    assert data["ok"] is False
    err = (data.get("error") or "").lower() + (data.get("stderr") or "").lower()
    assert "not found" in err or "no such file" in err


def test_api_article_image_no_url(client):
    db = os.environ["CDAILY_DB_PATH"]
    _seed(db)
    assert client.get("/api/articles/1/image").status_code == 200


def test_api_settings_flow(client):
    # Test GET settings
    res = client.get("/api/settings")
    assert res.status_code == 200

    # Test POST settings
    payload = {
        "enabled": True,
        "endpoint": "http://localhost:12345/v1/chat/completions",
        "api_key": "test_key",
        "auth_type": "bearer",
        "auth_header_name": "",
        "model": "test_model",
        "system_prompt": "Test Prompt",
        "max_content_chars": 15000
    }
    res = client.post("/api/settings", json=payload)
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # Test that config is updated
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    assert data["model"] == "test_model"
    assert data["max_content_chars"] == 15000

    # Test connection test endpoint (can be True or False depending on local server availability)
    res = client.post("/api/settings/test", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "ok" in data
    assert isinstance(data["ok"], bool)
    if data["ok"]:
        assert "message" in data
    else:
        assert "error" in data


