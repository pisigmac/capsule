"""FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..shared.config import config
from ..shared.logging import setup_logging
from ..shared.models import (
    engine as current_engine,
    get_session_factory,
    init_db,
    release_startup_lock,
    reset_engine,
    try_startup_lock,
)
from ..store.store import CapsuleStore, StoreError
from ..sync.watcher import CapsuleSyncService
from .routes import router

logger = logging.getLogger("capsule.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(config.log_level)
    config.ensure_dirs()
    if current_engine is None:
        reset_engine()
    init_db()

    db = get_session_factory()()
    locked = False
    try:
        if config.reconcile_on_start:
            locked = try_startup_lock(db)
            if locked:
                indexed = CapsuleStore(db).reconcile()
                db.commit()
                logger.info("Indexed %s capsule file(s)", indexed)
            else:
                logger.info("Startup reconcile skipped (another worker holds the lock)")
    except Exception:
        db.rollback()
        logger.exception("Startup reconcile failed")
        raise
    finally:
        if locked:
            try:
                release_startup_lock(db)
                db.commit()
            except Exception:
                db.rollback()
        db.close()

    watcher = None
    if config.watch_enabled:
        watcher = CapsuleSyncService(watch_dirs=[str(config.capsules_dir)])
        watcher.start()
        app.state.watcher = watcher
    else:
        app.state.watcher = None

    yield

    if watcher is not None:
        watcher.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Capsule API",
        description="Atomic knowledge management. Files are the source of truth.",
        version="0.3.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def require_token(request: Request, call_next):
        token = config.api_token
        if token and request.url.path not in {"/health", "/docs", "/openapi.json", "/redoc"}:
            header = request.headers.get("authorization", "")
            expected = f"Bearer {token}"
            if header != expected:
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)

    @app.exception_handler(StoreError)
    async def store_error_handler(_request: Request, exc: StoreError):
        message = str(exc)
        status = 404 if "not found" in message.lower() else 400
        return JSONResponse(status_code=status, content={"detail": message})

    app.include_router(router, prefix="/api/v1")

    @app.get("/health")
    async def health():
        from sqlalchemy import text

        from ..shared.models import get_engine

        db_ok = True
        capsule_count = 0
        try:
            with get_engine().connect() as conn:
                capsule_count = conn.execute(text("SELECT COUNT(*) FROM capsules")).scalar() or 0
                dialect = conn.dialect.name
        except Exception:
            db_ok = False
            dialect = "unknown"
            logger.exception("Health check database probe failed")
        status = "ok" if db_ok else "degraded"
        return {
            "status": status,
            "service": "capsule-api",
            "version": "0.3.0",
            "database": "ok" if db_ok else "error",
            "dialect": dialect,
            "capsules": capsule_count,
            "watcher": bool(getattr(app.state, "watcher", None)),
        }

    return app


app = create_app()
