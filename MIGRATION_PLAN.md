# HKO Weather Trader — Feature Migration Plan

## Goal
Rebuild the HKO weather trading system from scratch using `suislanchez/polymarket-kalshi-weather-bot` as the clean codebase foundation, incorporating best features from `sahnia3/polymarket-agent` and `nicolastinkl/hermes_weatherbot`, plus all HKO-specific features from the existing `hko-monitor` project.

## Target Repos

| # | Repo | Role | URL |
|---|------|------|-----|
| **BASE** | `suislanchez/polymarket-kalshi-weather-bot` | Clean architecture, React dashboard, FastAPI backend, ensemble weather signals, Kelly sizing, calibration | https://github.com/suislanchez/polymarket-kalshi-weather-bot |
| **PROVEN** | `sahnia3/polymarket-agent` | Production-proven: 139-member ensemble (4 sources), Platt calibration, adaptive per-city gates, real CLOB execution, audit trail, Discord reports | https://github.com/sahnia3/polymarket-agent |
| **SIMPLE** | `nicolastinkl/hermes_weatherbot` | Self-learning parameter tuning, Telegram notifications, Gaussian bucket model | https://github.com/nicolastinkl/hermes_weatherbot |
| **CURRENT** | `baodd5535-lgtm/hko-monitor` | HKO-specific features to preserve: multi-station data, multi-factor scoring, empirical error model, real-time orderbook WS, 3-trigger engine | https://github.com/baodd5535-lgtm/hko-monitor |

Target fork: `baodd5535-lgtm/hko-weather-trader` (cloned at `/shared-hermes/hko-weather-trader`)

---

## Feature Matrix — What to Keep vs Replace

### ✅ KEEP from BASE (`suislanchez`)
| Feature | Module | Status |
|---------|--------|--------|
| FastAPI backend structure | `backend/api/main.py`, `backend/config.py` | Keep as-is |
| React + TypeScript dashboard | `frontend/` | Keep as-is |
| Open-Meteo ensemble fetcher | `backend/data/weather.py` | **Upgrade** to 139-member (see PROVEN) |
| Weather signal generation | `backend/core/weather_signals.py` | Keep logic, swap data source |
| Weather market fetcher | `backend/data/weather_markets.py` | Keep logic, add HKO city |
| Signal scheduler | `backend/core/scheduler.py` | Keep, add HKO triggers |
| Settlement engine | `backend/core/settlement.py` | Keep |
| SQLite + SQLAlchemy models | `backend/models/database.py` | **Extend** with audit tables (see PROVEN) |
| Kelly criterion sizing | `backend/core/signals.py` | Keep, upgrade to quarter-Kelly |
| Brier score calibration | `backend/core/calibration` | Keep, add Platt calibration |
| Config system (pydantic) | `backend/config.py` | Extend with new settings |

### 🗑️ REMOVE from BASE (`suislanchez`)
| Feature | Module | Reason |
|---------|--------|--------|
| BTC 5-min strategy | `backend/core/signals.py` (BTC parts), `backend/data/crypto.py`, `backend/data/btc_markets.py` | Not relevant |
| Kalshi integration | `backend/data/kalshi_client.py`, `backend/data/kalshi_markets.py` | Not relevant |
| BTC-specific React components | `frontend/src/components/MicrostructurePanel.tsx`, `GlobeView.tsx` (BTC parts) | Not relevant |
| AI/Groq integration | `backend/ai/` | Replace with ensemble-only approach |

### ➕ ADD from PROVEN (`sahnia3/polymarket-agent`)
| Feature | Source File | Integration |
|---------|-------------|-------------|
| 139-member ensemble (GFS+ECMWF+ICON+GEM) | `core/data_feeds.py` | Replace Open-Meteo 31-member fetcher |
| Platt calibration (10% shrinkage) | `core/weather_trader.py` | Add to signal generation |
| Adaptive per-city edge gates | `scripts/adapt_weather_gates.py` | Add as new module |
| Real CLOB execution | `core/market_client.py`, `agents/trader.py` | Add as new module |
| Full audit trail (6 tables) | `db/models.py` | Extend database schema |
| Daily PDF reports | `scripts/cro_report.py` | Add as scheduled task |
| Discord webhook integration | N/A | Add to config |
| Quarter-Kelly sizing | `core/strategy.py` | Replace current Kelly |
| Risk management (11 checks) | `agents/risk_manager.py` | Add as new module |
| Kill switch | `config.py` | Add to config |

### ➕ ADD from SIMPLE (`nicolastinkl/hermes_weatherbot`)
| Feature | Source | Integration |
|---------|--------|-------------|
| Self-learning parameter tuning | `data/learning/` | Add adaptive module |
| Telegram notifications | Config | Add to config (optional) |

