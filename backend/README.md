# Leovee Backend

FastAPI application for the Leovee platform.

## Development

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Quality

```bash
ruff check app
ruff format --check app
mypy app
pytest
```

Run migrations (requires `DATABASE_URL`):

```bash
alembic upgrade head
```
