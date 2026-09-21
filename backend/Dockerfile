# task-01 에서 확정한다.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /srv/backend

COPY ai/pyproject.toml ai/README.md /srv/ai/
COPY ai/src /srv/ai/src
COPY backend/pyproject.toml backend/uv.lock /srv/backend/
RUN uv sync --locked --no-dev --no-editable

COPY backend/app /srv/backend/app
COPY backend/migrations /srv/backend/migrations
COPY backend/scripts /srv/backend/scripts
COPY backend/alembic.ini /srv/backend/alembic.ini

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
