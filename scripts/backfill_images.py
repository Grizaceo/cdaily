#!/usr/bin/env python3
"""
backfill_images.py — Backfills image cache for the latest 300 articles missing records.
Uses existing fetch_article_image logic to reuse crawler, validators, and DB writes.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys

# Ensure the project root is in the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from app.services.article_images import fetch_article_image


async def backfill() -> None:
    db_path = os.path.expanduser("~/.blogwatcher-cli/blogwatcher-cli.db")
    if not os.path.exists(db_path):
        print(f"Error: Base de datos no encontrada en {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Encontrar los últimos 300 artículos que no tienen fila en cdaily_article_images
    q = """
        SELECT a.id, a.title, a.url
        FROM articles a
        LEFT JOIN cdaily_article_images img ON img.article_id = a.id
        WHERE img.article_id IS NULL
        ORDER BY a.published_date DESC
        LIMIT 300
    """
    rows = conn.execute(q).fetchall()
    conn.close()

    total = len(rows)
    if total == 0:
        print("¡Todos los artículos ya tienen registros de imágenes cacheos! Nada que hacer.")
        return

    print(f"Encontrados {total} artículos sin registro de imagen. Iniciando backfill...")

    successful = 0
    failed = 0

    for idx, r in enumerate(rows, 1):
        art_id = r["id"]
        title = r["title"] or r["url"]
        print(f"[{idx}/{total}] Procesando artículo {art_id}: {title[:65]}...")
        try:
            # fetch_article_image se encarga de:
            # - Validar la URL (SSRF guard)
            # - Scrapear usando httpx
            # - Extraer la og:image usando BeautifulSoup
            # - Resolver URLs relativas a absolutas
            # - Guardar el resultado en la base de datos (sea URL o None)
            res = await fetch_article_image(art_id)
            if res.get("image_url"):
                print(f"  -> ÉXITO: {res['image_url'][:75]}")
                successful += 1
            else:
                err_msg = res.get("error") or "No se encontró og:image / Guardado como NULL"
                print(f"  -> NO IMAGEN: {err_msg}")
                failed += 1
        except Exception as e:
            print(f"  -> ERROR EXCEPCIÓN: {e}")
            failed += 1

        # Sleep de 1.0 segundos para ser extremadamente gentiles con los sitios remotos
        await asyncio.sleep(1.0)

    print(f"\n=== BACKFILL COMPLETADO ===")
    print(f"Exitosos (imágenes guardadas): {successful}")
    print(f"Sin imagen o Errores (registrados como NULL): {failed}")


if __name__ == "__main__":
    asyncio.run(backfill())
