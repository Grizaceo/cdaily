# CDaily para Hermes

Plugin nativo de herramientas para Hermes Agent, complementario al widget de
Omarchy y al servidor MCP. Solo usa la biblioteca estándar de Python: no instala
FastAPI, MCP ni dependencias de CDaily dentro del entorno de Hermes.

Usa el contrato público [`plugin.yaml` + `register(ctx)` de Hermes](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins).

## Diseño y alcance

```text
Widget Omarchy ─┐
Web CDaily ─────┼── API FastAPI existente ── servicios/repositorios ── SQLite compartido
Plugin Hermes ─┘
MCP stdio ──────────────────────────────── servicios/repositorios ── SQLite compartido
```

1. Mantener el backend y widget actuales como fuente del estado compartido.
2. Añadir este adaptador HTTP independiente, con herramientas prefijadas `cdaily_`
   para evitar colisiones con MCP u otros plugins.
3. Validar el registro con Plugin Doctor y las operaciones contra la API real con
   SQLite temporal. No escanear ni modificar la base personal durante las pruebas.

El plugin requiere que el backend esté encendido. No arranca procesos, no cambia
configuración de Omarchy, no accede al SQLite directamente y no programa scans.
El MCP existente sigue siendo la alternativa para usar CDaily sin servidor HTTP.
No incluye una vista de Hermes Desktop: esta versión añade herramientas para el
agente, disponibles en sus interfaces habituales.

## Instalar desde este checkout

Con Hermes Agent que soporte `plugin.yaml` y `register(ctx)`, desde la raíz de CDaily:

```bash
# Validación aislada: no habilita ni instala el plugin.
hermes plugins doctor integrations/hermes/cdaily --ci

# Copiar al perfil Hermes en el que se quiere usar.
# Si ya existe, revisar/respaldar esa copia antes de actualizar sus dos archivos.
mkdir -p "${HERMES_HOME:-$HOME/.hermes}/plugins/cdaily"
cp integrations/hermes/cdaily/__init__.py integrations/hermes/cdaily/plugin.yaml \
  "${HERMES_HOME:-$HOME/.hermes}/plugins/cdaily/"
hermes plugins enable cdaily
hermes plugins list
```

Abre una sesión nueva de Hermes después de habilitarlo. Conserva el backend que
ya usa el widget; para levantarlo manualmente se puede usar `python -m cdaily.main`
en el entorno Python de CDaily. El puerto predeterminado es `7890`.

También puede instalarse directamente desde GitHub:

```bash
hermes plugins install Grizaceo/cdaily/integrations/hermes/cdaily
```

Para instalaciones reproducibles, añade `--ref <SHA completo>`.

## Configuración

No necesita configuración para `http://127.0.0.1:7890`. Para cambiarlo, combina
estos campos con tu configuración de Hermes existente, sin reemplazar las otras
entradas ni la lista de plugins habilitados:

```yaml
plugins:
  enabled:
    - cdaily
  entries:
    cdaily:
      settings:
        api_url: http://127.0.0.1:7890
        timeout: 15
        slow_timeout: 180
```

`api_url` prevalece sobre `CDAILY_URL` del entorno; los timeouts se expresan en
segundos (1–600). En perfiles de Hermes, instala y configura el plugin en el
perfil que vaya a usarlo.

Si el backend usa `CDAILY_API_TOKEN`, proporciona el mismo valor en el entorno del
proceso Hermes. El plugin lo envía como `Authorization: Bearer …`; no lo guardes en
el manifiesto. No sigue redirecciones ni usa proxies del entorno. Para conexiones
remotas usa una URL HTTPS. El servidor continúa aplicando su autenticación,
validación de URLs y límites de peticiones habituales.

## Herramientas

| Herramienta (prefijo `cdaily_`) | Uso |
| --- | --- |
| `feed_read` | Leer, buscar por texto/categoría, favoritos, paginar; `verbose=true` incluye resumen cacheado |
| `feed_digest` | Briefing por categoría, blog o plano; total real y muestra de hasta 200 artículos |
| `feed_stats` | Conteos exactos de no leídos |
| `article_mark_apply` | Estados `read`, `unread` o `toggle_star` |
| `article_rate_apply` | Puntuar 1–5 o `null` para borrar |
| `article_summarize_apply` | Generar/cachear resumen con la IA configurada en CDaily |
| `article_translate_apply` | Traducir con la IA configurada en CDaily (sin caché) |
| `feed_clear_apply` | Marcar todo leído; requiere `confirm=true` |
| `feed_scan_apply` | Escanear fuentes con blogwatcher-cli |
| `sources_list` | Listar fuentes e identificadores |
| `sources_add_apply` | Añadir una fuente |
| `sources_remove_apply` | Quitar una fuente y sus artículos |

Ejemplos para pedirle a Hermes:

- «Muéstrame el digest de CDaily agrupado por categoría».
- «Busca noticias sobre Linux en CDaily y dame los enlaces».
- «Marca el artículo 42 como leído y ponle 5 estrellas de rating».
- «Genera el resumen del artículo 42».

Las operaciones `_apply` cambian el estado compartido; resúmenes y traducciones
pueden consumir la API de IA configurada. `toggle_star` alterna el favorito:
comprueba su estado antes de reintentar tras un timeout. Un scan que exceda el
timeout podría seguir ejecutándose en el backend. Las lecturas no marcan artículos
ni generan resúmenes. El digest no es una síntesis de IA: devuelve datos agrupados
para que Hermes redacte el briefing y muestra `truncated=true` si faltan artículos
fuera de la muestra. Conteo y muestra son dos consultas y pueden variar si otro
cliente modifica el feed entre ambas.

Para deshabilitarlo: `hermes plugins disable cdaily`. El widget y la web siguen
funcionando con el backend existente.

## Verificación

```bash
.venv/bin/python -m pytest tests/test_hermes_plugin.py -v
hermes plugins doctor integrations/hermes/cdaily --ci
/usr/bin/python -m unittest discover -s integrations/omarchy/cdaily/tests -v
```

Las pruebas del adaptador recorren las rutas FastAPI con SQLite temporal; scan,
IA y ejecución de blogwatcher-cli se sustituyen para no hacer llamadas externas.
El doctor prueba el loader y registro de la versión local de Hermes. Una sesión
con un modelo real y un backend personal constituye una verificación adicional.
