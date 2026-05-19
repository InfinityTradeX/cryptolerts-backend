"""
Cryptolerts — Telegram Bot
Formats signals into beautiful messages and posts to
the free channel (public) and Pro group (subscribers only).
"""
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from loguru import logger
from scanner.engine import Signal
from utils.config import cfg


# ── MESSAGE FORMATTER ─────────────────────────────────────────────────────────

def format_signal_free(signal: Signal) -> str:
    """
    Public free channel message — shows direction, pair, basic levels.
    Teases Pro content to drive upgrades.
    """
    dir_emoji = "🟢" if signal.direction == "long" else "🔴"
    dir_text  = "LONG ▲" if signal.direction == "long" else "SHORT ▼"
    lock_line = ""
    if signal.is_locked:
        lock_line = "\n\n🔒 *Full analysis available in Pro*\n_Entry zone, TP levels, and live updates_"

    factors_preview = " · ".join(f for f, _ in signal.confluence_factors[:2])

    return f"""
{dir_emoji} *{signal.pair} — {dir_text}*
⏱ Timeframe: `{signal.timeframe}` · {signal.signal_type}

📊 *Probability score:* `{signal.probability}%`
📌 *Confluence:* {factors_preview}

{"💰 *Entry:* `" + signal.entry_str + "`" if not signal.is_locked else "💰 *Entry:* `[Pro only]`"}
{"🎯 *Target:* `" + signal.tp_str  + "` · ⛔ *Stop:* `" + signal.sl_str + "`" if not signal.is_locked else ""}
📐 *Risk/Reward:* `{signal.risk_reward}:1`
{lock_line}
⚠️ _Not financial advice. Always manage risk._

👉 [Join Pro for full signals](https://t.me/cryptolertspro)
[📊 cryptolerts.com](https://cryptolerts.com)
""".strip()


def format_signal_pro(signal: Signal) -> str:
    """
    Pro group message — full details, all confluence factors, management notes.
    """
    dir_emoji   = "🟢" if signal.direction == "long" else "🔴"
    dir_text    = "LONG ▲" if signal.direction == "long" else "SHORT ▼"
    factors_txt = "\n".join(f"  ✦ {f} (+{w}pts)" for f, w in signal.confluence_factors)

    # Risk management guidance
    if signal.risk_reward >= 2.5:
        mgmt = "Strong R:R — consider scaling in 2 entries"
    elif signal.risk_reward >= 1.5:
        mgmt = "Standard R:R — single entry, full stop"
    else:
        mgmt = "Tight R:R — small size, tight management"

    return f"""
⚡ *PRO SIGNAL — {signal.pair}*

{dir_emoji} *{dir_text}* · `{signal.timeframe}` · {signal.signal_type}

━━━━━━━━━━━━━━━━━━━━━
💰 *Entry:*      `{signal.entry_str}`
🎯 *Take Profit:* `{signal.tp_str}`
⛔ *Stop Loss:*   `{signal.sl_str}`
📐 *R:R Ratio:*   `{signal.risk_reward}:1`
━━━━━━━━━━━━━━━━━━━━━

📊 *Probability: {signal.probability}%*
Confluence factors:
{factors_txt}

💡 *Risk management:* {mgmt}
🔔 Watch for confirmation on the `{signal.timeframe}` close.
Update will be posted when TP or SL is hit.

⚠️ _Max 1-2% of account. Not financial advice._
""".strip()


def format_result_message(pair: str, direction: str, result: str,
                           entry: str, exit_p: str, return_pct: str) -> str:
    emoji = "✅" if result == "win" else "❌"
    return f"""
{emoji} *{pair} CLOSED — {"WIN" if result == "win" else "LOSS"}*

Direction: {"Long ▲" if direction == "long" else "Short ▼"}
Entry: `{entry}` → Exit: `{exit_p}`
Return: `{return_pct}`

[View full results](https://cryptolerts.com/results)
""".strip()


# ── BOT SENDER ────────────────────────────────────────────────────────────────

class CryptolertsBot:
    def __init__(self):
        if not cfg.BOT_TOKEN:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not set in .env")
        self.bot = Bot(token=cfg.BOT_TOKEN)

    async def send_signal(self, signal: Signal) -> dict:
        """
        Post a signal to the appropriate channels.
        - Free channel: always (teaser for locked signals)
        - Pro group: always (full details)
        Returns dict with message IDs for tracking.
        """
        results = {}

        # Free channel
        if cfg.FREE_CHANNEL_ID:
            try:
                msg = await self.bot.send_message(
                    chat_id=cfg.FREE_CHANNEL_ID,
                    text=format_signal_free(signal),
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True,
                )
                results["free_msg_id"] = msg.message_id
                logger.info(f"Posted to free channel: {signal.pair} {signal.direction}")
            except TelegramError as e:
                logger.error(f"Failed to post to free channel: {e}")

        # Pro group (full details, all signals regardless of lock status)
        if cfg.PRO_GROUP_ID:
            try:
                msg = await self.bot.send_message(
                    chat_id=cfg.PRO_GROUP_ID,
                    text=format_signal_pro(signal),
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True,
                )
                results["pro_msg_id"] = msg.message_id
                logger.info(f"Posted to Pro group: {signal.pair} {signal.direction}")
            except TelegramError as e:
                logger.error(f"Failed to post to Pro group: {e}")

        return results

    async def send_result(self, pair: str, direction: str, result: str,
                          entry: str, exit_p: str, return_pct: str) -> None:
        """Post a trade result update to both channels."""
        msg = format_result_message(pair, direction, result, entry, exit_p, return_pct)
        for channel_id in [cfg.FREE_CHANNEL_ID, cfg.PRO_GROUP_ID]:
            if channel_id:
                try:
                    await self.bot.send_message(
                        chat_id=channel_id,
                        text=msg,
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True,
                    )
                except TelegramError as e:
                    logger.error(f"Failed to send result to {channel_id}: {e}")

    async def send_daily_recap(self, signals_today: int, win_rate: float, members: str) -> None:
        """Daily summary message — posted at end of day."""
        msg = f"""
📊 *Daily Recap — Cryptolerts*

Signals posted today: `{signals_today}`
Running win rate (30d): `{win_rate:.0f}%`
Community size: `{members}`

See all open setups → [cryptolerts.com](https://cryptolerts.com)
Join free → [t.me/cryptolerts](https://t.me/cryptolerts)
""".strip()
        if cfg.FREE_CHANNEL_ID:
            try:
                await self.bot.send_message(
                    chat_id=cfg.FREE_CHANNEL_ID,
                    text=msg,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True,
                )
            except TelegramError as e:
                logger.error(f"Failed to send daily recap: {e}")
