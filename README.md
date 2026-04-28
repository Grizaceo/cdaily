# CDaily — Cristóbal's Daily Feed

Feed reader minimalista para hojear mientras trabajas. Lee directo del SQLite de blogwatcher-cli — sin duplicar datos.

## Setup

### Prerrequisitos
- Python 3.11+
- blogwatcher-cli instalado (`~/.local/bin/blogwatcher-cli`)
- blogwatcher-cli.db en `~/.blogwatcher-cli/` con blogs configurados

### Instalación

```bash
cd ~/.hermes/workspace/repos/cdaily
pip install -r requirements.txt
python -m app.main
# Abre http://localhost:7890
```

## Configuración

Edita `config.yaml`:

```yaml
host: "0.0.0.0"
port: 7890
db_path: "~/.blogwatcher-cli/blogwatcher-cli.db"
scan_interval_minutes: 30
refresh_interval_seconds: 60
log_level: "INFO"
```

## Cronjob (auto-scan cada 30 min)

```bash
# Abre crontab
crontab -e

# Agrega esta línea:
*/30 * * * *  ~/.local/bin/blogwatcher-cli scan >> ~/.blogwatcher-cli/scan.log 2>&1
```

## Uso

1. `blogwatcher-cli scan` para poblar la base (ya tienes datos de la sesión de setup)
2. `python -m app.main` para arrancar el server
3. Abre http://localhost:7890
4. Mantén la ventana abierta mientras trabajas

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
