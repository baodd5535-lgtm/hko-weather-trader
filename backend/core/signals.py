"""Signal utility functions for weather trading."""
import logging
from datetime import datetime
from typing import Optional

from backend.config import settings
from backend.models.database import SessionLocal, Signal

logger = logging.getLogger("trading_bot")


def calculate_edge(
    model_prob: float,
    market_price: float,
) -> tuple[float, str]:
    """
    Calculate edge and determine direction.

    Returns:
        (edge, direction) where direction is "up" or "down"
    """
    up_edge = model_prob - market_price
    down_edge = (1 - model_prob) - (1 - market_price)

    if up_edge >= down_edge:
        return up_edge, "up"
    else:
        return down_edge, "down"


def calculate_kelly_size(
    edge: float,
    probability: float,
    market_price: float,
    direction: str,
    bankroll: float,
) -> float:
    """
    Calculate position size using quarter-Kelly criterion.

    Kelly formula: f = (p * b - q) / b
    where:
        f = fraction of bankroll to bet
        p = probability of winning
        q = probability of losing (1 - p)
        b = odds (payout ratio)
    """
    if direction == "up":
        win_prob = probability
        price = market_price
    else:
        win_prob = 1 - probability
        price = 1 - market_price

    if price <= 0 or price >= 1:
        return 0

    odds = (1 - price) / price
    lose_prob = 1 - win_prob
    kelly = (win_prob * odds - lose_prob) / odds

    # Quarter-Kelly (conservative)
    kelly *= 0.25

    # Cap at maximum per-trade limit
    max_fraction = 0.05  # 5% max per trade
    kelly = min(kelly, max_fraction)
    kelly = max(kelly, 0)

    size = kelly * bankroll
    size = min(size, settings.WEATHER_MAX_TRADE_SIZE)

    return size


def _persist_signals(signals: list):
    """Save signals with non-zero edge to DB, deduplicating on (market_ticker, timestamp)."""
    to_save = [s for s in signals if abs(getattr(s, 'edge', 0)) > 0]
    if not to_save:
        return

    db = SessionLocal()
    try:
        for signal in to_save:
            existing = db.query(Signal).filter(
                Signal.market_ticker == getattr(signal, 'market_id', ''),
                Signal.timestamp >= signal.timestamp.replace(second=0, microsecond=0),
            ).first()
            if existing:
                continue

            db_signal = Signal(
                market_ticker=getattr(signal, 'market_id', ''),
                platform=getattr(signal, 'platform', 'polymarket'),
                market_type="weather",
                timestamp=getattr(signal, 'timestamp', datetime.utcnow()),
                direction=getattr(signal, 'direction', ''),
                model_probability=getattr(signal, 'model_probability', 0.5),
                market_price=getattr(signal, 'market_probability', 0.5),
                edge=getattr(signal, 'edge', 0.0),
                confidence=getattr(signal, 'confidence', 0.5),
                kelly_fraction=getattr(signal, 'kelly_fraction', 0.0),
                suggested_size=getattr(signal, 'suggested_size', 0.0),
                sources=getattr(signal, 'sources', []),
                reasoning=getattr(signal, 'reasoning', ''),
                executed=False,
            )
            db.add(db_signal)

        db.commit()
    except Exception as e:
        logger.warning(f"Failed to persist signals: {e}")
        db.rollback()
    finally:
        db.close()
