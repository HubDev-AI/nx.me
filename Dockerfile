# ── Base ────────────────────────────────────────────────────────────────────
FROM python:3.12.9-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for Pillow / MediaPipe / psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Remove build tools after pip install (L-18)
RUN apt-get purge -y gcc && apt-get autoremove -y


# ── Dev ─────────────────────────────────────────────────────────────────────
FROM base AS dev

COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt

# Non-root user for dev (M-22)
RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# ── Production ──────────────────────────────────────────────────────────────
FROM base AS prod

RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY --chown=appuser:appuser . .

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"]

EXPOSE 8000
# IMPORTANT: --proxy-headers trusts X-Forwarded-For. Must run behind a reverse proxy.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", "--proxy-headers"]
