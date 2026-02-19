"""
FastAPI application entry point.
Webhook server for receiving TradingView alerts.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
import structlog

from app.database.connection import init_db
from app.gateway.webhook import router as webhook_router
from app.scheduler import setup_scheduler

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    # === Startup ===
    logger.info("Starting IB Trading Bot API...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Start scheduler (market open flush, daily report, sync, etc.)
    sched = setup_scheduler()
    logger.info("Scheduler started")

    logger.info("IB Trading Bot API is ready")

    yield

    # === Shutdown ===
    logger.info("Shutting down IB Trading Bot API...")
    sched.shutdown(wait=False)


app = FastAPI(
    title="IB Trading Bot",
    description="Automated trading bot with TradingView webhook integration",
    version="1.0.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(webhook_router, tags=["webhook"])
