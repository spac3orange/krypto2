# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Must match the owner of the host folders mounted into /app/data.
ARG APP_UID=1000
ARG APP_GID=1000

RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --create-home app

COPY pyproject.toml README.md ./
COPY app ./app

RUN pip install --upgrade pip \
    && pip install . \
    && mkdir -p /app/data/telegram /app/data/trading /app/logs \
    && chown -R app:app /app

USER app

VOLUME ["/app/data/telegram", "/app/data/trading", "/app/logs"]

# Readiness marker written by TelegramIngestionService when connected + source resolved
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "from pathlib import Path; import sys; sys.exit(0 if Path('data/telegram/.ready').is_file() else 1)"

CMD ["python", "-m", "app"]
