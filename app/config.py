"""
Application configuration.
All settings loaded from environment variables (.env file).
Trading defaults are used only for initial DB seeding.
Runtime settings are stored in DB and changeable via Telegram.
"""

from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # === IB Gateway ===
    ib_host: str = Field(default="127.0.0.1")
    ib_port: int = Field(default=4002)  # 4002=Paper, 4001=Live
    ib_client_id: int = Field(default=1)

    # === Broker Routing ===
    # ib_only | kis_only | dual_failover
    broker_mode: str = Field(default="kis_only")
    primary_broker: str = Field(default="kis")
    secondary_broker: str = Field(default="ib")

    # === KIS Open API (optional, for dual broker mode) ===
    kis_base_url: str = Field(default="")
    kis_app_key: str = Field(default="")
    kis_app_secret: str = Field(default="")
    kis_account_no: str = Field(default="")
    kis_account_product_code: str = Field(default="01")
    kis_token_cache_path: str = Field(default=".runtime/kis_access_token.json")
    kis_quote_exchange_code: str = Field(default="NAS")
    kis_order_exchange_code: str = Field(default="NASD")
    kis_quote_path: str = Field(default="/uapi/overseas-price/v1/quotations/price")
    kis_order_path: str = Field(default="/uapi/overseas-stock/v1/trading/order")
    kis_quote_tr_id: str = Field(default="HHDFS00000300")
    kis_buy_tr_id: str = Field(default="TTTT1002U")
    kis_sell_tr_id: str = Field(default="TTTT1006U")
    kis_custtype: str = Field(default="P")
    kis_target_buy_krw: float = Field(default=100000.0)
    kis_domestic_enabled: bool = Field(default=True)
    kis_domestic_market_div_code: str = Field(default="J")  # J: KRX, NX: NXT, UN: integrated
    kis_domestic_exchange_code: str = Field(default="KRX")
    kis_domestic_quote_path: str = Field(default="/uapi/domestic-stock/v1/quotations/inquire-price-2")
    kis_domestic_order_path: str = Field(default="/uapi/domestic-stock/v1/trading/order-cash")
    kis_domestic_target_buy_krw: float = Field(default=100000.0)
    kis_domestic_min_cash_reserve_krw: float = Field(default=0.0)
    sell_only_if_profit: bool = Field(default=True)
    sell_min_profit_pct: float = Field(default=0.0)
    kis_get_retry_count: int = Field(default=4)
    kis_get_retry_delay_seconds: float = Field(default=0.75)
    kis_get_retry_max_delay_seconds: float = Field(default=6.0)
    kis_buy_limit_markup_pct: float = Field(default=3.0)
    kis_sell_limit_markdown_pct: float = Field(default=1.0)
    kis_order_post_retry_count: int = Field(default=1)
    kis_order_post_retry_delay_seconds: float = Field(default=2.0)

    # Comma-separated YYYY-MM-DD values. Keep these configurable because
    # exchange holiday schedules can change and KIS remains the final guard.
    market_holidays_us: str = Field(default="")
    market_holidays_krx: str = Field(default="")
    market_holidays_hkex: str = Field(default="")
    market_holidays_sse: str = Field(default="")
    market_holidays_szse: str = Field(default="")
    market_holidays_tse: str = Field(default="")

    # 4h/4h strategy: a signal queued outside market hours should survive
    # normal overnight/weekend gaps, but not remain valid indefinitely.
    pending_order_ttl_hours: float = Field(default=96.0)

    # === Webhook Security ===
    webhook_secret: str = Field(default="change_me")
    webhook_port: int = Field(default=8000)
    webhook_allow_any_ip: bool = Field(default=False)
    trusted_proxy_ips: str = Field(default="127.0.0.1,::1,172.17.0.1,172.18.0.1")
    allowed_tickers: str = Field(default="")
    allow_sell_for_open_positions_outside_allowlist: bool = Field(default=True)
    webhook_enqueue_timeout_seconds: float = Field(default=1.0)
    webhook_idempotency_ttl_seconds: int = Field(default=604800)
    webhook_slow_request_ms: int = Field(default=1000)
    telegram_verbose_webhook_alerts: bool = Field(default=False)

    # === Telegram ===
    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")

    # === Database ===
    database_url: str = Field(
        default="postgresql+asyncpg://tradingbot:changeme@localhost:5432/tradingbot"
    )

    # === Redis ===
    redis_url: str = Field(default="redis://localhost:6379/0")

    # === Site Monitoring ===
    site_monitor_enabled: bool = Field(default=True)
    site_monitor_base_url: str = Field(default="http://127.0.0.1:8000")
    site_monitor_timeout_seconds: float = Field(default=5.0)
    site_monitor_slow_ms: int = Field(default=1800)
    site_monitor_state_path: str = Field(default="")
    site_monitor_report_path: str = Field(default="")

    # === Platform Web / OAuth ===
    platform_public_base_url: str = Field(default="")
    platform_oauth_state_secret: str = Field(default="change_me_platform_oauth")
    google_oauth_client_id: str = Field(default="")
    google_oauth_client_secret: str = Field(default="")
    x_oauth_client_id: str = Field(default="")
    x_oauth_client_secret: str = Field(default="")
    apple_oauth_client_id: str = Field(default="")
    apple_oauth_client_secret: str = Field(default="")

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
    max_order_retries: int = Field(default=3)

    # === Market Hours (US Eastern) ===
    market_open_hour: int = Field(default=9)
    market_open_minute: int = Field(default=30)
    market_close_hour: int = Field(default=16)
    market_close_minute: int = Field(default=0)

    # === TradingView Allowed IPs ===
    tv_allowed_ips: str = Field(
        default="52.89.214.238,34.212.75.30,54.218.53.128,52.32.178.7"
    )

    @property
    def tv_ip_list(self) -> list[str]:
        """Parse comma-separated TV IPs into a list."""
        return [ip.strip() for ip in self.tv_allowed_ips.split(",") if ip.strip()]

    @property
    def trusted_proxy_ip_list(self) -> list[str]:
        """Parse comma-separated trusted reverse proxy IPs into a list."""
        return [ip.strip() for ip in self.trusted_proxy_ips.split(",") if ip.strip()]

    @property
    def allowed_ticker_list(self) -> list[str]:
        """Parse optional comma-separated allowlist. Empty means allow all."""
        return [t.strip().upper() for t in self.allowed_tickers.split(",") if t.strip()]

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Singleton
settings = Settings()
