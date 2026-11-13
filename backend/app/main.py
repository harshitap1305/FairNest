"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware
from app.db.client import connect_db, close_db, get_db
from app.db.indexes import create_indexes
from app.db.validators import create_validators

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    await connect_db(settings.MONGO_URI)
    db = get_db(settings.MONGO_DB)
    await create_indexes(db)
    await create_validators(db)
    yield
    await close_db()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="FairNest Hostel Allotment API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    # ── Middlewares ────────────────────────────────────────────────────────────
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ─────────────────────────────────────────────────────
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        request_id = getattr(request.state, "request_id", "")
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": str(exc), "request_id": request_id}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", "")
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": str(exc.errors()),
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def generic_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "")
        logger.error("unhandled_exception request_id=%s: %s", request_id, exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                    "request_id": request_id,
                }
            },
        )

    # ── Routers ────────────────────────────────────────────────────────────────
    from app.api.routes import (
        admin, allotments, auth, catalogue, cycles, exports, groups, health, insights,
    )
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(catalogue.router, prefix="/api/v1")
    app.include_router(cycles.router, prefix="/api/v1")
    app.include_router(groups.router, prefix="/api/v1")
    app.include_router(allotments.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    app.include_router(insights.router, prefix="/api/v1")
    app.include_router(exports.router, prefix="/api/v1")

    return app


app = create_app()