### ➕ PRESERVE from CURRENT (`hko-monitor`)
| Feature | Source File | Integration |
|---------|-------------|-------------|
| HKO forecast parser | `hko_weather_monitor/parse_hko.py` | Add as new module |
| HKO forecast fetcher | `hko_weather_monitor/fetcher.py` | Add as new module |
| Multi-station readings | `hko_weather_monitor/db.py` (readings table) | Extend DB schema |
| Multi-factor weather scoring | `hko_weather_monitor/factors.py` | Integrate into signal generation |
| UV index tracking | `hko_weather_monitor/uv_fetcher.py` | Integrate into multi-factor |
| Empirical error model | `hko_weather_monitor/empirical_model.py` | Replace/enhance Platt calibration with HKO-specific errors |
| Real-time orderbook WebSocket | `hko_weather_monitor/orderbook_manager.py` | Add to engine |
| Three-trigger engine | `hko_weather_monitor/engine.py` | Replace scheduler with hybrid approach |
| Paper execution engine | `hko_weather_monitor/execution_engine.py` | Extend BASE settlement engine |
| Backtester | `hko_weather_monitor/backtester.py`, `weather_backtester.py` | Add as new module |
| Slippage calculator | `hko_weather_monitor/slippage.py` | Add to execution |
| Temporal tracker | `hko_weather_monitor/temporal_tracker.py` | Add to signal generation |
| Station correlations | `hko_weather_monitor/station_correlations.py` | Add to multi-station analysis |

---

## HKO-Specific Customizations

### 1. City Configuration
Add Hong Kong to `CITY_CONFIG`:
```python
"hko": {
    "name": "Hong Kong",
    "lat": 22.3080,
    "lon": 114.1700,
    "hko_stations": ["CCH", "KTN", "APT", "SKT", "SSC", "WTT", "KLT"],
    "primary_station": "CCH",  # Cheung Chau
}
```

### 2. HKO Forecast Integration
- Fetch HKO daily forecasts via `fetcher.py`
- Fetch per-minute readings for empirical calibration
- Parse HKO datetime format (YYYYMMDDHHmm)
- Multi-station ensemble (average across all available stations)

### 3. Multi-Factor Scoring
- Temperature + humidity + wind speed/direction + rainfall + cloud cover + UV index
- HKO weather codes mapped to cloud coverage
- UV spline peak prediction for temperature adjustment

### 4. Empirical Error Model
- Historical HKO forecast errors (computed from DB)
- Seasonal filtering (±30 days of target date)
- Fat-tail handling via bootstrap
- Replace/augment Platt calibration with HKO-specific error distributions

### 5. Polymarket HK Weather Markets
- Target: Polymarket markets about Hong Kong daily high temperature
- Parse market titles for "Hong Kong" + temperature thresholds
- Add to `CITY_ALIASES` in `weather_markets.py`

---

## Proposed Architecture (Final)

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                             │
│  React + TypeScript + TanStack Query + Tailwind             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ Weather  │ │ Signals  │ │ Trades   │ │ Stats +  │       │
│  │ Panel    │ │ Table    │ │ Table    │ │ Equity   │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                     │
│  │ HKO      │ │ Multi-   │ │ Calibration│                   │
│  │ Stations │ │ Factor   │ │ Panel    │                     │
│  └──────────┘ └──────────┘ └──────────┘                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        BACKEND                              │
│  FastAPI + Python + SQLite + APScheduler                    │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐   │
│  │ Weather   │ │ HKO       │ │ Signal    │ │ Settlement│   │
│  │ Signals   │ │ Data      │ │ Engine    │ │ + Real    │   │
│  │ (139-ens) │ │ Fetcher   │ │ (multi-   │ │ CLOB      │   │
│  │ + Platt)  │ │ (multi-   │ │  factor)  │ │ Execute   │   │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘   │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐                  │
│  │ Orderbook │ │ Adaptive  │ │ Risk      │                  │
│  │ WS        │ │ Gates     │ │ Manager   │                  │
│  └───────────┘ └───────────┘ └───────────┘                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │Open-Meteo │ │ HKO API  │ │Polymarket│ │ ECMWF    │       │
│  │139-member │ │ Forecast │ │ CLOB API │ │ ICON     │       │
│  │ ensemble  │ │ + Readings│ │ Gamma    │ │ GEM      │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Clean Foundation (BASE repo)
1. Delete BTC, Kalshi, AI/Groq modules
2. Update README, remove non-weather references
3. Add HKO city config to `weather.py`
4. Add "Hong Kong" to `CITY_ALIASES` in `weather_markets.py`
5. Clean up React dashboard — remove BTC/Kalshi components
6. Test: backend runs, dashboard loads, weather scan works for HK

### Phase 2: Upgrade Weather Model (from PROVEN)
1. Replace 31-member GFS fetcher with 139-member ensemble (GFS+ECMWF+ICON+GEM)
2. Add Platt calibration to signal generation
3. Upgrade to quarter-Kelly sizing
4. Extend DB schema with audit tables (6 tables from PROVEN)
5. Add adaptive per-city edge gates
6. Test: ensemble fetch works, signals improved, DB schema migration

