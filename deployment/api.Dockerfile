FROM python:3.12-slim

RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY backend/src ./backend/src
COPY backend/migrations ./backend/migrations
COPY alembic.ini ./

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
RUN uv sync --frozen --no-dev --no-editable && chown -R app:app /app

USER app
ENV PATH="/app/.venv/bin:$PATH"
ENV COLOR_RUSH_HOST=0.0.0.0
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "color_rush.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
