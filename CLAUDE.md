# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (Python 3.10 required)
uv sync

# Run the service locally
python -m app

# Lint
ruff check .
ruff format .
```

No test suite exists in this project.

## Architecture

The service is a single-endpoint FastAPI app wrapping a local MarianMT (Helsinki-NLP) translation model. All application logic lives in `app/__main__.py` — the model and tokenizer are loaded at startup from the path set in `MODEL_PATH`.

**Request flow:**
1. `POST /translate` requires `Authorization: Bearer <API_KEY>` (verified via `secrets.compare_digest` against `settings.API_KEY`).
2. The handler accepts two body formats: `{"source": "..."}` or OpenAI-style `{"messages": [...]}` (takes the last `role: "user"` message).
3. Inference runs synchronously with `torch.no_grad()` inside an `async` route — no background tasks.
4. Response is always an OpenAI `chat.completion`-shaped dict.

**Key design points:**
- `ENVIRONMENT=production` disables `/docs` and `/redoc`.
- `UVICORN_WORKERS > 1` in production; `UVICORN_RELOAD=true` only for local dev.
- The model directory (`Helsinki-train-combined-dedup-cleaned-05072025/`) is baked into the Docker image via `Dockerfile` and is not version-controlled as code.
- Logs go to stdout, `logs/log.log` (daily rotation, 31-day retention), and `logs/error_log.log` (WARNING+). The `logs/` directory is created automatically on startup.

## Configuration

All settings are in `app/core/config.py` (`pydantic-settings`). Required env vars — copy `.env.example` to `.env`:

| Variable | Description |
|---|---|
| `ENVIRONMENT` | `local` or `production` |
| `UVICORN_HOST` / `UVICORN_PORT` / `UVICORN_RELOAD` / `UVICORN_WORKERS` | Uvicorn server settings |
| `MODEL_PATH` | Path to the local MarianMT model directory |
| `API_KEY` | Bearer token for authentication |
| `DOCKER_IMAGE_BACKEND` / `TAG` | Docker image name and tag (Docker only) |

Nested env vars use `__` as delimiter.

## Docker

```bash
docker compose -f docker-compose-prod.yml up -d
```

The compose file uses `network_mode: host`. The model directory must be present locally before building — it is copied into the image by the Dockerfile.
