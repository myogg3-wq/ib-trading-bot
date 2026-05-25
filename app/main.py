"""
FastAPI application entry point.
Webhook server for receiving TradingView alerts.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import structlog

from app.database.connection import init_db
from app.gateway.webhook import router as webhook_router
from app.scheduler import setup_scheduler
from app.web.router import router as web_router

logger = structlog.get_logger()
STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"


class NoStoreStaticFiles(StaticFiles):
    """Serve frontend assets without browser caching during rapid UI iteration."""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        if getattr(response, "status_code", 200) == 200:
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


def create_app(*, skip_startup: bool = False) -> FastAPI:
    """Create the FastAPI app with optional startup skipping for tests."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application startup and shutdown."""
        if skip_startup:
            yield
            return

        logger.info("Starting IB Trading Bot API...")

        await init_db()
        logger.info("Database initialized")

        sched = setup_scheduler()
        logger.info("Scheduler started")

        logger.info("IB Trading Bot API is ready")

        yield

        logger.info("Shutting down IB Trading Bot API...")
        sched.shutdown(wait=False)

    app = FastAPI(
        title="IB Trading Bot",
        description="Automated trading bot with TradingView webhook integration",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.mount("/platform-static", NoStoreStaticFiles(directory=STATIC_DIR), name="platform-static")
    app.include_router(webhook_router, tags=["webhook"])
    app.include_router(web_router)
    return app


app = create_app()
