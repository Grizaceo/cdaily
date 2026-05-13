# Changelog

## Unreleased

### Security — Phase A (Containment)
- **SSRF guard**: New `validate_url()` rejects non-http/https URLs, private IPs
  (10.x, 192.168.x), loopback (localhost, 127.0.0.1), and internal domains
  (.local, .internal, .lan). Applies to article fetch, AI endpoint, and image
  fetching.
- **CSS injection fix**: `safeCssImageUrl()` in app.js validates image URLs are
  http/https only, escaping quotes and parentheses before injecting into
  `background-image`.
- **Host lockdown**: Changed default bind from `0.0.0.0` to `127.0.0.1` in both
  `config.yaml` and `main.py`. Explicit config override needed to expose.
- **CSP header**: Added Content-Security-Policy on all HTML responses, restricting
  scripts, styles, fonts, and images to trusted origins.
- **CSRF guard**: Middleware validates Origin/Referer on all POST/PUT/DELETE
  requests. Only localhost, 127.0.0.1, and host.docker.internal allowed.

### Security — Phase B (Hardening)
- **Asymmetric timeouts**: Article fetch 10s, AI endpoint 30s, batch images 8s,
  scan subprocess 120s.
- **Rate limiting**: Added slowapi — per-IP limits on mutation endpoints
  (5-60/min depending on cost).
- **Sanitized logging**: AI error responses no longer log full response bodies
  (only status code + content length).

### Documentation
- Standardized public defaults to generic blog categories.
- Added README screenshot and MIT license.
- Hardened config loading with environment-variable overrides.
- Documented current OpenAI-compatible AI endpoint examples.
- Added CHANGELOG.

### Dependencies
- Added `slowapi>=0.1.9` for rate limiting.
