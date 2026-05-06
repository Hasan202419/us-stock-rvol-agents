from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class JarvisSettings(BaseSettings):
    """Umumiy `.env` — MASTER_PLAN va mavjud RVOL loyiha o‘zgaruvchilari."""

    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: Optional[str] = Field(None, validation_alias="OPENAI_API_KEY")
    polygon_api_key: Optional[str] = Field(None, validation_alias="POLYGON_API_KEY")
    finnhub_api_key: Optional[str] = Field(None, validation_alias="FINNHUB_API_KEY")

    alpaca_api_key: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("ALPACA_API_KEY", "ALPACA_KEY_ID"),
    )
    alpaca_secret_key: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("ALPACA_SECRET_KEY", "ALPACA_SECRET"),
    )
    alpaca_base_url: str = Field(
        "https://paper-api.alpaca.markets",
        validation_alias="ALPACA_BASE_URL",
    )
    alpaca_data_url: str = Field(
        "https://data.alpaca.markets",
        validation_alias="ALPACA_DATA_URL",
    )

    zoya_api_key: Optional[str] = Field(None, validation_alias="ZOYA_API_KEY")

    deepseek_api_key: Optional[str] = Field(None, validation_alias="DEEPSEEK_API_KEY")

    telegram_bot_token: Optional[str] = Field(None, validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(None, validation_alias="TELEGRAM_CHAT_ID")

    fmp_api_key: Optional[str] = Field(None, validation_alias="FMP_API_KEY")
    newsapi_key: Optional[str] = Field(None, validation_alias="NEWSAPI_KEY")

    finviz_elite_auth: Optional[str] = Field(None, validation_alias="FINVIZ_ELITE_AUTH")
    finviz_elite_export_query: Optional[str] = Field(None, validation_alias="FINVIZ_ELITE_EXPORT_QUERY")

    trading_mode: str = Field("paper", validation_alias="TRADING_MODE")

    database_url: str = Field(
        "sqlite:///jarvis.db",
        validation_alias="DATABASE_URL",
    )

    capital: float = Field(10_000.0, validation_alias=AliasChoices("CAPITAL", "ACCOUNT_SIZE"))

    max_risk_pct: float = Field(1.0, validation_alias="MAX_RISK_PCT")
    max_daily_loss_pct: float = Field(2.0, validation_alias=AliasChoices("MAX_DAILY_LOSS_PCT", "MAX_DAILY_RISK_PCT"))

    halal_max_debt_ratio: float = Field(0.30, validation_alias="HALAL_MAX_DEBT_RATIO")
    halal_max_impure_rev: float = Field(0.05, validation_alias="HALAL_MAX_IMPURE_REV")
    halal_max_cash_ratio: float = Field(0.30, validation_alias="HALAL_MAX_CASH_RATIO")


@lru_cache
def get_settings() -> JarvisSettings:
    return JarvisSettings()
