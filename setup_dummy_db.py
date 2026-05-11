import sqlite3
import os
from pathlib import Path

db_dir = Path.home() / ".blogwatcher-cli"
db_dir.mkdir(parents=True, exist_ok=True)
db_path = db_dir / "blogwatcher-cli.db"

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Create blogs table
cur.execute('''
CREATE TABLE IF NOT EXISTS blogs (
    id INTEGER PRIMARY KEY,
    name TEXT,
    url TEXT
)
''')

# Create articles table
cur.execute('''
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    title TEXT,
    url TEXT,
    published_date DATETIME,
    is_read BOOLEAN,
    blog_id INTEGER,
    categories TEXT,
    FOREIGN KEY(blog_id) REFERENCES blogs(id)
)
''')

# Insert dummy data if empty
cur.execute("SELECT COUNT(*) FROM blogs")
if cur.fetchone()[0] == 0:
    cur.execute("INSERT INTO blogs (id, name, url) VALUES (1, 'CIPER Chile', 'https://ciper.cl')")
    cur.execute("INSERT INTO blogs (id, name, url) VALUES (2, 'The Onion', 'https://onion.com')")

cur.execute("SELECT COUNT(*) FROM articles")
if cur.fetchone()[0] == 0:
    cur.execute("INSERT INTO articles (id, title, url, published_date, is_read, blog_id, categories) VALUES (1, 'Noticia Falsa', 'https://onion.com/1', '2026-05-10 12:00:00', 0, 2, 'humor')")
    cur.execute("INSERT INTO articles (id, title, url, published_date, is_read, blog_id, categories) VALUES (2, 'Noticia Real', 'https://ciper.cl/1', '2026-05-10 13:00:00', 0, 1, 'politica')")

conn.commit()
conn.close()
print("Dummy DB setup complete.")
