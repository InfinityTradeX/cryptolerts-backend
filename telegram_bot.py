# Cryptolerts Backend — Full Stack Setup Guide

## What this is

A complete automated crypto signal pipeline:

```
Binance API (price data)
      ↓
Scanner Engine (RSI · MACD · Order blocks · Volume · EMA trend)
      ↓
Supabase (Postgres database — stores signals, trades, stats)
      ↓
Telegram Bot (fires alerts to free channel + Pro group)
      ↓
FastAPI (serves live data to cryptolerts.com)
      ↓
Website (displays live signals, auto-updates results)
```

---

## Step 1 — Supabase (database)

1. Go to https://supabase.com → Create a new project (free tier is fine)
2. Go to **SQL Editor** → paste the entire contents of `db/schema.sql` → Run
3. Go to **Settings → API** → copy:
   - Project URL → `SUPABASE_URL`
   - `anon` public key → `SUPABASE_KEY`
   - `service_role` secret key → `SUPABASE_SERVICE_KEY`

---

## Step 2 — Telegram bot

1. Open Telegram → message `@BotFather` → `/newbot`
2. Follow prompts → copy the token → `TELEGRAM_BOT_TOKEN`
3. Create your **free public channel** (e.g. @cryptolerts)
4. Add your bot as admin of the channel
5. Get channel ID: forward a message from it to `@userinfobot` → `TELEGRAM_FREE_CHANNEL_ID`
6. Create your **Pro private group** (e.g. Cryptolerts Pro)
7. Add bot as admin → get group ID → `TELEGRAM_PRO_GROUP_ID`

**Note:** Channel IDs are negative numbers like `-1001234567890`

---

## Step 3 — Binance API key

1. Go to binance.com → Account → API Management → Create API
2. Enable: **Read Only** (do NOT enable trading or withdrawals)
3. Copy key + secret → `BINANCE_API_KEY` / `BINANCE_SECRET`

---

## Step 4 — Configure environment

```bash
cp .env.example .env
# Edit .env with all your values from steps 1-3
```

---

## Step 5 — Deploy to Railway (recommended, ~$5/month)

Railway is the easiest cloud host for this backend.

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Create project
railway init

# Add all env vars (copy from your .env)
railway variables set SUPABASE_URL=... TELEGRAM_BOT_TOKEN=... # etc

# Deploy
railway up
```

Railway auto-detects Python and runs `python main.py`.

**Alternative: Render.com (free tier available)**
- New Web Service → connect your GitHub repo
- Build command: `pip install -r requirements.txt`
- Start command: `python main.py`
- Add env vars in the Render dashboard

---

## Step 6 — Connect website to API

Update your `cryptolerts.com` website to fetch from the API instead of localStorage.

In your `shared.js`, replace the `defaultSignals()` calls with:

```javascript
const API_BASE = "https://your-railway-app.railway.app";

async function fetchSignals() {
  const res = await fetch(`${API_BASE}/api/signals`);
  const data = await res.json();
  return data.signals;
}

async function fetchStats() {
  const res = await fetch(`${API_BASE}/api/stats`);
  return res.json();
}

async function fetchTrades() {
  const res = await fetch(`${API_BASE}/api/trades`);
  const data = await res.json();
  return data.trades;
}

async function fetchArticles() {
  const res = await fetch(`${API_BASE}/api/articles`);
  const data = await res.json();
  return data.articles;
}
```

---

## Local development

```bash
# Install dependencies
pip install -r requirements.txt

# Install TA-Lib system dependency first:
# macOS:   brew install ta-lib
# Ubuntu:  sudo apt-get install libta-lib-dev
# Windows: download from https://sourceforge.net/projects/ta-lib/

# Copy and fill env
cp .env.example .env

# Run scanner once (test mode)
python main.py --scan-once

# Run backtest on BTC 4H for 180 days
python -m backtest.engine --pair BTC/USDT --timeframe 4h --days 180

# Run full stack (scanner + API)
python main.py

# API only (for local frontend dev)
python main.py --api-only
```

---

## API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/signals` | Active signals (public, Pro details masked) |
| GET | `/api/trades` | Recent closed trades |
| GET | `/api/stats` | Win rate, members, totals |
| GET | `/api/articles` | Published education articles |
| GET | `/api/market` | Signal map per coin |
| POST | `/api/admin/signals` | Post manual signal *(requires API key)* |
| POST | `/api/admin/signals/close` | Close signal + notify TG *(requires API key)* |
| PATCH | `/api/admin/stats` | Update members, best trade *(requires API key)* |
| POST | `/api/admin/scan` | Trigger manual scanner run *(requires API key)* |

Admin endpoints require header: `X-API-Key: your_API_SECRET_KEY`

---

## Scanner logic — how signals are scored

Each pair × timeframe combination is scored by confluence:

| Factor | Points |
|--------|--------|
| EMA 20/50/200 trend aligned | 18 |
| Bullish/Bearish order block | 18 |
| RSI divergence | 16 |
| RSI oversold/overbought | 15 |
| MACD cross | 15 |
| Price at key S/R level | 14 |
| Bollinger Band extreme | 10 |
| Volume spike | 10 |

Signals scoring **≥ 80** → Free + Pro channels (unlocked)
Signals scoring **65–79** → Pro only (locked on website)
Signals scoring **< 65** → Not posted

Run a backtest to see how your scoring thresholds perform historically before going live.

---

## Whop payment integration

Whop handles Pro subscriptions and auto-invites paying members to your Telegram group.

1. Create account at https://whop.com
2. New product → "Cryptolerts Pro" → $29/mo
3. Connect to your Pro Telegram group (Whop does the invite/kick automatically)
4. Copy your Whop link → update in the website pricing section

---

## File structure

```
cryptolerts-backend/
├── main.py                  # Orchestrator — scheduler + API server
├── requirements.txt
├── .env.example
├── scanner/
│   └── engine.py            # OHLCV fetch + TA indicators + signal scoring
├── bot/
│   └── telegram_bot.py      # Message formatting + Telegram sends
├── api/
│   └── server.py            # FastAPI REST endpoints
├── db/
│   ├── schema.sql            # Supabase table setup — run once
│   └── operations.py         # All database read/write functions
├── backtest/
│   └── engine.py            # Historical strategy validation
└── utils/
    └── config.py            # Settings + Supabase client
```
