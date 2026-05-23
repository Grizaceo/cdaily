# Contributing to CDaily

Thanks for your interest in CDaily. This project is MIT-licensed.

## Development setup

```bash
git clone https://github.com/<your-org>/cdaily.git
cd cdaily
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
python -m cdaily.main
```

You need [blogwatcher-cli](https://github.com/) with a populated `~/.blogwatcher-cli/blogwatcher-cli.db` to run the app against real feeds. Tests do not require it.

## Code style

- Format with `black` (line length 88)
- Lint with `flake8`
- CI runs both on every push to `master`

## Pull requests

1. Branch from `master` (not directly on `master` for feature work)
2. Keep changes focused; include tests when behavior changes
3. Update `CHANGELOG.md` under **Unreleased** for user-visible changes
4. Do not commit secrets, `.env`, `config.local.yaml`, or machine-specific YAML overrides

## Security

Report sensitive issues privately to the maintainer rather than opening a public issue with exploit details.
