"""FastAPI application entry point."""

from __future__ import annotations

import logging
import sys

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.audit import router as audit_router
from backend.api.decks import router as decks_router
from backend.api.rewrites import router as rewrites_router
from backend.api.settings import router as settings_router
from backend.api.templates import router as templates_router
from backend.config import settings
from backend.storage import init_db

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Anki Maxxing",
    description=(
        "Augment Anki notes with semantically equivalent prompt variations "
        "while preserving native spaced-repetition scheduling."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def on_startup() -> None:
    await init_db()
    logging.getLogger(__name__).info("Database initialized.")


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(decks_router, prefix="/api")
app.include_router(rewrites_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(templates_router, prefix="/api")
app.include_router(settings_router, prefix="/api")


# ---------------------------------------------------------------------------
# Root health check
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {
        "app": "anki-maxxing",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    from backend.anki_client import AnkiClient
    anki = AnkiClient()
    anki_ok = await anki.ping()
    return {
        "api": "ok",
        "anki_connect": "ok" if anki_ok else "unreachable",
    }


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
