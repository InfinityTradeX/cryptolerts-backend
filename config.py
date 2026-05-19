# ─── CRYPTOLERTS BACKEND — ENVIRONMENT VARIABLES ───────────────────────────
# Copy this file to .env and fill in your values. Never commit .env to git.

# ── EXCHANGE ────────────────────────────────────────────────────────────────
# Binance (read-only API key — no trading permissions needed)
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET=your_binance_secret

# ── SUPABASE DATABASE ────────────────────────────────────────────────────────
# Get these from your Supabase project → Settings → API
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_SERVICE_KEY=your_supabase_service_role_key

# ── TELEGRAM ─────────────────────────────────────────────────────────────────
# Create a bot at t.me/BotFather → /newbot → copy the token
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Your channel/group IDs (get via @userinfobot or @RawDataBot)
TELEGRAM_FREE_CHANNEL_ID=-1001234567890
TELEGRAM_PRO_GROUP_ID=-1009876543210

# ── API SERVER ────────────────────────────────────────────────────────────────
API_SECRET_KEY=your_random_secret_key_here_min_32_chars
API_HOST=0.0.0.0
API_PORT=8000

# ── SCANNER ───────────────────────────────────────────────────────────────────
# How often to run the scanner (minutes)
SCAN_INTERVAL_MINUTES=15

# Minimum probability score to fire an alert (0-100)
MIN_PROBABILITY_TO_ALERT=70

# Pairs to scan (comma-separated)
SCAN_PAIRS=BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT,AVAX/USDT,DOGE/USDT,LINK/USDT,ADA/USDT,DOT/USDT,MATIC/USDT,UNI/USDT

# Timeframes to scan
SCAN_TIMEFRAMES=1h,4h,1d

# ── ENVIRONMENT ───────────────────────────────────────────────────────────────
ENVIRONMENT=development
LOG_LEVEL=INFO
