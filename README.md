"""
Cryptolerts — Main Orchestrator
Runs the full pipeline on a schedule:
  1. Scanner fetches + analyses OHLCV data
  2. New signals saved to Supabase
  3. Telegram alerts fired to free + Pro channels
  4. Website API automatically serves updated data

Also runs the price monitor to auto-close signals when TP/SL is hit.

Usage:
  python main.py              # Run full pipeline (scanner + API + monitor)
  python main.py --api-only   # Run only the API server
  python main.py --scan-once  # Run scanner once and exit
"""
import asyncio
import argparse
import time
from datetime import datetime, timezone

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from utils.config import cfg, get_db
from scanner.engine import run_scan, Signal
from bot.telegram_bot import CryptolertsBot
from db.operations import (
    save_signal, mark_signal_posted, get_active_signals,
    close_signal, log_scanner_run, get_stats
)
import ccxt.async_support as ccxt


# ── PRICE MONITOR (auto-close signals on TP/SL hit) ─────────────────────────

async def check_prices_against_signals():
    """
    Checks current prices against all active signals.
    Closes signals and fires result alerts when TP or SL is hit.
    """
    signals = await get_active_signals()
    if not signals:
        return

    # Get unique pairs to check
    pairs = list({s["pair"] for s in signals})
    exchange = ccxt.binance({"enableRateLimit": True})

    try:
        tickers = await exchange.fetch_tickers(pairs)
    except Exception as e:
        logger.warning(f"Price check failed: {e}")
        await exchange.close()
        return

    bot = CryptolertsBot()

    for sig in signals:
        ticker = tickers.get(sig["pair"])
        if not ticker:
            continue

        current = ticker["last"]
        tp_raw  = sig.get("tp_raw")
        sl_raw  = sig.get("sl_raw")

        if not tp_raw or not sl_raw:
            continue

        result = None
        if sig["direction"] == "long":
            if current >= tp_raw:
                result = "win"
                ret = f"+{(tp_raw - sig['entry_raw']) / sig['entry_raw'] * 100:.1f}%"
            elif current <= sl_raw:
                result = "loss"
                ret = f"{(sl_raw - sig['entry_raw']) / sig['entry_raw'] * 100:.1f}%"
        else:
            if current <= tp_raw:
                result = "win"
                ret = f"+{(sig['entry_raw'] - tp_raw) / sig['entry_raw'] * 100:.1f}%"
            elif current >= sl_raw:
                result = "loss"
                ret = f"{(sig['entry_raw'] - sl_raw) / sig['entry_raw'] * 100:.1f}%"

        if result:
            # Calculate hold time
            opened = datetime.fromisoformat(sig["created_at"].replace("Z", "+00:00"))
            hold_h = (datetime.now(timezone.utc) - opened).total_seconds() / 3600

            await close_signal(sig["id"], result, current, ret, round(hold_h, 1))
            await bot.send_result(
                pair=sig["pair"], direction=sig["direction"],
                result=result, entry=sig["entry_price"],
                exit_p=f"${current:,.4f}".rstrip("0").rstrip("."),
                return_pct=ret,
            )
            logger.info(f"Signal auto-closed: {sig['pair']} {result} {ret}")

    await exchange.close()


# ── SCANNER PIPELINE ──────────────────────────────────────────────────────────

async def run_scanner_pipeline():
    """
    Full scanner → save → alert pipeline.
    Called by the scheduler every SCAN_INTERVAL minutes.
    """
    start  = time.time()
    run_id = ""
    alerts = 0
    logger.info(f"Scanner pipeline starting — pairs: {len(cfg.SCAN_PAIRS)}, TFs: {cfg.SCAN_TIMEFRAMES}")

    try:
        signals = await run_scan(cfg.SCAN_PAIRS, cfg.SCAN_TIMEFRAMES, cfg.MIN_PROBABILITY)
        bot     = CryptolertsBot()

        for sig in signals:
            sig_id = await save_signal(sig)
            if sig_id:
                await bot.send_signal(sig)
                await mark_signal_posted(sig_id)
                alerts += 1
                await asyncio.sleep(1)  # Telegram rate limit

        duration = int((time.time() - start) * 1000)
        run_id   = await log_scanner_run(
            pairs_scanned=len(cfg.SCAN_PAIRS) * len(cfg.SCAN_TIMEFRAMES),
            signals_found=len(signals),
            alerts_sent=alerts,
            duration_ms=duration,
        )
        logger.info(f"Pipeline complete — {alerts} alerts sent in {duration}ms")

    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        await log_scanner_run(0, 0, 0, 0, error=str(e))


# ── DAILY RECAP ───────────────────────────────────────────────────────────────

async def send_daily_recap():
    try:
        stats  = await get_stats()
        sigs   = await get_active_signals()
        bot    = CryptolertsBot()
        await bot.send_daily_recap(
            signals_today=len(sigs),
            win_rate=float(stats.get("win_rate", 78)),
            members=stats.get("members", "4,800+"),
        )
        logger.info("Daily recap sent")
    except Exception as e:
        logger.error(f"Daily recap failed: {e}")


# ── SCHEDULER SETUP ───────────────────────────────────────────────────────────

def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    # Scanner — every N minutes
    scheduler.add_job(
        run_scanner_pipeline,
        trigger=IntervalTrigger(minutes=cfg.SCAN_INTERVAL),
        id="scanner",
        name="Signal scanner",
        replace_existing=True,
    )

    # Price monitor — every 5 minutes (checks TP/SL hits)
    scheduler.add_job(
        check_prices_against_signals,
        trigger=IntervalTrigger(minutes=5),
        id="price_monitor",
        name="Price monitor (TP/SL)",
        replace_existing=True,
    )

    # Daily recap — every day at 20:00 UTC
    scheduler.add_job(
        send_daily_recap,
        trigger=CronTrigger(hour=20, minute=0, timezone="UTC"),
        id="daily_recap",
        name="Daily recap",
        replace_existing=True,
    )

    return scheduler


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

async def main_async(api_only: bool = False, scan_once: bool = False):
    if scan_once:
        logger.info("Running scanner once…")
        await run_scanner_pipeline()
        return

    # Start scheduler
    if not api_only:
        scheduler = build_scheduler()
        scheduler.start()
        logger.info(f"Scheduler started — scanner every {cfg.SCAN_INTERVAL}min, price monitor every 5min")

        # Run scanner immediately on startup
        asyncio.create_task(run_scanner_pipeline())

    # Start API server
    from api.server import app
    config = uvicorn.Config(
        app=app,
        host=cfg.API_HOST,
        port=cfg.API_PORT,
        log_level=cfg.LOG_LEVEL.lower(),
    )
    server = uvicorn.Server(config)
    logger.info(f"API server starting on {cfg.API_HOST}:{cfg.API_PORT}")
    await server.serve()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cryptolerts Backend")
    parser.add_argument("--api-only",  action="store_true", help="Run only the API server, no scanner")
    parser.add_argument("--scan-once", action="store_true", help="Run scanner once and exit")
    args = parser.parse_args()

    try:
        asyncio.run(main_async(api_only=args.api_only, scan_once=args.scan_once))
    except KeyboardInterrupt:
        logger.info("Shutting down")
