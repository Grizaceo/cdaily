"""Resolve Google News redirect URLs to the original publisher article.

Google News wraps every RSS item in an opaque redirect
(``news.google.com/rss/articles/<id>``). Since mid-2024 the id is no longer a
plain base64 payload you can decode locally: the page serves an interstitial
and the real URL is only obtainable through Google's ``batchexecute`` RPC.

Flow (per article id):
  1. GET ``/rss/articles/<id>?hl&gl&ceid`` -> 200 HTML (``/articles`` and
     ``/read`` 302 to a "sorry" page for non-browser clients).
  2. Read ``data-n-a-sg`` (signature) and ``data-n-a-ts`` (timestamp) from that
     HTML. A regex fallback is used instead of a full HTML parser so this module
     carries no third-party dependency.
  3. POST the (id, timestamp, signature) triple to the ``batchexecute``
     endpoint. Google replies with the decoded publisher URL.

This is best-effort and network-dependent: Google may change the RPC again.
Callers must treat failure as non-fatal and keep the original URL.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import parse_qs, quote, urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

BATCHEXECUTE_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
RSS_ARTICLE_URL = "https://news.google.com/rss/articles/{id}"

_SG_RE = re.compile(r'data-n-a-sg="([^"]+)"')
_TS_RE = re.compile(r'data-n-a-ts="([^"]+)"')

# The garturlreq context blob Google's client sends. Values are stable across
# the RPC; only the article id / timestamp / signature slots matter to us.
_GARTURLREQ_CTX = [
    ["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
    "X",
    "X",
    1,
    [1, 1, 1],
    1,
    1,
    None,
    0,
    0,
    None,
    0,
]

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def is_google_news_url(url: str) -> bool:
    """True if the URL is a Google News redirect we know how to resolve."""
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.hostname != "news.google.com":
        return False
    parts = p.path.split("/")
    return len(parts) > 1 and parts[-2] in ("articles", "read") and bool(parts[-1])


def _article_id(source_url: str) -> str | None:
    try:
        p = urlparse(source_url)
        parts = p.path.split("/")
        if p.hostname == "news.google.com" and len(parts) > 1 and parts[-2] in ("articles", "read"):
            return parts[-1] or None
    except Exception:
        return None
    return None


def _params_page_url(art_id: str, source_url: str | None) -> str:
    hl, gl, ceid = "en-US", "US", "US:en"
    if source_url:
        qs = parse_qs(urlparse(source_url).query)
        if qs.get("hl"):
            hl = qs["hl"][0]
        if qs.get("gl"):
            gl = qs["gl"][0]
        if qs.get("ceid"):
            ceid = qs["ceid"][0]
    return (
        f"{RSS_ARTICLE_URL.format(id=art_id)}"
        f"?hl={quote(hl, safe='')}&gl={quote(gl, safe='')}&ceid={quote(ceid, safe='')}"
    )


def _next_google_hop(current: str, location: str | None) -> str | None:
    if not location:
        return None
    dest = urljoin(current, location)
    if urlparse(dest).hostname == "news.google.com":
        return dest
    return None


def _parse_signature(html: str) -> tuple[str, str] | None:
    sg = _SG_RE.search(html)
    ts = _TS_RE.search(html)
    if sg and ts:
        return sg.group(1), ts.group(1)
    return None


def _build_batchexecute_body(items: list[tuple[str, str, str]]) -> str:
    envelopes = []
    for req_id, art_id, ts, sig in items:
        inner = ["garturlreq", _GARTURLREQ_CTX, art_id, int(ts) if str(ts).isdigit() else ts, sig]
        envelopes.append(["Fbv4je", json.dumps(inner, separators=(",", ":")), None, str(req_id)])
    return f"f.req={quote(json.dumps([envelopes], separators=(',', ':')))}"


def _parse_batchexecute(text: str) -> list[tuple[str | None, str]]:
    body = text
    if "\n\n" in body:
        body = body.split("\n\n", 1)[1]
    body = body.lstrip()
    if body.startswith(")]}'"):
        body = body.split("\n", 1)[1] if "\n" in body else body[4:]
        body = body.lstrip()
    rows = json.loads(body)
    if rows and isinstance(rows[-1], list) and rows[-1] and rows[-1][0] == "di":
        rows = rows[:-1]
    if rows and isinstance(rows[-1], list) and rows[-1] and rows[-1][0] == "e":
        rows = rows[:-1]
    pairs: list[tuple[str | None, str]] = []
    for row in rows:
        if not (isinstance(row, list) and len(row) >= 3):
            continue
        payload = row[2]
        if row[0] == "wrb.fr" or row[1] == "Fbv4je":
            if isinstance(payload, str):
                payload = json.loads(payload)
            if isinstance(payload, list) and payload and payload[0] == "garturlres":
                req_id = None
                for cell in reversed(row[3:]):
                    if cell is not None:
                        req_id = str(cell)
                        break
                pairs.append((req_id, payload[1]))
    return pairs


async def resolve_google_news_url(
    client: httpx.AsyncClient, source_url: str
) -> str | None:
    """Resolve a single Google News URL to the publisher URL.

    Returns the decoded URL, or None on any failure (best-effort). Never raises.
    """
    art_id = _article_id(source_url)
    if not art_id:
        return None
    # 1. GET the article params page (follow only same-host redirects).
    current = _params_page_url(art_id, source_url)
    resp = None
    try:
        for _ in range(3):
            resp = await client.get(current, follow_redirects=False)
            if not resp.is_redirect:
                break
            nxt = _next_google_hop(current, resp.headers.get("location"))
            if nxt is None:
                return None
            current = nxt
        if resp is None or not resp.is_success:
            return None
        parsed = _parse_signature(resp.text)
        if not parsed:
            return None
        sig, ts = parsed
        # 2. POST batchexecute to get the decoded URL.
        body = _build_batchexecute_body([("0", art_id, ts, sig)])
        r = await client.post(
            BATCHEXECUTE_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            content=body,
        )
        r.raise_for_status()
        pairs = _parse_batchexecute(r.text)
        for _req_id, url in pairs:
            if url and urlparse(url).scheme in ("http", "https"):
                return url
    except (httpx.HTTPError, json.JSONDecodeError, IndexError, TypeError, KeyError, ValueError) as exc:
        logger.warning("Google News resolve failed for %s: %s", source_url[:60], exc)
        return None
    return None
