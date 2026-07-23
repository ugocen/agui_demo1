# ---------- Backend: FastAPI + Uvicorn ----------
FROM python:3.13-slim AS base

# Prevent Python from writing .pyc and enable unbuffered stdout (important for
# streaming SSE — architecture invariant 1: never buffer the AG-UI SSE stream).
# PYTHONDONTWRITEBYTECODE is also what lets the pod run with a read-only root
# filesystem: with it off, the first import tries to write __pycache__/ and the
# container dies on a read-only mount.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer cache). Done as root, before the USER switch:
# the packages land in the system site-packages and are world-readable.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Run as a non-root user. Kubernetes clusters enforcing the `restricted` Pod
# Security Standard reject a container that can run as uid 0, so an image that
# only works as root cannot be scheduled at all. uid 1001 matches the frontend
# image, so one PodSecurityContext covers both.
RUN groupadd --system --gid 1001 appuser && \
    useradd --system --uid 1001 --gid 1001 --no-create-home appuser
USER appuser

# Expose the default port
EXPOSE 8000

# Health check using the existing /healthz endpoint (unauthenticated by design —
# it is also what the Kubernetes liveness/readiness probes hit).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"

# Single worker — scale with pod replicas, not pre-fork workers.
# Pre-fork breaks OTEL Python (workers export nothing after fork).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
