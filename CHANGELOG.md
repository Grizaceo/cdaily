# Changelog

## Unreleased

### Added
- **Hermes Agent plugin** (`integrations/hermes/cdaily`): 12 standalone HTTP tools for feed briefings, search, curation, AI summaries/translation and source management, sharing the existing backend with the Omarchy widget. Includes isolated API tests and installation instructions.
- **Demo script**: `scripts/demo.sh` seeds a throwaway blogwatcher-cli DB with public feeds and runs CDaily on loopback, isolated from `~/.blogwatcher-cli` and the tracked `config.yaml`.
- **Google News resolver**: Google News redirect URLs are resolved to the publisher article before summarizing; anti-bot walls fail fast instead of being summarized.
- **Omarchy bar widget** (`integrations/omarchy/cdaily`): Quickshell panel with isolated thumbnail cache, mouse resize and per-monitor size persistence.
- **worldmonitor sync service** (`cdaily/services/worldmonitor_sync.py`).

### Fixed
- **Security (H1)**: `GET /api/settings` masks the API key; settings writes require `CDAILY_API_TOKEN` when it is set.
- **Security (H1 follow-up)**: the masked key is only honored for the stored endpoint, so `/api/settings` and `/api/settings/test` can no longer send the stored key to a caller-chosen host. A key supplied via `CDAILY_AI_API_KEY` is never written to `config.yaml`, and `/api/settings/test` redacts provider error bodies.
- **Security (host default)**: tracked `config.yaml` and `config.yaml.example` bind to `127.0.0.1` again (had regressed to `0.0.0.0` in 0.1.1.0).
- **Security (H2/S1-S3)**: AI provider error bodies are redacted; SSRF guard resolves DNS and re-validates every redirect hop when fetching articles.
- **AI summaries**: bounded retries on transport/5xx errors.
- **remove_blog**: deletes child rows in FK order; frontend infinite-scroll pagination polish.
- **CI**: black/flake8 clean again; network-marked tests are excluded in CI and skip when no local DB exists.

### Changed
- `mcp[cli]` pinned to `<2` in `requirements.txt`.
- **Personal data out of tracked files**: tracked `config.yaml` now holds public defaults only (port 7890, matching the README); keep your own settings in the gitignored `config.local.yaml` and point `CDAILY_CONFIG` at it. Local IPs, paths and names removed from docs and tests.
- **Omarchy widget id** is now `io.github.grizaceo.cdaily` (layer namespace `cdaily-panel`); update the id in `~/.config/omarchy/shell.json` when reinstalling.

## [0.1.2.0] - 2026-06-22

### Added
- **blogwatch_mcp_server**: alternative MCP entrypoint wrapping `blogwatcher-cli` subprocess directly. 9 tools (4 read + 5 mutating with `_apply` suffix). Useful when blogwatcher-cli is installed but cdaily DB schema doesn't match. Registered as `cdaily-blogwatch-mcp` console script.

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
- **Personal references removed**: Neutralized personal names and local paths across README, SPEC, QUICK_REFERENCE, app/__init__.py, and app/main.py. Only LICENSE retains copyright.
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
