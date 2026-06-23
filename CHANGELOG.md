# Changelog

## Unreleased

## [0.1.1.0] - 2026-05-23

### Fixed
- **CI post-rename**: workflow references updated from `app` to `cdaily` package.
- **Stale docstring**: `cdaily/database.py` now correctly references `cdaily.repositories`.

### Changed
- **MCP test coverage**: expanded from 2/13 to 11/13 tools tested end-to-end. Remaining 4 require external services (blogwatcher-cli, AI endpoint) and are documented skips.

### RepoCiv integration
- **Kiosk rest area**: clicking the kiosk tile now auto-discovers a rest area with 1.25× recovery bonus, closing the gap between visual placement and bridge logic.

## [0.1.0.0] - 2026-05-18

First public open-source release.

### Public release cleanup
- **Black formatting**: Applied to 4 files (validate_url, routes/system, routes/articles, main.py).
- **CI fix**: Changed CI trigger from `main` to `master` branch.
- **Tests rewritten**: Now fully self-contained with in-memory SQLite fixtures (no blogwatcher-cli DB dependency).
- **Personal references removed**: Neutralized "Cristóbal", "DAVI", "/home/gris/" across README, SPEC, QUICK_REFERENCE, app/__init__.py, and app/main.py. Only LICENSE retains copyright.
- **Flake8 compliance**: Fixed line-length issues in tests, 0 errors.

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
