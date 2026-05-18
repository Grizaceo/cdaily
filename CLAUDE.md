# CDaily

Minimal personal feed reader: FastAPI backend, vanilla JS frontend, reads articles from **blogwatcher-cli** SQLite (`~/.blogwatcher-cli/blogwatcher-cli.db`). No duplicate data store.

## Stack

- Python 3.11+, FastAPI, Uvicorn, Jinja2, httpx, BeautifulSoup4, slowapi
- `app/routes/` — HTTP API
- `app/services/` — summaries, OG images, scan
- `app/repositories/` — SQLite access
- `app/static/`, `app/templates/` — UI

## Testing

```bash
pytest tests/ -v
python -m black app tests
python -m flake8 app tests
```

Tests use in-memory SQLite fixtures; no live blogwatcher-cli DB required.

## Local run

```bash
pip install -r requirements.txt
python -m app.main
# http://127.0.0.1:7890
```

Config: tracked `config.yaml` + env overrides (`CDAILY_*`). Secrets only via `.env` / env vars (never commit).

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
