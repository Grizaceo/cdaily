# SPEC.md — CDaily

## 1. Concept & Vision

CDaily es un feed reader personal minimalista: una ventana que dejas abierta mientras trabajas y hojeas durante breaks. No pretende ser un reader completo tipo Feedly — es un diario personalizado con categorías generales que reflejan intereses amplios (news, tech, science, business, culture, security) y un algoritmo de priorización que aprende de tu feedback.

La experiencia se siente como un mural de noticias — cartas con título corto, origen, categoría con emoji, snippet legible — diseñado para hojear en 30 segundos. No hay scroll infinito ni noticias de hace 3 días (a menos que no las hayas abierto).

**Filosofía:** El feed eres tú. El algoritmo ajusta fuentes según tu feedback. No necesita ML para 20 fuentes.

---

## 2. Design Language

### Aesthetic Direction
Inspiración: Notion meets Hacker News — limpio, denso-en-información, sin ruido visual. Dark mode por defecto. Tarjetas blancas sobre fondo gris oscuro, acentos de color por categoría.

### Color Palette
```
--bg-primary:      #0f1117   (fondo ventana)
--bg-card:         #1a1d27   (tarjeta)
--bg-card-hover:   #232736   (tarjeta hover)
--border:          #2d3348   (borde sutil)
--text-primary:    #e8eaf0   (título)
--text-secondary:  #8b90a0   (meta: blog, fecha)
--text-muted:      #555a70   (snippet)
--accent-politica: #f59e0b   (🏛️ amarillo)
--accent-intl:     #3b82f6   (🌎 azul)
--accent-ciencia:  #10b981   (🔬 verde)
--accent-economia: #8b5cf6   (💰 violeta)
--accent-humor:    #ef4444   (😂 rojo)
--accent-cyber:   #06b6d4   (🔐 cyan)
```

### Typography
- **Headlines:** Inter (Google Fonts), 500 weight, 15px
- **Meta/blog:** JetBrains Mono, 12px, muted
- **Snippet:** Inter, 400, 13px
- **Monospace fallback:** `ui-monospace, monospace`

### Spatial System
- Tarjeta: padding 14px 16px, gap 8px entre tarjetas
- Columnas: masonry/grid responsive (3 cols desktop, 2 tablet, 1 mobile)
- Sin margen gigante — maximiza densidad de información
- Scroll suave, cards con hover transition 150ms

### Motion Philosophy
- Transición hover en tarjetas: `transform: translateY(-1px)`, `box-shadow` sutil
- No animaciones de entrada — las cartas aparecen, punto
- Filtros con `opacity` transition 100ms
- Loading skeleton en vez de spinner

### Visual Assets
- Sin imágenes de artículos (no tiene sentido en un feed denso)
- Emoji de categoría como único "ícono" — visible, no decorativo
- Filtros pill-style con colores de categoría

---

## 3. Layout & Structure

```
┌─────────────────────────────────────────────────────┐
│  CDaily 🌿  [search]  [mark all read]  [refresh ↻] │
├─────────────────────────────────────────────────────┤
│  [All] [📰News] [💻Tech] [🔬Sci] [💼Biz] [🎭Cult] [🔐Sec] │
├─────────────────────────────────────────────────────┤
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ Title here  │ │ Title here  │ │ Title here  │   │
│  │ blog • date │ │ blog • date │ │ blog • date │   │
│  │ snippet...  │ │ snippet...  │ │ snippet...  │   │
│  └─────────────┘ └─────────────┘ └─────────────┘   │
│  ...                                                │
├─────────────────────────────────────────────────────┤
│  42 unread · Last scan: 09:14 · blogwatcher-cli    │
└─────────────────────────────────────────────────────┘
```

### Responsive Strategy
- **Desktop (>1200px):** 3 columnas masonry
- **Tablet (768-1200px):** 2 columnas
- **Mobile (<768px):** 1 columna, filtros horizontales scrolleables
- Sidebar de filtros colapsable en mobile

### Structure Notes
- Header sticky, contenido scrolleable
- Sin footer — mínimo
- Filtros son pill buttons, estado activo con color de categoría
- Footer minimal: contador unread + última vez scan + "powered by blogwatcher-cli"

---

