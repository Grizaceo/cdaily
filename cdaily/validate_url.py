"""SSRF protection: validate URLs are safe http/https before fetching.

Two layers of defense:

1. Host-string filter (fast, cheap, catches literal IPs and obvious internal
   hostnames). This is the primary gate for endpoints supplied by the user
   (article URLs) and by config (AI endpoint, when allow_private is False).

2. Effective-IP resolution (when allow_private is False). We resolve the host
   with socket.getaddrinfo and reject any address that falls in a reserved /
   private / link-local / loopback range. This defeats DNS-rebinding and
   tricks where a public-looking hostname resolves to an internal address.

The AI endpoint relies on allow_private=True (so it can reach a local Ollama
on 127.0.0.1 / 192.168.x). That path skips BOTH layers intentionally.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = frozenset({"http", "https"})

# Obvious internal hostname suffixes (covers hostnames the user could supply
# that do not parse as IPs but clearly resolve internally).
BLOCKED_HOST_SUFFIXES = frozenset(
    {
        ".local",
        ".internal",
        ".lan",
        ".localhost",
        ".example",
        ".invalid",
    }
)


def _is_blocked_string_host(hostname: str, *, allow_private: bool) -> bool:
    """Layer 1: reject by host string alone. Returns True if blocked."""
    if allow_private:
        return False

    lower = hostname.lower()

    # Explicit loopback / unspecified hosts
    if lower in ("localhost", "localhost.localdomain", "::1", "0.0.0.0", "::"):
        return True

    # Common RFC1918 / private literal-IP prefixes (fast reject)
    if lower.startswith(("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.", "172.2", "172.30.", "172.31.")):
        return True

    # Link-local (169.254.x.x) and CGNAT (100.64.0.0/10) literal prefixes
    if lower.startswith("169.254.") or lower.startswith("100.6") or lower.startswith("100.7"):
        return True

    # Blocked suffixes
    for suffix in BLOCKED_HOST_SUFFIXES:
        if lower.endswith(suffix):
            return True

    return False


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if an ip_address() object is reserved/internal/link-local."""
    # Loopback / multicast / reserved / unspecified
    if ip.is_loopback or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return True

    # IPv4 / IPv4-in-IPv6 mapped blocks
    if ip.version == 4:
        if (
            ip in ipaddress.ip_network("10.0.0.0/8")
            or ip in ipaddress.ip_network("172.16.0.0/12")
            or ip in ipaddress.ip_network("192.168.0.0/16")
            or ip in ipaddress.ip_network("169.254.0.0/16")  # link-local / cloud metadata
            or ip in ipaddress.ip_network("100.64.0.0/10")  # CGNAT
            or ip in ipaddress.ip_network("127.0.0.0/8")
        ):
            return True
        return False

    # IPv6
    if ip.version == 6:
        # IPv4-mapped IPv6 (::ffff:0:0/96) — unwrap and re-check as IPv4
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            return _ip_is_blocked(ip.ipv4_mapped)
        if (
            ip in ipaddress.ip_network("fc00::/7")  # ULA
            or ip in ipaddress.ip_network("fe80::/10")  # link-local
            or ip in ipaddress.ip_network("::1/128")  # loopback (already caught above)
            or ip in ipaddress.ip_network("64:ff9b::/96")  # IPv4 NAT64
        ):
            return True
        return False

    return True


def _resolve_and_check(hostname: str) -> None:
    """Layer 2: resolve hostname and reject reserved/internal addresses."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        # If we can't resolve, we cannot prove it is safe -> block.
        # (Callers that must allow unknown hosts are expected to use
        #  allow_private=True, which never reaches this point.)
        raise ValueError(
            f"Could not resolve host '{hostname}' for SSRF validation: {exc}"
        ) from exc

    if not infos:
        raise ValueError(f"Host '{hostname}' resolved to no addresses.")

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            # Not a parseable IP — be conservative.
            raise ValueError(f"Host '{hostname}' resolved to an invalid address: {addr}")
        if _ip_is_blocked(ip):
            raise ValueError(
                f"URL host '{hostname}' resolves to a blocked/reserved address: {ip}"
            )


def validate_url(url: str, allow_private: bool = False) -> None:
    """Validate that `url` is safe to fetch.

    Raises ValueError with a descriptive message if the URL is unsafe.
    When allow_private is True (used for the local AI endpoint such as
    Ollama on 127.0.0.1), neither the host-string nor the DNS/IP checks
    run, preserving existing local-endpoint behavior.
    """
    if not url:
        raise ValueError("URL is empty")

    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"URL scheme '{parsed.scheme}' is not allowed (only http/https)")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")

    if allow_private:
        return

    # Layer 1: string-based rejection
    if _is_blocked_string_host(hostname, allow_private=allow_private):
        raise ValueError(f"URL points to a blocked host: {hostname}")

    # Layer 2: resolve and check effective IP(s) (anti DNS-rebinding)
    _resolve_and_check(hostname)
