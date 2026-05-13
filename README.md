# CDaily — Cristóbal's Daily Feed

Feed reader minimalista para hojear mientras trabajas. Lee directo del SQLite de blogwatcher-cli, sin duplicar datos.

## Qué hace

- Lista artículos desde la base de `blogwatcher-cli`
- Filtra por categoría y búsqueda de texto
- Marca leído / no leído
- Marca favoritos / para leer después
- Guarda ratings 1–5 para reordenar el feed
- Genera resúmenes IA bajo demanda
- Extrae y cachea imágenes OG cuando existen

## Requisitos

- Python 3.11+
- `blogwatcher-cli` instalado
- `blogwatcher-cli.db` en `~/.blogwatcher-cli/`
- SQLite con el schema requerido por blogwatcher-cli

## Quick start local

```bash
cd ~/.hermes/workspace/repos/cdaily
python -m pip install -r requirements.txt
python -m app.main
# abrir http://localhost:7890
```

## Configuración

El archivo tracked `config.yaml` solo contiene defaults seguros. Para overrides locales, usa variables de entorno o un archivo local ignorado por git.

Variables útiles:

- `CDAILY_CONFIG` — ruta a un YAML alternativo
- `CDAILY_DB_PATH` — override del path a la DB
- `CDAILY_AI_ENDPOINT` — endpoint OpenAI-compatible para resúmenes
- `CDAILY_AI_API_KEY` — API key opcional para el endpoint de IA

Ejemplo rápido:

```bash
export CDAILY_AI_ENDPOINT="http://localhost:12345/v1/chat/completions"
export CDAILY_AI_API_KEY="tu_key_si_aplica"
```

También puedes copiar `.env.example` a `.env` o `config.local.yaml.example` a `config.local.yaml` si prefieres overrides en YAML. `.env`, `.env.local` y `config.local.yaml` están ignorados por git.

## Docker

```bash
docker compose up --build
# App disponible en http://localhost:7890
```

Si usas Docker con un endpoint IA que vive en tu host, el `docker-compose.yml` ya deja `CDAILY_AI_ENDPOINT` apuntando a `host.docker.internal`.

## Desarrollo

### Lint y formato

```bash
python -m black app tests
python -m flake8 app tests
```

### Tests

```bash
pytest tests/ -v
```

## Arquitectura

- `app/main.py` — bootstrap mínimo de FastAPI
- `app/routes/` — capa HTTP
- `app/services/` — scraping, resúmenes, scan y caché de imágenes
- `app/repositories/` — acceso a SQLite y queries
- `app/database.py` — shim de compatibilidad para imports antiguos
- `app/static/` — JS y CSS del frontend
- `app/templates/` — HTML base

## Agregar o quitar blogs

```bash
# Agregar
blogwatcher-cli add "Nombre" https://example.com --feed-url https://example.com/feed.xml

# Quitar
blogwatcher-cli remove "Nombre" --yes
```

Los cambios se reflejan en CDaily al siguiente refresh automático o manual.

## Notas de publicación pública

- No hay secretos hardcodeados en el repo.
- Las credenciales de IA van por variables de entorno, nunca dentro de `config.yaml`.
- Archivos locales sensibles o personalizados se ignoran con `.gitignore`:
  - `.env`
  - `.env.local`
  - `config.local.yaml`
  - `.venv/`

## Troubleshooting

### La base de datos no existe

- Verifica que `~/.blogwatcher-cli/blogwatcher-cli.db` exista
- Revisa permisos: `ls -la ~/.blogwatcher-cli/blogwatcher-cli.db`

### Faltan columnas en articles

- Verifica el schema de blogwatcher-cli
- Revisa: `sqlite3 ~/.blogwatcher-cli/blogwatcher-cli.db ".schema articles"`

### El endpoint IA no responde

- Revisa `CDAILY_AI_ENDPOINT`
- Si usas Docker, asegúrate de que el endpoint sea alcanzable desde el contenedor

### El puerto ya está ocupado

- Revisa si algo usa el 7890: `lsof -i :7890`
- Cambia el puerto en `config.yaml` o en tu override local
