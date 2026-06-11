# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

HTTP machine-translation service built on FastAPI, wrapping a locally-loaded MarianMT (Helsinki-NLP) model. Single endpoint `POST /translate` that returns OpenAI Chat Completions-shaped responses so the service can be dropped behind tooling that expects an OpenAI-compatible backend.

## Commands

Dependency management uses **uv** (`pyproject.toml` + `uv.lock`); Python is pinned to `>=3.10,<3.11`.

```bash
uv sync                       # install deps (dev + runtime)
python -m app                 # run the server (entrypoint is app/__main__.py)
uv run ruff check .           # lint
uv run ruff format .          # format
docker compose -f docker-compose-prod.yml up -d --build   # prod container
```

There is no test suite.

## Configuration

All settings come from `.env` via `pydantic-settings` (`app/core/config.py`). All listed vars are required — `Settings()` will fail at import time if any are missing:

- `ENVIRONMENT` — `local` or `production`. In `production`, FastAPI is constructed with `docs_url=None, redoc_url=None` (Swagger / ReDoc disabled).
- `UVICORN_HOST`, `UVICORN_PORT`, `UVICORN_RELOAD`, `UVICORN_WORKERS`
- `MODEL_PATH` — filesystem path to a MarianMT model directory. Loaded with `local_files_only=True`, so the directory must contain a complete model (no HF Hub fallback).
- `API_KEY` — Bearer token compared via `secrets.compare_digest` in `verify_bearer_token`.

## Architecture notes

- **Single-module app.** `app/__main__.py` is both the FastAPI app and the uvicorn entrypoint (`python -m app`). The model and tokenizer are loaded at module import time as globals — there is no lifespan/startup hook, so import cost == model load cost, and `UVICORN_WORKERS > 1` means N copies of the model in memory. **GPU warning:** on a GPU server keep `UVICORN_WORKERS=1` — multiple workers compete for the same CUDA device and will OOM or deadlock. On a CPU server multiple workers are fine if RAM can fit N model copies. Check: `uv run python -c "import torch; print(torch.cuda.is_available())"`.
- **Request shape is dual.** `/translate` reads the raw JSON body (not the `TranslationRequest` Pydantic model — that class is defined but unused on the route). It accepts either `{"source": "..."}` or an OpenAI-style `{"messages": [...]}` and picks the last `role: "user"` message. Missing both fields returns `{"translation": ""}` with 200 (not an error).
- **Response shape is OpenAI-minimal.** Always returns `id: "test"` (hardcoded, known limitation — do not "fix"), `object: "chat.completion"`, single `choices[0]` with the translation in `message.content`. No usage/model fields.
- **Auth.** `HTTPBearer` dependency on the route; non-Bearer scheme or token mismatch → 401 with `WWW-Authenticate: Bearer`.
- **Logging.** `app/utils/logging.py` configures the root logger with three handlers (console, `logs/log.log` rotating daily kept 31 days, `logs/error_log.log` for WARNING+). The `logs/` directory is created on `setup_logger()`. Uvicorn is started with `log_config=None` so the dictConfig isn't overwritten.

## Docker

The Dockerfile **bakes the model into the image** — it `COPY`s `./Helsinki-train-combined-dedup-cleaned-05072025/` into `/app/`. If the model directory is renamed or moved, the Dockerfile must be updated to match. `docker-compose-prod.yml` uses `network_mode: host` and hardcodes uvicorn settings via `environment:` (these override `.env` for the container).

## Lint config

Ruff is configured in `pyproject.toml` with a non-default selection (`E,W,F,I,T10,T20,Q,RET,B,PLC,C,PLW,UP,ISC,PLR1714,ASYNC,G004,TC003,ANN201,ARG001`). Notable: `T20` bans `print()` — use the logger. `G004` bans f-strings in logging calls — use `%`-style (`logger.info("x: %s", x)`), which is the existing convention.
