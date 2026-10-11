#!/usr/bin/python
"""Fetch bounded public thumbnails outside Quickshell's TLS process.

Input: JSON array as one argv element. Output: URL -> local file URL (or "").
No shell, credentials, persistent daemon or CDaily database writes.
"""
import concurrent.futures
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
import urllib.parse
import urllib.request

MAX_BYTES = 4 * 1024 * 1024
MAX_URLS = 40
TIMEOUT = 8
SUCCESS_TTL = 86400
FAILURE_TTL = 900
CACHE_BUDGET = 128 * 1024 * 1024


def is_public_url(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            return False
        if parsed.username or parsed.password or parsed.port not in (None, 80, 443):
            return False
        host = parsed.hostname.lower().rstrip('.')
        if host == 'localhost' or host.endswith(('.localhost', '.local')):
            return False
        addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        return bool(addresses) and all(ipaddress.ip_address(a[4][0]).is_global for a in addresses)
    except (ValueError, OSError):
        return False


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_public_url(newurl):
            raise ValueError('non-public image redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def is_image(data):
    return (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff')
            or data.startswith((b'GIF87a', b'GIF89a'))
            or (data.startswith(b'RIFF') and data[8:12] == b'WEBP')
            or (len(data) >= 16 and data[4:8] == b'ftyp' and data[8:12] in (b'avif', b'avis')))


def cache_key(url):
    return hashlib.sha256(url.encode()).hexdigest() + '.img'


def download(url):
    if not is_public_url(url):
        raise ValueError('non-public image URL')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), PublicRedirect())
    req = urllib.request.Request(url, headers={'User-Agent': 'CDaily-thumbnail/1.1', 'Accept': 'image/*'})
    started = time.monotonic()
    with opener.open(req, timeout=TIMEOUT) as response:
        length = response.headers.get('Content-Length')
        if length and int(length) > MAX_BYTES:
            raise ValueError('image too large')
        chunks = []
        total = 0
        while True:
            if time.monotonic() - started > TIMEOUT * 2:
                raise TimeoutError('image time budget exceeded')
            chunk = response.read(min(65536, MAX_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_BYTES:
                raise ValueError('image too large')
        data = b''.join(chunks)
        if not is_image(data):
            raise ValueError('unsupported image format')
        return data


def get_thumbnail(url, root):
    target = root / cache_key(url)
    failed = target.with_suffix('.failed')
    now = time.time()
    try:
        if target.exists() and now - target.stat().st_mtime < SUCCESS_TTL:
            return target.as_uri()
        if failed.exists() and now - failed.stat().st_mtime < FAILURE_TTL:
            return ''
        data = download(url)
        with tempfile.NamedTemporaryFile(dir=root, prefix='.download-', delete=False) as f:
            temporary = Path(f.name)
            f.write(data)
        try:
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        failed.unlink(missing_ok=True)
        return target.as_uri()
    except (OSError, ValueError, TimeoutError):
        failed.touch()
        return ''


def prune(root):
    files = list(root.glob('*.img'))
    total = sum(p.stat().st_size for p in files)
    for p in sorted(files, key=lambda p: p.stat().st_mtime):
        stat = p.stat()
        if total <= CACHE_BUDGET and time.time() - stat.st_mtime < SUCCESS_TTL * 7:
            continue
        total -= stat.st_size
        p.unlink(missing_ok=True)
    for p in root.glob('*.failed'):
        if time.time() - p.stat().st_mtime > SUCCESS_TTL:
            p.unlink(missing_ok=True)


def main():
    urls = json.loads(sys.argv[1])
    if not isinstance(urls, list):
        raise ValueError('expected URL array')
    urls = list(dict.fromkeys(u for u in urls if isinstance(u, str) and len(u) < 8192))[:MAX_URLS]
    root = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'cdaily-thumbnails'
    root.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        paths = list(pool.map(lambda u: get_thumbnail(u, root), urls))
    prune(root)
    print(json.dumps(dict(zip(urls, paths))))


if __name__ == '__main__':
    main()
