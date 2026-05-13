"""SSRF protection: validate URLs are safe http/https before fetching."""

from __future__ import annotations

from urllib.parse import urlparse

ALLOWED_SCHEMES = frozenset({"http", "https"})
# Block access to private/reserved IP ranges via scheme validation
# This is a first-pass filter — httpx still resolves DNS, but this
# catches file://, gopher://, data://, javascript://, etc.
BLOCKED_HOST_SUFFIXES = frozenset({
    ".local", ".internal", ".lan",
})


def validate_url(url: str) -> None:
    """Validate that `url` is safe to fetch.

    Raises ValueError with a descriptive message if the URL is unsafe.
    """
    if not url:
        raise ValueError("URL is empty")

    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"URL scheme '{parsed.scheme}' is not allowed (only http/https)")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")

    # Block obvious private/internal hosts
    lower_host = hostname.lower()
    if lower_host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise ValueError(f"URL points to localhost/loopback: {hostname}")

    if lower_host.startswith("10.") or lower_host.startswith("192.168."):
        raise ValueError(f"URL points to private IP range: {hostname}")

    # Block RFC 1918 / link-local via common suffixes
    for suffix in BLOCKED_HOST_SUFFIXES:
        if lower_host.endswith(suffix):
            raise ValueError(f"URL points to internal/reserved host: {hostname}")
