"""FastAPI backend for HKO Weather Trader dashboard."""
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Optional
import asyncio
import logging

from backend.config import settings
from backend.models.database import (
    get_db, init_db, SessionLocal,
    Signal, Trade, BotState, ScanLog
)
from backend.core.weather_signals import scan_for_weather_signals, WeatherTradingSignal
from backend.data.weather import fetch_ensemble_forecast, EnsembleForecast

from pydantic import BaseModel

app = FastAPI(
    title="HKO Weather Trader",
    description="Hong Kong Observatory weather prediction market trading bot",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("hko_trader")

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


ws_manager = ConnectionManager()


# Pydantic response models
class WeatherForecastResponse(BaseModel):
    city_key: str
    city_name: str
    target_date: str
    mean_high: float
    std_high: float
    mean_low: float
    std_low: float
    num_members: int
    ensemble_agreement: float


class WeatherSignalResponse(BaseModel):
    market_id: str
    city_key: str
    city_name: str
    target_date: str
    threshold_f: float
    metric: str
    direction: str
    model_probability: float
    market_probability: float
    edge: float
    confidence: float
    suggested_size: float
    reasoning: str
    ensemble_mean: float
    ensemble_std: float
    ensemble_members: int
    actionable: bool = False


class TradeResponse(BaseModel):
    id: int
    market_ticker: str
    platform: str
    event_slug: Optional[str] = None
    direction: str
    entry_price: float
    size: float
    timestamp: datetime
    settled: bool
    result: str
    pnl: Optional[float]


class BotStats(BaseModel):
    bankroll: float
    total_trades: int
    winning_trades: int
    win_rate: float
    total_pnl: float
    is_running: bool
    last_run: Optional[datetime]


class CalibrationBucket(BaseModel):
    bucket: str
    predicted_avg: float
    actual_rate: float
    count: int


class CalibrationSummary(BaseModel):
    total_signals: int
    total_with_outcome: int
    accuracy: float
    avg_predicted_edge: float
    avg_actual_edge: float
    brier_score: float


class DashboardData(BaseModel):
    stats: BotStats
    weather_signals: List[WeatherSignalResponse]
    weather_forecasts: List[WeatherForecastResponse]
    recent_trades: List[TradeResponse]
    equity_curve: List[dict]
    calibration: Optional[CalibrationSummary] = None


class EventResponse(BaseModel):
    timestamp: str
    type: str
    message: str
    data: dict = {}


# Startup / Shutdown
@app.on_event("startup")
async def startup():
    print("=" * 60)
    print("HKO WEATHER TRADER v1.0")
    print("=" * 60)
    print("Initializing database...")

    init_db()

    db = SessionLocal()
    try:
        state = db.query(BotState).first()
        if not state:
            state = BotState(
                bankroll=settings.INITIAL_BANKROLL,
                total_trades=0,
                winning_trades=0,
                total_pnl=0.0,
                is_running=True,
            )
            db.add(state)
            db.commit()
            print(f"Created bot state: ${settings.INITIAL_BANKROLL:,.2f} bankroll")
        else:
            state.is_running = True
            db.commit()
            print(f"Loaded bot state: ${state.bankroll:,.2f}, P&L ${state.total_pnl:+,.2f}, {state.total_trades} trades")
    finally:
        db.close()

    print(f"\nConfiguration:")
    print(f"  - Simulation: {settings.SIMULATION_MODE}")
    print(f"  - Min edge: {settings.WEATHER_MIN_EDGE_THRESHOLD:.0%}")
    print(f"  - Kelly: quarter-Kelly")
    print(f"  - Scan: every {settings.WEATHER_SCAN_INTERVAL_SECONDS}s")
    print(f"  - Cities: {settings.WEATHER_CITIES}")
    print("=" * 60)

    from backend.core.scheduler import start_scheduler, log_event
    start_scheduler()
    log_event("success", "HKO Weather Trader initialized")


@app.on_event("shutdown")
async def shutdown():
    from backend.core.scheduler import stop_scheduler
    stop_scheduler()


# Core endpoints
@app.get("/")
async def root():
    return {"status": "ok", "message": "HKO Weather Trader API", "simulation_mode": settings.SIMULATION_MODE}


@app.get("/api/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/stats", response_model=BotStats)
async def get_stats(db: Session = Depends(get_db)):
    state = db.query(BotState).first()
    if not state:
        raise HTTPException(status_code=404, detail="Bot state not initialized")

    win_rate = state.winning_trades / state.total_trades if state.total_trades > 0 else 0

    return BotStats(
        bankroll=state.bankroll,
        total_trades=state.total_trades,
        winning_trades=state.winning_trades,
        win_rate=win_rate,
        total_pnl=state.total_pnl,
        is_running=state.is_running,
        last_run=state.last_run,
    )


@app.get("/api/dashboard", response_model=DashboardData)
async def get_dashboard(db: Session = Depends(get_db)):
    """Get all dashboard data in one call."""
    # Stats
    state = db.query(BotState).first()
    win_rate = state.winning_trades / state.total_trades if state.total_trades > 0 else 0
    stats = BotStats(
        bankroll=state.bankroll,
        total_trades=state.total_trades,
        winning_trades=state.winning_trades,
        win_rate=win_rate,
        total_pnl=state.total_pnl,
        is_running=state.is_running,
        last_run=state.last_run,
    )

    # Weather signals
    signals = []
    try:
        all_signals = await scan_for_weather_signals()
        signals = [_weather_signal_to_response(s) for s in all_signals]
    except Exception as e:
        logger.warning(f"Failed to scan weather signals: {e}")

    # Weather forecasts
    forecasts = []
    try:
        from backend.data.weather import CITY_CONFIG
        city_keys = [c.strip() for c in settings.WEATHER_CITIES.split(",") if c.strip()]
        for city_key in city_keys:
            forecast = await fetch_ensemble_forecast(city_key)
            if forecast:
                forecasts.append(WeatherForecastResponse(
                    city_key=forecast.city_key,
                    city_name=forecast.city_name,
                    target_date=forecast.target_date.isoformat(),
                    mean_high=forecast.mean_high,
                    std_high=forecast.std_high,
                    mean_low=forecast.mean_low,
                    std_low=forecast.std_low,
                    num_members=forecast.num_members,
                    ensemble_agreement=forecast.ensemble_agreement,
                ))
    except Exception as e:
        logger.warning(f"Failed to fetch forecasts: {e}")

    # Recent trades
    trades = db.query(Trade).order_by(Trade.timestamp.desc()).limit(20).all()
    recent_trades = [TradeResponse(
        id=t.id,
        market_ticker=t.market_ticker,
        platform=t.platform,
        event_slug=t.event_slug,
        direction=t.direction,
        entry_price=t.entry_price,
        size=t.size,
        timestamp=t.timestamp,
        settled=t.settled,
        result=t.result,
        pnl=t.pnl,
    ) for t in trades]

    # Equity curve
    settled_trades = db.query(Trade).filter(Trade.settled == True).order_by(Trade.timestamp).all()
    curve = []
    cumulative_pnl = 0
    for t in settled_trades:
        if t.pnl is not None:
            cumulative_pnl += t.pnl
            curve.append({
                "timestamp": t.timestamp.isoformat(),
                "pnl": cumulative_pnl,
                "bankroll": settings.INITIAL_BANKROLL + cumulative_pnl,
                "trade_id": t.id,
            })

    # Calibration
    calibration = _get_calibration_summary(db)

    return DashboardData(
        stats=stats,
        weather_signals=signals,
        weather_forecasts=forecasts,
        recent_trades=recent_trades,
        equity_curve=curve,
        calibration=calibration,
    )


@app.get("/api/weather/signals", response_model=List[WeatherSignalResponse])
async def get_weather_signals():
    """Get current weather trading signals."""
    try:
        signals = await scan_for_weather_signals()
        return [_weather_signal_to_response(s) for s in signals]
    except Exception:
        return []


@app.get("/api/weather/forecasts", response_model=List[WeatherForecastResponse])
async def get_weather_forecasts():
    """Get ensemble forecasts for all tracked cities."""
    from backend.data.weather import CITY_CONFIG
    city_keys = [c.strip() for c in settings.WEATHER_CITIES.split(",") if c.strip()]
    forecasts = []
    for city_key in city_keys:
        forecast = await fetch_ensemble_forecast(city_key)
        if forecast:
            forecasts.append(WeatherForecastResponse(
                city_key=forecast.city_key,
                city_name=forecast.city_name,
                target_date=forecast.target_date.isoformat(),
                mean_high=forecast.mean_high,
                std_high=forecast.std_high,
                mean_low=forecast.mean_low,
                std_low=forecast.std_low,
                num_members=forecast.num_members,
                ensemble_agreement=forecast.ensemble_agreement,
            ))
    return forecasts


@app.get("/api/trades", response_model=List[TradeResponse])
async def get_trades(limit: int = 50, db: Session = Depends(get_db)):
    trades = db.query(Trade).order_by(Trade.timestamp.desc()).limit(limit).all()
    return [TradeResponse(
        id=t.id, market_ticker=t.market_ticker, platform=t.platform,
        event_slug=t.event_slug, direction=t.direction, entry_price=t.entry_price,
        size=t.size, timestamp=t.timestamp, settled=t.settled, result=t.result, pnl=t.pnl,
    ) for t in trades]


@app.get("/api/equity-curve")
async def get_equity_curve(db: Session = Depends(get_db)):
    trades = db.query(Trade).filter(Trade.settled == True).order_by(Trade.timestamp).all()
    curve = []
    cumulative_pnl = 0
    for t in trades:
        if t.pnl is not None:
            cumulative_pnl += t.pnl
            curve.append({
                "timestamp": t.timestamp.isoformat(),
                "pnl": cumulative_pnl,
                "bankroll": settings.INITIAL_BANKROLL + cumulative_pnl,
            })
    return curve


@app.get("/api/calibration", response_model=Optional[CalibrationSummary])
async def get_calibration(db: Session = Depends(get_db)):
    return _get_calibration_summary(db)


@app.post("/api/run-scan")
async def run_scan(db: Session = Depends(get_db)):
    from backend.core.scheduler import run_manual_scan, log_event

    state = db.query(BotState).first()
    if state:
        state.last_run = datetime.utcnow()
        db.commit()

    log_event("info", "Manual scan triggered (Weather)")
    await run_manual_scan()

    return {"status": "ok"}


@app.post("/api/simulate-trade")
async def simulate_trade(signal_market_id: str, db: Session = Depends(get_db)):
    from backend.core.scheduler import log_event

    signals = await scan_for_weather_signals()
    signal = next((s for s in signals if s.market.market_id == signal_market_id), None)

    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    state = db.query(BotState).first()
    if not state:
        raise HTTPException(status_code=500, detail="Bot state not initialized")

    entry_price = signal.market.yes_price if signal.direction == "yes" else signal.market.no_price

    trade = Trade(
        market_ticker=signal.market.market_id,
        platform="polymarket",
        event_slug=signal.market.slug,
        market_type="weather",
        direction=signal.direction,
        entry_price=entry_price,
        size=min(signal.suggested_size, state.bankroll * 0.05),
        model_probability=signal.model_probability,
        market_price_at_entry=signal.market_probability,
        edge_at_entry=signal.edge,
    )

    db.add(trade)
    state.total_trades += 1
    db.commit()

    log_event("trade", f"Manual WX trade: {signal.direction.upper()} {signal.market.city_name}")
    return {"status": "ok", "trade_id": trade.id, "size": trade.size}


@app.post("/api/bot/start")
async def start_bot(db: Session = Depends(get_db)):
    from backend.core.scheduler import log_event
    state = db.query(BotState).first()
    if state:
        state.is_running = True
        db.commit()
    log_event("success", "Bot started")
    return {"status": "running"}


@app.post("/api/bot/stop")
async def stop_bot(db: Session = Depends(get_db)):
    from backend.core.scheduler import log_event
    state = db.query(BotState).first()
    if state:
        state.is_running = False
        db.commit()
    log_event("info", "Bot stopped")
    return {"status": "stopped"}


@app.post("/api/bot/reset")
async def reset_bot(db: Session = Depends(get_db)):
    from backend.core.scheduler import log_event
    state = db.query(BotState).first()
    if state:
        state.bankroll = settings.INITIAL_BANKROLL
        state.total_trades = 0
        state.winning_trades = 0
        state.total_pnl = 0.0
        db.commit()
    log_event("info", "Bot state reset")
    return {"status": "reset"}


@app.get("/api/events", response_model=List[EventResponse])
async def get_events(limit: int = 50):
    from backend.core.scheduler import get_recent_events
    events = get_recent_events(limit)
    return [EventResponse(**e) for e in events]


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# Helper functions
def _weather_signal_to_response(s: WeatherTradingSignal) -> WeatherSignalResponse:
    return WeatherSignalResponse(
        market_id=s.market.market_id,
        city_key=s.market.city_key,
        city_name=s.market.city_name,
        target_date=s.market.target_date.isoformat(),
        threshold_f=s.market.threshold_f,
        metric=s.market.metric,
        direction=s.market.direction,
        model_probability=s.model_probability,
        market_probability=s.market_probability,
        edge=s.edge,
        confidence=s.confidence,
        suggested_size=s.suggested_size,
        reasoning=s.reasoning,
        ensemble_mean=s.ensemble_mean,
        ensemble_std=s.ensemble_std,
        ensemble_members=s.ensemble_members,
        actionable=s.passes_threshold,
    )


def _get_calibration_summary(db: Session) -> Optional[CalibrationSummary]:
    """Calculate Brier score and calibration metrics."""
    signals_with_outcome = db.query(Signal).filter(
        Signal.outcome_correct != None,
        Signal.settled_at != None,
    ).all()

    if not signals_with_outcome:
        return None

    total = len(signals_with_outcome)
    correct = sum(1 for s in signals_with_outcome if s.outcome_correct)
    accuracy = correct / total

    predicted_probs = []
    actual_probs = []
    for s in signals_with_outcome:
        predicted_probs.append(s.model_probability)
        actual_probs.append(1.0 if s.outcome_correct else 0.0)

    # Brier score
    brier = sum((p - a) ** 2 for p, a in zip(predicted_probs, actual_probs)) / total

    avg_predicted_edge = sum(abs(s.edge) for s in signals_with_outcome) / total
    avg_actual_edge = abs(accuracy - 0.5) * 2  # simplified

    return CalibrationSummary(
        total_signals=total,
        total_with_outcome=total,
        accuracy=accuracy,
        avg_predicted_edge=avg_predicted_edge,
        avg_actual_edge=avg_actual_edge,
        brier_score=brier,
    )
