from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = Field(default="development", alias="ENVIRONMENT")
    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")
    public_url: str = Field(default="http://localhost:5173", alias="PUBLIC_URL")
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        alias="CORS_ORIGINS",
    )

    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    database_migration_url: str | None = Field(default=None, alias="DATABASE_MIGRATION_URL")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    access_token_expire_seconds: int = Field(default=900, alias="ACCESS_TOKEN_EXPIRE_SECONDS")
    refresh_token_expire_days: int = Field(default=30, alias="REFRESH_TOKEN_EXPIRE_DAYS")
    email_from: str = Field(default="notifications@leovee.example.com", alias="EMAIL_FROM")
    resend_api_key: str | None = Field(default=None, alias="RESEND_API_KEY")

    auth_rate_limit_login: int = Field(default=10, alias="AUTH_RATE_LIMIT_LOGIN")
    auth_rate_limit_signup: int = Field(default=5, alias="AUTH_RATE_LIMIT_SIGNUP")
    auth_rate_limit_password_reset: int = Field(default=3, alias="AUTH_RATE_LIMIT_PASSWORD_RESET")

    oanda_api_token: str | None = Field(default=None, alias="OANDA_API_TOKEN")
    oanda_account_id: str | None = Field(default=None, alias="OANDA_ACCOUNT_ID")
    oanda_environment: str = Field(default="practice", alias="OANDA_ENVIRONMENT")
    oanda_api_url: str | None = Field(default=None, alias="OANDA_API_URL")
    oanda_stream_url: str | None = Field(default=None, alias="OANDA_STREAM_URL")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    finnhub_api_key: str | None = Field(default=None, alias="FINNHUB_API_KEY")

    billing_provider: str = Field(default="manual", alias="BILLING_PROVIDER")
    stripe_secret_key: str | None = Field(default=None, alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = Field(default=None, alias="STRIPE_WEBHOOK_SECRET")

    memory_min_sample: int = Field(default=20, alias="MEMORY_MIN_SAMPLE")
    strategy_decay_threshold_avg_r: float = Field(
        default=0.5,
        alias="STRATEGY_DECAY_THRESHOLD_AVG_R",
    )
    strategy_decay_min_trades: int = Field(default=10, alias="STRATEGY_DECAY_MIN_TRADES")

    candle_retention_m1_days: int = Field(default=365, alias="CANDLE_RETENTION_M1_DAYS")
    candle_retention_m5_days: int = Field(default=1095, alias="CANDLE_RETENTION_M5_DAYS")
    candle_retention_m15_days: int = Field(default=1095, alias="CANDLE_RETENTION_M15_DAYS")
    candle_retention_m30_days: int = Field(default=1095, alias="CANDLE_RETENTION_M30_DAYS")
    candle_retention_h1_days: int = Field(default=3650, alias="CANDLE_RETENTION_H1_DAYS")
    candle_retention_h4_days: int = Field(default=3650, alias="CANDLE_RETENTION_H4_DAYS")
    candle_retention_d1_days: int = Field(default=3650, alias="CANDLE_RETENTION_D1_DAYS")

    @property
    def oanda_rest_base_url(self) -> str:
        if self.oanda_api_url:
            return self.oanda_api_url.rstrip("/")
        if self.oanda_environment == "live":
            return "https://api-fxtrade.oanda.com"
        return "https://api-fxpractice.oanda.com"

    @property
    def oanda_stream_base_url(self) -> str:
        if self.oanda_stream_url:
            return self.oanda_stream_url.rstrip("/")
        if self.oanda_environment == "live":
            return "https://stream-fxtrade.oanda.com"
        return "https://stream-fxpractice.oanda.com"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
