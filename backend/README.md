# Angmoo backend

From this directory:

```bash
cp .env.example .env
uv sync --frozen
uv run alembic upgrade head
uv run uvicorn app.public_main:app --reload --host 127.0.0.1 --port 8080
```

The public entrypoint requires LangGraph/direct and rejects scheduler, image
worker, and service-image enablement. Use synthetic data and fake providers for
local tests.
