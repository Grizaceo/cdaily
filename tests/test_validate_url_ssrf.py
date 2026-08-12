"""SSRF hardening tests for cdaily.validate_url and redirect re-validation.

Covers findings S1 (cloud metadata / link-local), S2 (Docker/CGNAT/IPv6
reserved ranges + DNS-resolution check) and S3 (re-validate every redirect hop
in article_summary._fetch_article_text).

These tests intentionally avoid live network calls. Internal/loopback hosts are
rejected at layer 1 (string host) before any DNS; for the DNS-resolution path we
monkeypatch socket.getaddrinfo to return attacker-controlled IPs so we exercise
the effective-IP check without touching the network.
"""

from __future__ import annotations

import asyncio
import socket
from unittest.mock import patch

import httpx
import pytest

from cdaily.validate_url import validate_url
from cdaily.services.article_summary import _fetch_article_text


def _af_inet():
    return socket.AF_INET


def _af_inet6():
    return socket.AF_INET6


# --- Layer 1: literal/string hosts (no DNS needed) -------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",   # S1 cloud metadata
        "https://169.254.1.1/",                        # S1 link-local
        "http://172.16.0.5/",                          # S2 Docker
        "http://172.17.0.2/",                          # S2 Docker default bridge
        "http://172.31.255.255/",                      # S2 Docker upper
        "http://100.64.0.1/",                          # S2 CGNAT
        "http://100.127.255.254/",                     # S2 CGNAT upper
        "http://10.0.0.1/",                            # RFC1918
        "http://192.168.1.1/",                         # RFC1918
        "http://127.0.0.1/",                           # loopback
        "http://localhost/",                           # loopback host
        "http://[::1]/",                               # IPv6 loopback
        "http://[fe80::1]/",                           # S2 IPv6 link-local
        "http://[fc00::1]/",                           # S2 IPv6 ULA
        "http://[::ffff:127.0.0.1]/",                  # IPv4-mapped IPv6 -> loopback
        "http://[::ffff:169.254.169.254]/",            # IPv4-mapped IPv6 -> metadata
        "file:///etc/passwd",                          # wrong scheme
        "gopher://127.0.0.1:11211/",                   # wrong scheme
        "http://foo.local/",                           # blocked suffix
        "http://foo.internal/",                        # blocked suffix
    ],
)
def test_blocked_hosts_rejected(url):
    with pytest.raises(ValueError):
        validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/article",
        "http://example.com/",
        "https://news.ycombinator.com/",
        "https://arstechnica.com/rust",
    ],
)
def test_public_hosts_allowed(url):
    # Monkeypatch DNS so these resolve to a safe public IP; avoids flaky network.
    with patch("socket.getaddrinfo", return_value=[(_af_inet(), None, None, None, ("93.184.216.34", 0))]):
        validate_url(url)  # must not raise


# --- Layer 2: DNS resolution returns a blocked effective IP -----------------

# (getaddrinfo monkeypatch makes these deterministic and network-free)


def test_dns_rebinding_to_metadata_blocked():
    with patch(
        "socket.getaddrinfo",
        return_value=[(_af_inet(), None, None, None, ("169.254.169.254", 0))],
    ):
        with pytest.raises(ValueError):
            validate_url("http://innocent-looking.example.com/article")


def test_dns_rebinding_to_docker_blocked():
    with patch(
        "socket.getaddrinfo",
        return_value=[(_af_inet(), None, None, None, ("172.16.5.5", 0))],
    ):
        with pytest.raises(ValueError):
            validate_url("http://blog.example.com/post")


def test_dns_rebinding_to_cgnat_blocked():
    with patch(
        "socket.getaddrinfo",
        return_value=[(_af_inet(), None, None, None, ("100.64.0.1", 0))],
    ):
        with pytest.raises(ValueError):
            validate_url("http://cdn.example.com/x")


def test_dns_ipv6_linklocal_blocked():
    with patch(
        "socket.getaddrinfo",
        return_value=[(_af_inet6(), None, None, None, ("fe80::1", 0, 0, 0))],
    ):
        with pytest.raises(ValueError):
            validate_url("http://host.example.com/x")


