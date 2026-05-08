# CDaily — Cristóbal's Daily Feed

Feed reader minimalista para hojear mientras trabajas. Lee directo del SQLite de blogwatcher-cli — sin duplicar datos.

## Prerequisites

- Python 3.11+
- `blogwatcher-cli` installed (`~/.local/bin/blogwatcher-cli`)
- `blogwatcher-cli.db` in `~/.blogwatcher-cli/` with blogs configured
- SQLite3 with required schema (validated at startup)

## Installation

```bash
cd ~/.hermes/workspace/repos/cdaily
pip install -r requirements.txt
python -m app.main
# Open http://localhost:7890
```

## Configuration

Edit `config.yaml`:

```yaml
host: "0.0.0.0"
port: 7890
db_path: "~/.blogwatcher-cli/blogwatcher-cli.db"
scan_interval_minutes: 30
refresh_interval_seconds: 60
log_level: "INFO"

# Blog → Category Mapping (defaults provided if omitted)
blog_categories:
  "CIPER Chile": "politica"
  # ... more blogs

# Category → Emoji Mapping (defaults provided if omitted)
category_emoji:
  "politica": "🏛️"
  # ... more categories

# AI Summarization (Optional)
ai_preferences:
  enabled: true
  endpoint: "http://localhost:12345/v1/chat/completions"
  model: "qwen2.5-7b-instruct-1m"
  max_content_chars: 12000
  system_prompt: "..."
```

### Environment Variables

- `CDAILY_CONFIG`: Path to custom config.yaml (default: `./config.yaml`)
- `CDAILY_AI_ENDPOINT`: Override AI endpoint (optional)

## Automated Scanning with Cron

```bash
crontab -e

# Add this line for auto-scan every 30 min:
*/30 * * * *  ~/.local/bin/blogwatcher-cli scan >> ~/.blogwatcher-cli/scan.log 2>&1
```

## Usage

1. Run `blogwatcher-cli scan` to populate the database
2. Start the server: `python -m app.main`
3. Open http://localhost:7890
4. Use category filters, search, star articles, and add ratings
5. Click ✨ button to generate AI summaries for articles

## Docker

```bash
docker-compose up -d
# App available at http://localhost:7890
```

## Development

### Linting & Formatting

```bash
pip install black flake8
black app tests           # Auto-format
flake8 app tests         # Check linting
```

### Running Tests

```bash
pip install pytest
pytest tests/ -v
```

### CI/CD

GitHub Actions automatically runs lint and tests on push/PR to `main`.

## Troubleshooting

### "Database path does not exist"
- Ensure `config.yaml` `db_path` points to a valid blogwatcher-cli.db
- Check permissions: `ls -la ~/.blogwatcher-cli/blogwatcher-cli.db`

### "Articles table missing columns"
- Validate the blogwatcher-cli database schema
- Run: `sqlite3 ~/.blogwatcher-cli/blogwatcher-cli.db ".schema articles"`
- Should have columns: `id`, `title`, `url`, `published_date`, `is_read`, `blog_id`

### "AI summarization disabled"
- Set `ai_preferences.enabled: true` in config.yaml
- Ensure AI endpoint is reachable: `curl http://endpoint/v1/chat/completions`

### "Address already in use"
- Check if port 7890 is in use: `lsof -i :7890`
- Kill process or change port in config.yaml

### App crashes on startup
- Check logs for validation errors (missing config keys)
- Ensure `db_path` exists and is readable
- Verify blog_categories and category_emoji are not empty

## Architecture

### Backend (FastAPI)
- `/api/articles` — List articles with filtering
- `/api/articles/{id}/read` — Mark as read
- `/api/articles/{id}/summarize` — Generate AI summary
- `/api/stats` — Unread counts by category
- `/api/scan` — Force blogwatcher-cli scan

### Database
- Reads from: blogwatcher-cli tables (`articles`, `blogs`)
- Writes to: CDaily tables (`cdaily_starred`, `cdaily_summaries`, `cdaily_article_images`, `cdaily_article_ratings`)

### Frontend (Vanilla JS + CSS)
- Responsive masonry grid
- Dark mode with glassmorphism design
- Category filters with emoji badges
- Real-time search and refresh

## Features

- **Personalization**: Rate articles (1-5 stars) to reorder feed
- **AI Summaries**: On-demand OpenAI-compatible summarization
- **Star & Read**: Mark for later or dismiss
- **Search**: Real-time title search with highlighting
- **Auto-refresh**: Configurable background polling
- **Docker Ready**: docker-compose for easy deployment

## License

Personal project. Feel free to fork and customize.

## Agregar/quitar blogs

```bash
# Agregar
blogwatcher-cli add "Nombre" https://example.com --feed-url https://example.com/feed.xml

# Quitar
blogwatcher-cli remove "Nombre" --yes
```

Los cambios se reflejan en CDaily al siguiente refresh automático (60s) o manual (↻).

## Estructura

```
cdaily/
├── app/
│   ├── main.py          # FastAPI app + endpoints
│   ├── database.py      # Conexión SQLite + queries
│   ├── models.py        # Pydantic models
│   ├── config.py        # Carga config.yaml
│   ├── routes/
│   │   └── articles.py  # Endpoints de artículos
│   ├── static/
│   │   ├── css/style.css
│   │   └── js/app.js
│   └── templates/
│       └── index.html
├── scripts/
│   └── scan.sh          # Script de scan para cron
├── tests/
│   └── test_api.py
├── config.yaml
├── requirements.txt
├── SPEC.md
└── README.md
```

## API

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/` | Página principal |
| GET | `/api/articles` | Lista artículos (?cat=&q=&unread=1) |
| POST | `/api/articles/{id}/read` | Marca leído |
| POST | `/api/articles/{id}/unread` | Marca no leído |
| POST | `/api/articles/{id}/star` | Toggle star |
| POST | `/api/articles/read-all` | Marca todos leídos |
| POST | `/api/scan` | Fuerza blogwatcher-cli scan |
| GET | `/api/stats` | Contadores por categoría |

## Decisiones de diseño

- **Vanilla JS** — no framework, overkill para la complejidad real
- **SQLite compartida** — solo lee, no modifica schema de blogwatcher
- **Categorías via config** — mapeo blog→categoría fijo, no extrae del RSS
- **No auth** — localhost only, para Cristóbal
- **CDaily own state** — tabla `cdaily_starred` para features propias

## Créditos

- Motor de feed: [blogwatcher-cli](https://github.com/JulienTant/blogwatcher-cli)
- Tipografía: Inter + JetBrains Mono (Google Fonts)
