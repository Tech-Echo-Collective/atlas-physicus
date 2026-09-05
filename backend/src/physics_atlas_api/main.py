import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .api import router
from .config import get_settings
from .logging_config import configure_logging

logger = logging.getLogger("physics_atlas_api")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("API starting", extra={"event": "api.start", "source": "backend"})
    yield
    logger.info("API stopping", extra={"event": "api.stop", "source": "backend"})


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Atlas Physica API",
        version=__version__,
        description=(
            "Read-oriented scientific metadata API. v3.0.5-alpha exposes bounded "
            "live evidence and withholds unvalidated scientific metric layers. "
            "Atlas Physica is developed and maintained by Tech Echo Collective."
        ),
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "If-None-Match"],
    )

    @application.middleware("http")
    async def request_logging(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        logger.info(
            "request completed",
            extra={
                "event": "http.request",
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "records": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                },
            },
        )
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "context": {"issues": exc.errors()},
                }
            },
        )

    application.include_router(router, prefix=settings.api_prefix)
    return application


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "physics_atlas_api.main:app",
        host="0.0.0.0",  # noqa: S104 - container entrypoint must accept host traffic
        port=settings.port,
        reload=False,
    )
