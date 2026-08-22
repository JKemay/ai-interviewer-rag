# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Builder — resolves dependencies into a virtualenv.
#
# Kept separate from the runtime stage so that uv, build tooling, and the
# package cache never reach the shipped image.
# ---------------------------------------------------------------------------
FROM python:3.13-slim-trixie AS builder

# uv is pinned; a floating version would make builds non-reproducible.
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency layer first: it changes far less often than source, so edits to
# application code reuse this cached layer instead of re-resolving everything.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
FROM python:3.13-slim-trixie AS runtime

# Runs as an unprivileged user. A container process running as root that gets
# compromised has a far shorter path to escaping the container.
RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --create-home app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app src/ ./src/

USER app

EXPOSE 8000

# The slim image has no curl, so the probe uses the interpreter that is
# guaranteed to be present.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status==200 else 1)"]

# 0.0.0.0 is correct *inside* the container — the host-side exposure is
# controlled by the port binding in compose, which is loopback-only.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
