FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY migrations ./migrations
COPY scripts ./scripts
COPY data ./data
COPY evals ./evals
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.12-slim AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system orderops \
    && useradd --system --gid orderops --home-dir /app orderops

WORKDIR /app
COPY --from=builder --chown=orderops:orderops /app /app
RUN mkdir -p /app/.streamlit \
    && chown orderops:orderops /app/.streamlit
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER orderops
EXPOSE 8000 8001 8501
