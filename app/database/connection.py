"""
Database connection management.
Provides async SQLAlchemy sessions and initialization.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from contextlib import asynccontextmanager
import structlog

from app.config import settings
from app.models.base import Base
from app.models.settings import BotSettings

logger = structlog.get_logger()

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

# Session factory
async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


@asynccontextmanager
async def get_session():
    """Get an async database session."""
    session = async_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db():
    """Initialize database tables and seed default settings."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables created")

    # Seed default settings if not exists
    async with get_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(BotSettings).limit(1))
        existing = result.scalar_one_or_none()

        if not existing:
            default_settings = BotSettings(
                buy_amount_usd=settings.default_buy_amount_usd,
                max_open_positions=settings.default_max_open_positions,
                max_daily_buys=settings.default_max_daily_buys,
                max_total_investment=settings.default_max_total_investment,
                max_per_ticker=settings.default_max_per_ticker,
                max_daily_loss=settings.default_max_daily_loss,
                min_cash_reserve=settings.default_min_cash_reserve,
            )
            session.add(default_settings)
            logger.info("Default bot settings seeded")


async def get_bot_settings() -> BotSettings:
    """Fetch current bot settings from DB."""
    async with get_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(BotSettings).limit(1))
        bot_settings = result.scalar_one_or_none()
        if not bot_settings:
            raise RuntimeError("Bot settings not found in DB. Run init_db() first.")
        return bot_settings


async def update_bot_setting(key: str, value) -> BotSettings:
    """Update a single bot setting and return updated settings."""
    async with get_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(BotSettings).limit(1))
        bot_settings = result.scalar_one()
        setattr(bot_settings, key, value)
        return bot_settings
