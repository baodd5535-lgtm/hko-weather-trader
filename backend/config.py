"""Configuration settings for HKO Weather Trader."""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database (SQLite)
    DATABASE_URL: str = "sqlite:///./tradingbot.db"

    # Bot settings — Weather-only trading
    SIMULATION_MODE: bool = True
    INITIAL_BANKROLL: float = 10000.0
    KELLY_FRACTION: float = 0.25  # Quarter-Kelly (conservative)

    # Weather trading settings
    WEATHER_ENABLED: bool = True
    WEATHER_SCAN_INTERVAL_SECONDS: int = 900  # 15 min
    WEATHER_SETTLEMENT_INTERVAL_SECONDS: int = 1800  # 30 min
    WEATHER_MIN_EDGE_THRESHOLD: float = 0.08  # 8% — weather has more signal
    WEATHER_MAX_ENTRY_PRICE: float = 0.70
    WEATHER_MAX_TRADE_SIZE: float = 100.0
    WEATHER_CITIES: str = "hko"

    # Risk management
    DAILY_LOSS_LIMIT: float = 300.0
    MAX_TOTAL_PENDING_TRADES: int = 20

    # Polymarket CLOB (for real trading)
    POLYGON_WALLET_PRIVATE_KEY: Optional[str] = None
    POLYMARKET_API_KEY: Optional[str] = None
    POLYMARKET_SECRET: Optional[str] = None
    POLYMARKET_PASSPHRASE: Optional[str] = None

    # Notifications
    DISCORD_WEBHOOK_URL: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None

    # Kill switch — create this file to stop all trading
    KILL_SWITCH_PATH: str = "/tmp/HKO_WEATHER_TRADER_STOP"

    class Config:
        env_file = ".env"


settings = Settings()
