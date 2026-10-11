# CDaily — widget de barra Omarchy

Fuente versionada del plugin de usuario instalado en
`~/.config/omarchy/plugins/cdaily/`. El backend debe estar disponible en
`http://127.0.0.1:8090` y el equipo debe disponer de Quickshell y `/usr/bin/python`.

## Instalación / actualización manual

Desde la raíz del repositorio, respalda primero el plugin existente y copia
únicamente estos archivos al directorio de usuario:

- `integrations/omarchy/cdaily/Widget.qml`
- `integrations/omarchy/cdaily/thumbnail_cache.py`
- `integrations/omarchy/cdaily/manifest.json`

Mantén la configuración de la barra que habilita `davi.cdaily`. No modificar
`/usr/share/omarchy/`. Recarga con `omarchy-restart-shell` y comprueba ambas barras.
El worker guarda miniaturas en `$XDG_CACHE_HOME/cdaily-thumbnails` (por defecto
`~/.cache/cdaily-thumbnails`); no necesita base de datos, credenciales ni daemon.

## Pruebas

```bash
/usr/bin/python -m unittest discover -s integrations/omarchy/cdaily/tests -v
```

Estas pruebas apuntan a esta copia versionada, no a la instalación del usuario.
Los contratos estáticos no sustituyen las pruebas de ejecución de Quickshell.
Consulta `VERIFICATION.md` para el alcance, resultados y límites de la
verificación realizada sobre el plugin instalado. Capturas, logs y harnesses
locales no se incluyen en Git.
