"""
Artilery API — FastAPI application entry point.

Includes:
- GitHub webhook router (PR events)
- Chatbot API router
- Health check endpoint
- Request logging middleware
- CORS middleware
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("artilery.api")
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: validate config on startup."""
    logger.info("Artilery API starting up...")
    try:
        from shared.config import get_settings
        settings = get_settings()
        # Only validate platform-level vars (Kafka), not all agent vars
        logger.info("Configuration loaded | bootstrap=%s", settings.CONFLUENT_BOOTSTRAP_SERVERS or "NOT SET")
    except Exception as exc:
        logger.warning("Config validation warning: %s", exc)
    yield
    logger.info("Artilery API shutting down...")


app = FastAPI(
    title="Artilery API",
    description="Kafka Automated Ops System — Event-driven CI/CD orchestration",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request Logging Middleware ───────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next: Any) -> Response:
    """Log every request with method, path, status, and duration."""
    start = time.perf_counter()
    response: Response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "API | %s %s | status=%d | duration=%.1fms",
        request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


# ── Health Check ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "version": "1.0.0", "service": "artilery-api"}


# ── Routers ──────────────────────────────────────────────────────────────────
from api.routers.github import router as github_router  # noqa: E402
from api.routers.chat import router as chat_router  # noqa: E402
from api.routers.graph import router as graph_router  # noqa: E402

app.include_router(github_router, tags=["GitHub Webhooks"])
app.include_router(chat_router, tags=["Chatbot"])
app.include_router(graph_router, tags=["Knowledge Graph"])

