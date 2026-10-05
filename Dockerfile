# ==============================================================================
# Artilery — Production Dockerfile
# ==============================================================================
# Multi-stage build: slim final image with only runtime dependencies.
#
# Usage:
#   docker build -t artilery-api .
#   docker run -p 8000:8000 --env-file .env artilery-api
# ==============================================================================

FROM python:3.13-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    librdkafka-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Final stage ──────────────────────────────────────────────────────────────

FROM python:3.13-slim

WORKDIR /app

# Install runtime C library for confluent-kafka
RUN apt-get update && apt-get install -y --no-install-recommends \
    librdkafka1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY . .

ENV PYTHONUNBUFFERED=1
ENV ARTILERY_ENV=production
ENV PORT=8000

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8000/health'); r.raise_for_status()" || exit 1

# Run with uvicorn (production settings)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--log-level", "info"]
