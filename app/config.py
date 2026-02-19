"""
Application configuration.
All settings loaded from environment variables (.env file).
Trading defaults are used only for initial DB seeding.
Runtime settings are stored in DB and changeable via Telegram.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # === IB Gateway ===
    ib_host: str = Field(default="127.0.0.1")
    ib_port: int = Field(default=4002)  # 4002=Paper, 4001=Live
    ib_client_id: int = Field(default=1)

    # === Webhook Security ===
    webhook_secret: str = Field(default="change_me")
    webhook_port: int = Field(default=8000)

    # === Telegram ===
    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")

    # === Database ===
    database_url: str = Field(
        default="postgresql+asyncpg://tradingbot:changeme@localhost:5432/tradingbot"
    )

    # === Redis ===
    redis_url: str = Field(default="redis://localhost:6379/0")

    # === Trading Defaults (initial values, runtime values stored in DB) ===
    default_buy_amount_usd: float = Field(default=300.0)
    default_max_open_positions: int = Field(default=200)
    default_max_daily_buys: int = Field(default=80)
    default_max_total_investment: float = Field(default=90000.0)
    default_max_per_ticker: int = Field(default=5)
    default_max_daily_loss: float = Field(default=5000.0)
    default_min_cash_reserve: float = Field(default=1000.0)

    # === IB Order Settings ===
    order_timeout_seconds: int = Field(default=30)
    max_orders_per_second: int = Field(default=10)

    # === Market Hours (US Eastern) ===
    market_open_hour: int = Field(default=9)
    market_open_minute: int = Field(default=30)
    market_close_hour: int = Field(default=16)
    market_close_minute: int = Field(default=0)

    # === TradingView Allowed IPs ===
    tv_allowed_ips: str = Field(
        default="52.89.214.238,34.212.75.30,34.222.187.21,52.32.178.7"
    )

    @property
    def tv_ip_list(self) -> list[str]:
        """Parse comma-separated TV IPs into a list."""
        return [ip.strip() for ip in self.tv_allowed_ips.split(",") if ip.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Singleton
settings = Settings()
