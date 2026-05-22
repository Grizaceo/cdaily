#!/usr/bin/env python3
"""Cleanup relative/invalid image URLs from the cdaily_article_images database."""

import os
import sqlite3


def clean_relative_images():
    db_path = os.path.expanduser("~/.blogwatcher-cli/blogwatcher-cli.db")
    print(f"Connecting to database at {db_path}...")
    if not os.path.exists(db_path):
        print("Database file does not exist. Nothing to clean.")
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        # Count relative/invalid image URLs (not null, and not starting with http)
        cur.execute(
            "SELECT COUNT(*) FROM cdaily_article_images WHERE image_url IS NOT NULL AND image_url NOT LIKE 'http%'"
        )
        invalid_count = cur.fetchone()[0]

        if invalid_count == 0:
            print("No relative or invalid image URLs found in cdaily_article_images. Database is clean!")
            return

        print(f"Found {invalid_count} relative/invalid image URLs in cdaily_article_images.")

        # Delete relative/invalid entries so they can be re-fetched correctly
        with conn:
            conn.execute(
                "DELETE FROM cdaily_article_images WHERE image_url IS NOT NULL AND image_url NOT LIKE 'http%'"
            )

        print("Cleanup completed successfully! Invalid cached images removed.")

    except Exception as e:
        print(f"Error cleaning database: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    clean_relative_images()