def test_dns_ipv4_mapped_blocked():
    with patch(
        "socket.getaddrinfo",
        return_value=[(_af_inet6(), None, None, None, ("::ffff:192.168.1.5", 0, 0, 0))],
    ):
        with pytest.raises(ValueError):
            validate_url("http://host.example.com/x")


def test_dns_public_ip_allowed():
    with patch(
        "socket.getaddrinfo",
        return_value=[(_af_inet(), None, None, None, ("93.184.216.34", 0))],
    ):
        validate_url("http://host.example.com/x")  # must not raise


# --- allow_private preserves local AI endpoint (no DNS, no IP checks) -------

def test_allow_private_allows_localhost():
    # S2/S3 rule: local Ollama endpoint must keep working.
    validate_url("http://localhost:11434/v1/chat/completions", allow_private=True)
    validate_url("http://127.0.0.1:11434/v1/chat/completions", allow_private=True)
    validate_url("http://192.168.1.50:11434/v1/chat/completions", allow_private=True)


def test_allow_private_allows_internal_dns_host_without_resolution():
    # A hostname that would otherwise be unresolved/blocked must pass when
    # allow_private=True, because the AI endpoint comes from trusted config.
    validate_url("http://ollama.local:11434/v1/chat/completions", allow_private=True)


# --- S3: redirect re-validation in _fetch_article_text ---------------------


def _make_response(status_code, headers=None, text=""):
    """Build a minimal fake httpx.Response-like object."""

    class _Resp:
        def __init__(self, status_code, headers, text):
            self.status_code = status_code
            self.headers = headers or {}
            self.text = text
            self.is_redirect = 300 <= status_code < 400 and "location" in self.headers

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("status", request=None, response=None)

    return _Resp(status_code, headers or {}, text)


def test_fetch_rejects_redirect_to_internal_host():
    """A public URL that 302-redirects to 169.254.169.254 must be blocked (S3)."""
    redirect_resp = _make_response(302, {"location": "http://169.254.169.254/latest/meta-data/"})
    final_resp = _make_response(200, {}, "<html><body>secret</body></html>")

    captured = {}

    class FakeClient:
        def __init__(self, *a, **k):
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            self.calls += 1
            captured["url"] = url
            # First call -> redirect to metadata; second call would hit internal.
            if self.calls == 1:
                return redirect_resp
            return final_resp

    with patch("cdaily.services.article_summary.httpx.AsyncClient", FakeClient):
        with pytest.raises(RuntimeError):
            asyncio.run(_fetch_article_text("http://public.example.com/article", 1))
    # The fetch must NOT have followed the redirect to the internal host.
    assert captured.get("url") != "http://169.254.169.254/latest/meta-data/"


def test_fetch_follows_safe_redirect_chain():
    """Public -> another public redirect -> 200 is fetched and parsed (S3 happy path)."""
    r1 = _make_response(301, {"location": "https://news.example.com/real"})
    r2 = _make_response(200, {}, "<html><body><p>Hello world</p></body></html>")

    class FakeClient:
        def __init__(self, *a, **k):
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            self.calls += 1
            if self.calls == 1:
                return r1
            return r2

    with patch("cdaily.services.article_summary.httpx.AsyncClient", FakeClient):
        with patch(
            "socket.getaddrinfo",
            return_value=[(_af_inet(), None, None, None, ("93.184.216.34", 0))],
        ):
            content, _ = asyncio.run(_fetch_article_text("http://public.example.com/article", 1))
    assert "Hello world" in content


def test_fetch_redirect_loop_is_bounded():
    """Infinite redirect loop must terminate (no hang / no infinite fetch)."""
    loop_resp = _make_response(302, {"location": "http://public.example.com/article"})

    class FakeClient:
        def __init__(self, *a, **k):
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            self.calls += 1
            return loop_resp

    with patch("cdaily.services.article_summary.httpx.AsyncClient", FakeClient):
        with pytest.raises(RuntimeError):
            asyncio.run(_fetch_article_text("http://public.example.com/article", 1))
