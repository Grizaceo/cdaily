"""World Monitor sync service — pulls global intelligence events into cdaily."""

from __future__ import annotations

import os
import time
import logging
from typing import Optional
from dataclasses import dataclass, asdict

import httpx

logger = logging.getLogger(__name__)

# ─── Config via env / config.yaml ──────────────────────────────────
WM_BASE = os.environ.get("WM_BASE", "http://localhost:3000")
WM_API_KEY = os.environ.get("WM_API_KEY", "")
WM_SYNC_INTERVAL = int(os.environ.get("WM_SYNC_INTERVAL", "300"))  # 5min default
WM_LIMIT = int(os.environ.get("WM_LIMIT", "50"))

# ─── Data Classes ───────────────────────────────────────────────────
@dataclass
class WMEvent:
    title: str
    summary: str
    url: str
    category: str          # cdaily category: news, security, tech, business, culture, science
    severity: str          # LOW, MEDIUM, HIGH, CRITICAL
    source: str
    published_at: int      # epoch ms
    location_name: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


# ─── Domain → cdaily category mapping ──────────────────────────────
DOMAIN_TO_CATEGORY = {
    "news": "news",
    "conflict": "security",
    "unrest": "news",
    "intelligence": "business",
    "aviation": "tech",
    "sanctions": "business",
    "military": "security",
    "cyber": "security",
    "seismology": "science",
    "natural": "science",
    "default": "news",
}

SEVERITY_MAP = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
    "unknown": "LOW",
}

# ─── Public endpoints (no auth required) ───────────────────────────
PUBLIC_ENDPOINTS: list[tuple[str, str]] = [
    # (domain, path)
    ("conflict", "/api/conflict/v1/list-acled-events"),
    ("unrest", "/api/unrest/v1/list-unrest-events"),
    ("natural", "/api/natural/v1/list-natural-events"),
    ("seismology", "/api/seismology/v1/list-earthquakes"),
]


def _map_severity(sev: str) -> str:
    return SEVERITY_MAP.get(sev.lower(), "LOW")


def _map_threat_to_category(threat: dict) -> str:
    if not threat:
        return "news"
    cat = (threat.get("category") or "").lower()
    if "cyber" in cat or "military" in cat or "conflict" in cat:
        return "security"
    if "aviation" in cat:
        return "tech"
    if "finance" in cat or "market" in cat:
        return "business"
    return "news"


def _headers() -> dict[str, str]:
    h = {"Accept": "application/json"}
    if WM_API_KEY:
        h["X-WorldMonitor-Key"] = WM_API_KEY
    return h


def fetch_events(domain: str, path: str, limit: int = WM_LIMIT) -> list[WMEvent]:
    """Fetch events from a single World Monitor public endpoint."""
    url = f"{WM_BASE.rstrip('/')}{path}"
    params = {"limit": str(limit)}
    try:
        r = httpx.get(url, params=params, headers=_headers(), timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.warning("wm_fetch %s failed: %s", domain, e)
        return []

    events: list[WMEvent] = []
    category = DOMAIN_TO_CATEGORY.get(domain, "news")

    # Response shapes vary by domain
    raw_events = data.get("events") or data.get("earthquakes") or data.get("items") or []
    if not isinstance(raw_events, list):
        raw_events = [raw_events]

    for item in raw_events:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("name") or item.get("event_text") or "Untitled"
        summary = item.get("summary") or item.get("description") or item.get("notes") or ""
        event_url = item.get("url") or item.get("link") or ""
        severity = _map_severity(item.get("severity") or item.get("magnitude") or "unknown")
        source = item.get("source") or domain

        # Timestamp: try multiple fields
        ts = item.get("published_at") or item.get("timestamp") or item.get("time") or 0
        if isinstance(ts, str):
            try:
                from datetime import datetime
                ts = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
            except Exception:
                ts = 0

        location_name = item.get("location") or item.get("place") or item.get("country")
        lat = item.get("lat") or item.get("latitude")
        lng = item.get("lng") or item.get("lon") or item.get("longitude")
        if lat is not None:
            try:
                lat = float(lat)
            except (TypeError, ValueError):
                lat = None
        if lng is not None:
            try:
                lng = float(lng)
            except (TypeError, ValueError):
                lng = None

        events.append(WMEvent(
            title=str(title),
            summary=str(summary)[:500],
            url=str(event_url),
            category=category,
            severity=severity,
            source=str(source),
            published_at=int(ts) if ts else 0,
            location_name=str(location_name) if location_name else None,
            lat=lat,
            lng=lng,
        ))

    logger.info("wm_fetch %s: %d events", domain, len(events))
    return events


def fetch_all_events(limit: int = WM_LIMIT) -> list[WMEvent]:
    """Fetch events from all public endpoints, deduped by URL."""
    all_events: list[WMEvent] = []
    seen_urls: set[str] = set()

    for domain, path in PUBLIC_ENDPOINTS:
        events = fetch_events(domain, path, limit=limit)
        for ev in events:
            dedup_key = ev.url or f"{ev.title}:{ev.published_at}"
            if dedup_key not in seen_urls:
                seen_urls.add(dedup_key)
                all_events.append(ev)

    # Sort by published_at descending
    all_events.sort(key=lambda e: e.published_at, reverse=True)
    return all_events


# ─── Optional scheduler (for future loop integration) ──────────────
def sync_loop(stop_after: Optional[int] = None) -> None:
    """Run fetch_all_events in a loop. For use with a background task manager."""
    runs = 0
    while True:
        events = fetch_all_events()
        # TODO: persist to cdaily DB when worldmonitor article model is added
        logger.info("wm_sync: fetched %d events", len(events))
        runs += 1
        if stop_after and runs >= stop_after:
            break
        time.sleep(WM_SYNC_INTERVAL)
