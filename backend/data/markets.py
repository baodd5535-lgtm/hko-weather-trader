"""Market data types - simplified for weather trading."""
import logging
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MarketData:
    """Structured market data for weather prediction markets."""
    platform: str
    ticker: str
    title: str
    category: str
    subcategory: Optional[str]

    yes_price: float  # 0-1 (Yes price)
    no_price: float   # (No price)
    volume: float
    settlement_time: Optional[datetime]

    threshold: Optional[float] = None
    direction: Optional[str] = None
    metric: Optional[str] = None  # "high" or "low" for weather

    event_slug: Optional[str] = None


async def fetch_all_markets(**kwargs) -> List[MarketData]:
    """Fetch all markets - currently only weather markets."""
    # Weather markets are fetched directly in weather_signals.py
    return []
