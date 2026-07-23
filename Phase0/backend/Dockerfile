# ---------- Backend: FastAPI + Uvicorn ----------
FROM python:3.13-slim AS base

# Prevent Python from writing .pyc and enable unbuffered stdout (important for
# streaming SSE — architecture invariant 1: never buffer the AG-UI SSE stream)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Expose the default port
EXPOSE 8000

# Health check using the existing /healthz endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"

# Single worker — scale with pod replicas, not pre-fork workers.
# Pre-fork breaks OTEL Python (workers export nothing after fork).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
