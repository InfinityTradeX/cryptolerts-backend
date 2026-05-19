"""
Cryptolerts — REST API (FastAPI)
Serves live data to the website frontend.
All public endpoints use the anon Supabase key (respects RLS).
Admin endpoints require the API secret header.
"""
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from loguru import logger
from utils.config import cfg, get_db, get_public_db
from db.operations import (
    get_active_signals, get_recent_trades, get_stats,
    close_signal, update_stats
)
from scanner.engine import run_scan, Signal
from bot.telegram_bot import CryptolertsBot

app = FastAPI(
    title="Cryptolerts API",
    description="Backend API for cryptolerts.com",
    version="1.0.0",
)

# CORS — allow the website to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://cryptolerts.com",
        "https://www.cryptolerts.com",
        "http://localhost:*",          # local dev
        "http://127.0.0.1:*",
    ],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


# ── AUTH ─────────────────────────────────────────────────────────────────────

def verify_admin(x_api_key: str = Header(None)) -> None:
    if x_api_key != cfg.API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── PUBLIC ENDPOINTS ──────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"service": "Cryptolerts API", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/signals")
async def list_signals(locked: Optional[bool] = None):
    """
    Get active signals. Website calls this to populate the signals grid.
    ?locked=false → only free signals
    ?locked=true  → all signals (Pro, use with auth)
    """
    db = get_public_db()
    try:
        query = db.table("signals").select(
            "id,pair,coin,direction,signal_type,timeframe,strategy,"
            "probability,entry_price,take_profit,stop_loss,is_locked,created_at"
        ).eq("status", "active").order("created_at", desc=True)

        if locked is False:
            query = query.eq("is_locked", False)

        result = query.execute()

        # Mask Pro signal details for public access
        signals = []
        for s in result.data:
            if s["is_locked"]:
                s["entry_price"] = "Pro only"
                s["take_profit"] = "Pro only"
                s["stop_loss"]   = "Pro only"
            signals.append(s)

        return {"signals": signals, "count": len(signals)}
    except Exception as e:
        logger.error(f"API error /signals: {e}")
        raise HTTPException(500, "Failed to fetch signals")


@app.get("/api/trades")
async def list_trades(limit: int = 20):
    """Get recent closed trades for the Results page."""
    trades = await get_recent_trades(limit)
    return {"trades": trades, "count": len(trades)}


@app.get("/api/stats")
async def get_platform_stats():
    """Homepage stats: win rate, members, totals."""
    stats = await get_stats()
    return stats


@app.get("/api/articles")
async def list_articles(category: Optional[str] = None):
    """Published articles for the Education page."""
    db = get_public_db()
    try:
        query = db.table("articles").select(
            "id,title,category,level,body,read_time,created_at"
        ).eq("is_published", True).order("created_at", desc=True)
        if category:
            query = query.eq("category", category)
        result = query.execute()
        return {"articles": result.data, "count": len(result.data)}
    except Exception as e:
        raise HTTPException(500, "Failed to fetch articles")


@app.get("/api/market")
async def market_summary():
    """
    Combines active signals with live coin data for the market page.
    Returns signal status per coin to overlay on price data.
    """
    signals = await get_active_signals()
    signal_map = {}
    for s in signals:
        coin = s["pair"].split("/")[0]
        if coin not in signal_map:
            signal_map[coin] = {
                "direction": s["direction"],
                "probability": s["probability"],
                "is_locked": s["is_locked"],
            }
    return {"signal_map": signal_map}


# ── ADMIN ENDPOINTS (require API key header) ───────────────────────────────────

class CloseSignalRequest(BaseModel):
    signal_id: str
    result: str               # 'win' | 'loss' | 'breakeven'
    exit_price: float
    return_pct: str           # e.g. "+5.4%"
    hold_hours: float = 0.0
    notify_telegram: bool = True

@app.post("/api/admin/signals/close")
async def admin_close_signal(body: CloseSignalRequest, _=Depends(verify_admin)):
    """Close a signal and optionally notify Telegram."""
    await close_signal(
        body.signal_id, body.result, body.exit_price,
        body.return_pct, body.hold_hours
    )
    if body.notify_telegram:
        db = get_db()
        sig = db.table("signals").select("*").eq("id", body.signal_id).single().execute().data
        bot = CryptolertsBot()
        await bot.send_result(
            pair=sig["pair"], direction=sig["direction"],
            result=body.result, entry=sig["entry_price"],
            exit_p=f"${body.exit_price:,.4f}".rstrip("0").rstrip("."),
            return_pct=body.return_pct,
        )
    return {"ok": True}


class UpdateStatsRequest(BaseModel):
    members: Optional[str]    = None
    best_trade: Optional[str] = None
    avg_hold: Optional[str]   = None

@app.patch("/api/admin/stats")
async def admin_update_stats(body: UpdateStatsRequest, _=Depends(verify_admin)):
    await update_stats(body.members, body.best_trade, body.avg_hold)
    return {"ok": True}


class ManualSignalRequest(BaseModel):
    pair: str
    coin: str
    direction: str
    signal_type: str
    timeframe: str
    strategy: str
    probability: int
    entry_price: str
    take_profit: str
    stop_loss: str
    is_locked: bool = False

@app.post("/api/admin/signals")
async def admin_post_signal(body: ManualSignalRequest, _=Depends(verify_admin)):
    """Manually post a signal (bypass scanner) — for when you spot a setup yourself."""
    from db.operations import save_signal
    from scanner.engine import Signal
    from datetime import datetime, timezone

    # Parse price strings to float for raw storage
    def parse_price(s: str) -> float:
        return float(s.replace("$", "").replace(",", ""))

    sig = Signal(
        pair=body.pair, coin=body.coin, direction=body.direction,
        signal_type=body.signal_type, timeframe=body.timeframe,
        strategy=body.strategy, probability=body.probability,
        entry_price=parse_price(body.entry_price),
        take_profit=parse_price(body.take_profit),
        stop_loss=parse_price(body.stop_loss),
        is_locked=body.is_locked,
    )
    # Override formatted strings with admin's input
    sig._entry_override = body.entry_price
    sig._tp_override    = body.take_profit
    sig._sl_override    = body.stop_loss

    sig_id = await save_signal(sig)
    if sig_id:
        bot = CryptolertsBot()
        await bot.send_signal(sig)
        await mark_signal_posted(sig_id)

    return {"ok": True, "signal_id": sig_id}


@app.post("/api/admin/scan")
async def admin_trigger_scan(_=Depends(verify_admin)):
    """Manually trigger a scanner run — useful for testing."""
    import asyncio
    signals = await run_scan(cfg.SCAN_PAIRS, cfg.SCAN_TIMEFRAMES, cfg.MIN_PROBABILITY)
    return {"signals_found": len(signals)}
