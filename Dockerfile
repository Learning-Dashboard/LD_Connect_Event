# ── Stage 1: install dependencies in a throwaway builder ──────────────
FROM python:3.14-slim AS builder

# Prevent .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install deps into a separate prefix so we can copy only what we need
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: lean runtime image ──────────────────────────────────────
FROM python:3.14-slim AS runtime

LABEL maintainer="Learning Dashboard team" \
      description="LD Connect Event – webhook ingestion service"

# Same env vars for runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy only the installed packages from the builder stage
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application code (respects .dockerignore)
COPY . .

# Create a non-root user and switch to it
RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup appuser && \
    chown -R appuser:appgroup /app
USER appuser

# Expose the port Gunicorn will listen on
EXPOSE 5000

# Healthcheck so Docker / Compose can monitor the service
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

# Run gunicorn with the create_app() factory
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:create_app()"]
