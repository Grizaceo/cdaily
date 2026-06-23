# CDaily

Minimal personal feed reader: FastAPI backend, vanilla JS frontend, reads articles from **blogwatcher-cli** SQLite (`~/.blogwatcher-cli/blogwatcher-cli.db`). No duplicate data store.

## Stack

- Python 3.11+, FastAPI, Uvicorn, Jinja2, httpx, BeautifulSoup4, slowapi
- `cdaily/routes/` — HTTP API
- `cdaily/services/` — summaries, OG images, scan
- `cdaily/repositories/` — SQLite access
- `cdaily/static/`, `cdaily/templates/` — UI

## Testing

```bash
pytest tests/ -v
python -m black cdaily tests
python -m flake8 cdaily tests
```

Tests use in-memory SQLite fixtures; no live blogwatcher-cli DB required.

## Local run

```bash
pip install -r requirements.txt
python -m cdaily.main
# http://127.0.0.1:8000
```

Config: tracked `config.yaml` + env overrides (`CDAILY_*`). Secrets only via `.env` / env vars (never commit).

### WSL2 — acceso desde Windows

`localhost:8000` no funciona desde el navegador de Windows aunque el servidor responda.
Causa: Windows Firewall + portproxy bloquean HTTP. Tailscale enruta correctamente.

**URL real desde Windows:** `http://100.123.206.92:8000/` (IP Tailscale de WSL2)

La IP Tailscale es estable entre reinicios (a diferencia de la IP eth0 de WSL2 que cambia).
Si Tailscale no está activo, alternativa: `http://172.28.246.75:8000` (IP eth0, cambia en cada reinicio de WSL).

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool.

- Product ideas / brainstorming → `/office-hours`
- Strategy / scope → `/plan-ceo-review`
- Architecture → `/plan-eng-review`
- Design → `/plan-design-review`
- Bugs / errors → `/investigate`
- QA / site behavior → `/qa` or `/qa-only`
- Code review / diff → `/review`
- Ship / deploy / PR → `/ship` or `/land-and-deploy`
- Docs after ship → `/document-release`
- Save / resume context → `/context-save`, `/context-restore`
- Semantic code search → `/sync-gbrain` (requires gbrain setup via `/setup-gbrain`)

## Release

- Version file: `VERSION` (4-part semver for gstack)
- Changelog: `CHANGELOG.md`
- Default branch: `master`
- License: MIT
