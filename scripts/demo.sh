#!/usr/bin/env bash
# demo.sh — Run CDaily against a throwaway blogwatcher-cli DB seeded with public feeds.
# Never touches ~/.blogwatcher-cli or the tracked config.yaml.
#
# Usage: scripts/demo.sh [DEMO_DIR]
#   CDAILY_DEMO_PORT   port to bind on 127.0.0.1 (default 7891)
#   CDAILY_AI_ENDPOINT / CDAILY_AI_API_KEY   optional, enables AI summaries

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_DIR="${1:-${TMPDIR:-/tmp}/cdaily-demo}"
PORT="${CDAILY_DEMO_PORT:-7891}"
DB="$DEMO_DIR/blogwatcher-cli.db"
CONFIG="$DEMO_DIR/config.yaml"
BLOGWATCHER="${BLOGWATCHER:-blogwatcher-cli}"
PYTHON="${PYTHON:-python3}"

command -v "$BLOGWATCHER" >/dev/null || { echo "blogwatcher-cli not found in PATH" >&2; exit 1; }
mkdir -p "$DEMO_DIR"

if [[ ! -f "$DB" ]]; then
    echo "Seeding demo DB at $DB ..."
    while IFS='|' read -r name url feed; do
        "$BLOGWATCHER" --db "$DB" add "$name" "$url" --feed-url "$feed" >/dev/null
    done <<'FEEDS'
Ars Technica|https://arstechnica.com|https://feeds.arstechnica.com/arstechnica/index
The Verge AI|https://www.theverge.com|https://www.theverge.com/rss/ai-artificial-intelligence/index.xml
MIT Tech Review AI|https://www.technologyreview.com|https://www.technologyreview.com/feed/
Schneier on Security|https://www.schneier.com|https://www.schneier.com/feed/
Krebs on Security|https://krebsonsecurity.com|https://krebsonsecurity.com/feed/
The Hacker News|https://thehackernews.com|https://feeds.feedburner.com/TheHackersNews
Science Daily|https://www.sciencedaily.com|https://www.sciencedaily.com/rss/all.xml
BBC Mundo|https://www.bbc.com/mundo|https://feeds.bbci.co.uk/mundo/rss.xml
FEEDS
    "$BLOGWATCHER" --db "$DB" scan
fi

# Demo config: public defaults, loopback only, pointed at the demo DB.
sed -e "s|^host:.*|host: \"127.0.0.1\"|" \
    -e "s|^port:.*|port: $PORT|" \
    -e "s|^db_path:.*|db_path: \"$DB\"|" \
    "$REPO_DIR/config.yaml.example" >"$CONFIG"

echo "CDaily demo → http://127.0.0.1:$PORT/"
cd "$REPO_DIR"
CDAILY_CONFIG="$CONFIG" exec "$PYTHON" -m cdaily.main
