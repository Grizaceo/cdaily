"""Hermes tools backed by the same HTTP API as the CDaily Omarchy widget.

Standalone stdlib-only plugin: importing/registering performs no I/O.
"""

from __future__ import annotations

import json
import math
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, ctx):
        self.ctx = ctx

    def request(self, method, path, query=None, body=None, slow=False):
        base = str(self.ctx.get_config("api_url", os.environ.get("CDAILY_URL", "http://127.0.0.1:7890"))).rstrip("/")
        parsed = urlsplit(base)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("api_url must be an http(s) URL without embedded credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("api_url must not contain a query or fragment")
        timeout = float(self.ctx.get_config("slow_timeout" if slow else "timeout", 180 if slow else 15))
        if not math.isfinite(timeout) or not 1 <= timeout <= 600:
            raise ValueError("timeout must be between 1 and 600 seconds")
        token = os.environ.get("CDAILY_API_TOKEN", "").strip()
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        url = base + path
        if query:
            url += "?" + urlencode(
                {k: str(v).lower() if isinstance(v, bool) else v for k, v in query.items() if v is not None}
            )
        req = Request(url, data=data, headers=headers, method=method)
        # Never forward the API token through a redirect or environment proxy.
        opener = build_opener(ProxyHandler({}), NoRedirect())
        try:
            with opener.open(req, timeout=timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            messages = {
                401: "Authentication required: set CDAILY_API_TOKEN in Hermes' environment.",
                403: "Access denied by CDaily.",
                404: "CDaily resource or endpoint not found.",
                429: "CDaily rate limit reached; wait before retrying.",
            }
            return {
                "ok": False,
                "status": exc.code,
                "error": messages.get(exc.code, "CDaily rejected the request; check the backend logs."),
            }
        except (URLError, TimeoutError, OSError):
            return {
                "ok": False,
                "error": "CDaily is unavailable or timed out. Check the backend, api_url and timeout. "
                "A timed-out mutation may have completed; check its state before retrying.",
            }
        except (ValueError, UnicodeError):
            return {"ok": False, "error": "CDaily returned an invalid JSON response."}


def article(a, verbose=False):
    slim = {
        "id": a["id"],
        "title": a["title"],
        "url": a["url"],
        "blog": a["blog_name"],
        "published": a.get("published_date"),
        "is_read": a.get("is_read"),
        "starred": a.get("is_starred", False),
        "rating": a.get("user_rating"),
        "category": a.get("category"),
    }
    return {**a, **slim} if verbose else slim


def string(**kwargs):
    return {"type": "string", **kwargs}


def integer(minimum=1, maximum=None):
    return {"type": "integer", "minimum": minimum, **({"maximum": maximum} if maximum is not None else {})}


BOOL = {"type": "boolean"}
TOOLS = {
    "feed_read": (
        "Read or search CDaily articles by title/category. URLs are included; verbose includes cached summaries. "
        "Search is text matching, not semantic search. Does not mark articles read.",
        {
            "filter": string(enum=["unread", "starred", "all"], default="unread"),
            "category": string(),
            "query": string(),
            "limit": integer(maximum=200),
            "offset": integer(0),
            "verbose": BOOL,
        },
        [],
    ),
    "feed_digest": (
        "Briefing of unread articles grouped by category or blog. Returns the exact unread count, "
        "a bounded sample and a flag if the sample is incomplete. No AI call or state change.",
        {"top_n": integer(maximum=20), "group_by": string(enum=["category", "blog", "flat"])},
        [],
    ),
    "feed_stats": ("Get exact unread counts overall and by category.", {}, []),
    "article_mark_apply": (
        "[MUTATES] Mark an article read/unread or toggle its favorite state. "
        "toggle_star is NOT idempotent: do not blindly retry it.",
        {"id": integer(), "state": string(enum=["read", "unread", "toggle_star"])},
        ["id", "state"],
    ),
    "article_rate_apply": (
        "[MUTATES] Set an article rating from 1 to 5, or null to clear it.",
        {"id": integer(), "rating": {"type": ["integer", "null"], "minimum": 1, "maximum": 5}},
        ["id", "rating"],
    ),
    "article_summarize_apply": (
        "[MUTATES, COSTLY] Generate/cache an AI summary using CDaily's configured AI endpoint.",
        {"id": integer()},
        ["id"],
    ),
    "article_translate_apply": (
        "[MUTATES, COSTLY] Translate article content (not cached) using CDaily's configured AI endpoint.",
        {"id": integer()},
        ["id"],
    ),
    "feed_clear_apply": (
        "[MUTATES, BULK] Mark ALL unread articles read. Use only when the user requests clearing the feed.",
        {"confirm": {"type": "boolean", "enum": [True]}},
        ["confirm"],
    ),
    "feed_scan_apply": (
        "[MUTATES, SLOW] Scan configured sources using blogwatcher-cli. May take several minutes.",
        {},
        [],
    ),
    "sources_list": ("List the blog sources configured in CDaily.", {}, []),
    "sources_add_apply": (
        "[MUTATES] Add a blog source using blogwatcher-cli. Backend validates external URLs.",
        {"name": string(minLength=1), "url": string(minLength=1), "feed_url": string(), "scrape_selector": string()},
        ["name", "url"],
    ),
    "sources_remove_apply": (
        "[MUTATES] Remove a configured blog source and its articles by blog id.",
        {"blog_id": integer()},
        ["blog_id"],
    ),
}


def validate(args, properties, required):
    if not isinstance(args, dict):
        raise ValueError("arguments must be an object")
    if set(args) - set(properties) or set(required) - set(args):
        raise ValueError("unknown or missing arguments")
    for key, value in args.items():
        spec = properties[key]
        types = spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
        actual = {str: "string", int: "integer", bool: "boolean", type(None): "null"}.get(type(value))
        if actual not in types:
            raise ValueError(f"invalid type for {key}")
        if "enum" in spec and value not in spec["enum"]:
            raise ValueError(f"invalid value for {key}")
        if actual == "integer" and (value < spec.get("minimum", value) or value > spec.get("maximum", value)):
            raise ValueError(f"{key} is outside the allowed range")
        if actual == "string" and len(value.strip()) < spec.get("minLength", 0):
            raise ValueError(f"{key} must not be empty")


def invoke(client, name, args):
    if name == "feed_read":
        result = client.request(
            "GET",
            "/api/articles",
            query={
                "cat": args.get("category"),
                "q": args.get("query"),
                "unread": args.get("filter", "unread") == "unread",
                "starred": args.get("filter") == "starred",
                "limit": args.get("limit", 20),
                "offset": args.get("offset", 0),
            },
        )
        if "articles" in result:
            return {
                "count": result["count"],
                "articles": [article(a, args.get("verbose", False)) for a in result["articles"]],
            }
        return result
    if name == "feed_digest":
        stats = client.request("GET", "/api/stats")
        if "total" not in stats:
            return stats
        result = client.request("GET", "/api/articles", query={"unread": True, "limit": 200})
        if "articles" not in result:
            return result
        groups = {}
        mode = args.get("group_by", "category")
        for a in result["articles"]:
            key = (
                "all" if mode == "flat" else a.get("category" if mode == "category" else "blog_name") or "uncategorized"
            )
            group = groups.setdefault(key, [])
            if len(group) < args.get("top_n", 5):
                group.append(article(a))
        return {
            "total_unread": stats["total"],
            "sampled": len(result["articles"]),
            "truncated": stats["total"] > len(result["articles"]),
            "by_group": groups,
        }
    if name == "feed_stats":
        return client.request("GET", "/api/stats")
    if name == "sources_list":
        result = client.request("GET", "/api/blogs")
        return {"count": len(result), "sources": result} if isinstance(result, list) else result
    if name == "sources_add_apply":
        return client.request("POST", "/api/blogs", body=args, slow=True)
    if name == "sources_remove_apply":
        return client.request("DELETE", f"/api/blogs/{args['blog_id']}", slow=True)
    if name == "feed_scan_apply":
        return client.request("POST", "/api/scan", slow=True)
    if name == "feed_clear_apply":
        return client.request("POST", "/api/articles/read-all")
    if name == "article_mark_apply":
        action = "star" if args["state"] == "toggle_star" else args["state"]
        return client.request("POST", f"/api/articles/{args['id']}/{action}")
    action = {
        "article_rate_apply": "rate",
        "article_summarize_apply": "summarize",
        "article_translate_apply": "translate",
    }[name]
    return client.request(
        "POST",
        f"/api/articles/{args['id']}/{action}",
        body={"rating": args["rating"]} if action == "rate" else None,
        slow=action != "rate",
    )


def register(ctx):
    client = Client(ctx)
    for short_name, (description, properties, required) in TOOLS.items():
        name = "cdaily_" + short_name

        def handler(args, _name=short_name, _props=properties, _required=required, **kwargs):
            try:
                validate(args, _props, _required)
                result = invoke(client, _name, args)
            except (ValueError, TypeError):
                result = {
                    "ok": False,
                    "error": "Invalid arguments or plugin settings; check the tool schema and CDaily settings.",
                }
            return json.dumps(result, ensure_ascii=False)

        ctx.register_tool(
            name=name,
            toolset="cdaily",
            schema={
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
            handler=handler,
            description=description,
        )
