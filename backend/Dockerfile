# The application image.
#
# One process per container: the business API, the agent runtime and the worker are three services of
# one code revision that share this image and differ by `command` (ADR-0020 splits the HTTP surface;
# the worker is the queue consumer). That is also why this image has no process manager and no
# `gunicorn`/`--workers`: the runtime is assembled by dependency injection in each module's `main()`,
# and ADR-0025 sizes every connection pool per process — a pre-fork master would multiply both.
# Scale by running more replicas of a service, not more workers inside one container.
#
# Build context is the repository root (`.dockerignore` keeps the working tree and `.env` out of it):
#
#   docker build -f backend/Dockerfile -t clauserag-backend .
#
# `uv` is the tool this project locks with, so the image installs the same tool instead of
# reimplementing its resolution with pip. The version is pinned: a newer uv may resolve `uv.lock`
# differently than the review that accepted it.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first, in their own layer: it changes only when the lockfile does, so editing a source
# file does not re-resolve the graph. `--no-install-project` is what keeps the project itself out of
# this layer; `--no-dev` leaves Ruff, Pyright and the evaluation judge in the repository.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# The application, the migration history and Alembic's configuration. `alembic.ini` reads
# `DATABASE_URL` from the environment, so the one-shot `migrate` service needs nothing else.
COPY backend/src ./backend/src
COPY backend/migrations ./backend/migrations
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

# Nothing in the image writes to its own filesystem, so the process does not need to be root. The
# ports are the two HTTP surfaces' defaults; the worker serves none.
RUN useradd --create-home --uid 10001 rag
USER rag
EXPOSE 8000 8001

CMD ["python", "-m", "api.main"]