### Phase 3: Add HKO Integration (from CURRENT)
1. Add HKO forecast fetcher and parser
2. Add multi-station readings to DB schema
3. Implement multi-factor weather scoring (temp+humidity+wind+rain+cloud+UV)
4. Implement empirical error model (HKO historical errors)
5. Integrate HKO data into signal generation pipeline
6. Test: HKO data fetches, multi-factor scoring works, signals incorporate HKO data

### Phase 4: Real Trading (from PROVEN + CURRENT)
1. Add real CLOB execution (from PROVEN)
2. Add risk management (11 checks from PROVEN)
3. Add orderbook WebSocket (from CURRENT)
4. Implement three-trigger engine (from CURRENT)
5. Add slippage calculator (from CURRENT)
6. Add kill switch (from PROVEN)
7. Test: paper trades execute, risk checks work, triggers fire correctly

### Phase 5: Monitoring & Reports (from PROVEN + SIMPLE)
1. Add daily PDF report generation (from PROVEN)
2. Add Discord webhook integration (from PROVEN)
3. Add Telegram notifications (from SIMPLE, optional)
4. Add self-learning parameter tuning (from SIMPLE)
5. Add backtester (from CURRENT)
6. Test: reports generate, webhooks fire, learning works

---

## Key Questions for Gemini Architect Review

1. **Ensemble approach:** Should we use 139-member Open-Meteo ensemble (PROVEN) as the primary probability source, or blend it with HKO empirical error model (CURRENT)? The HKO model has local ground truth but Open-Meteo has more ensemble diversity.

2. **Signal generation architecture:** Should multi-factor scoring (humidity, wind, UV, etc.) be a post-hoc adjustment to the ensemble probability, or should it replace the ensemble entirely for HKO-specific signals?

3. **Execution engine:** Should we keep the three-trigger engine (orderbook momentum, 30-min heartbeat, HKO forecast update) or simplify to the scheduler-based approach from the BASE repo?

4. **Database schema:** Should we merge the 6-table audit schema from PROVEN with the current HKO schema (readings, forecasts, triggers), or keep them separate?

5. **Dashboard:** Should we extend the React dashboard or keep it simple and add a separate HKO-specific view?

6. **Temperature units:** Open-Meteo returns Fahrenheit, HKO uses Celsius. Should we standardize on one unit throughout?

---

## File-by-File Changes Summary

### Delete
- `backend/core/signals.py` (BTC parts only — keep import structure)
- `backend/data/crypto.py`
- `backend/data/btc_markets.py`
- `backend/data/kalshi_client.py`
- `backend/data/kalshi_markets.py`
- `backend/ai/` (entire directory)
- `frontend/src/components/MicrostructurePanel.tsx`
- `frontend/src/components/GlobeView.tsx` (BTC parts)

### Modify
- `backend/config.py` — add HKO, CLOB, Discord, Telegram settings
- `backend/data/weather.py` — add HKO city, upgrade to 139-member ensemble
- `backend/data/weather_markets.py` — add "Hong Kong" alias
- `backend/core/weather_signals.py` — add Platt calibration, quarter-Kelly, multi-factor
- `backend/core/scheduler.py` — add three-trigger engine
- `backend/core/settlement.py` — extend with real CLOB execution
- `backend/models/database.py` — extend with audit tables + HKO tables
- `backend/api/main.py` — add HKO endpoints
- `frontend/src/App.tsx` — remove BTC/Kalshi, add HKO views
- `frontend/src/components/WeatherPanel.tsx` — add HKO station view
- `frontend/src/components/SignalsTable.tsx` — add multi-factor columns
- `requirements.txt` — add missing deps

### Add (new files)
- `backend/data/hko_fetcher.py` — HKO forecast + readings fetcher
- `backend/data/hko_parser.py` — HKO datetime parser
- `backend/core/multi_factor.py` — multi-factor weather scoring
- `backend/core/empirical_model.py` — HKO empirical error model
- `backend/core/orderbook_manager.py` — Polymarket WebSocket
- `backend/core/risk_manager.py` — 11 risk checks
- `backend/core/adaptive_gates.py` — adaptive per-city thresholds
- `backend/core/execution_engine.py` — real CLOB execution
- `backend/core/slippage.py` — slippage calculator
- `backend/core/report_generator.py` — daily PDF reports
- `backend/core/learning.py` — self-learning parameter tuning
- `backend/core/backtester.py` — backtesting engine
- `frontend/src/components/HKOStationsPanel.tsx` — HKO station data
- `frontend/src/components/MultiFactorPanel.tsx` — multi-factor scores
- `frontend/src/components/AdaptiveGatesPanel.tsx` — per-city gates

---

## Risks

1. **Open-Meteo API rate limits** — 139-member ensemble means more data per request. May need caching.
2. **HKO API stability** — HKO forecast XML format may change. Need robust parsing.
3. **Polymarket HK market availability** — If no HK-specific weather markets exist, need to fallback to nearby cities or wait for new markets.
4. **CLOB execution complexity** — Real trading adds significant complexity vs paper trading.
5. **Dashboard complexity** — Adding too many panels may overwhelm the UI.
