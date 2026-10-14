# CDaily / barra Omarchy — reparación y verificación

## Alcance

Cambios únicamente en el plugin de usuario `~/.config/omarchy/plugins/cdaily/`.
No se modificó Omarchy administrado ni código del backend CDaily.
Se respaldó el `Widget.qml` previo antes de los cambios.

## Evidencia y cambios

- El core original muestra SIGSEGV en la ruta OpenSSL/Qt TLS: `libcrypto.so.3`, `libqopensslbackend.so`, `QSslCertificate::fromData`. Esto identifica la ruta del fallo, no demuestra la causa upstream exacta.
- Las miniaturas HTTPS se descargan mediante `thumbnail_cache.py` en un proceso separado. Quickshell recibe rutas locales, con placeholder en fallos, límites de bytes/cache, TTL y validación de URL e imágenes. No es una sandbox contra DNS rebinding.
- Reparado `summaryBox` y su altura.
- Añadido contrato `open()` / `close()` compatible con la barra.
- GET: error HTTP/JSON y watchdog de 15 s. POST: error HTTP/JSON y watchdog de 120 s; resumen libera `busy` en error.
- Recargado con el launcher soportado `omarchy-restart-shell`.

## Verificaciones reales

- Suite de regresión del plugin: **10/10 pasan**.
- Harness QML final: exit 0; `articles=40 loading=false opened=true`; sin ReferenceError/TypeError del widget.
- Barra final: **6/6 ciclos** de apertura/cierre, tres en DP-2 y tres en DP-4. Dos barras mapeadas; mismo proceso Quickshell durante los seis ciclos. `integration-cycles.json` contiene los registros.
- Captura del panel muestra títulos y miniaturas; posición por encima de la barra.
- Fallos GET controlados en un servidor loopback aislado: rechazo de conexión, JSON inválido y timeout. Los tres terminan con `loading=false` y error explícito. `network-check.json` contiene resultados. No se detuvo el servicio live para estas pruebas.
- `cdaily.service`: activo. `/api/stats` y listado de artículos: responden.
- Web `http://127.0.0.1:7890/`: renderiza artículos; filtro Tech y búsqueda sin coincidencias funcionan; filtro y búsqueda restaurados.
- Suite backend: **118 passed, 4 skipped**, 13 warnings de deprecación de slowapi, exit 0.
- Logs finales: sin errores atribuibles a `plugins/cdaily/`.

## Redimensionamiento con mouse

- Añadidos ocho tiradores limitados a los bordes y esquinas; coordenadas de arrastre relativas a la superficie fija del panel para evitar saltos.
- Preferencias de tamaño por monitor mediante FileView con escritura atómica; límites de pantalla y restauración a 640 × 720.
- QtTest sobre el plugin instalado: eventos mousePress/mouseMove/mouseRelease ampliaron a 790 × 820 y redujeron al mínimo de ancho 480.
- Cierre/reapertura y recreación del Loader conservaron 480 × 820.
- Rueda sobre ListView tras reducir: contentY=216, scroll operativo.
- Harness final terminó con exit 0. El primer harness usó Qt.quit dentro del bucle anidado de QtTest y abortó al finalizar; reparado usando un Timer externo, sin cambios al plugin por ese fallo del test.
- Versión final cargada en barra mediante reinicio soportado y summon con respuesta ok. Funcionamiento confirmado manualmente con mouse.
- Prueba automatizada con un harness QML local (no incluido en el repo).

## Límites y observaciones

- Apertura real probada mediante `omarchy-shell shell summon` / `hide`; la herramienta de escritorio no pudo obtener el surface de la barra para un clic físico automatizado.
- No se ejecutó scan ni una generación LLM real ni se pulsaron acciones que modifican artículos live. Las rutas correspondientes cuentan con la suite backend, no con una prueba end-to-end de proveedor LLM.
- Logs, capturas y harnesses quedaron fuera del repo.