## 4. Features & Interactions

### Core Features

#### F1: Feed principal (grid de tarjetas)
- Muestra artículos unread, ordenados por fecha (más nuevo primero)
- Tarjeta = título clickeable → abre URL en nueva pestaña
- Tarjeta = marca como leída (click en X o "mark read" hover)
- Hover muestra snippet completo (corte 200 chars)
- Tarjeta ya leída se atenúa (opacity 0.5) pero no desaparece

#### F2: Sistema de filtros por categoría
- Pills: All | 📰 News | 💻 Tech | 🔬 Science | 💼 Business | 🎭 Culture | 🔐 Security
- Click pill = filtra solo esa categoría
- Múltiples categorías: NO (filtro único activo)
- Persistencia del filtro en URL query param (`?cat=news`)
- Contador de unread al lado de cada filtro

#### F3: Búsqueda por texto
- Input en header, busca en título + snippet
- Debounce 300ms
- Resalta matches en amarillo
- Vacío = vuelve al feed normal

#### F4: Mark read / mark unread
- Click en X de tarjeta = mark read
- Hover en tarjeta = muestra "mark read" button
- "Mark all read" en header = marca todos como leídos con confirmación
- Mark unread = click en artículo ya leído lo revive

#### F5: Auto-refresh (cronjob)
- `blogwatcher-cli scan` se corre vía cron cada 30 minutos
- La UI auto-refresca cada 60 segundos (polling simple)
- Botón manual "↻" fuerza re-scan + re-fetch de artículos
- Indicador visual: "Scanning..." mientras fetch

#### F6: Marcar artículos como "para leer después"
- Botón "★" en hover → guarda en lista "Para Leer"
- Tab separado "Para Leer" con artículos starred
- Persiste en SQLite local (tabla propia)

### Edge Cases
- **0 artículos unread:** Mensaje "Todo al día 🌿 — 0 nuevos artículos" + time of last scan
- **Feed vacío en categoría:** "No hay artículos en [categoría] — prueba otra"
- **Error de scan:** Toast notification "Error en scan: [mensaje]" + sigue mostrando artículos anteriores
- **Artículo sin título:** Muestra URL truncada como título
- **Artículo sin fecha:** Muestra "fecha desconocida"

---

## 5. Component Inventory

### Card (Tarjeta de artículo)
```
States:
  default:   bg-card, título blanco, meta gris
  hover:     bg-card-hover, translateY(-1px), shadow sutil
  read:      opacity 0.5, título gris
  starred:   borde izquierdo con --accent-economia
  filtered:  se oculta con opacity 0
```

### Filter Pill (Pill de categoría)
```
States:
  inactive:  border --border, bg transparent
  active:    bg category-accent, text white
  hover:     bg category-accent/20
```

### Search Input
```
States:
  empty:     placeholder "Buscar artículos..."
  focused:   border --accent-ciencia
  has-value: texto blanco, X para limpiar
```

### Header Bar
```
Fixed top, bg --bg-primary, border-bottom --border
Contiene: logo "CDaily 🌿", search, mark-all-read btn, refresh btn
Height: 52px
```

### Footer Status Bar
```
Fixed bottom, bg --bg-primary, border-top --border
Contiene: "X unread · Last scan: HH:MM · blogwatcher-cli"
Height: 32px, text --text-muted
```

### Toast Notification
```
Aparece top-right, bg --accent-ciencia, white text
Auto-dismiss 4s, manual dismiss con X
```

---

## 6. Technical Approach

### Stack
- **Backend:** Python 3.11+, FastAPI
- **Frontend:** Vanilla JS + CSS (sin framework — overkill para esto)
- **Database:** SQLite — compartida con blogwatcher-cli (`~/.blogwatcher-cli/blogwatcher-cli.db`)
- **Server:** Uvicorn, serve en `http://localhost:7890`
- **Styling:** CSS custom properties, no framework CSS

### Arquitectura de datos

#### Tablas del schema existente (blogwatcher-cli)
```
blogs:      id, name, url, feed_url, selector, created_at, last_scanned
articles:   id, blog_id, title, url, content, summary, author,
            published_at, guid, is_read, is_starred, created_at
categories: id, article_id, name
```

