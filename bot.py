#!/usr/bin/env python3
"""
XAUUSDT.P Bot — Binance Perpetual Edition
Price source: Binance FAPI (real-time, no API key needed)
"""

import logging, sqlite3, os, io, asyncio, threading
from datetime import datetime
from typing import Optional, Dict, Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import numpy as np
import requests

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════
BOT_TOKEN      = os.getenv("BOT_TOKEN", "")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))
DB_PATH        = os.getenv("DB_PATH", "alerts.db")
BINANCE        = "https://fapi.binance.com/fapi/v1"

BINANCE_TF = {
    "1m":"1m","3m":"3m","5m":"5m","15m":"15m","30m":"30m",
    "1h":"1h","2h":"2h","4h":"4h","6h":"6h","12h":"12h",
    "1d":"1d","1w":"1w",
}
VALID_TF = "  ".join(BINANCE_TF)

TV = dict(
    bg="#131722", panel="#1e2230", grid="#1e2230",
    up="#26a69a", down="#ef5350",
    vol_u="#1a5c53", vol_d="#7a2020",
    text="#d1d4dc",
    ema9="#2962ff", ema50="#ffca28",
    zone_g="#00897b", zone_r="#c62828",
    price="#ffffff",
)

logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S", level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# BINANCE PRICE FEED
# ══════════════════════════════════════════════════════════════════════════════

def get_price_data() -> Optional[Dict[str, Any]]:
    """Fetch XAUUSDT perpetual data from Binance FAPI."""
    try:
        # 24H rolling ticker
        r1 = requests.get(f"{BINANCE}/ticker/24hr",
                          params={"symbol": "XAUUSDT"}, timeout=7)
        d1 = r1.json()
        if "lastPrice" not in d1:
            raise ValueError("Unexpected Binance response")

        # Mark price + funding rate
        r2 = requests.get(f"{BINANCE}/premiumIndex",
                          params={"symbol": "XAUUSDT"}, timeout=7)
        d2 = r2.json()

        last = float(d1["lastPrice"])
        mark = float(d2.get("markPrice", last))
        fund = float(d2.get("lastFundingRate", 0)) * 100

        return {
            "exchange":  "Binance",
            "symbol":    "XAUUSDT.P",
            "last":      last,
            "mark":      mark,
            "bid":       float(d1.get("bidPrice", 0)),
            "ask":       float(d1.get("askPrice", 0)),
            "high24h":   float(d1["highPrice"]),
            "low24h":    float(d1["lowPrice"]),
            "change":    float(d1["priceChange"]),
            "pct":       float(d1["priceChangePercent"]),
            "volume24h": float(d1["volume"]),
            "funding":   fund,
            "open24h":   float(d1["openPrice"]),
        }
    except Exception as e:
        logger.error("Binance price fetch: %s", e)
        return None


def get_price() -> Optional[float]:
    d = get_price_data()
    return d["last"] if d else None


def get_ohlcv(tf: str = "1h") -> Optional[pd.DataFrame]:
    """Binance futures klines for chart."""
    interval = BINANCE_TF.get(tf, "1h")
    try:
        r = requests.get(
            f"{BINANCE}/klines",
            params={"symbol": "XAUUSDT", "interval": interval, "limit": 80},
            timeout=8,
        )
        data = r.json()
        if not isinstance(data, list) or len(data) < 10:
            return None

        rows = [{
            "ts":     pd.to_datetime(int(k[0]), unit="ms"),
            "Open":   float(k[1]),
            "High":   float(k[2]),
            "Low":    float(k[3]),
            "Close":  float(k[4]),
            "Volume": float(k[5]),
        } for k in data]

        df = pd.DataFrame(rows).set_index("ts")
        df.index = pd.DatetimeIndex(df.index)
        return df
    except Exception as e:
        logger.warning("Binance kline: %s", e)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════════════════════════════════════

def _con():
    return sqlite3.connect(DB_PATH)

