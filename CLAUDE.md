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
# http://127.0.0.1:7890
```

Config: tracked `config.yaml` holds public defaults only. Personal settings go in `config.local.yaml` (gitignored) via `CDAILY_CONFIG`; the settings UI writes to that file. Secrets only via env vars (`CDAILY_AI_API_KEY`, `CDAILY_API_TOKEN`), never committed. Never put real hostnames, IPs, local paths or personal names in tracked files.

### Acceso desde otro equipo (p. ej. navegador en Windows con WSL2)

`localhost` del host no es alcanzable desde otra máquina. Usa la IP Tailscale del host (`tailscale ip -4`) y, en `config.local.yaml`, un `host` que escuche en esa interfaz. Fuera de loopback cualquiera en esa red puede usar la API: la UI web no envía `CDAILY_API_TOKEN`, así que ese token solo sirve para clientes de API.

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
