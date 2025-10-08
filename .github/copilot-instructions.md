# Copilot Instructions for fastapi-translation-service

## Overview
This project is a FastAPI-based translation service. It is structured for clarity, maintainability, and production-readiness, with configuration and environment management handled via Pydantic and `.env` files.

## Architecture
- **Entry Point:** `app/__main__.py` launches the FastAPI application.
- **Configuration:**
  - `app/core/config.py` defines environment and runtime settings using Pydantic's `BaseSettings`.
  - Environment variables are loaded from `.env` (see `env_file` in config).
- **Core Logic:**
  - `app/core/` contains foundational modules (e.g., `config.py`).
  - `app/utils/` holds utility code (e.g., `logging.py`).
- **Model Artifacts:**
  - `Helsinki-train-combined-dedup-cleaned-05072025/` contains model files and configs for translation.

## Developer Workflows
- **Run the Service (dev):**
  ```sh
  python -m app
  ```
- **Production Run:**
  Use `uvicorn` with settings from `app/core/config.py` (host, port, workers, etc.).
- **Configuration:**
  - All runtime settings are managed via environment variables (see `app/core/config.py`).
  - Use `.env` for local development overrides.
- **Dependencies:**
  - Install with `pip install -r requirements.txt`.
  - Project uses Pydantic, FastAPI, and Uvicorn.
- **Docker:**
  - Use `Dockerfile` and `docker-compose-prod.yml` for containerized deployments.

## Patterns & Conventions
- **Settings:**
  - All config is centralized in `app/core/config.py` using Pydantic's `BaseSettings`.
  - Use nested environment variables with `__` as delimiter.
- **No business logic in `__main__.py`**; keep it as the entry point only.
- **Model files** are not code—do not modify files in `Helsinki-train-combined-dedup-cleaned-05072025/` unless updating the translation model.

## Integration Points
- **Model Loading:**
  - Model and tokenizer files are loaded from the `Helsinki-train-combined-dedup-cleaned-05072025/` directory.
- **Logging:**
  - Use `app/utils/logging.py` for logging setup and conventions.

## Examples
- To add a new config variable, update `app/core/config.py` and document the corresponding environment variable.
- To change the model, replace files in `Helsinki-train-combined-dedup-cleaned-05072025/` and update config if needed.

---
For questions about project structure or conventions, see this file or `app/core/config.py` for authoritative patterns.
