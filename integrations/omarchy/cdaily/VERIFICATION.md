# CDaily / barra Omarchy — reparación y verificación

## Alcance

Cambios únicamente en el plugin de usuario `~/.config/omarchy/plugins/cdaily/`.
No se modificó Omarchy administrado ni código del backend CDaily.
Backup anterior a los cambios: `Widget.qml.bak.20261010-212604`.

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
- Barra final: **6/6 ciclos** de apertura/cierre, tres en DP-2 y tres en DP-4. Dos barras mapeadas; mismo PID Quickshell 1514297 durante los seis ciclos. `integration-cycles.json` contiene los registros.
- Captura del panel muestra títulos y miniaturas; posición por encima de la barra.
- Fallos GET controlados en un servidor loopback aislado: rechazo de conexión, JSON inválido y timeout. Los tres terminan con `loading=false` y error explícito. `network-check.json` contiene resultados. No se detuvo el servicio live para estas pruebas.
- `cdaily.service`: activo. `/api/stats` y listado de artículos: responden.
- Web `http://127.0.0.1:8090/`: renderiza artículos; filtro Tech y búsqueda sin coincidencias funcionan; filtro y búsqueda restaurados.
- Suite backend: **118 passed, 4 skipped**, 13 warnings de deprecación de slowapi, exit 0.
- Logs finales: sin errores atribuibles a `plugins/cdaily/`.

## Límites y observaciones

- Apertura real probada mediante `omarchy-shell shell summon` / `hide`; la herramienta de escritorio no pudo obtener el surface de la barra para un clic físico automatizado.
- No se ejecutó scan ni una generación LLM real ni se pulsaron acciones que modifican artículos live. Las rutas correspondientes cuentan con la suite backend, no con una prueba end-to-end de proveedor LLM.
- Existe un warning independiente de `io.github.tammyx44.omaglimpse/SettingsPanel.qml:1710`: `TypeError: Property 'String' ... is not a function`. No se modificó ese plugin en esta reparación.
- Logs/capturas/harnesses: `~/.hermes/workspace/ACTIVE/cdaily-bar-debug/`.