#### Nuevas tablas CDaily (extensión local)
```sql
CREATE TABLE cdaily_starred (
    id INTEGER PRIMARY KEY,
    article_id INTEGER REFERENCES articles(id),
    starred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(article_id)
);

CREATE TABLE cdaily_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Renderiza página principal |
| GET | `/api/articles` | Lista artículos (filtros: `?cat=&q=&unread=1`) |
| POST | `/api/articles/{id}/read` | Marca como leído |
| POST | `/api/articles/{id}/unread` | Marca como no leído |
| POST | `/api/articles/{id}/star` | Toggle star |
| POST | `/api/articles/read-all` | Marca todos como leídos |
| POST | `/api/scan` | Fuerza blogwatcher-cli scan |
| GET | `/api/stats` | `{unread_total, by_category}` |

### Data Flow
```
blogwatcher-cli (cron) → SQLite (blogwatcher)
                         ↓
                    FastAPI (lee SQLite)
                         ↓
                    Templates (renderizan)
```

CDaily NO escribe en las tablas de blogwatcher — solo lee. Propio estado en `cdaily_starred`.

### Cronjob
```
*/30 * * * *  ~/.local/bin/blogwatcher-cli scan >> ~/.blogwatcher-cli/scan.log 2>&1
```

### Archivo de configuración
```yaml
# ~/.config/cdaily/config.yaml
host: "0.0.0.0"
port: 7890
db_path: "~/.blogwatcher-cli/blogwatcher-cli.db"
scan_interval_minutes: 30
refresh_interval_seconds: 60
log_level: "INFO"
```

### Decisiones de implementación (ya tomadas)
- **Vanilla JS sin framework** — overkill para la complejidad real
- **SQLite compartida** — no duplicar datos, solo leer
- **No auth** — es local, uso personal
- **No cache Redis/memcached** — overkill para escala personal
- **CSS puro con custom properties** — rápido de mantener
- **Templates con Jinja2** — ya viene con FastAPI
- **Categorías desde blogwatcher** — mapeo blog→categoría en config

---

## 7. Mapeo de blogs → categorías

| Blog | Categoría | Emoji |
|------|-----------|-------|
| CIPER Chile | news | 📰 |
| BioBioChile | news | 📰 |
| Cambio21 | news | 📰 |
| El Clarin | news | 📰 |
| The Clinic | culture | 🎭 |
| BBC Mundo | news | 📰 |
| The Guardian Mundo | news | 📰 |
| Ars Technica | tech | 💻 |
| Science Daily | science | 🔬 |
| Diario Financiero | business | 💼 |
| The Onion | culture | 🎭 |
| CyberScoop | security | 🔐 |
| Dark Reading | security | 🔐 |
| Help Net Security | security | 🔐 |
| Infosecurity Magazine | security | 🔐 |
| Krebs on Security | security | 🔐 |
| MIT Tech Review AI | tech | 💻 |
| SANS ISC | security | 🔐 |
| Schneier on Security | security | 🔐 |
| Talos Intelligence | security | 🔐 |
| The Hacker News | security | 🔐 |
| The Verge AI | tech | 💻 |
| Unit 42 Palo Alto | security | 🔐 |
| We Live Security | security | 🔐 |

---

## 8. Non-Goals (no implementar)

- Login/auth
- OPML import desde la UI
- Notas personales en artículos
- Extensión de navegador
- Push notifications
- Historial de lectura
- Múltiples usuarios
- API pública
- Despliegue en producción (localhost only)

---

## 9. Definition of Done para Handoff

El repo está listo para implementación cuando:
- [ ] `README.md` con setup completo y commands
- [ ] `app/main.py` con FastAPI skeleton y todos los endpoints definidos
- [ ] `app/database.py` con conexión a SQLite y queries
- [ ] `app/templates/index.html` con estructura HTML semántica
- [ ] `app/static/css/style.css` con todas las variables CSS
- [ ] `app/static/js/app.js` con toda la lógica frontend
- [ ] `config.yaml` con configuración
- [ ] `scripts/scan.sh` script de cron
- [ ] `requirements.txt` con dependencias
- [ ] Tests básicos en `tests/`
- [ ] Todo código autocontenido — ningún misterio para otro agente
