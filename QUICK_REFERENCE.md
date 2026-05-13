# CDaily — Quick Reference

## Changes at a Glance

### 🔧 What Was Fixed

| Issue | Solution | File |
| --- | --- | --- |
| Missing config defaults crash | Added DEFAULT_BLOG_CATEGORIES and DEFAULT_CATEGORY_EMOJI | app/config.py |
| Config not validated | Added validate_config() called at startup | app/config.py |
| DB schema not checked | Added validate_db_schema() in init_db() | app/database.py |
| Personalization logic broken | Fixed get_personalization_profile() duplicate query | app/database.py |
| No rate limiting | Added asyncio.sleep(1) in fetch_missing_images() | app/main.py |
| Code quality issues | Fixed all flake8/Black issues, formatted codebase | all .py files |
| No CI/CD pipeline | Added GitHub Actions workflow | .github/workflows/ci.yml |
| Incomplete documentation | Updated README with troubleshooting | README.md |

---

## Before & After

### Configuration

**Before**: Would crash if `blog_categories` missing
```python
BLOG_CATEGORIES = CONFIG.get("blog_categories", {})  # Empty dict = bad
```

**After**: Defaults provided, validation enforced
```python
BLOG_CATEGORIES = CONFIG.get("blog_categories", DEFAULT_BLOG_CATEGORIES)
validate_config(raw)  # Raises descriptive errors
```

### Database

**Before**: Personalization broken (duplicate query)
```python
cur.execute("SELECT b.name, AVG(...) GROUP BY b.name")
by_blog_rows = cur.fetchall()
cur.execute("SELECT b.name, AVG(...) GROUP BY b.name")  # SAME QUERY!
by_category_rows = cur.fetchall()
```

**After**: Fixed with single query, Python grouping
```python
cur.execute("SELECT b.name, AVG(...) GROUP BY b.name")
by_blog_rows = cur.fetchall()
# Python groups by category using blog_category_map
```

### Performance

**Before**: Image fetches could overwhelm servers
```python
for art in articles:
    resp = await client.get(art["url"])  # No delay
```

**After**: Rate limited with 1-second delay
```python
for art in articles:
    resp = await client.get(art["url"])
    await asyncio.sleep(1)  # Respectful pacing
```

---

## Testing Commands

### Run Tests
```bash
cd /home/gris/.hermes/workspace/repos/cdaily
pytest tests/ -v
```

### Check Linting
```bash
flake8 app tests
```

### Format Code
```bash
black app tests
```

### Start App
```bash
python -m app.main
# Open http://localhost:7890
```

### Docker
```bash
docker-compose up -d
docker logs cdaily_widget
docker-compose down
```

---

## Configuration Tips

### Basic Setup
```yaml
host: "0.0.0.0"
port: 7890
db_path: "~/.blogwatcher-cli/blogwatcher-cli.db"
scan_interval_minutes: 30
refresh_interval_seconds: 60
log_level: "INFO"
```

### Enable AI Summarization
```yaml
ai_preferences:
  enabled: true
  endpoint: "http://localhost:12345/v1/chat/completions"  # example OpenAI-compatible endpoint
  model: "qwen2.5-7b-instruct-1m"
  max_content_chars: 12000
  system_prompt: "Summarize briefly in 3 bullet points."
```

### Override AI Endpoint (env var)
```bash
export CDAILY_AI_ENDPOINT="http://new-endpoint:8000/v1/chat/completions"
python -m app.main
```

---

## Common Errors & Solutions

### "Database path does not exist"
```bash
# Check if DB exists
ls -la ~/.blogwatcher-cli/blogwatcher-cli.db

# If missing, run blogwatcher-cli
blogwatcher-cli scan
```

### "Articles table missing columns"
```bash
# Validate schema
sqlite3 ~/.blogwatcher-cli/blogwatcher-cli.db ".schema articles"

# Should have: id, title, url, published_date, is_read, blog_id
```

### "Address already in use (Port 7890)"
```bash
# Check what's using the port
lsof -i :7890

# Kill the process or change port in config.yaml
```

### "AI Server Error 500"
```bash
# Test AI endpoint connectivity
curl -X POST http://localhost:12345/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-7b","messages":[{"role":"user","content":"test"}]}'

# Or disable AI: ai_preferences.enabled: false
```

---

## File Structure

```
cdaily/
├── app/
│   ├── main.py              # FastAPI routes
│   ├── config.py            # Configuration loading & validation
│   ├── database.py          # Database queries & schema validation
│   ├── models.py            # Pydantic models
│   ├── routes/              # (unused, extensible)
│   ├── static/
│   │   ├── css/style.css    # Dark mode UI
│   │   └── js/app.js        # Frontend logic
│   └── templates/
│       └── index.html       # HTML template
├── tests/
│   └── test_api.py          # API tests (smoke tests)
├── config.yaml              # Configuration file
├── docker-compose.yml       # Docker setup
├── Dockerfile               # Docker image
├── README.md                # Documentation
├── IMPLEMENTATION.md        # Changes summary
├── setup.cfg                # Flake8 config
├── pyproject.toml           # Black config
├── requirements.txt         # Dependencies
└── .github/
    └── workflows/
        └── ci.yml           # GitHub Actions CI
```

---

## Key Improvements Summary

✅ **Robustness**: Config validation + defaults prevent crashes
✅ **Reliability**: DB schema validation catches issues early
✅ **Correctness**: Personalization logic fixed for accurate ranking
✅ **Performance**: Rate limiting + async improvements
✅ **Quality**: 100% linting compliant, Black formatted
✅ **Automation**: GitHub Actions CI on all changes
✅ **Documentation**: Comprehensive troubleshooting guide
✅ **Maintainability**: Clean codebase, easy to extend

---

## Next Steps

1. **Deploy** updated code to production
2. **Monitor** logs for validation warnings
3. **Test** AI summarization (if enabled)
4. **Consider** optional improvements from IMPLEMENTATION.md
5. **Maintain** code quality with pre-commit hooks

---

For detailed information, see IMPLEMENTATION.md and README.md