def init_db():
    with _con() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                target REAL NOT NULL,
                direction TEXT NOT NULL,
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS zones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                price_low REAL NOT NULL,
                price_high REAL NOT NULL,
                label TEXT DEFAULT '',
                color TEXT DEFAULT 'green',
                active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS live_subs (
                chat_id INTEGER PRIMARY KEY,
                active INTEGER DEFAULT 1
            );
        """); c.commit()

def al_add(cid, target, direction, note=""):
    with _con() as c:
        r = c.execute(
            "INSERT INTO alerts(chat_id,target,direction,note,created_at) VALUES(?,?,?,?,?)",
            (cid, target, direction, note, datetime.utcnow().isoformat(timespec="seconds"))
        ); c.commit(); return r.lastrowid

def al_list(cid):
    with _con() as c:
        return c.execute(
            "SELECT id,target,direction,note FROM alerts WHERE chat_id=? AND active=1 ORDER BY id",
            (cid,)
        ).fetchall()

def al_cancel(aid, cid):
    with _con() as c:
        r = c.execute("UPDATE alerts SET active=0 WHERE id=? AND chat_id=? AND active=1",(aid,cid))
        c.commit(); return r.rowcount > 0

def al_cancel_all(cid):
    with _con() as c:
        r = c.execute("UPDATE alerts SET active=0 WHERE chat_id=? AND active=1",(cid,))
        c.commit(); return r.rowcount

def al_all_active():
    with _con() as c:
        return c.execute("SELECT id,chat_id,target,direction FROM alerts WHERE active=1").fetchall()

def al_off(aid):
    with _con() as c:
        c.execute("UPDATE alerts SET active=0 WHERE id=?", (aid,)); c.commit()

def zo_add(cid, low, high, label="", color="green"):
    with _con() as c:
        r = c.execute(
            "INSERT INTO zones(chat_id,price_low,price_high,label,color) VALUES(?,?,?,?,?)",
            (cid, low, high, label, color)
        ); c.commit(); return r.lastrowid

def zo_list(cid):
    with _con() as c:
        return c.execute(
            "SELECT id,price_low,price_high,label,color FROM zones WHERE chat_id=? AND active=1 ORDER BY price_low",
            (cid,)
        ).fetchall()

def zo_del(zid, cid):
    with _con() as c:
        r = c.execute("UPDATE zones SET active=0 WHERE id=? AND chat_id=? AND active=1",(zid,cid))
        c.commit(); return r.rowcount > 0

def live_toggle(cid) -> bool:
    with _con() as c:
        row = c.execute("SELECT active FROM live_subs WHERE chat_id=?",(cid,)).fetchone()
        if row is None:
            c.execute("INSERT INTO live_subs(chat_id,active) VALUES(?,1)",(cid,)); c.commit(); return True
        new = 0 if row[0] else 1
        c.execute("UPDATE live_subs SET active=? WHERE chat_id=?",(new,cid)); c.commit(); return bool(new)

def live_subs():
    with _con() as c:
        return [r[0] for r in c.execute("SELECT chat_id FROM live_subs WHERE active=1").fetchall()]


# ══════════════════════════════════════════════════════════════════════════════
# FORMATTERS
# ══════════════════════════════════════════════════════════════════════════════

def fp(p): return f"${p:,.2f}"
def fpf(p): return f"${p:,.3f}"
def de(d): return "📈" if d == "above" else "📉"
def utcnow(): return datetime.utcnow().strftime("%Y-%m-%d  %H:%M:%S  UTC")

def price_bar(cur, lo, hi, w=12):
    if not (lo > 0 and hi > lo): return ""
    pct = max(0, min(100, (cur - lo) / (hi - lo) * 100))
    f   = int(pct / 100 * w)
    return f"`[{'█'*f}{'░'*(w-f)}]`  `{pct:.0f}%`"

def fmt_price_msg(d: dict) -> str:
    up   = d["change"] >= 0
    c_e  = "🟢" if up else "🔴"
    a_e  = "📈" if up else "📉"
    sign = "+" if up else ""
    f_e  = "🟢" if d["funding"] < 0 else ("🔴" if d["funding"] > 0.05 else "🟡")
    f_s  = "+" if d["funding"] >= 0 else ""
    bar  = price_bar(d["last"], d["low24h"], d["high24h"])

    lines = [
        f"{c_e} *XAUUSDT  ·  PERPETUAL*",
        "",
        f"   💎 *{fpf(d['last'])}*",
        f"   📌 Mark    `{fp(d['mark'])}`",
    ]
    if d["bid"] and d["ask"]:
        lines.append(f"   🔁 `Bid: {fp(d['bid'])}  ╱  Ask: {fp(d['ask'])}`")
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"   {a_e} Change     `{sign}{fp(d['change'])}  ({sign}{d['pct']:.2f}%)`",
        "",
        f"   🔺 High 24H   `{fp(d['high24h'])}`",
        f"   🔻 Low  24H   `{fp(d['low24h'])}`",
    ]
    if bar:
        lines += ["", f"   {bar}", "   _L ←──── position ────→ H_"]
    lines += [
        "",
        f"   {f_e} Funding    `{f_s}{abs(d['funding']):.4f}%`",
        f"   📦 Volume     `{d['volume24h']:,.0f} XAU`",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"🏦 _Binance Futures_   🕐 `{utcnow()}`",
    ]
    return "\n".join(lines)

def fmt_alert_created(aid, target, direction, current, note=""):
    up   = direction == "above"
    diff = abs(current - target)
    sign = "+" if up else "-"
    lines = [
        "✅ *ALERT CREATED*",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"   🆔 ID        `#{aid}`",
        f"   🎯 Target    `{fp(target)}`",
        f"   📊 Current   `{fp(current)}`",
        f"   ↔️  Gap       `{sign}{fp(diff)}`",
        f"   {'📈' if up else '📉'} Fires when *{direction}* `{fp(target)}`",
    ]
    if note: lines.append(f"   📝 _{note}_")
    lines += ["━━━━━━━━━━━━━━━━━━━━━━━━", f"   ⏱ _Checked every {CHECK_INTERVAL}s_"]
    return "\n".join(lines)

def fmt_alert_fired(aid, current, target, direction):
    up   = direction == "above"
    diff = abs(current - target)
    sign = "+" if up else "-"
    return "\n".join([
        "🚨 *PRICE ALERT TRIGGERED!*",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"   {'📈' if up else '📉'} XAUUSDT went *{direction}* your target!",
        "",
        f"   💰 Current    `{fp(current)}`",
        f"   🎯 Target     `{fp(target)}`",
        f"   📏 Moved by   `{sign}{fp(diff)}`",
        "",
        f"   🕐 `{utcnow()}`",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"   _Alert `#{aid}` removed · /alert to set new one_",
    ])

def fmt_live_tick(price, d=None):
    if d:
        up = d["change"] >= 0
        sign = "+" if up else ""
        e = "🟢" if up else "🔴"
        return f"{e} `{fpf(price)}`  `{sign}{d['pct']:.2f}%`  🕐 `{utcnow()}`"
    return f"📡 `{fp(price)}`  🕐 `{utcnow()}`"

def kb_price():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 15m", callback_data="chart_15m"),
            InlineKeyboardButton("📊 1H",  callback_data="chart_1h"),
            InlineKeyboardButton("📊 4H",  callback_data="chart_4h"),
            InlineKeyboardButton("📊 1D",  callback_data="chart_1d"),
        ],
        [
            InlineKeyboardButton("🔄 Refresh",   callback_data="refresh"),
            InlineKeyboardButton("🔔 Set Alert", callback_data="alert_help"),
        ],
    ])

def kb_chart(tf):
    tfs = ["1h","4h","1d"]
    row = [InlineKeyboardButton(
        ("✅ " if t==tf else "")+t.upper(), callback_data=f"chart_{t}"
    ) for t in tfs]
    return InlineKeyboardMarkup([row,[
        InlineKeyboardButton("💰 Price",  callback_data="refresh"),
        InlineKeyboardButton("🔄 Redraw", callback_data=f"chart_{tf}"),
    ]])


# ══════════════════════════════════════════════════════════════════════════════
# CHART GENERATION
# ══════════════════════════════════════════════════════════════════════════════

_lock = threading.Lock()

def build_chart(tf="1h", zones_data=None):
    with _lock:
        df = get_ohlcv(tf)
        if df is None or df.empty:
            return None

        df["EMA9"]  = df["Close"].ewm(span=9,  adjust=False).mean()
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        has_vol     = df["Volume"].sum() > 0

        mc = mpf.make_marketcolors(
            up=TV["up"], down=TV["down"],
            edge={"up":TV["up"],"down":TV["down"]},
            wick={"up":TV["up"],"down":TV["down"]},
            volume={"up":TV["vol_u"],"down":TV["vol_d"]},
        )
        style = mpf.make_mpf_style(
            base_mpl_style="dark_background", marketcolors=mc,
            figcolor=TV["bg"], facecolor=TV["bg"],
            gridcolor=TV["grid"], gridstyle="-", gridaxis="both",
            rc={"axes.labelcolor":TV["text"],"axes.edgecolor":TV["panel"],
                "xtick.color":TV["text"],"ytick.color":TV["text"],
                "text.color":TV["text"],"font.size":9},
        )

        cur  = df["Close"].iloc[-1]
        prev = df["Open"].iloc[0]
        chg  = cur - prev
        pct  = (chg / prev * 100) if prev else 0
        is_up = chg >= 0
        clr  = TV["up"] if is_up else TV["down"]
        sign = "+" if is_up else ""
        arr  = "▲" if is_up else "▼"

        ap = [
            mpf.make_addplot(df["EMA9"],  color=TV["ema9"],  width=1.5),
            mpf.make_addplot(df["EMA50"], color=TV["ema50"], width=1.5),
        ]

        fig, axes = mpf.plot(
            df, type="candle", style=style, addplot=ap,
            volume=has_vol, figsize=(14, 8 if has_vol else 7),
            returnfig=True,
            title=f"\nXAUUSDT.P   {tf.upper()}   ${cur:,.2f}   {arr} {sign}{chg:.2f} ({sign}{pct:.2f}%)",
        )
        ax = axes[0]

        ax.axhline(y=cur, color=TV["price"], linestyle="--", linewidth=0.9, alpha=0.9, zorder=6)
        ax.annotate(
            f" {cur:,.2f}",
            xy=(1.0, cur), xycoords=("axes fraction","data"),
            fontsize=9, color="white", va="center", zorder=10,
            bbox=dict(boxstyle="round,pad=0.3", facecolor=clr, edgecolor="none", alpha=0.9),
        )

        if zones_data:
            for z_low, z_high, z_label, z_color in zones_data:
                hc = TV["zone_g"] if z_color == "green" else TV["zone_r"]
                ax.axhspan(z_low, z_high, alpha=0.15, color=hc, zorder=2)
                ax.axhline(y=z_low,  color=hc, linestyle="--", linewidth=0.8, alpha=0.6, zorder=3)
                ax.axhline(y=z_high, color=hc, linestyle="--", linewidth=0.8, alpha=0.6, zorder=3)
                if z_label:
                    ax.annotate(f"  {z_label}", xy=(0.01,(z_low+z_high)/2),
                                xycoords=("axes fraction","data"),
                                fontsize=8, color=hc, va="center", alpha=0.9)

        ax.text(
            0.01, 0.98,
            f"EMA 9: {df['EMA9'].iloc[-1]:,.2f}   EMA 50: {df['EMA50'].iloc[-1]:,.2f}",
            transform=ax.transAxes, fontsize=8, color=TV["text"],
            va="top", ha="left",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=TV["bg"], edgecolor=TV["panel"], alpha=0.85),
        )
        ax.plot([], [], color=TV["ema9"],  linewidth=1.5, label="EMA 9")
        ax.plot([], [], color=TV["ema50"], linewidth=1.5, label="EMA 50")
        ax.legend(loc="upper right", fontsize=8, framealpha=0.3,
                  facecolor=TV["bg"], edgecolor=TV["panel"], labelcolor=TV["text"])
        fig.text(0.99, 0.01, "XAUUSDT.P · Binance", ha="right", fontsize=7, color="#555", alpha=0.45)

        buf = io.BytesIO()
        fig.savefig(buf, dpi=150, bbox_inches="tight", facecolor=TV["bg"])
        plt.close(fig)
        buf.seek(0)
        return buf


# ══════════════════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  🏅  *XAUUSDT PERPETUAL BOT*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📡 Live data from *Binance Futures*\n\n"
        "📊 /price — Live price + 24H stats\n"
        "🕯 /chart — TradingView style chart\n"
        "🔔 /alert — Price alert notification\n"
        "🟢 /zone  — Support/resistance zone\n"
        "📡 /live  — Toggle live price stream\n"
        "❓ /help  — All commands\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "_Type /price to start_ 🚀",
        parse_mode="Markdown",
    )

async def cmd_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg  = await update.message.reply_text("⏳ _Fetching from Binance…_", parse_mode="Markdown")
    data = get_price_data()
    if data:
        await msg.edit_text(fmt_price_msg(data), parse_mode="Markdown", reply_markup=kb_price())
    else:
        await msg.edit_text(
            "❌ *Binance unavailable*\n\nMarket closed or API issue. Try again.",
            parse_mode="Markdown",
        )

async def cmd_chart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tf = (ctx.args[0].lower() if ctx.args else "1h")
    if tf not in BINANCE_TF:
        await update.message.reply_text(
            f"❌ Unknown timeframe.\n\nAvailable:\n`{VALID_TF}`", parse_mode="Markdown")
        return
    msg   = await update.message.reply_text(f"⏳ _Rendering {tf.upper()} chart…_", parse_mode="Markdown")
    cid   = update.effective_chat.id
    zones = [(r[1],r[2],r[3],r[4]) for r in zo_list(cid)]
    loop  = asyncio.get_event_loop()
    buf   = await loop.run_in_executor(None, build_chart, tf, zones)
    if buf is None:
        await msg.edit_text("❌ Chart data unavailable. Try again."); return
    price = get_price()
    cap   = (
        f"🕯 *XAUUSDT.P  ·  {tf.upper()}*"
        + (f"\n💎 `{fp(price)}`" if price else "")
        + (f"\n🟢 {len(zones)} zone(s)" if zones else "")
        + f"\n🕐 `{utcnow()}`"
    )
    await ctx.bot.send_photo(cid, buf, caption=cap, parse_mode="Markdown", reply_markup=kb_chart(tf))
    await msg.delete()

async def cmd_alert(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    usage = "*Usage:* `/alert <price>` `[note]`\n• `/alert 4100`\n• `/alert 3950 buy zone`"
    if not ctx.args:
        await update.message.reply_text(usage, parse_mode="Markdown"); return
    try:
        target = round(float(ctx.args[0].replace(",","").replace("$","")), 2)
    except ValueError:
        await update.message.reply_text(f"❌ Invalid.\n\n{usage}", parse_mode="Markdown"); return
    if not (100 < target < 100_000):
        await update.message.reply_text("❌ Price out of range."); return
    note    = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else ""
    current = get_price()
    if current is None:
        await update.message.reply_text("❌ Can't fetch price now. Try again."); return
    direction = "above" if target > current else "below"
    cid = update.effective_chat.id
    aid = al_add(cid, target, direction, note)
    await update.message.reply_text(
        fmt_alert_created(aid, target, direction, current, note), parse_mode="Markdown")

async def cmd_alerts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid  = update.effective_chat.id
    rows = al_list(cid)
    cur  = get_price()
    if not rows:
        await update.message.reply_text("📭 *No active alerts*\n_/alert <price> to create_", parse_mode="Markdown"); return
    lines = ["📋 *Active Alerts*"]
    if cur: lines.append(f"💎 Current: `{fp(cur)}`\n")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")
    for aid, target, direction, note in rows:
        gap = f"  ↔️ `{fp(abs(cur-target))}`" if cur else ""
        note_ = f"\n       📝 _{note}_" if note else ""
        lines.append(f"   {de(direction)} `#{aid}` → `{fp(target)}` ({direction}){gap}{note_}")
    lines += ["━━━━━━━━━━━━━━━━━━━━━━━━", f"_{len(rows)} active · /cancel <id> · /cancelall_"]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: `/cancel <id>`", parse_mode="Markdown"); return
    try: aid = int(str(ctx.args[0]).lstrip("#"))
    except ValueError:
        await update.message.reply_text("❌ Invalid ID."); return
    cid = update.effective_chat.id
    if al_cancel(aid, cid):
        await update.message.reply_text(f"✅ Alert `#{aid}` removed.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Alert `#{aid}` not found.")

async def cmd_cancelall(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    n = al_cancel_all(update.effective_chat.id)
    await update.message.reply_text(
        f"🗑 Removed *{n}* alert(s)." if n else "📭 No active alerts.", parse_mode="Markdown")

async def cmd_zone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    usage = "*Usage:* `/zone <low> <high> [label] [green|red]`\n• `/zone 3950 4000 support`\n• `/zone 4100 4150 resistance red`"
    if len(ctx.args) < 2:
        await update.message.reply_text(usage, parse_mode="Markdown"); return
    try:
        low  = float(ctx.args[0].replace(",","").replace("$",""))
        high = float(ctx.args[1].replace(",","").replace("$",""))
    except ValueError:
        await update.message.reply_text(f"❌ Invalid.\n{usage}", parse_mode="Markdown"); return
    if low >= high: low, high = high, low
    rest = list(ctx.args[2:])
    color = "green"
    if rest and rest[-1].lower() in ("green","red"): color = rest.pop().lower()
    label = " ".join(rest)
    cid   = update.effective_chat.id
    zid   = zo_add(cid, low, high, label, color)
    e = "🟢" if color == "green" else "🔴"
    await update.message.reply_text(
        f"{e} *Zone Added — `#{zid}`*\n\n"
        f"   📉 `{fp(low)}`  →  📈 `{fp(high)}`\n"
        + (f"   📝 _{label}_\n" if label else "")
        + "\n_Appears on next /chart_", parse_mode="Markdown")

async def cmd_zones(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid  = update.effective_chat.id
    rows = zo_list(cid)
    if not rows:
        await update.message.reply_text("📭 *No zones*\n_/zone <low> <high> to add_", parse_mode="Markdown"); return
    lines = ["🗺 *Chart Zones*\n","━━━━━━━━━━━━━━━━━━━━━━━━"]
    for zid, low, high, label, color in rows:
        e = "🟢" if color=="green" else "🔴"
        l = f"  _{label}_" if label else ""
        lines.append(f"   {e} `#{zid}` `{fp(low)} — {fp(high)}`{l}")
    lines += ["━━━━━━━━━━━━━━━━━━━━━━━━","_/delzone <id> to remove_"]
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_delzone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: `/delzone <id>`", parse_mode="Markdown"); return
    try: zid = int(str(ctx.args[0]).lstrip("#"))
    except ValueError:
        await update.message.reply_text("❌ Invalid ID."); return
    cid = update.effective_chat.id
    if zo_del(zid, cid):
        await update.message.reply_text(f"✅ Zone `#{zid}` removed.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Zone `#{zid}` not found.")

async def cmd_live(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid   = update.effective_chat.id
    is_on = live_toggle(cid)
    if is_on:
        await update.message.reply_text(
            f"📡 *Live Stream  ON*\n\nPrice updates every *{CHECK_INTERVAL}s*.\n_/live again to stop._",
            parse_mode="Markdown")
    else:
        await update.message.reply_text("📡 *Live Stream  OFF*", parse_mode="Markdown")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ *Full Commands*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "*📊 Price & Charts*\n"
        "  /price — Live price + mark + funding\n"
        "  /chart — 1H chart (default)\n"
        f"  /chart `1h` `4h` `1d` etc.\n"
        "  _Timeframes:_ `" + VALID_TF + "`\n\n"
        "*🔔 Alerts*\n"
        "  /alert `4100` — Notify at $4,100\n"
        "  /alert `3950 buy dip` — With note\n"
        "  /alerts — List active\n"
        "  /cancel `3` — Remove #3\n"
        "  /cancelall — Remove all\n\n"
        "*🟢 Chart Zones*\n"
        "  /zone `3950 4000 support`\n"
        "  /zone `4100 4150 resistance red`\n"
        "  /zones · /delzone `2`\n\n"
        "*📡 Live Stream*\n"
        "  /live — Toggle 60s price updates\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "_Data: Binance XAUUSDT Perpetual_",
        parse_mode="Markdown",
    )


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACK HANDLER
# ══════════════════════════════════════════════════════════════════════════════

async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    cd  = q.data
    cid = q.message.chat_id

    if cd.startswith("chart_"):
        tf = cd.split("_")[1]
        await q.answer(f"Rendering {tf.upper()}…")
        zones = [(r[1],r[2],r[3],r[4]) for r in zo_list(cid)]
        loop  = asyncio.get_event_loop()
        buf   = await loop.run_in_executor(None, build_chart, tf, zones)
        if buf:
            price = get_price()
            cap   = f"🕯 *XAUUSDT.P  ·  {tf.upper()}*" + (f"\n💎 `{fp(price)}`" if price else "") + f"\n🕐 `{utcnow()}`"
            await ctx.bot.send_photo(cid, buf, caption=cap, parse_mode="Markdown", reply_markup=kb_chart(tf))
        else:
            await q.answer("❌ Data unavailable", show_alert=True)

    elif cd == "refresh":
        await q.answer("Refreshing…")
        data = get_price_data()
        if data:
            try:
                await q.message.edit_text(fmt_price_msg(data), parse_mode="Markdown", reply_markup=kb_price())
            except Exception:
                pass
        else:
            await q.answer("❌ Binance unavailable", show_alert=True)

    elif cd == "alert_help":
        await q.answer()
        price = get_price()
        hint  = f"`/alert {int(price)+50}`" if price else "`/alert 4150`"
        await ctx.bot.send_message(cid,
            f"🔔 *Set a Price Alert*\n\nExample: {hint}\nOr: `/alert 3950 support zone`\n\n_Bot notifies you when price hits target._",
            parse_mode="Markdown")

    else:
        await q.answer()


# ══════════════════════════════════════════════════════════════════════════════
# BACKGROUND JOBS
# ══════════════════════════════════════════════════════════════════════════════

async def job_alerts(ctx: ContextTypes.DEFAULT_TYPE):
    current = get_price()
    if current is None: return
    rows = al_all_active()
    if not rows: return
    logger.info("Alert check: %s  active=%d", fp(current), len(rows))
    for aid, cid, target, direction in rows:
        hit = (direction=="above" and current>=target) or (direction=="below" and current<=target)
        if not hit: continue
        try:
            await ctx.bot.send_message(cid, fmt_alert_fired(aid,current,target,direction), parse_mode="Markdown")
            al_off(aid)
            logger.info("🔔 Alert #%d fired → chat %d @ %s", aid, cid, fp(current))
        except Exception as e:
            logger.error("Notify failed (chat %d): %s", cid, e)

async def job_live(ctx: ContextTypes.DEFAULT_TYPE):
    subs = live_subs()
    if not subs: return
    data    = get_price_data()
    current = data["last"] if data else None
    if current is None: return
    msg = fmt_live_tick(current, data)
    for cid in subs:
        try:
            await ctx.bot.send_message(cid, msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning("Live (chat %d): %s", cid, e)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    if not BOT_TOKEN:
        print("\n❌  BOT_TOKEN not set!")
        print("   export BOT_TOKEN='your_token'  (Mac/Linux)")
        print("   set BOT_TOKEN=your_token        (Windows)\n")
        return

    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    for name, fn in [
        ("start","cmd_start"),("price","cmd_price"),("chart","cmd_chart"),
        ("alert","cmd_alert"),("alerts","cmd_alerts"),("cancel","cmd_cancel"),
        ("cancelall","cmd_cancelall"),("zone","cmd_zone"),("zones","cmd_zones"),
        ("delzone","cmd_delzone"),("live","cmd_live"),("help","cmd_help"),
    ]:
        app.add_handler(CommandHandler(name, eval(fn)))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.job_queue.run_repeating(job_alerts, interval=CHECK_INTERVAL, first=10, name="alerts")
    app.job_queue.run_repeating(job_live,   interval=CHECK_INTERVAL, first=20, name="live")

    logger.info("🤖 Bot started | Binance XAUUSDT.P | interval=%ds", CHECK_INTERVAL)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
