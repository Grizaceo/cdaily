"""Exercise the standalone Hermes plugin against CDaily with a disposable DB."""

import importlib.util
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

import pytest
import yaml

from test_api import _seed, client  # noqa: F401 — shared disposable API fixture

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "integrations/hermes/cdaily"
spec = importlib.util.spec_from_file_location("cdaily_test_plugin", PLUGIN_DIR / "__init__.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


class Context:
    def __init__(self, settings=None):
        self.settings = settings or {}
        self.tools = {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_tool(self, **tool):
        self.tools[tool["name"]] = tool

    def call(self, tool_name, **args):
        return json.loads(self.tools["cdaily_" + tool_name]["handler"](args, task_id="test"))


@pytest.fixture
def bridge(client, monkeypatch):  # noqa: F811 — imported pytest fixture
    import cdaily.config as config

    _seed(str(config.DB_PATH))
    calls = []

    class Response:
        def __init__(self, data):
            self.data = data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return self.data

    class Opener:
        def open(self, req, timeout):
            parsed = urlsplit(req.full_url)
            calls.append((req, timeout))
            response = client.request(
                req.method, parsed.path + "?" + parsed.query, content=req.data, headers=dict(req.header_items())
            )
            if response.status_code >= 400:
                raise HTTPError(req.full_url, response.status_code, "error", {}, None)
            return Response(response.content)

    monkeypatch.setattr(plugin, "build_opener", lambda *args: Opener())
    ctx = Context()
    plugin.register(ctx)
    return ctx, calls


def test_registration_is_offline_and_manifest_matches(monkeypatch):
    monkeypatch.setattr(plugin, "build_opener", lambda *a: pytest.fail("registration must not connect"))
    ctx = Context()
    plugin.register(ctx)
    manifest = yaml.safe_load((PLUGIN_DIR / "plugin.yaml").read_text())
    assert set(manifest["provides_tools"]) == set(ctx.tools)
    assert len(ctx.tools) == 12
    for name, tool in ctx.tools.items():
        assert tool["schema"]["name"] == name
        assert tool["toolset"] == "cdaily"


def test_reads_digest_and_shared_mutations(bridge):
    ctx, _ = bridge
    assert ctx.call("feed_stats")["total"] == 1
    feed = ctx.call("feed_read")
    assert feed["count"] == 1
    assert feed["articles"][0]["url"] == "https://arstechnica.com/rust"
    assert ctx.call("feed_read", filter="all", query="Copper")["articles"][0]["id"] == 2
    assert ctx.call("feed_digest")["total_unread"] == 1
    assert ctx.call("article_mark_apply", id=1, state="toggle_star")["starred"] is True
    assert ctx.call("feed_read", filter="starred")["articles"][0]["id"] == 1
    assert ctx.call("article_rate_apply", id=1, rating=5)["rating"] == 5
    assert ctx.call("feed_read", verbose=True)["articles"][0]["user_rating"] == 5
    assert ctx.call("article_rate_apply", id=1, rating=None)["rating"] is None
    assert ctx.call("article_mark_apply", id=1, state="read")["ok"]
    assert ctx.call("feed_stats")["total"] == 0
    assert ctx.call("article_mark_apply", id=1, state="unread")["ok"]
    assert ctx.call("feed_clear_apply", confirm=True)["count"] == 1
    assert ctx.call("sources_list")["count"] == 2


@pytest.mark.parametrize(
    "name,args",
    [
        ("feed_read", {"limit": -1}),
        ("feed_read", {"filter": "invalid"}),
        ("article_mark_apply", {"id": "1/../../scan", "state": "read"}),
        ("article_mark_apply", {"id": True, "state": "read"}),
        ("article_rate_apply", {"id": 1, "rating": 6}),
        ("feed_clear_apply", {"confirm": False}),
        ("feed_clear_apply", {}),
        ("feed_scan_apply", {"unknown": 1}),
        ("sources_add_apply", {"name": " ", "url": "https://example.com"}),
    ],
)
def test_invalid_arguments_do_not_send_requests(bridge, name, args):
    ctx, calls = bridge
    assert ctx.call(name, **args)["ok"] is False
    assert not calls


def test_authentication_and_configuration(bridge, monkeypatch):
    ctx, calls = bridge
    monkeypatch.setenv("CDAILY_API_TOKEN", "test-secret")
    ctx.settings.update(api_url="http://localhost:9999", timeout=9)
    assert ctx.call("feed_stats")["total"] == 1
    req, timeout = calls[-1]
    assert req.full_url == "http://localhost:9999/api/stats"
    assert req.get_header("Authorization") == "Bearer test-secret"
    assert timeout == 9
    monkeypatch.delenv("CDAILY_API_TOKEN")
    # Backend auth is enabled separately; a missing client token yields a useful error.
    import cdaily.main as main

    monkeypatch.setattr(main, "_AUTH_TOKEN", "server-secret")
    result = ctx.call("feed_stats")
    assert result["status"] == 401
    assert "CDAILY_API_TOKEN" in result["error"]
    assert "server-secret" not in json.dumps(result)


def test_scan_ai_and_source_routes(bridge, monkeypatch):
    ctx, calls = bridge
    import cdaily.routes.articles as articles
    import cdaily.routes.blogs as blogs
    import cdaily.routes.system as system

    async def scan():
        return {"ok": True, "returncode": 0}

    async def images():
        pass

    async def summary(id, prefs):
        return {"ok": True, "summary": "cached summary", "cached": True}

    async def translation(id, prefs):
        return {"ok": True, "translation": "translated text"}

    changes = []

    async def add(**kwargs):
        changes.append(kwargs)
        return {"ok": True}

    async def remove(**kwargs):
        changes.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(system, "run_scan", scan)
    monkeypatch.setattr(system, "fetch_missing_images", images)
    monkeypatch.setattr(articles, "summarize_article", summary)
    monkeypatch.setattr(articles, "translate_article", translation)
    monkeypatch.setattr(blogs, "add_blog", add)
    monkeypatch.setattr(blogs, "remove_blog", remove)
    assert ctx.call("feed_scan_apply")["ok"]
    assert ctx.call("article_summarize_apply", id=1)["summary"] == "cached summary"
    assert ctx.call("article_translate_apply", id=1)["translation"] == "translated text"
    assert ctx.call("sources_add_apply", name="Example", url="https://example.com")["ok"]
    assert ctx.call("sources_remove_apply", blog_id=2)["ok"]
    assert changes[0]["name"] == "Example"
    assert changes[1] == {"blog_id": 2}
    assert all(timeout == 180 for _, timeout in calls)


def test_digest_reports_true_count_and_truncation():
    class FakeClient:
        def request(self, method, path, **kwargs):
            if path == "/api/stats":
                return {"total": 350}
            return {
                "articles": [
                    {"id": i, "title": "Title", "url": "https://example.com", "blog_name": "Blog", "category": "tech"}
                    for i in range(200)
                ]
            }

    result = plugin.invoke(FakeClient(), "feed_digest", {"top_n": 2, "group_by": "blog"})
    assert result["total_unread"] == 350
    assert result["sampled"] == 200
    assert result["truncated"] is True
    assert len(result["by_group"]["Blog"]) == 2


@pytest.mark.parametrize(
    "failure",
    [URLError("secret in exception"), TimeoutError("secret"), HTTPError("http://host", 429, "secret", {}, None)],
)
def test_transport_errors_are_safe(monkeypatch, failure):
    class Opener:
        def open(self, *args, **kwargs):
            raise failure

    monkeypatch.setattr(plugin, "build_opener", lambda *a: Opener())
    ctx = Context()
    plugin.register(ctx)
    result = ctx.call("feed_stats")
    assert result["ok"] is False
    assert "secret" not in json.dumps(result)


def test_redirect_does_not_forward_credentials():
    assert plugin.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://other.example") is None


@pytest.mark.parametrize(
    "settings",
    [
        {"api_url": "file:///tmp/data"},
        {"api_url": "http://user:password@host"},
        {"timeout": float("nan")},
        {"timeout": 0},
    ],
)
def test_invalid_settings_fail_before_connecting(monkeypatch, settings):
    monkeypatch.setattr(plugin, "build_opener", lambda *a: pytest.fail("must not connect"))
    ctx = Context(settings)
    plugin.register(ctx)
    assert ctx.call("feed_stats")["ok"] is False
