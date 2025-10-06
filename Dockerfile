FROM python:3.10-slim-bookworm AS builder

WORKDIR /app/

# Install uv
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /bin/

# Compile bytecode
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#compiling-bytecode
ENV UV_COMPILE_BYTECODE=1

# uv Cache
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#caching
ENV UV_LINK_MODE=copy

# Install dependencies
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#intermediate-layers
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY ./pyproject.toml ./uv.lock /app/

COPY ./Helsinki-train-combined-dedup-cleaned-05072025/ /app/Helsinki-train-combined-dedup-cleaned-05072025/

COPY ./app/ /app/app/

# Sync the project
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#intermediate-layers
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev


FROM python:3.10-slim-bookworm

WORKDIR /app/

COPY --from=builder /app/ /app/

# Place executables in the environment at the front of the path
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#using-the-environment
# python
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app" \
    PATH="/app/.venv/bin:$PATH" \
    # prevents python creating .pyc files
    #PYTHONDONTWRITEBYTECODE=1 \
    \
    # timezone
    TZ=Europe/Moscow

# EXPOSE 8000

# CMD ["fastapi", "run", "--workers", "4", "app/main.py"]

CMD ["python", "-m", "app"]
