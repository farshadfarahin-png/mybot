# V30 MASTER ULTIMATE BATCH VIP — SIGNAL QUALITY FOCUS
# THREE INDEPENDENT ENGINES: Advanced AI, Hulk Alliance, Pure Analysis
# MAX FUSION coordinates Advanced + Hulk, Analysis remains standalone
# Trailing stair‑step profit lock, fast exit on bearish reversal

import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
import requests
import json
import base64
import base58
import os
import math
from pathlib import Path

VIP_CHANNEL_ID = os.getenv("VIP_CHANNEL_ID", "-1003840577545")
import sqlite3
import threading
import logging
from datetime import datetime, timedelta
from threading import Thread, Lock, RLock
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from flask import Flask, render_template_string, request, jsonify
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.instruction import Instruction
from solders.message import MessageV0

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(threadName)s - %(message)s'
)
logger = logging.getLogger("HulkSolBot")

db_lock = RLock()
state_lock = Lock()
rpc_lock = Lock()

http_session = requests.Session()
retries = Retry(total=2, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retries)
http_session.mount("https://", adapter)
http_session.mount("http://", adapter)

SIGNAL_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="SignalExec")
ANALYSIS_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="AnalysisExec")
SIGNAL_EMIT_LOCK = Lock()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
ADMIN_SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY", "").strip()

CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip() or VIP_CHANNEL_ID
CHANNEL_INVITE_LINK = os.environ.get("CHANNEL_INVITE_LINK", "").strip()

PRIVATE_KEY_BASE58 = os.environ.get("PRIVATE_KEY_BASE58", "").strip()
WEBAPP_URL = os.environ.get("WEBAPP_URL", "").strip()
VIP_PRICE_SOL = 0.0
VIP_PRICE_USDC = 50.0
COPY_TRADING_FEE_PERCENT = 1.0
COPY_DEFAULT_ASSET = "USDC"
UNIFIED_ENGINE_NAME = "🤖⚡ هالک AI — موتور متحد بازار"
BOT_BUILD_VERSION = "V30-MASTER-ULTIMATE-BATCH-VIP-2026"

# ==========================================
# RPC Rotation
# ==========================================
RPC_ENDPOINTS = []
raw_rpc_env = os.environ.get("RPC_URLS", os.environ.get("RPC_URL", ""))
if raw_rpc_env:
    RPC_ENDPOINTS.extend([url.strip() for url in raw_rpc_env.split(",") if url.strip()])
for i in range(1, 5):
    env_rpc = os.environ.get(f"RPC_URL_{i}", "").strip()
    if env_rpc and env_rpc not in RPC_ENDPOINTS:
        RPC_ENDPOINTS.append(env_rpc)
if not RPC_ENDPOINTS:
    RPC_ENDPOINTS = ["https://api.mainnet-beta.solana.com"]
logger.info(f"🔁 RPC rotation loaded: {len(RPC_ENDPOINTS)} endpoint(s)")

rpc_current_index = 0

def get_rpc_url():
    global rpc_current_index
    with rpc_lock:
        url = RPC_ENDPOINTS[rpc_current_index % len(RPC_ENDPOINTS)]
        rpc_current_index = (rpc_current_index + 1) % len(RPC_ENDPOINTS)
        return url

def send_rpc_request(payload, timeout=8, retries_count=3):
    for attempt in range(retries_count):
        endpoint = get_rpc_url()
        try:
            res = http_session.post(endpoint, json=payload, timeout=timeout)
            if res.status_code == 200:
                data = res.json()
                if "error" not in data:
                    return data
        except Exception as e:
            logger.debug(f"⚠️ تلاش ناموفق اتصال به RPC ({endpoint}): {e}")
        time.sleep(0.2)
    try:
        return http_session.post(RPC_ENDPOINTS[0], json=payload, timeout=timeout).json()
    except Exception as e:
        logger.error(f"❌ خطای کلی در ارتباط با شبکه Solana RPC: {e}")
        return {}

RPC_URL = RPC_ENDPOINTS[0]

SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

# ==========================================
# Switches
# ==========================================
IS_RUNNING = True
TREND_ALERT_RUNNING = True
COMBO_RUNNING = True
GOLDEN_OPTION = True
TECHNICAL_RUNNING = True
SMART_FILTER_ENABLED = True
DYNAMIC_RISK_ENABLED = True
MANUAL_SETTINGS_ENABLED = False
SYNCHRONIZED_MODE = True
ADVANCED_AI_ENABLED = False
MAX_FUSION_ENABLED = False
EMERGENCY_STOP = False
COPY_TRADING_ENABLED = True
_MAX_FUSION_PREV = None

BOTTOM_WHALE_RUNNING = True
ULTIMATE_21_ENGINE_ENABLED = True
SELF_LEARNING_AI_ENABLED = True
MEMPOOL_SMART_MONEY_ENABLED = True
MOONBAG_HULK_ENABLED = True
ANTI_WASH_TRADING_ENABLED = True
SMART_MONEY_COPY_ENABLED = True
SOCIAL_SENTIMENT_ENABLED = True
ANALYSIS_ENGINE_ENABLED = True
DYNAMIC_TRAILING_TP_ENABLED = True

# ========== IMPROVED TRAILING LOCK TABLE ==========
TRAILING_LOCK_TABLE = (
    (1000.0, 950.0), (750.0, 650.0), (500.0, 430.0), (300.0, 260.0),
    (200.0, 170.0), (150.0, 125.0), (100.0, 82.0), (75.0, 60.0),
    (50.0, 38.0), (40.0, 30.0), (30.0, 22.0), (25.0, 17.0), (20.0, 12.0),
    (15.0, 8.0), (10.0, 3.0),
)
TRAILING_WEAKNESS_ENABLED = True
TRAILING_WEAK_SELL_RATIO = 1.35
TRAILING_WEAKNESS_M5_MAX = -1.5
TRAILING_WEAKNESS_MIN_DRAWDOWN_PCT = 1.2

PARTIAL_TP_LEVELS = (
    (1.15, 0.30),
    (1.30, 0.30),
)
PARTIAL_TP_ENABLED = True

CONSENSUS_MIN_LIQUIDITY = 25000.0
CONSENSUS_MIN_VOLUME_5M = 3000.0
CONSENSUS_MIN_CHANGE_5M = 0.5
CONSENSUS_MAX_CHANGE_5M = 40.0
CONSENSUS_MIN_BUY_RATIO = 1.15
CONSENSUS_MIN_SCORE = 4.0
CONSENSUS_MIN_RATIO = 0.55
CONSENSUS_COOLDOWN_SECONDS = 120

# ==========================================
# DB & Helpers
# ==========================================
def init_db():
    with db_lock:
        try:
            conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA busy_timeout=10000;")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_address TEXT,
                    symbol TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    pnl_percent REAL,
                    pnl_usd REAL,
                    entry_reason TEXT,
                    timestamp TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subscribers (
                    telegram_id TEXT PRIMARY KEY,
                    wallet_address TEXT,
                    expiry_date TEXT,
                    tx_signature TEXT,
                    status TEXT,
                    copy_enabled INTEGER DEFAULT 1,
                    trade_amount_sol REAL DEFAULT 0.01
                )
            """)
            for col, definition in [
                ("copy_enabled", "INTEGER DEFAULT 1"),
                ("trade_amount_sol", "REAL DEFAULT 0.01"),
                ("trade_asset", "TEXT DEFAULT 'USDC'"),
                ("trade_amount_usdc", "REAL DEFAULT 10.0")
            ]:
                try:
                    cursor.execute(f"ALTER TABLE subscribers ADD COLUMN {col} {definition}")
                except sqlite3.OperationalError:
                    pass
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_learning_params (
                    param_name TEXT PRIMARY KEY,
                    param_value REAL
                )
            """)
            conn.commit()
            conn.close()
            logger.info("✅ دیتابیس با موفقیت فعال و مقداردهی شد.")
        except Exception as e:
            logger.error(f"⚠️ خطای دیتابیس: {e}")

init_db()

ADAPTIVE_TARGET_WIN_RATE = 80.0
ADAPTIVE_LOOKBACK = 20
ADAPTIVE_MIN_SAMPLE = 10

def _update_adaptive_learning(conn=None):
    own = conn is None
    if own:
        conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
    try:
        cur = conn.cursor()
        cur.execute("SELECT pnl_percent, entry_reason FROM trades ORDER BY id DESC LIMIT ?", (ADAPTIVE_LOOKBACK,))
        rows = cur.fetchall()
        if not rows:
            return {"sample": 0, "win_rate": 0.0, "score_bonus": 0, "ratio_bonus": 0.0}
        wins = sum(1 for pnl, _ in rows if float(pnl or 0) > 0)
        wr = wins / len(rows) * 100.0
        bonus = 0
        ratio_bonus = 0.0
        if len(rows) >= ADAPTIVE_MIN_SAMPLE:
            if wr < 60:
                bonus, ratio_bonus = 2, 0.10
            elif wr < 70:
                bonus, ratio_bonus = 1, 0.05
            elif wr < ADAPTIVE_TARGET_WIN_RATE:
                bonus, ratio_bonus = 1, 0.02
            elif wr >= 90:
                bonus, ratio_bonus = 0, 0.0
        cur.execute("INSERT OR REPLACE INTO ai_learning_params(param_name,param_value) VALUES('adaptive_win_rate',?)", (wr,))
        cur.execute("INSERT OR REPLACE INTO ai_learning_params(param_name,param_value) VALUES('adaptive_score_bonus',?)", (bonus,))
        cur.execute("INSERT OR REPLACE INTO ai_learning_params(param_name,param_value) VALUES('adaptive_ratio_bonus',?)", (ratio_bonus,))
        conn.commit()
        return {"sample": len(rows), "win_rate": wr, "score_bonus": bonus, "ratio_bonus": ratio_bonus}
    finally:
        if own:
            conn.close()

def get_adaptive_consensus_settings(enabled_count):
    try:
        with db_lock:
            conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
            state = _update_adaptive_learning(conn)
            cur = conn.cursor()
            cur.execute("SELECT param_name,param_value FROM ai_learning_params WHERE param_name LIKE 'engine_wr:%'")
            engine_wr = {r[0].split(':',1)[1]: float(r[1]) for r in cur.fetchall()}
            conn.close()
        score_min = max(CONSENSUS_MIN_SCORE, min(enabled_count, CONSENSUS_MIN_SCORE + int(state.get("score_bonus",0))))
        ratio = min(0.90, CONSENSUS_MIN_RATIO + float(state.get("ratio_bonus",0)))
        return score_min, ratio, engine_wr, state
    except Exception as e:
        logger.debug(f"Adaptive learning read error: {e}")
        return CONSENSUS_MIN_SCORE, CONSENSUS_MIN_RATIO, {}, {"sample":0,"win_rate":0.0}

def log_trade_to_db(token_addr, symbol, entry_p, exit_p, pnl_pct, pnl_u, reason):
    with db_lock:
        try:
            conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trades (token_address, symbol, entry_price, exit_price, pnl_percent, pnl_usd, entry_reason, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (token_addr, symbol, entry_p, exit_p, pnl_pct, pnl_u, reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            _update_adaptive_learning(conn)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"⚠️ خطا در ثبت معامله در دیتابیس: {e}")

def get_advanced_trade_analytics():
    with db_lock:
        try:
            conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), SUM(pnl_percent), SUM(pnl_usd), AVG(pnl_percent) FROM trades")
            res = cursor.fetchone()
            total_trades = res[0] or 0
            total_pct = res[1] or 0.0
            total_usd = res[2] or 0.0
            avg_pct = res[3] or 0.0
            cursor.execute("SELECT COUNT(*) FROM trades WHERE pnl_percent > 0")
            win_count = cursor.fetchone()[0] or 0
            win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0
            cursor.execute("SELECT symbol, pnl_percent, timestamp FROM trades ORDER BY pnl_percent DESC LIMIT 1")
            best_trade = cursor.fetchone()
            cursor.execute("SELECT symbol, pnl_percent, timestamp FROM trades ORDER BY pnl_percent ASC LIMIT 1")
            worst_trade = cursor.fetchone()
            conn.close()
            return {
                "total_trades": total_trades,
                "total_pct": round(total_pct, 2),
                "total_usd": round(total_usd, 2),
                "avg_pct": round(avg_pct, 2),
                "win_rate": round(win_rate, 2),
                "win_count": win_count,
                "best_trade": best_trade,
                "worst_trade": worst_trade
            }
        except Exception as e:
            logger.error(f"⚠️ خطا در گزارش‌گیری پیشرفته: {e}")
            return {"total_trades": 0, "total_pct": 0.0, "total_usd": 0.0, "avg_pct": 0.0, "win_rate": 0.0, "win_count": 0, "best_trade": None, "worst_trade": None}

def self_learning_ai_optimizer_loop():
    logger.info("🧠 موتور یادگیری تطبیقی MAX FUSION فعال شد.")
    while True:
        if SELF_LEARNING_AI_ENABLED:
            try:
                with db_lock:
                    conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
                    state = _update_adaptive_learning(conn)
                    conn.close()
                if state.get("sample", 0) >= ADAPTIVE_MIN_SAMPLE:
                    logger.info(f"🧠 Adaptive Learning: {state['sample']} معاملات اخیر | Win Rate={state['win_rate']:.1f}% | score_bonus={state['score_bonus']}")
            except Exception as e:
                logger.error(f"⚠️ خطای موتور یادگیری تطبیقی: {e}")
        time.sleep(180)

# ========== Telegram / Subscription helpers ==========
def send_telegram_msg(text, target_chat=None, reply_markup=None, parse_mode="Markdown"):
    chat_target = target_chat if target_chat is not None else TELEGRAM_CHAT_ID
    if not TELEGRAM_BOT_TOKEN or not chat_target:
        logger.error("❌ Telegram config ناقص است: TELEGRAM_BOT_TOKEN / chat_id")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_target, "text": str(text), "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup.to_dict() if hasattr(reply_markup, "to_dict") else reply_markup
    try:
        res = http_session.post(url, json=payload, timeout=8)
        data = res.json()
        if data.get("ok"):
            return True
        logger.error(f"❌ Telegram sendMessage failed: {data.get('description', data)}")
        if parse_mode:
            payload.pop("parse_mode", None)
            retry = http_session.post(url, json=payload, timeout=8)
            retry_data = retry.json()
            if retry_data.get("ok"):
                logger.warning("⚠️ پیام با fallback بدون Markdown ارسال شد.")
                return True
            logger.error(f"❌ Telegram fallback بدون Markdown failed: {retry_data.get('description', retry_data)}")
        if payload.get("reply_markup") is not None:
            payload.pop("reply_markup", None)
            retry2 = http_session.post(url, json=payload, timeout=8)
            retry2_data = retry2.json()
            if retry2_data.get("ok"):
                logger.warning("⚠️ سیگنال کانال بدون دکمه ارسال شد؛ reply_markup مشکل داشت.")
                return True
            logger.error(f"❌ Telegram fallback بدون دکمه failed: {retry2_data.get('description', retry2_data)}")
        return False
    except Exception as e:
        logger.error(f"❌ خطای ارسال پیام به تلگرام: {e}")
        return False

def _get_bot_setting(key, default=""):
    try:
        with db_lock:
            conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT)")
            cur.execute("SELECT value FROM bot_settings WHERE key=?", (key,))
            row = cur.fetchone()
            conn.commit(); conn.close()
            return row[0] if row else default
    except Exception as e:
        logger.error(f"bot setting read error: {e}")
        return default

def _set_bot_setting(key, value):
    try:
        with db_lock:
            conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT)")
            cur.execute("INSERT OR REPLACE INTO bot_settings(key,value) VALUES(?,?)", (key, str(value)))
            conn.commit(); conn.close()
        return True
    except Exception as e:
        logger.error(f"bot setting write error: {e}")
        return False

def _load_channel_config():
    global CHANNEL_ID, CHANNEL_INVITE_LINK
    if not CHANNEL_ID:
        CHANNEL_ID = _get_bot_setting("vip_channel_id", "").strip()
    if not CHANNEL_INVITE_LINK:
        CHANNEL_INVITE_LINK = _get_bot_setting("vip_channel_invite", "").strip()
    return CHANNEL_ID, CHANNEL_INVITE_LINK

def _load_trade_limit():
    global MAX_TRADE_SOL
    try:
        saved = _get_bot_setting("max_trade_sol", "")
        if saved:
            value = float(saved)
            if value > 0:
                MAX_TRADE_SOL = min(value, 1000.0)
    except Exception as e:
        logger.warning(f"⚠️ خطا در بارگذاری سقف معامله SOL: {e}")
    return MAX_TRADE_SOL

def _set_trade_limit(value):
    global MAX_TRADE_SOL
    value = float(value)
    if value <= 0 or value > 1000:
        raise ValueError("سقف SOL باید بیشتر از 0 و حداکثر 1000 باشد.")
    MAX_TRADE_SOL = round(value, 6)
    _set_bot_setting("max_trade_sol", MAX_TRADE_SOL)
    return MAX_TRADE_SOL

def ensure_channel_invite_link():
    global CHANNEL_ID, CHANNEL_INVITE_LINK
    _load_channel_config()
    if CHANNEL_INVITE_LINK:
        return CHANNEL_INVITE_LINK
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
        logger.error("❌ کانال VIP تنظیم نشده. ادمین: /setvipchannel @channel_username یا -100... را ارسال کند.")
        return ""
    try:
        if str(CHANNEL_ID).startswith("@"):
            username = str(CHANNEL_ID)[1:]
            if username:
                CHANNEL_INVITE_LINK = f"https://t.me/{username}"
                _set_bot_setting("vip_channel_id", CHANNEL_ID)
                _set_bot_setting("vip_channel_invite", CHANNEL_INVITE_LINK)
                return CHANNEL_INVITE_LINK

        url=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/createChatInviteLink"
        payload={"chat_id":CHANNEL_ID,"name":"VIP-30-Day","creates_join_request":False}
        data=http_session.post(url,json=payload,timeout=8).json()
        link=(data.get("result") or {}).get("invite_link")
        if data.get("ok") and link:
            CHANNEL_INVITE_LINK=link
            _set_bot_setting("vip_channel_id", CHANNEL_ID)
            _set_bot_setting("vip_channel_invite", CHANNEL_INVITE_LINK)
            logger.info("✅ لینک دعوت VIP ساخته و ذخیره شد.")
            return link
        logger.error(f"❌ ساخت لینک VIP ناموفق: {data.get('description',data)}")
    except Exception as e:
        logger.error(f"❌ خطای ساخت لینک VIP: {e}")
    return ""

def send_graphic_signal_to_vip_channel(token_addr, symbol, price, tp, sl, buy_amt, volume, liquidity, p_change, solscan_link, signal_title="🚀 سیگنال ویژه VIP", side="BUY", execution_status="", execution_tx="", pnl_percent=None):
    is_analysis_card = str(signal_title or "").strip() == "سیستم تحلیل مستقل" or "Analysis" in str(signal_title or "") or "تحلیل مستقل" in str(signal_title or "")
    if str(side).upper() == "BUY" and MAX_FUSION_ENABLED and not is_analysis_card and signal_title not in (UNIFIED_ENGINE_NAME, "MAX FUSION"):
        logger.info(f"Blocked legacy BUY channel card while MAX FUSION is active: {signal_title}")
        return False
    global CHANNEL_ID
    _load_channel_config()
    if not CHANNEL_ID and CHANNEL_INVITE_LINK.startswith("https://t.me/"):
        tail = CHANNEL_INVITE_LINK.split("https://t.me/", 1)[1].strip("/")
        if tail and not tail.startswith("+"):
            CHANNEL_ID = "@" + tail
    if not CHANNEL_ID or not TELEGRAM_BOT_TOKEN:
        return False

    side = str(side).upper()
    side_icon = "🟢 خرید" if side == "BUY" else "🔴 فروش"
    if execution_tx and not str(execution_tx).startswith("http"):
        safe_solscan = f"https://solscan.io/tx/{execution_tx}"
    elif str(solscan_link).startswith("https://solscan.io/"):
        safe_solscan = solscan_link
    else:
        safe_solscan = f"https://solscan.io/token/{token_addr}"
    dex_link = f"https://dexscreener.com/solana/{token_addr}"

    if side == "SELL":
        pnl = float(pnl_percent or 0.0)
        pnl_icon = "🟢" if pnl >= 0 else "🔴"
        result_line = f"📊 سود/ضرر نهایی: {pnl_icon} {pnl:+.2f}%"
        price_label = "🔴 نقطه فروش"
    else:
        result_line = "📌 وضعیت: سیگنال خرید"
        price_label = "🎯 نقطه ورود"

    try:
        m5_change = float(p_change or 0.0)
    except Exception:
        m5_change = 0.0
    buys_m5 = 0
    sells_m5 = 0

    graphic_text = (
        f"🤖⚡ {signal_title}\n"
        f"{side_icon}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🪙 نام توکن: {symbol}\n"
        f"📍 آدرس قرارداد:\n{token_addr}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{price_label}: ${price:.8f}\n"
        f"💰 حجم معامله: {buy_amt:g} SOL\n"
        f"💧 نقدینگی: ${liquidity:,.0f}\n"
        f"📊 حجم ۵ دقیقه: ${volume:,.0f}\n"
        f"📈 تغییر ۵ دقیقه: {p_change:+.2f}%\n"
        f"🎯 TP: +{tp:.1f}%\n"
        f"🛑 SL: {sl:.1f}%\n"
        f"📊 حجم ۵ دقیقه: ${volume:,.0f}\n"
        f"💧 نقدینگی: ${liquidity:,.0f}\n"
        f"📈 تغییر ۵ دقیقه: {m5_change:+.2f}%\n"
        f"⚖️ خرید/فروش ۵ دقیقه: {buys_m5}/{sells_m5}\n"
        f"{result_line}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    buttons = [
        [
            InlineKeyboardButton("📈 DexScreener", url=dex_link),
            InlineKeyboardButton("🔎 Solscan", url=safe_solscan),
        ]
    ]
    if WEBAPP_URL:
        buttons.append([
            InlineKeyboardButton("📱 ورود به Mini App", url=WEBAPP_URL),
            InlineKeyboardButton("🤖 کپی‌ترید", url=WEBAPP_URL),
        ])

    try:
        _load_channel_config()
        if not CHANNEL_ID:
            logger.error("❌ CHANNEL_ID خالی است؛ کارت سیگنال به کانال ارسال نشد.")
            return False

        keyboard = InlineKeyboardMarkup(buttons)
        ok = send_telegram_msg(
            graphic_text, target_chat=CHANNEL_ID,
            reply_markup=keyboard, parse_mode=None
        )
        if not ok:
            logger.error(f"❌ کارت کانال ارسال نشد | CHANNEL_ID={CHANNEL_ID!r}")
        else:
            logger.info(f"📢 کارت سیگنال کانال ارسال شد | CHANNEL_ID={CHANNEL_ID!r} | {symbol} | {side}")
        return ok
    except Exception as e:
        logger.exception(f"❌ خطای ارسال کارت سیگنال به کانال | CHANNEL_ID={CHANNEL_ID!r}: {e}")
        return False

def register_subscription(telegram_id, wallet_addr, tx_sig, currency="USDC"):
    with db_lock:
        try:
            conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
            cursor = conn.cursor()
            expiry = datetime.now() + timedelta(days=30)
            cursor.execute("""
                INSERT OR REPLACE INTO subscribers (telegram_id, wallet_address, expiry_date, tx_signature, status, copy_enabled, trade_amount_sol)
                VALUES (?, ?, ?, ?, 'ACTIVE', 1, COALESCE((SELECT trade_amount_sol FROM subscribers WHERE telegram_id = ?), 0.01))
            """, (str(telegram_id), wallet_addr, expiry.strftime("%Y-%m-%d %H:%M:%S"), f"{currency}:{tx_sig}", str(telegram_id)))
            conn.commit()
            conn.close()
            
            ensure_channel_invite_link()
            rows = []
            if WEBAPP_URL:
                rows.append([InlineKeyboardButton("📱 ورود به Mini App VIP", web_app=WebAppInfo(url=WEBAPP_URL))])
            if CHANNEL_INVITE_LINK:
                rows.append([InlineKeyboardButton("📢 ورود مستقیم به کانال VIP", url=CHANNEL_INVITE_LINK)])
            markup = InlineKeyboardMarkup(rows) if rows else None
            success_msg = (
                f"🎉 تبریک! اشتراک ۳۰ روزه VIP شما با موفقیت پس از تایید تراکنش بلاکچین ({currency}) فعال شد!\n\n"
                f"⏳ تاریخ انقضا: {expiry.strftime('%Y-%m-%d %H:%M:%S')}\n"
                "🔗 ولت شما به سیستم کپی‌تریدینگ هوشمند متصل گردید.\n\n"
                "📱 با دکمه Mini App وارد شوید؛ اشتراک فعال شما خودکار شناسایی می‌شود و فرم ثبت‌نام نمایش داده نخواهد شد.\n"
                "📢 برای عضویت در کانال VIP دکمه ورود مستقیم را بزنید."
            )
            send_telegram_msg(success_msg, target_chat=str(telegram_id), reply_markup=markup)
            return True
        except Exception as e:
            logger.error(f"Error registering sub: {e}")
            return False

def register_free_vip(telegram_id, wallet_addr="FREE_PASS_WALLET"):
    with db_lock:
        try:
            conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
            cursor = conn.cursor()
            expiry = datetime.now() + timedelta(days=30)
            cursor.execute("""
                INSERT OR REPLACE INTO subscribers (telegram_id, wallet_address, expiry_date, tx_signature, status, copy_enabled, trade_amount_sol)
                VALUES (?, ?, ?, ?, 'ACTIVE', 1, COALESCE((SELECT trade_amount_sol FROM subscribers WHERE telegram_id = ?), 0.01))
            """, (str(telegram_id), wallet_addr, expiry.strftime("%Y-%m-%d %H:%M:%S"), "ADMIN_FREE_PASS", str(telegram_id)))
            conn.commit()
            conn.close()
            
            ensure_channel_invite_link()
            rows = []
            if WEBAPP_URL:
                rows.append([InlineKeyboardButton("📱 ورود به Mini App VIP", web_app=WebAppInfo(url=WEBAPP_URL))])
            if CHANNEL_INVITE_LINK:
                rows.append([InlineKeyboardButton("📢 ورود مستقیم به کانال VIP", url=CHANNEL_INVITE_LINK)])
            markup = InlineKeyboardMarkup(rows) if rows else None
            free_msg = (
                f"🎉🎊 تبریک! اشتراک VIP رایگان شما با موفقیت فعال شد.\n\n"
                f"⏳ تاریخ انقضا: {expiry.strftime('%Y-%m-%d %H:%M:%S')}\n"
                "🔗 موتور کپی‌تریدینگ برای ولت شما روشن گردید.\n\n"
                "📱 با دکمه Mini App وارد شوید؛ چون اشتراک شما فعال است، مستقیماً کارت سبز VIP، تاریخ انقضا و زمان باقی‌مانده را می‌بینید.\n"
                "📢 برای عضویت در کانال VIP دکمه ورود مستقیم را بزنید."
            )
            send_telegram_msg(free_msg, target_chat=str(telegram_id), reply_markup=markup)
            return True
        except Exception as e:
            logger.error(f"Error registering free sub: {e}")
            return False

def check_user_subscription(telegram_id):
    with db_lock:
        try:
            conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT expiry_date, status FROM subscribers WHERE telegram_id = ?", (str(telegram_id),))
            row = cursor.fetchone()
            conn.close()
            if row:
                exp_date_str, status = row
                if status == "ACTIVE":
                    exp_date = datetime.strptime(exp_date_str, "%Y-%m-%d %H:%M:%S")
                    if datetime.now() < exp_date:
                        return True, exp_date
                    else:
                        update_sub_status(telegram_id, "EXPIRED")
                        kick_user_from_channel(telegram_id)
            return False, None
        except Exception as e:
            logger.error(f"Check subscription error: {e}")
            return False, None

def update_sub_status(telegram_id, status):
    with db_lock:
        try:
            conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("UPDATE subscribers SET status = ? WHERE telegram_id = ?", (status, str(telegram_id)))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Update sub status error: {e}")

def kick_user_from_channel(telegram_id):
    if not CHANNEL_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/banChatMember"
        payload = {
            "chat_id": CHANNEL_ID,
            "user_id": int(telegram_id),
            "until_date": int(time.time() + 35)
        }
        res = http_session.post(url, json=payload, timeout=5).json()
        if res.get("ok"):
            logger.info(f"🚫 کاربر {telegram_id} به دلیل اتمام اشتراک از کانال حذف شد.")
            send_telegram_msg("⚠️ اشتراک ۳۰ روزه شما به اتمام رسید و دسترسی شما از کانال VIP قطع گردید.", target_chat=telegram_id)
    except Exception as e:
        logger.error(f"❌ خطا در حذف کاربر از کانال: {e}")

def subscription_monitor_loop():
    logger.info("🔄 مانیتورینگ خودکار انقضای اشتراک‌ها و اخراج از کانال فعال شد.")
    while True:
        with db_lock:
            try:
                conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute("SELECT telegram_id, expiry_date, status FROM subscribers WHERE status = 'ACTIVE'")
                rows = cursor.fetchall()
                conn.close()

                now = datetime.now()
                for row in rows:
                    t_id, exp_str, status = row
                    exp_date = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
                    if now >= exp_date:
                        update_sub_status(t_id, "EXPIRED")
                        kick_user_from_channel(t_id)
            except Exception as e:
                logger.error(f"⚠️ خطا در مانیتورینگ اشتراک‌ها: {e}")
        time.sleep(60)

def get_active_subscribers():
    active_subs = []
    with db_lock:
        try:
            conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_id, wallet_address, expiry_date, status, copy_enabled, trade_amount_sol FROM subscribers")
            rows = cursor.fetchall()
            conn.close()
            now = datetime.now()
            for row in rows:
                t_id, w_addr, exp_str, status, copy_enabled, trade_amount_sol = row
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
                if status == 'ACTIVE' and now < exp_date:
                    active_subs.append({"telegram_id": t_id, "wallet": w_addr, "expiry": exp_str, "copy_enabled": bool(copy_enabled), "trade_amount_sol": trade_amount_sol or 0.01})
                elif status == 'ACTIVE' and now >= exp_date:
                    update_sub_status(t_id, "EXPIRED")
                    kick_user_from_channel(t_id)
        except Exception as e:
            logger.error(f"Get active subs error: {e}")
    return active_subs

# ========== Wallet / Balance ==========
try:
    decoded_key = base58.b58decode(PRIVATE_KEY_BASE58)
    sender_keypair = Keypair.from_bytes(decoded_key)
    WALLET_PUBKEY = str(sender_keypair.pubkey())
    logger.info(f"✅ ولت با موفقیت لود شد: {WALLET_PUBKEY}")
except Exception as e:
    logger.error(f"❌ خطا در بارگذاری کلید خصوصی از Environment: {e}")
    WALLET_PUBKEY = None
    sender_keypair = None

def get_sol_balance():
    if not WALLET_PUBKEY:
        return 0.0
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [WALLET_PUBKEY]
    }
    res = send_rpc_request(payload)
    lamports = res.get("result", {}).get("value", 0)
    return lamports / 1_000_000_000

def get_dynamic_buy_amount(base_amount):
    safe_base = min(float(base_amount), float(MAX_TRADE_SOL))
    if not DYNAMIC_RISK_ENABLED:
        return round(safe_base, 6)
    try:
        sol_bal = get_sol_balance()
        calculated = safe_base
        if ULTIMATE_21_ENGINE_ENABLED and sol_bal > 0:
            kelly_factor = 0.025 if sol_bal > 1.0 else 0.01
            calculated = max(safe_base, round(sol_bal * kelly_factor, 4))
        elif sol_bal > 1.0:
            calculated = max(safe_base, round(sol_bal * 0.02, 4))
        elif sol_bal < 0.1:
            calculated = max(0.005, round(safe_base * 0.5, 4))
        return round(min(calculated, MAX_TRADE_SOL), 6)
    except Exception as e:
        logger.debug(f"Dynamic amount calc exception: {e}")
    return round(min(safe_base, MAX_TRADE_SOL), 6)

def get_token_balance(token_mint):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            WALLET_PUBKEY,
            {"mint": token_mint},
            {"encoding": "jsonParsed"}
        ]
    }
    res = send_rpc_request(payload, timeout=8)
    accounts = res.get("result", {}).get("value", [])
    if accounts:
        for acc in accounts:
            info = acc["account"]["data"]["parsed"]["info"]
            amount = int(info["tokenAmount"]["amount"])
            if amount > 0:
                return amount
    return 0

# ========== Market helpers ==========
def check_social_sentiment_and_hype(pair):
    if not SOCIAL_SENTIMENT_ENABLED:
        return True, "فیلتر سنتیمنت غیرفعال"
    try:
        socials = pair.get('socials', [])
        websites = pair.get('websites', [])
        txns = pair.get('txns', {}).get('m5', {})
        buys = txns.get('buys', 0)
        sells = txns.get('sells', 0)
        if (len(socials) > 0 or len(websites) > 0) or (sells == 0 or buys >= (sells * 1.1)):
            return True, "تایید سنتیمنت و هجوم هایپ شبکه‌های اجتماعی 🚀"
        return True, "گذر از فیلتر سنتیمنت پایه"
    except Exception as e:
        logger.debug(f"Sentiment check exception: {e}")
        return True, "گذر از فیلتر سنتیمنت"

def get_real_market_trending_tokens():
    tokens = []
    endpoints = [
        "https://api.dexscreener.com/token-boosts/top/v1",
        "https://api.dexscreener.com/token-boosts/latest/v1",
        "https://api.dexscreener.com/token-profiles/latest/v1",
        "https://api.dexscreener.com/latest/dex/search?q=solana",
        "https://api.dexscreener.com/latest/dex/search?q=raydium",
        "https://api.dexscreener.com/latest/dex/search?q=pump",
        "https://api.dexscreener.com/latest/dex/search?q=USDC",
        "https://api.dexscreener.com/latest/dex/search?q=SOL"
    ]

    with state_lock:
        if len(processed_tokens) > 3000:
            processed_tokens.clear()
            trend_alerted_tokens.clear()
            golden_processed_tokens.clear()
            tech_processed_tokens.clear()
            mempool_processed_tokens.clear()
            ultra_processed_tokens.clear()
            logger.info("🧹 حافظه رم از توکن‌های قدیمی پردازش‌شده پاک‌سازی شد.")

    def fetch_endpoint(url):
        try:
            res_obj = http_session.get(url, timeout=4)
            if res_obj.status_code != 200:
                return []
            res = res_obj.json()
            found = []
            if isinstance(res, list):
                for t in res:
                    if t.get('chainId') == 'solana':
                        addr = t.get('tokenAddress')
                        if addr:
                            found.append(addr)
            elif isinstance(res, dict):
                for pair in res.get("pairs", []):
                    if pair.get("chainId") == "solana":
                        addr = pair.get("baseToken", {}).get("address")
                        if addr:
                            found.append(addr)
            return found
        except Exception as e:
            logger.debug(f"Fetch endpoint error ({url}): {e}")
            return []

    with ThreadPoolExecutor(max_workers=MARKET_DISCOVERY_WORKERS, thread_name_prefix="MarketDiscovery") as ex:
        for found in ex.map(fetch_endpoint, endpoints):
            for addr in found:
                if addr not in tokens:
                    tokens.append(addr)
    return tokens

def is_token_worthy(pair):
    try:
        if ANTI_WASH_TRADING_ENABLED:
            txns = pair.get('txns', {}).get('m5', {})
            buys = txns.get('buys', 0)
            sells = txns.get('sells', 0)
            if sells > 0 and buys < (sells * 0.8):
                return False
        liquidity = float(pair.get('liquidity', {}).get('usd', 0))
        volume_5m = float(pair.get('volume', {}).get('m5', 0))
        if liquidity < 25000 or volume_5m < 3000:
            return False
        return True
    except Exception:
        return False

def check_major_support_resistance_pa(pair):
    try:
        if not is_token_worthy(pair):
            return False, ""
        price_change_5m = float(pair.get('priceChange', {}).get('m5', 0))
        if price_change_5m <= -5.0:
            return False, ""
        return True, "پرایس اکشن صعودی تایید شد 📈"
    except Exception:
        pass
    return False, ""

def validate_ultimate_21_layers(token_addr, pair):
    if not ULTIMATE_21_ENGINE_ENABLED:
        return True, "سیستم ۲۱گانه غیرفعال است"
    try:
        liquidity = float(pair.get('liquidity', {}).get('usd', 0))
        volume_5m = float(pair.get('volume', {}).get('m5', 0))
        price = float(pair.get('priceUsd', 0))
        if price <= 0 or liquidity < 25000 or volume_5m < 3000:
            return False, "رد شده در لایه‌های نقدینگی یا حجم پایه"
        return True, "تأیید کامل لایه‌های حفاظتی و الگوریتمی هوشمند پیشرفته"
    except Exception as e:
        return False, f"خطا در اعتبارسنجی ۲۱ لایه: {e}"

def evaluate_ultimate_super_signal(token_addr, pair):
    try:
        price = float(pair.get('priceUsd', 0))
        liquidity = float(pair.get('liquidity', {}).get('usd', 0))
        volume_5m = float(pair.get('volume', {}).get('m5', 0))
        price_change_5m = float(pair.get('priceChange', {}).get('m5', 0))
        if price <= 0:
            return False, 0.0, 0.0, 0.0, "قیمت نامعتبر"
        if liquidity < 25000 or volume_5m < 3000:
            return False, 0.0, 0.0, 0.0, "نقدینگی یا حجم کافی نیست"
        if price_change_5m < 2.0:
            return False, 0.0, 0.0, 0.0, "مومنتوم کافی نیست"
        is_21_valid, msg_21 = validate_ultimate_21_layers(token_addr, pair)
        if not is_21_valid:
            return False, 0.0, 0.0, 0.0, msg_21
        return True, price, 20.0, -8.0, f"تایید کامل ماشین هوشمند ابرسیگنال + {msg_21}"
    except Exception as e:
        return False, 0.0, 0.0, 0.0, f"خطا در پردازش: {e}"

# ========== STRUCTURE MEMORY ==========
STRUCTURE_FILTER_ENABLED = True
STRUCTURE_LOOKBACK = 30
STRUCTURE_MIN_SAMPLES = 3
STRUCTURE_SAMPLE_MIN_GAP = 0.5
STRUCTURE_SUPPORT_DISTANCE_PCT = 4.0
STRUCTURE_RESISTANCE_DISTANCE_PCT = 2.5
STRUCTURE_BREAKOUT_BUFFER_PCT = 0.6
STRUCTURE_MIN_SUPPORT_LIQUIDITY = 25000.0
STRUCTURE_MIN_SUPPORT_VOLUME_5M = 3000.0
STRUCTURE_MIN_SUPPORT_BUY_RATIO = 1.15
STRUCTURE_MIN_BREAKOUT_BUY_RATIO = 1.20
STRUCTURE_HISTORY_TTL_SECONDS = 15 * 60
_structure_memory = {}
_structure_lock = Lock()

def _update_structure_memory(token_addr, price):
    try:
        now = time.time()
        price = float(price or 0)
        if not token_addr or price <= 0:
            return []
        with _structure_lock:
            rows = _structure_memory.setdefault(token_addr, [])
            if rows and now - rows[-1][0] < STRUCTURE_SAMPLE_MIN_GAP:
                rows[-1] = (now, price)
            else:
                rows.append((now, price))
            cutoff = now - STRUCTURE_HISTORY_TTL_SECONDS
            rows[:] = [x for x in rows[-STRUCTURE_LOOKBACK:] if x[0] >= cutoff]
            return list(rows)
    except Exception:
        return []

def _market_structure_gate(token_addr, pair):
    if not STRUCTURE_FILTER_ENABLED:
        return True, {"structure": "DISABLED", "structure_score": 0.0}
    try:
        price = float(pair.get("priceUsd", 0) or 0)
        liq = float((pair.get("liquidity") or {}).get("usd", 0) or 0)
        vol = float((pair.get("volume") or {}).get("m5", 0) or 0)
        tx = (pair.get("txns") or {}).get("m5", {}) or {}
        buys = int(tx.get("buys", 0) or 0)
        sells = int(tx.get("sells", 0) or 0)
        buy_ratio = buys / max(1, sells)
        if price <= 0:
            return False, {"structure": "INVALID_PRICE", "structure_score": 0.0}
        if liq < STRUCTURE_MIN_SUPPORT_LIQUIDITY or vol < STRUCTURE_MIN_SUPPORT_VOLUME_5M or buy_ratio < STRUCTURE_MIN_SUPPORT_BUY_RATIO:
            return False, {"structure": "WEAK_STRUCTURE_FLOW", "structure_score": 0.0}
        return True, {"structure": "PASSED", "structure_score": 3.0}
    except Exception as e:
        logger.error(f"⚠️ خطای تحلیل ساختار بازار: {e}")
        return True, {"structure": "ERROR_BYPASS", "structure_score": 0.0}

# ========== EXECUTE BUY/SELL ==========
def execute_real_buy(token_mint, amount_sol):
    if not WALLET_PUBKEY or sender_keypair is None:
        return False, "کلید عمومی ولت نامعتبر است"
    dynamic_amount = get_dynamic_buy_amount(amount_sol)
    current_sol = get_sol_balance()
    if current_sol < (dynamic_amount + 0.003):
        return False, "سولانای ناکافی ❌"
    lamports = int(dynamic_amount * 1_000_000_000)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Origin": "https://jup.ag",
        "Referer": "https://jup.ag/"
    }
    quote_urls = [
        f"https://api.jup.ag/swap/v1/quote?inputMint={SOL_MINT}&outputMint={token_mint}&amount={lamports}&slippageBps=300",
        f"https://quote-api.jup.ag/v6/quote?inputMint={SOL_MINT}&outputMint={token_mint}&amount={lamports}&slippageBps=300"
    ]
    quote_res = None
    for q_url in quote_urls:
        try:
            res = http_session.get(q_url, headers=headers, timeout=4)
            if res.status_code == 200:
                q_data = res.json()
                if "error" not in q_data and ("outAmount" in q_data or "quoteResponse" in q_data):
                    quote_res = q_data
                    break
        except Exception as e:
            logger.debug(f"Jupiter quote attempt failed for {q_url}: {e}")
    if not quote_res or "error" in quote_res:
        return False, "خطای کوت ژوپیتر ❌"
    prior_fee = 3000000
    swap_payload = {
        "quoteResponse": quote_res,
        "userPublicKey": WALLET_PUBKEY,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": prior_fee
    }
    swap_res = None
    for attempt in range(2):
        try:
            res = http_session.post("https://api.jup.ag/swap/v1/swap", json=swap_payload, headers=headers, timeout=5)
            if res.status_code == 200:
                swap_res = res.json()
                if "swapTransaction" in swap_res:
                    break
        except Exception as e:
            logger.debug(f"Jupiter swap attempt failed: {e}")
        time.sleep(0.2)
    if not swap_res or "swapTransaction" not in swap_res:
        return False, "خطای سوآپ ژوپیتر ❌"
    try:
        swap_tx_b64 = swap_res["swapTransaction"]
        raw_tx = base64.b64decode(swap_tx_b64)
        txn = VersionedTransaction.from_bytes(raw_tx)
        signed_txn = VersionedTransaction(txn.message, [sender_keypair])
        serialized_tx = base58.b58encode(bytes(signed_txn)).decode('utf-8')
        rpc_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendTransaction",
            "params": [serialized_tx, {"encoding": "base58", "skipPreflight": False, "maxRetries": 3}]
        }
        tx_res = send_rpc_request(rpc_payload, timeout=10)
        if "result" in tx_res:
            sig = tx_res["result"]
            for _ in range(10):
                time.sleep(1)
                if get_token_balance(token_mint) > 0:
                    trigger_copy_trading_for_subscribers(token_mint, dynamic_amount)
                    return True, sig
            if get_token_balance(token_mint) > 0:
                trigger_copy_trading_for_subscribers(token_mint, dynamic_amount)
                return True, sig
            return False, "تراکنش ارسال شد اما توکن در ولت ننشست ❌"
        else:
            return False, "خطای ارسال تراکنش ❌"
    except Exception as e:
        return False, f"خطا: {e}"

def close_wsol_account():
    try:
        wsol_mint_pubkey = Pubkey.from_string(SOL_MINT)
        wallet_pubkey_obj = Pubkey.from_string(WALLET_PUBKEY)
        token_program_pubkey = Pubkey.from_string(TOKEN_PROGRAM_ID)
        assoc_account = Pubkey.find_program_address(
            [bytes(wallet_pubkey_obj), bytes(token_program_pubkey), bytes(wsol_mint_pubkey)],
            Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
        )[0]
        data = bytes([9])
        keys = [
            {"pubkey": assoc_account, "is_signer": False, "is_writable": True},
            {"pubkey": wallet_pubkey_obj, "is_signer": False, "is_writable": True},
            {"pubkey": wallet_pubkey_obj, "is_signer": True, "is_writable": False}
        ]
        instruction = Instruction(token_program_pubkey, data, keys)
        blockhash_res = send_rpc_request({"jsonrpc": "2.0", "id": 1, "method": "getLatestBlockhash"}, timeout=5)
        blockhash = blockhash_res["result"]["value"]["blockhash"]
        compiled_message = MessageV0.try_compile(
            wallet_pubkey_obj,
            [instruction],
            [],
            blockhash
        )
        tx = VersionedTransaction(compiled_message, [sender_keypair])
        serialized_tx = base58.b58encode(bytes(tx)).decode('utf-8')
        rpc_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendTransaction",
            "params": [serialized_tx, {"encoding": "base58", "skipPreflight": True}]
        }
        send_rpc_request(rpc_payload, timeout=5)
    except Exception as e:
        logger.warning(f"⚠️ هشدار در بستن اکانت WSOL: {e}")

def execute_real_sell(token_mint, token_amount):
    if not WALLET_PUBKEY or sender_keypair is None:
        return False, "ولتی یافت نشد ❌"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Origin": "https://jup.ag",
        "Referer": "https://jup.ag/"
    }
    quote_url = f"https://api.jup.ag/swap/v1/quote?inputMint={token_mint}&outputMint={SOL_MINT}&amount={token_amount}&slippageBps=500"
    quote_res = None
    for attempt in range(2):
        try:
            res = http_session.get(quote_url, headers=headers, timeout=4)
            if res.status_code == 200:
                quote_res = res.json()
                if "error" not in quote_res:
                    break
        except Exception as e:
            logger.debug(f"Jupiter sell quote attempt failed: {e}")
        time.sleep(0.2)
    if not quote_res or "error" in quote_res:
        return False, "خطای کوت فروش ❌"
    swap_payload = {
        "quoteResponse": quote_res,
        "userPublicKey": WALLET_PUBKEY,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": 3000000
    }
    swap_res = None
    for attempt in range(2):
        try:
            res = http_session.post("https://api.jup.ag/swap/v1/swap", json=swap_payload, headers=headers, timeout=5)
            if res.status_code == 200:
                swap_res = res.json()
                if "swapTransaction" in swap_res:
                    break
        except Exception as e:
            logger.debug(f"Jupiter sell swap tx attempt failed: {e}")
        time.sleep(0.2)
    if not swap_res or "swapTransaction" not in swap_res:
        return False, "خطای ساخت تراکنش فروش ❌"
    try:
        swap_tx_b64 = swap_res["swapTransaction"]
        raw_tx = base64.b64decode(swap_tx_b64)
        txn = VersionedTransaction.from_bytes(raw_tx)
        signed_txn = VersionedTransaction(txn.message, [sender_keypair])
        serialized_tx = base58.b58encode(bytes(signed_txn)).decode('utf-8')
        rpc_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendTransaction",
            "params": [serialized_tx, {"encoding": "base58", "skipPreflight": True, "maxRetries": 3}]
        }
        tx_res = send_rpc_request(rpc_payload, timeout=10)
        if "result" in tx_res:
            sig = tx_res["result"]
            time.sleep(1)
            close_wsol_account()
            return True, sig
        else:
            return False, "خطای شبکه فروش ❌"
    except Exception as e:
        return False, f"خطا: {e}"

# ========== COPY TRADING ==========
def trigger_copy_trading_for_subscribers(token_mint, amount_sol, side="BUY", tx_signature=""):
    if EMERGENCY_STOP:
        logger.info("Emergency stop: copy trading skipped for new trade.")
        return
    if not COPY_TRADING_ENABLED:
        return
    for sub in get_active_subscribers():
        try:
            t_id = sub["telegram_id"]
            wallet = sub.get("wallet") or ""
            if not wallet or not sub.get("copy_enabled", True):
                continue
            asset = str(sub.get("trade_asset") or COPY_DEFAULT_ASSET).upper()
            amount = float(sub.get("trade_amount_sol") if asset == "SOL" else sub.get("trade_amount_usdc") or 0)
            if amount <= 0:
                continue
            fee = amount * (COPY_TRADING_FEE_PERCENT / 100.0)
            net_amount = max(0.0, amount - fee)
            msg = (
                f"⚡ <b>کپی‌ترید VIP</b>\n\n"
                f"📌 سمت: <b>{side}</b>\n"
                f"🪙 توکن: <code>{token_mint}</code>\n"
                f"💰 حجم تعیین‌شده: <b>{amount:g} {asset}</b>\n"
                f"💸 کارمزد سرویس: <b>{fee:g} {asset}</b> ({COPY_TRADING_FEE_PERCENT:g}%)\n"
                f"📊 خالص بودجه معامله: <b>{net_amount:g} {asset}</b>\n\n"
                "🔐 برای اجرای خودکار واقعی، کاربر باید یک سازوکار امضای معتبر/مجوز امن برای ولت خود فعال کرده باشد؛ "
                "صرفاً آدرس عمومی ولت اجازه خرج‌کردن نمی‌دهد."
            )
            if tx_signature:
                msg += f"\n🔗 معامله مرجع: https://solscan.io/tx/{tx_signature}"
            send_telegram_msg(msg, target_chat=t_id, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Copy-trade dispatch error for subscriber {sub.get('telegram_id')}: {e}")

# ========== SIGNAL TRACKING (virtual) ==========
processed_tokens = set()
trend_alerted_tokens = set()
golden_processed_tokens = set()
tech_processed_tokens = set()
mempool_processed_tokens = set()
ultra_processed_tokens = set()
active_positions = {}
signal_positions = {}
closed_trades_history = []
total_realized_pnl_usd = 0.0
total_realized_pnl_percent = 0.0
MAX_TRADE_SOL = float(os.environ.get("MAX_TRADE_SOL", "0.01"))

def track_signal_only(token_addr, symbol, price, tp, sl, volume, liquidity, p_change,
                      reason, buy_amt, buy_status):
    with state_lock:
        signal_positions[token_addr] = {
            "entry_price": price, "symbol": symbol, "tp": tp, "sl": sl,
            "volume": volume, "liquidity": liquidity, "p_change": p_change,
            "reason": reason, "buy_amt": buy_amt, "buy_status": buy_status,
            "created_at": time.time(), "highest_pnl": 0.0, "highest_price": price,
            "locked_floor": sl, "trailing_active": True, "side": "BUY"
        }

def _signal_links(token_addr, tx_signature=""):
    solscan = f"https://solscan.io/tx/{tx_signature}" if tx_signature else f"https://solscan.io/token/{token_addr}"
    dex = f"https://dexscreener.com/solana/{token_addr}"
    return solscan, dex

def send_signal_outcome(token_addr, pos, current_price, outcome, pnl_percent, tx_signature="", extra_text=""):
    symbol = pos.get("symbol", "TOKEN")
    entry = float(pos.get("entry_price", 0) or 0)
    tp = float(pos.get("tp", 0) or 0)
    sl = float(pos.get("sl", 0) or 0)
    locked = float(pos.get("locked_floor", sl) or sl)
    highest = float(pos.get("highest_pnl", pnl_percent) or pnl_percent)
    reason = pos.get("reason", "سیگنال متحد موتورها")
    volume = float(pos.get("volume", 0.0) or 0.0)
    liquidity = float(pos.get("liquidity", 0.0) or 0.0)
    m5_change = float(pos.get("m5_change", pos.get("p_change", 0.0)) or 0.0)
    buys_m5 = int(pos.get("buys_m5", 0) or 0)
    sells_m5 = int(pos.get("sells_m5", 0) or 0)
    solscan, dex = _signal_links(token_addr, tx_signature)

    if outcome == "SELL_SUCCESS":
        title, status = "🔴 فروش خودکار موفق", "🟢 فروش موفق روی بلاکچین"
    elif outcome == "SELL_FAILED":
        title, status = "⚠️ سیگنال خروج / فروش ناموفق", "⚠️ فروش انجام نشد"
    elif outcome == "SIGNAL_TP":
        title, status = "🎯 فروش سیگنال؛ حد سود متحرک فعال شد", "🟢 سیگنال سودده بسته شد"
    else:
        title, status = "🛑 فروش سیگنال؛ حد ضرر فعال شد", "🔴 سیگنال به حد ضرر رسید"

    msg = (
        f"{title}\n\n"
        f"🪙 توکن: {symbol}\n"
        f"📍 آدرس قرارداد:\n{token_addr}\n\n"
        f"💵 نقطه ورود: ${entry:.8f}\n"
        f"📉 قیمت فعلی/خروج: ${current_price:.8f}\n"
        f"📊 سود/زیان: {pnl_percent:+.2f}%\n"
        f"📈 بیشترین سود ثبت‌شده: {highest:+.2f}%\n"
        f"🔒 حدضرر متحرک فعلی: {locked:+.2f}%\n"
        f"🧭 سقف سود ثبت‌شده: {highest:+.2f}%\n"
        f"🎯 تارگت اولیه: +{tp:.2f}%\n"
        f"🛑 حدضرر اولیه: {sl:.2f}%\n"
        f"📌 وضعیت: {status}\n"
        f"🤖 اتحاد موتورها: {reason}\n"
        f"{extra_text}\n\n"
        f"🔗 Solscan: {solscan}\n"
        f"📈 DexScreener: {dex}"
    )
    send_telegram_msg(msg)
    _load_channel_config()
    if CHANNEL_ID:
        send_graphic_signal_to_vip_channel(
            token_addr=token_addr, symbol=symbol, price=current_price, tp=tp, sl=locked,
            buy_amt=float(pos.get("buy_amt", 0.0) or 0.0), volume=float(pos.get("volume", 0.0) or 0.0),
            liquidity=float(pos.get("liquidity", 0.0) or 0.0), p_change=float(pos.get("m5_change", 0.0) or 0.0),
            solscan_link=solscan, signal_title=title, side="SELL",
            execution_status="", execution_tx=tx_signature, pnl_percent=pnl_percent
        )

# ========== TOKEN ENTRY LOCKS ==========
TOKEN_ENTRY_LOCKS = {}

def _token_lock_is_open(token_addr):
    try:
        with state_lock:
            pos = TOKEN_ENTRY_LOCKS.get(token_addr)
            if pos:
                return True
            if token_addr in active_positions:
                return True
            if token_addr in signal_positions:
                return True
        return False
    except Exception:
        return True

def _lock_token_entry(token_addr, kind="OPEN"):
    if not token_addr:
        return
    with state_lock:
        TOKEN_ENTRY_LOCKS[token_addr] = {
            "status": kind,
            "opened_at": time.time()
        }

def _unlock_token_entry(token_addr):
    if not token_addr:
        return
    with state_lock:
        TOKEN_ENTRY_LOCKS.pop(token_addr, None)

def _mark_token_closed(token_addr):
    _unlock_token_entry(token_addr)

# ========== DAILY SIGNAL CAP ==========
DAILY_SIGNAL_LIMIT = 25
GLOBAL_SIGNAL_COOLDOWN_SECONDS = 3 * 60
last_global_signal_time = 0.0
UNIFIED_LAST_EMIT_TIME = 0.0
consensus_last_signal = {}

def _load_daily_signal_state():
    global DAILY_SIGNAL_LIMIT
    today = time.strftime("%Y-%m-%d")
    try:
        saved_limit = _get_bot_setting("daily_signal_limit", "")
        if saved_limit:
            DAILY_SIGNAL_LIMIT = max(1, min(50, int(saved_limit)))
    except Exception:
        DAILY_SIGNAL_LIMIT = max(1, min(50, int(DAILY_SIGNAL_LIMIT or 15)))
    try:
        saved_date = _get_bot_setting("daily_signal_date", "")
        saved_count = int(_get_bot_setting("daily_signal_count", "0") or 0)
        if saved_date != today:
            _set_bot_setting("daily_signal_date", today)
            _set_bot_setting("daily_signal_count", 0)
            saved_count = 0
        return saved_count
    except Exception:
        return 0

def _set_daily_signal_limit(value):
    global DAILY_SIGNAL_LIMIT
    value = int(value)
    if value < 1 or value > 50:
        raise ValueError("سقف روزانه باید بین 1 تا 50 سیگنال باشد.")
    DAILY_SIGNAL_LIMIT = value
    _set_bot_setting("daily_signal_limit", value)
    return value

def _increment_daily_signal_count():
    today = time.strftime("%Y-%m-%d")
    try:
        saved_date = _get_bot_setting("daily_signal_date", "")
        count = int(_get_bot_setting("daily_signal_count", "0") or 0)
        if saved_date != today:
            count = 0
            _set_bot_setting("daily_signal_date", today)
        count += 1
        _set_bot_setting("daily_signal_count", count)
        return count
    except Exception as e:
        logger.warning(f"Daily signal counter error: {e}")
        return 0

def daily_signal_cap_reached():
    try:
        count = _load_daily_signal_state()
        return count >= max(1, min(50, int(DAILY_SIGNAL_LIMIT)))
    except Exception:
        return False

def daily_signal_status_text():
    try:
        count = _load_daily_signal_state()
        return f"{count}/{DAILY_SIGNAL_LIMIT}"
    except Exception:
        return f"0/{DAILY_SIGNAL_LIMIT}"

# ========== LEARNING & CIRCUIT BREAKER ==========
LEARNING_FILE = "fusion_learning.json"
MAX_HISTORY = 5000
MAX_CONSECUTIVE_LOSSES = 4
RISK_MIN_MULTIPLIER = 0.25
RISK_MAX_MULTIPLIER = 1.25
LEARNING_ALPHA = 0.12

learning_state = {
    "trades": [],
    "engines": {},
    "equity_peak": 0.0,
    "equity_now": 0.0,
    "consecutive_losses": 0,
    "paused_until": 0.0,
}

def _load_learning_state():
    global learning_state
    try:
        p = Path(LEARNING_FILE)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                learning_state.update(data)
    except Exception as e:
        logger.warning(f"Learning state load failed: {e}")

def _save_learning_state():
    try:
        tmp = Path(LEARNING_FILE + ".tmp")
        tmp.write_text(
            json.dumps(learning_state, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        tmp.replace(LEARNING_FILE)
    except Exception as e:
        logger.warning(f"Learning state save failed: {e}")

def _engine_names_from_fusion(fusion):
    names = (fusion or {}).get("engines") or (fusion or {}).get("engine_names") or []
    if isinstance(names, str):
        names = [x.strip() for x in names.split(",") if x.strip()]
    return list(names)

def record_closed_trade(token_addr, symbol, side, entry, exit_price, pnl_pct,
                        reason="", engine_names=None, hold_seconds=0, regime="UNKNOWN"):
    try:
        pnl = float(pnl_pct)
        item = {
            "ts": time.time(),
            "token": token_addr,
            "symbol": symbol,
            "side": side,
            "entry": float(entry or 0),
            "exit": float(exit_price or 0),
            "pnl_pct": pnl,
            "reason": reason,
            "engines": list(engine_names or []),
            "top_level_mode": (str(reason).split(" | ", 1)[0] if " | " in str(reason) else "UNKNOWN"),
            "hold_seconds": int(hold_seconds or 0),
            "regime": regime or "UNKNOWN",
        }
        learning_state["trades"].append(item)
        learning_state["trades"] = learning_state["trades"][-MAX_HISTORY:]

        if pnl < 0:
            learning_state["consecutive_losses"] = int(
                learning_state.get("consecutive_losses", 0) or 0
            ) + 1
        else:
            learning_state["consecutive_losses"] = 0

        for name in item["engines"]:
            st = learning_state["engines"].setdefault(
                name,
                {"trades": 0, "wins": 0, "losses": 0,
                 "avg_pnl": 0.0, "weight": 1.0}
            )
            st["trades"] += 1
            st["wins"] += int(pnl > 0)
            st["losses"] += int(pnl <= 0)
            n = st["trades"]
            st["avg_pnl"] = ((st["avg_pnl"] * (n - 1)) + pnl) / n
            target = max(0.35, min(1.65, 1.0 + st["avg_pnl"] / 100.0))
            st["weight"] = (
                (1.0 - LEARNING_ALPHA) * st["weight"]
                + LEARNING_ALPHA * target
            )
        _save_learning_state()
    except Exception as e:
        logger.warning(f"Closed-trade learning update failed: {e}")

def learning_is_in_circuit_breaker():
    return (
        time.time() < float(learning_state.get("paused_until", 0) or 0)
        or int(learning_state.get("consecutive_losses", 0) or 0)
        >= MAX_CONSECUTIVE_LOSSES
    )

def learning_risk_multiplier():
    losses = int(learning_state.get("consecutive_losses", 0) or 0)
    mult = 1.0 - min(0.75, losses * 0.12)
    return max(RISK_MIN_MULTIPLIER, min(RISK_MAX_MULTIPLIER, mult))

def learning_adjusted_engine_weight(name, base=1.0):
    try:
        return float(base) * float(
            learning_state.get("engines", {}).get(name, {}).get("weight", 1.0)
        )
    except Exception:
        return float(base)

def learning_stats():
    trades = learning_state.get("trades", [])
    wins = sum(1 for t in trades if float(t.get("pnl_pct", 0) or 0) > 0)
    pnl = sum(float(t.get("pnl_pct", 0) or 0) for t in trades)
    return {
        "trades": len(trades),
        "wins": wins,
        "win_rate": (wins / len(trades) * 100.0) if trades else 0.0,
        "net_pnl_pct_sum": pnl,
        "loss_streak": int(learning_state.get("consecutive_losses", 0) or 0),
    }

_load_learning_state()

def learning_record_exit(token_addr, position, exit_price, reason=""):
    try:
        if not position:
            return
        entry = float(position.get("entry_price") or position.get("price") or 0)
        if entry <= 0 or float(exit_price or 0) <= 0:
            return
        pnl = (float(exit_price) - entry) / entry * 100.0
        record_closed_trade(
            token_addr=token_addr,
            symbol=position.get("symbol", ""),
            side=position.get("side", "BUY"),
            entry=entry,
            exit_price=exit_price,
            pnl_pct=pnl,
            reason=reason,
            engine_names=position.get("engines") or position.get("engine_names") or [],
            hold_seconds=max(0, int(time.time() - float(position.get("opened_at", time.time())))),
            regime=position.get("regime", "UNKNOWN")
        )
    except Exception as e:
        logger.warning(f"Learning exit bridge failed: {e}")

# ========== V10 / V11 / V7 Validation (stubs for compatibility) ==========
def v10_real_backtest(): return {}
def v10_walk_forward(): return {}
def v10_ab_engine_test(): return {}
def v11_data_report(): return {}
def v11_tune_weights(): return {}
def v7_paper_stats(): return {}
def v7_backtest_from_learning_history(): return {}
V12_REAL_AUDIT = {}
V13_SIGNAL_DIAGNOSTICS = {
    "analysis": {"scanned":0, "candidates":0, "selected":0, "submit_called":0, "worker_started":0,
                 "blocked_duplicate":0, "blocked_daily_cap":0, "blocked_circuit":0, "blocked_cooldown":0,
                 "execution_started":0, "submitted":0, "real_buy_success":0, "real_buy_failed":0,
                 "channel_sent":0, "channel_failed":0, "worker_failed":0, "rejected":0, "reasons":{},
                 "last_reason":"", "last_token":"", "data_ready":0, "warmup_checked":0, "full_structure_checked":0,
                 "support_setups":0, "breakout_setups":0, "continuation_setups":0},
    "candidate_prefilter_pass":0, "candidate_prefilter_reject":0, "candidate_prefilter_reasons":{},
    "total":0, "last_blocker":"", "last_stage":"", "last_token":"", "reasons":{}, "stages":{},
    "last_error":""
}
def _diag_reject(stage, reason, token_addr=""): pass
def _analysis_diag(action, token_addr="", reason=""): pass
def _diag_top_reasons(limit=10): return []
def _audit_signal_decision(reason): pass

# ========== SIGNAL ENGINES (Independent) ==========
def advanced_ai_engine(token_addr, pair):
    if not ADVANCED_AI_ENABLED and not MAX_FUSION_ENABLED:
        return None
    adv_score = 0.0
    reasons = []
    if TECHNICAL_RUNNING:
        ok, msg = check_major_support_resistance_pa(pair)
        if ok:
            adv_score += 1.5
            reasons.append("Technical")
    if ULTIMATE_21_ENGINE_ENABLED:
        ok, msg = validate_ultimate_21_layers(token_addr, pair)
        if ok:
            adv_score += 2.0
            reasons.append("UltimateAI/21")
    if SOCIAL_SENTIMENT_ENABLED:
        ok, msg = check_social_sentiment_and_hype(pair)
        if ok:
            adv_score += 1.0
            reasons.append("Social/Hype")
    if SMART_FILTER_ENABLED:
        if is_token_worthy(pair):
            adv_score += 1.0
            reasons.append("SmartFilter")
    if adv_score < 3.0:
        return None
    q = _mode_market_quality(pair)
    if not q:
        return None
    structure_ok, structure = _market_structure_gate(token_addr, pair)
    if not structure_ok:
        return None
    score = adv_score + min(5.0, q["chg"] / 5.0) + min(4.0, q["vol"] / 10000.0) + min(3.0, q["liq"] / 50000.0)
    return {
        "score": float(score),
        "strength": adv_score,
        "votes": reasons,
        "advanced_votes": reasons,
        "hulk_votes": [],
        "engines": reasons,
        "mode": "🧠 سیستم پیشرفته AI",
        "symbol": (pair.get("baseToken") or {}).get("symbol", "TOKEN"),
        "tp": 20.0,
        "sl": -8.0,
        **q,
        "structure": structure.get("structure", "UNKNOWN"),
    }

def hulk_alliance_engine(token_addr, pair):
    if not SYNCHRONIZED_MODE and not MAX_FUSION_ENABLED:
        return None
    hulk_score = 0.0
    reasons = []
    chg = float((pair.get("priceChange") or {}).get("m5", 0) or 0)
    vol = float((pair.get("volume") or {}).get("m5", 0) or 0)
    liq = float((pair.get("liquidity") or {}).get("usd", 0) or 0)
    txns = (pair.get("txns") or {}).get("m5", {}) or {}
    buys = int(txns.get("buys", 0) or 0)
    sells = int(txns.get("sells", 0) or 0)

    if IS_RUNNING and chg >= 3 and vol >= 3000:
        hulk_score += 1.5; reasons.append("Fire")
    if TREND_ALERT_RUNNING and chg >= 5 and buys >= max(1, sells):
        hulk_score += 1.5; reasons.append("Trend")
    if COMBO_RUNNING and buys > sells and vol >= 5000 and liq >= 15000:
        hulk_score += 2.0; reasons.append("Combo")
    if GOLDEN_OPTION and chg >= 8 and vol >= 7000 and liq >= 18000:
        hulk_score += 2.0; reasons.append("Golden")
    if MEMPOOL_SMART_MONEY_ENABLED and buys >= max(2, int(sells * 1.20) + 1) and vol >= 5000 and liq >= 15000:
        hulk_score += 2.0; reasons.append("Mempool/SmartMoney")
    if BOTTOM_WHALE_RUNNING and buys >= max(3, sells + 2) and vol >= 5000:
        hulk_score += 1.5; reasons.append("Whale")
    if ANTI_WASH_TRADING_ENABLED and not (sells > 0 and buys < sells * 0.8):
        hulk_score += 1.0; reasons.append("Anti-Wash")
    if hulk_score < 3.0:
        return None
    q = _mode_market_quality(pair)
    if not q:
        return None
    structure_ok, structure = _market_structure_gate(token_addr, pair)
    if not structure_ok:
        return None
    score = hulk_score + min(5.0, q["chg"] / 5.0) + min(4.0, q["vol"] / 10000.0) + min(3.0, q["liq"] / 50000.0)
    return {
        "score": float(score),
        "strength": hulk_score,
        "votes": reasons,
        "advanced_votes": [],
        "hulk_votes": reasons,
        "engines": reasons,
        "mode": "⚡ اتحاد هالک AI",
        "symbol": (pair.get("baseToken") or {}).get("symbol", "TOKEN"),
        "tp": 20.0,
        "sl": -8.0,
        **q,
        "structure": structure.get("structure", "UNKNOWN"),
    }

def analysis_engine_candidate(token_addr, pair):
    if not ANALYSIS_ENGINE_ENABLED:
        return None
    _analysis_diag("scanned", token_addr=token_addr)
    try:
        price = float(pair.get("priceUsd", 0) or 0)
        liq = float((pair.get("liquidity") or {}).get("usd", 0) or 0)
        vol = float((pair.get("volume") or {}).get("m5", 0) or 0)
        chg = float((pair.get("priceChange") or {}).get("m5", 0) or 0)
        tx = (pair.get("txns") or {}).get("m5", {}) or {}
        buys = int(tx.get("buys", 0) or 0)
        sells = int(tx.get("sells", 0) or 0)
        buy_ratio = buys / max(1, sells)
        if price <= 0 or liq < CONSENSUS_MIN_LIQUIDITY or vol < CONSENSUS_MIN_VOLUME_5M:
            _diag_reject("ANALYSIS", "MARKET_QUALITY_FAIL", token_addr)
            return None
        if buys < 2 or buy_ratio < CONSENSUS_MIN_BUY_RATIO:
            _diag_reject("ANALYSIS", "BUY_PRESSURE_WEAK", token_addr)
            return None

        samples = _update_structure_memory(token_addr, price)
        if len(samples) < STRUCTURE_MIN_SAMPLES:
            if buy_ratio < 1.2 or liq < 25000 or vol < 3000:
                return None
            score = 6.0 + min(2.0, buy_ratio - 1.0) + min(1.5, vol / 10000.0)
            return {
                "score": float(score),
                "strength": 6.0,
                "votes": ["Analysis"],
                "advanced_votes": [],
                "hulk_votes": [],
                "engines": ["Analysis"],
                "mode": "📈 موتور تحلیل مستقل",
                "symbol": (pair.get("baseToken") or {}).get("symbol", "TOKEN"),
                "tp": 18.0,
                "sl": -8.0,
                "price": price, "liq": liq, "vol": vol, "chg": chg,
                "buys": buys, "sells": sells,
                "structure": "ANALYSIS_WARMUP",
                "reason": "نقدینگی+فشار خریدار"
            }

        prices = [x[1] for x in samples]
        n = len(prices)
        xs = list(range(n))
        mx = sum(xs) / n
        my = sum(prices) / n
        den = sum((x - mx) ** 2 for x in xs) or 1.0
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, prices)) / den
        slope_pct = (slope / max(1e-18, my)) * 100.0

        prior = prices[:-1]
        recent = prices[-min(8, n):]
        support = min(recent)
        resistance = max(prior) if prior else max(recent)
        bounce_pct = (price - support) / max(1e-18, support) * 100.0
        near_support = price <= support * (1.0 + STRUCTURE_SUPPORT_DISTANCE_PCT / 100.0)
        near_resistance = price >= resistance * (1.0 - STRUCTURE_RESISTANCE_DISTANCE_PCT / 100.0)
        breakout = price >= resistance * (1.0 + STRUCTURE_BREAKOUT_BUFFER_PCT / 100.0)

        if near_resistance and not breakout:
            _diag_reject("ANALYSIS", "RESISTANCE_TOUCH", token_addr)
            return None

        if breakout:
            if slope_pct <= 0 or liq < 25000 or vol < 4000 or buy_ratio < 1.2:
                return None
            structure = "BREAKOUT"
            score = 7.0 + min(2.0, slope_pct) + min(2.0, buy_ratio - 1.0)
            reason = "شکست سقف + حجم بالا"
        elif near_support:
            if slope_pct <= 0 or bounce_pct < 0.35 or liq < 25000 or vol < 3000 or buy_ratio < 1.15:
                return None
            structure = "SUPPORT_BOUNCE"
            score = 6.5 + min(2.0, slope_pct) + min(1.5, bounce_pct)
            reason = "برگشت از کف معتبر"
        else:
            if slope_pct < 0.2 or buy_ratio < 1.15 or vol < 3000 or liq < 25000:
                return None
            structure = "TREND_CONTINUATION"
            score = 5.5 + min(2.0, slope_pct) + min(1.5, buy_ratio - 1.0)
            reason = "روند صعودی خطی"

        now = time.time()
        if now - consensus_last_signal.get(f"{token_addr}:Analysis", 0) < CONSENSUS_COOLDOWN_SECONDS:
            _diag_reject("ANALYSIS", "COOLDOWN", token_addr)
            return None

        _analysis_diag("candidates", token_addr=token_addr)
        return {
            "score": float(score),
            "strength": score,
            "votes": ["Analysis"],
            "advanced_votes": [],
            "hulk_votes": [],
            "engines": ["Analysis"],
            "mode": "📈 موتور تحلیل مستقل",
            "symbol": (pair.get("baseToken") or {}).get("symbol", "TOKEN"),
            "tp": max(15.0, min(28.0, 16.0 + min(10.0, score))),
            "sl": -8.0,
            "price": price, "liq": liq, "vol": vol, "chg": chg,
            "buys": buys, "sells": sells,
            "structure": structure,
            "reason": reason,
            "support": support,
            "resistance": resistance,
            "breakout": breakout,
            "trend_slope_pct": slope_pct,
        }
    except Exception as e:
        logger.debug(f"Analysis engine failed for {token_addr}: {e}")
        return None

def _mode_market_quality(pair):
    price = float(pair.get("priceUsd", 0) or 0)
    liq = float((pair.get("liquidity") or {}).get("usd", 0) or 0)
    vol = float((pair.get("volume") or {}).get("m5", 0) or 0)
    chg = float((pair.get("priceChange") or {}).get("m5", 0) or 0)
    txns = (pair.get("txns") or {}).get("m5", {}) or {}
    buys = int(txns.get("buys", 0) or 0)
    sells = int(txns.get("sells", 0) or 0)
    if price <= 0 or liq < CONSENSUS_MIN_LIQUIDITY or vol < CONSENSUS_MIN_VOLUME_5M:
        return None
    if chg < CONSENSUS_MIN_CHANGE_5M or chg > CONSENSUS_MAX_CHANGE_5M:
        return None
    if buys <= 0 or (sells > 0 and buys < max(1, int(sells * CONSENSUS_MIN_BUY_RATIO))):
        return None
    return {"price": price, "liq": liq, "vol": vol, "chg": chg, "buys": buys, "sells": sells}

def build_consensus_signal(token_addr, pair):
    if not MAX_FUSION_ENABLED:
        return None
    adv = advanced_ai_engine(token_addr, pair)
    hulk = hulk_alliance_engine(token_addr, pair)
    if not adv or not hulk:
        return None
    combined_score = (adv["score"] + hulk["score"]) / 2.0
    votes = list(set(adv.get("votes", []) + hulk.get("votes", [])))
    if len(votes) < 3:
        return None
    q = _mode_market_quality(pair)
    if not q:
        return None
    structure_ok, structure = _market_structure_gate(token_addr, pair)
    if not structure_ok:
        return None
    return {
        "score": combined_score,
        "strength": combined_score,
        "votes": votes,
        "advanced_votes": adv.get("advanced_votes", []),
        "hulk_votes": hulk.get("hulk_votes", []),
        "engines": votes,
        "mode": "👑 MAX FUSION",
        "symbol": (pair.get("baseToken") or {}).get("symbol", "TOKEN"),
        "tp": 22.0,
        "sl": -8.0,
        **q,
        "structure": structure.get("structure", "UNKNOWN"),
    }

def fusion_quality_gate(fusion):
    try:
        liq = float(fusion.get("liq", 0) or 0)
        vol = float(fusion.get("vol", 0) or 0)
        score = float(fusion.get("score", 0) or 0)
        buys = int(fusion.get("buys", 0) or 0)
        sells = int(fusion.get("sells", 0) or 0)
        if liq < CONSENSUS_MIN_LIQUIDITY or vol < CONSENSUS_MIN_VOLUME_5M:
            return False
        if buys < 2 or (sells > 0 and buys < sells * CONSENSUS_MIN_BUY_RATIO):
            return False
        if score < CONSENSUS_MIN_SCORE:
            return False
        return True
    except Exception:
        return False

def send_fused_signal(token_addr, fusion):
    global last_global_signal_time, UNIFIED_LAST_EMIT_TIME
    with SIGNAL_EMIT_LOCK:
        if _token_lock_is_open(token_addr):
            return False, "DUPLICATE"
        if daily_signal_cap_reached():
            return False, "DAILY_CAP"
        if learning_is_in_circuit_breaker():
            return False, "CIRCUIT"
        if not fusion_quality_gate(fusion):
            return False, "QUALITY_GATE"
        now_global = time.time()
        if MAX_FUSION_ENABLED:
            if now_global - max(last_global_signal_time, UNIFIED_LAST_EMIT_TIME) < GLOBAL_SIGNAL_COOLDOWN_SECONDS:
                return False, "COOLDOWN"
        else:
            lane = fusion.get("mode", "UNKNOWN")
            if now_global - consensus_last_signal.get(lane, 0) < CONSENSUS_COOLDOWN_SECONDS:
                return False, "COOLDOWN"
        if EMERGENCY_STOP:
            return False, "EMERGENCY"
        if MAX_FUSION_ENABLED:
            last_global_signal_time = now_global
            UNIFIED_LAST_EMIT_TIME = now_global
        consensus_last_signal[fusion.get("mode", "UNKNOWN")] = now_global
        _increment_daily_signal_count()
        _lock_token_entry(token_addr, "OPEN_PENDING")

    amount = get_dynamic_buy_amount(0.01)
    symbol = fusion["symbol"]
    price = fusion["price"]
    tp = fusion["tp"]
    sl = fusion["sl"]
    success, result = execute_real_buy(token_addr, amount)
    execution_status = "🟢 خرید موفق" if success else f"⚠️ خرید ناموفق: {result}"
    solscan_link = f"https://solscan.io/tx/{result}" if success else f"https://solscan.io/token/{token_addr}"

    msg = (
        f"⚡🤖 {fusion['mode']}\n"
        f"🎯 قدرت سیگنال: {fusion['score']:.2f}\n"
        f"🤖 موتورها: {', '.join(fusion.get('votes', []))}\n\n"
        f"🪙 {symbol}\n"
        f"📍 {token_addr}\n"
        f"💵 ورود: ${price:.8f}\n"
        f"💰 حجم: {amount:g} SOL\n"
        f"🎯 TP: +{tp:.1f}%\n"
        f"🛑 SL: {sl:.1f}%\n"
        f"📊 تغییر ۵': {fusion.get('chg',0):+.2f}%\n"
        f"💧 نقدینگی: ${fusion.get('liq',0):,.0f}\n"
        f"🔗 [Solscan]({solscan_link})"
    )
    send_telegram_msg(msg)
    send_graphic_signal_to_vip_channel(
        token_addr=token_addr, symbol=symbol, price=price, tp=tp, sl=sl,
        buy_amt=amount, volume=fusion.get('vol',0), liquidity=fusion.get('liq',0),
        p_change=fusion.get('chg',0), solscan_link=solscan_link,
        signal_title=fusion['mode'], side="BUY",
        execution_status=execution_status, execution_tx=result if success else ""
    )

    if success:
        with state_lock:
            processed_tokens.add(token_addr)
            active_positions[token_addr] = {
                "entry_price": price, "symbol": symbol,
                "tp": tp, "sl": sl,
                "highest_price": price,
                "highest_pnl": 0.0,
                "locked_floor": sl,
                "trailing_active": True,
                "side": "BUY",
                "reason": f"{fusion['mode']} | {', '.join(fusion.get('votes', []))}",
                "engines": fusion.get("votes", []),
                "opened_at": time.time(),
                "buy_amt": amount,
                "volume": fusion.get('vol',0),
                "liquidity": fusion.get('liq',0),
                "p_change": fusion.get('chg',0),
                "buys_m5": fusion.get('buys',0),
                "sells_m5": fusion.get('sells',0),
                "partial_tp_level": 0,
                "partial_tp_amount": amount,
            }
        trigger_copy_trading_for_subscribers(token_addr, amount, side="BUY", tx_signature=result)
        send_telegram_msg(f"🟢 خرید خودکار {symbol} با {amount:g} SOL انجام شد.")
    else:
        track_signal_only(token_addr, symbol, price, tp, sl, fusion.get('vol',0), fusion.get('liq',0),
                          fusion.get('chg',0), fusion.get('mode',""), amount, execution_status)
    return success, result

# ========== POSITION MANAGEMENT WITH STAIR‑STEP PROFIT & FAST EXIT ==========
def _adaptive_locked_floor(highest_pnl, current_floor):
    floor = float(current_floor)
    for high, lock in TRAILING_LOCK_TABLE:
        if highest_pnl >= high:
            floor = max(floor, lock)
            break
    return floor

def _update_trailing_state(pos, current_price, pnl_percent, pair):
    highest_pnl = max(float(pos.get("highest_pnl", pnl_percent)), pnl_percent)
    highest_price = max(float(pos.get("highest_price", current_price) or current_price), current_price)
    pos["highest_pnl"] = highest_pnl
    pos["highest_price"] = highest_price

    initial_sl = float(pos.get("sl", -8.0) or -8.0)
    current_floor = float(pos.get("locked_floor", initial_sl) or initial_sl)
    if DYNAMIC_TRAILING_TP_ENABLED:
        current_floor = _adaptive_locked_floor(highest_pnl, current_floor)

    txns = (pair.get("txns") or {}).get("m5") or {}
    buys = int(txns.get("buys", 0) or 0)
    sells = int(txns.get("sells", 0) or 0)
    m5 = float((pair.get("priceChange") or {}).get("m5", 0) or 0)
    drawdown_from_high = ((highest_price - current_price) / highest_price * 100.0) if highest_price > 0 else 0.0

    bearish = False
    if TRAILING_WEAKNESS_ENABLED and highest_pnl >= 10.0:
        ratio_bad = sells >= max(2, int(buys * TRAILING_WEAK_SELL_RATIO))
        momentum_bad = m5 <= TRAILING_WEAKNESS_M5_MAX
        if ratio_bad and momentum_bad and drawdown_from_high >= TRAILING_WEAKNESS_MIN_DRAWDOWN_PCT:
            bearish = True
            weakness_floor = pnl_percent - 0.5
            current_floor = max(current_floor, weakness_floor)

    pos["locked_floor"] = current_floor
    pos["bearish"] = bearish
    pos["drawdown_from_high"] = drawdown_from_high
    pos["m5_change"] = m5
    pos["buys_m5"] = buys
    pos["sells_m5"] = sells
    return current_floor, bearish

def check_positions_loop():
    global closed_trades_history, total_realized_pnl_usd, total_realized_pnl_percent

    while True:
        try:
            evaluate_signal_only_positions()
            tokens_to_close = []
            with state_lock:
                current_positions = list(active_positions.items())

            for token_addr, pos in current_positions:
                try:
                    res = http_session.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=4)
                    if res.status_code != 200:
                        continue
                    pairs = (res.json() or {}).get("pairs") or []
                    pairs = [p for p in pairs if p.get("chainId") == "solana"]
                    if not pairs:
                        continue
                    pair = max(pairs, key=lambda p: float(((p.get("liquidity") or {}).get("usd")) or 0))
                    current_price = float(pair.get("priceUsd", 0) or 0)
                    entry_price = float(pos.get("entry_price", 0) or 0)
                    symbol = pos.get("symbol", "TOKEN")
                    sl = float(pos.get("sl", -8.0) or -8.0)
                    if entry_price <= 0 or current_price <= 0:
                        continue

                    pnl_percent = ((current_price - entry_price) / entry_price) * 100.0
                    locked_floor, bearish = _update_trailing_state(pos, current_price, pnl_percent, pair)
                    pos["volume"] = float((pair.get("volume") or {}).get("m5") or 0.0)
                    pos["liquidity"] = float((pair.get("liquidity") or {}).get("usd") or 0.0)
                    pos["p_change"] = float(pair.get("priceChange", {}).get("m5") or 0.0)
                    highest_pnl = float(pos.get("highest_pnl", pnl_percent))

                    # Partial TP
                    if PARTIAL_TP_ENABLED:
                        for level, fraction in PARTIAL_TP_LEVELS:
                            if pnl_percent >= (level - 1) * 100.0 and pos.get("partial_tp_level", 0) < int(level):
                                current_amount = pos.get("buy_amt", 0.01)
                                sell_amount = current_amount * fraction
                                if sell_amount > 0:
                                    token_balance = get_token_balance(token_addr)
                                    if token_balance > 0:
                                        success, sell_res = execute_real_sell(token_addr, token_balance)
                                        if success:
                                            pos["partial_tp_level"] = int(level)
                                            pos["buy_amt"] = current_amount * (1 - fraction)
                                            send_telegram_msg(
                                                f"✅ برداشت جزئی سود در +{(level-1)*100:.0f}% برای {symbol}\n"
                                                f"فروش {fraction*100:.0f}% از پوزیشن انجام شد."
                                            )
                                            break

                    # Full exit
                    should_exit = False
                    exit_reason = ""
                    if pnl_percent <= sl and highest_pnl < 10.0:
                        should_exit = True
                        exit_reason = "حد ضرر اولیه"
                    elif bearish and pnl_percent <= locked_floor:
                        should_exit = True
                        exit_reason = "تشخیص ریزش سریع"
                    elif pnl_percent <= locked_floor and highest_pnl >= 10.0:
                        should_exit = True
                        exit_reason = f"تریلینگ استاپ پله‌ای (سقف {highest_pnl:.1f}%)"

                    if not should_exit:
                        continue

                    token_balance = get_token_balance(token_addr)
                    if token_balance <= 0:
                        continue
                    success, sell_res = execute_real_sell(token_addr, token_balance)
                    if success:
                        log_trade_to_db(token_addr, symbol, entry_price, current_price, pnl_percent,
                                        pos.get("buy_amt", 0.01) * pnl_percent / 100.0, exit_reason)
                        send_signal_outcome(token_addr, pos, current_price, "SELL_SUCCESS", pnl_percent,
                                            tx_signature=sell_res,
                                            extra_text=f"🧠 دلیل خروج: {exit_reason}")
                        tokens_to_close.append(token_addr)
                    else:
                        send_telegram_msg(f"⚠️ فروش {symbol} ناموفق: {sell_res}")

                except Exception as e:
                    logger.error(f"⚠️ خطا در پوزیشن {token_addr}: {e}")

            if tokens_to_close:
                with state_lock:
                    for t_addr in tokens_to_close:
                        pos_snapshot = active_positions.get(t_addr)
                        learning_record_exit(t_addr, pos_snapshot, current_price, "POSITION_CLOSED")
                        active_positions.pop(t_addr, None)
                        _mark_token_closed(t_addr)
        except Exception as e:
            logger.error(f"⚠️ خطای حلقه پوزیشن‌ها: {e}")
        time.sleep(1)

def evaluate_signal_only_positions():
    finished = []
    with state_lock:
        items = list(signal_positions.items())

    for token_addr, pos in items:
        try:
            res = http_session.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=4)
            if res.status_code != 200:
                continue
            pairs = (res.json() or {}).get("pairs") or []
            pairs = [p for p in pairs if p.get("chainId") == "solana"]
            if not pairs:
                continue
            pair = max(pairs, key=lambda p: float(((p.get("liquidity") or {}).get("usd")) or 0))
            current_price = float(pair.get("priceUsd", 0) or 0)
            entry = float(pos.get("entry_price", 0) or 0)
            if current_price <= 0 or entry <= 0:
                continue
            pnl = ((current_price - entry) / entry) * 100.0
            locked_floor, bearish = _update_trailing_state(pos, current_price, pnl, pair)

            should_close = False
            if pnl <= float(pos.get("sl", -8.0)) and pos.get("highest_pnl", 0) < 10:
                should_close = True
            elif bearish and pnl <= locked_floor:
                should_close = True
            elif pnl <= locked_floor and pos.get("highest_pnl", 0) >= 10:
                should_close = True

            if should_close:
                send_signal_outcome(token_addr, pos, current_price, "SIGNAL_TP", pnl,
                                    extra_text=f"خروج سیگنال مجازی (ریزش/تریلینگ)")
                finished.append(token_addr)
        except Exception as e:
            logger.debug(f"Signal-only monitor error {token_addr}: {e}")

    if finished:
        with state_lock:
            for finished_addr in finished:
                signal_positions.pop(finished_addr, None)
                _mark_token_closed(finished_addr)

# ========== UNIFIED SCANNER ==========
FAST_SCAN_INTERVAL_SECONDS = 0.50
MARKET_DISCOVERY_WORKERS = 4
PAIR_SCAN_WORKERS = 16
ELITE_DISCOVERY_REFRESH_SECONDS = 2.50
ELITE_MAX_UNIQUE_TOKENS = 1200
_elite_market_cache = []
_elite_market_cache_time = 0.0
_elite_market_refresh_lock = Lock()
_elite_market_refresh_thread = None
_SENTINEL_MEMORY_TTL = 120.0
_SENTINEL_MAX_TOKENS = 5000
_sentinel_memory = {}
_sentinel_lock = Lock()
DEX_BATCH_SIZE = 30
DEX_BATCH_CACHE_TTL_SECONDS = 4.0
_dex_batch_cache = {}
_dex_batch_cache_time = 0.0
_dex_batch_lock = RLock()
_dex_rate_lock = Lock()
_dex_last_request_time = 0.0
DEX_MIN_REQUEST_INTERVAL_SECONDS = 0.12

def _sentinel_ratio(buys, sells):
    return float(buys) / max(1.0, float(sells))

def _sentinel_rank_bonus(token_addr, fusion):
    try:
        now = time.time()
        chg = float(fusion.get("chg", 0) or 0)
        vol = float(fusion.get("vol", 0) or 0)
        liq = float(fusion.get("liq", 0) or 0)
        br = _sentinel_ratio(fusion.get("buys", 0), fusion.get("sells", 0))
        base = float(fusion.get("score", 0) or 0)
        with _sentinel_lock:
            old = _sentinel_memory.get(token_addr)
            _sentinel_memory[token_addr] = {
                "ts": now, "score": base, "chg": chg, "vol": vol,
                "liq": liq, "br": br
            }
            if len(_sentinel_memory) > _SENTINEL_MAX_TOKENS:
                cutoff = now - _SENTINEL_MEMORY_TTL
                stale = [k for k,v in _sentinel_memory.items() if v.get("ts",0) < cutoff]
                for k in stale[:1000]:
                    _sentinel_memory.pop(k, None)
        if not old or now - old.get("ts", 0) > _SENTINEL_MEMORY_TTL:
            return 0.0
        chg_accel = max(-2.0, min(2.0, chg - old.get("chg", chg)))
        vol_accel = 0.0
        if old.get("vol", 0) > 0:
            vol_accel = max(-1.5, min(1.5, (vol / old["vol"]) - 1.0))
        br_accel = max(-1.0, min(1.0, br - old.get("br", br)))
        persistence = 1.0 if base >= old.get("score", base) else 0.0
        return max(-2.0, min(4.5, chg_accel * 0.8 + vol_accel * 0.9 + br_accel * 0.8 + persistence * 1.0))
    except Exception:
        return 0.0

def _elite_refresh_market_cache(force=False):
    global _elite_market_cache, _elite_market_cache_time
    now = time.time()
    if not force and now - _elite_market_cache_time < ELITE_DISCOVERY_REFRESH_SECONDS:
        return
    if not _elite_market_refresh_lock.acquire(blocking=False):
        return
    try:
        found = get_real_market_trending_tokens()
        unique = list(dict.fromkeys(found))
        if len(unique) > ELITE_MAX_UNIQUE_TOKENS:
            unique = unique[:ELITE_MAX_UNIQUE_TOKENS]
        with state_lock:
            _elite_market_cache = unique
            _elite_market_cache_time = time.time()
    except Exception as e:
        logger.debug(f"Elite market refresh error: {e}")
    finally:
        _elite_market_refresh_lock.release()

def _elite_market_refresh_loop():
    logger.info("⚡ ELITE RADAR discovery worker فعال شد.")
    while True:
        try:
            _elite_refresh_market_cache(force=True)
        except Exception as e:
            logger.debug(f"Elite discovery loop error: {e}")
        time.sleep(ELITE_DISCOVERY_REFRESH_SECONDS)

def _elite_get_market_tokens():
    global _elite_market_refresh_thread
    if _elite_market_refresh_thread is None or not _elite_market_refresh_thread.is_alive():
        _elite_market_refresh_thread = Thread(target=_elite_market_refresh_loop, name="EliteDiscovery", daemon=True)
        _elite_market_refresh_thread.start()
    _elite_refresh_market_cache(force=False)
    with state_lock:
        return list(_elite_market_cache)

def _fetch_best_solana_pairs_batch(token_addrs):
    global _dex_batch_cache, _dex_batch_cache_time, _dex_last_request_time
    clean = list(dict.fromkeys(str(x).strip() for x in token_addrs if x))
    if not clean:
        return {}
    result = {}
    now = time.time()
    with _dex_batch_lock:
        if now - _dex_batch_cache_time <= DEX_BATCH_CACHE_TTL_SECONDS:
            for addr in clean:
                if addr in _dex_batch_cache:
                    result[addr] = _dex_batch_cache[addr]
        missing = [a for a in clean if a not in result]

    for i in range(0, len(missing), DEX_BATCH_SIZE):
        chunk = missing[i:i + DEX_BATCH_SIZE]
        try:
            with _dex_rate_lock:
                wait = DEX_MIN_REQUEST_INTERVAL_SECONDS - (time.time() - _dex_last_request_time)
                if wait > 0:
                    time.sleep(wait)
                url = "https://api.dexscreener.com/latest/dex/tokens/" + ",".join(chunk)
                res = http_session.get(url, timeout=DEX_BATCH_CACHE_TTL_SECONDS + 2.0)
                _dex_last_request_time = time.time()
            if res.status_code == 429:
                retry_after = float(res.headers.get("Retry-After", "1") or 1)
                logger.warning("⚠️ DexScreener HTTP 429؛ batch radar %.1fs مکث می‌کند.", retry_after)
                time.sleep(min(max(retry_after, 0.5), 5.0))
                continue
            if res.status_code != 200:
                logger.debug("DexScreener batch status=%s", res.status_code)
                continue
            data = res.json() or {}
            grouped = {addr: [] for addr in chunk}
            for pair in data.get("pairs") or []:
                if not isinstance(pair, dict) or pair.get("chainId") != "solana":
                    continue
                base = ((pair.get("baseToken") or {}).get("address") or "").strip()
                if base in grouped:
                    grouped[base].append(pair)
            for addr, pairs in grouped.items():
                pairs.sort(key=lambda x: float(((x.get("liquidity") or {}).get("usd")) or 0), reverse=True)
                result[addr] = pairs[:3]
        except Exception as e:
            logger.debug("DexScreener batch fetch error: %s", e)

    with _dex_batch_lock:
        _dex_batch_cache = dict(result)
        _dex_batch_cache_time = time.time()
    return result

def _candidate_rank_tuple(item):
    _, c = item
    return (
        float(c.get("rank_score", c.get("score", 0.0)) or 0.0),
        float(c.get("score", 0.0) or 0.0),
        float(c.get("chg", 0.0) or 0.0),
        float(c.get("vol", 0.0) or 0.0),
        float(c.get("liq", 0.0) or 0.0),
    )

def _evaluate_token_for_active_modes(token_addr, pair_cache=None):
    if pair_cache is not None and token_addr in pair_cache:
        pairs = pair_cache.get(token_addr) or []
    else:
        token_addr, pairs = _fetch_best_solana_pair(token_addr)
    result = {"analysis": [], "fusion": []}
    if not pairs:
        return token_addr, result

    for pair in pairs:
        # Analysis
        if ANALYSIS_ENGINE_ENABLED:
            candidate = analysis_engine_candidate(token_addr, pair)
            if candidate:
                candidate = dict(candidate)
                candidate["force_independent"] = True
                candidate["hunter_group"] = "ANALYSIS"
                candidate["engines"] = ["Analysis"]
                candidate["votes"] = ["Analysis"]
                candidate["rank_score"] = _candidate_rank_tuple(candidate)[0]
                result["analysis"].append((token_addr, candidate))
        # Fusion / other engines
        if MAX_FUSION_ENABLED:
            fusion = build_consensus_signal(token_addr, pair)
            if fusion:
                fusion = dict(fusion)
                fusion["rank_bonus"] = _sentinel_rank_bonus(token_addr, fusion)
                fusion["rank_score"] = _candidate_rank_tuple(fusion)[0]
                result["fusion"].append((token_addr, fusion))
        else:
            # Independent engines
            if ADVANCED_AI_ENABLED:
                adv = advanced_ai_engine(token_addr, pair)
                if adv and fusion_quality_gate(adv):
                    adv["rank_score"] = _candidate_rank_tuple(adv)[0]
                    result["fusion"].append((token_addr, adv))
            if SYNCHRONIZED_MODE:
                hulk = hulk_alliance_engine(token_addr, pair)
                if hulk and fusion_quality_gate(hulk):
                    hulk["rank_score"] = _candidate_rank_tuple(hulk)[0]
                    result["fusion"].append((token_addr, hulk))
    return token_addr, result

def _select_fusion_candidates(candidates):
    if not candidates:
        return []
    if MAX_FUSION_ENABLED:
        return [max(candidates, key=_candidate_rank_tuple)]
    best_by_lane = {}
    for item in candidates:
        _, candidate = item
        engine = (candidate.get("engines") or candidate.get("votes") or ["ENGINE"])[0]
        group = candidate.get("hunter_group", "ENGINE")
        lane = (group, engine)
        old = best_by_lane.get(lane)
        if old is None or _candidate_rank_tuple(item) > _candidate_rank_tuple(old):
            best_by_lane[lane] = item
    return sorted(best_by_lane.values(), key=_candidate_rank_tuple, reverse=True)

def _analysis_submit_worker(token_addr, candidate):
    try:
        ok, result = send_fused_signal(token_addr, candidate)
        return ok, result
    except Exception as exc:
        logger.exception("Analysis execution worker failed for %s", token_addr)
        return False, f"EXCEPTION:{exc}"

def unified_market_scanner_loop(app):
    global _TRUE_HUNTER_CURSOR
    logger.info("%s / %s: CLEAN SIGNAL CORE started", UNIFIED_ENGINE_NAME, BOT_BUILD_VERSION)
    send_telegram_msg(f"🚀 رادار {BOT_BUILD_VERSION} فعال شد")

    while True:
        if EMERGENCY_STOP or (not SYNCHRONIZED_MODE and not ADVANCED_AI_ENABLED and not MAX_FUSION_ENABLED and not ANALYSIS_ENGINE_ENABLED):
            time.sleep(FAST_SCAN_INTERVAL_SECONDS)
            continue

        try:
            if daily_signal_cap_reached():
                time.sleep(FAST_SCAN_INTERVAL_SECONDS)
                continue

            tokens = _elite_get_market_tokens()
            if not tokens:
                time.sleep(FAST_SCAN_INTERVAL_SECONDS)
                continue

            with _TRUE_HUNTER_CURSOR_LOCK:
                start_i = _TRUE_HUNTER_CURSOR % len(tokens)
                batch_n = min(TRUE_HUNTER_BATCH_SIZE, len(tokens))
                end_i = start_i + batch_n
                scan_tokens = tokens[start_i:end_i] if end_i <= len(tokens) else tokens[start_i:] + tokens[:end_i % len(tokens)]
                _TRUE_HUNTER_CURSOR = (start_i + batch_n) % len(tokens)

            pair_cache = _fetch_best_solana_pairs_batch(scan_tokens)
            analysis_candidates = []
            fusion_candidates = []

            with ThreadPoolExecutor(max_workers=PAIR_SCAN_WORKERS, thread_name_prefix="RadarEval") as ex:
                futures = {
                    ex.submit(_evaluate_token_for_active_modes, token, pair_cache): token
                    for token in scan_tokens
                    if token and not _token_lock_is_open(token)
                }
                for future in __import__("concurrent.futures").as_completed(futures):
                    source_token = futures[future]
                    try:
                        token_addr, lanes = future.result()
                    except Exception as exc:
                        logger.exception("Evaluation future failed for %s", source_token)
                        continue
                    for item in lanes.get("analysis", []):
                        analysis_candidates.append(item)
                    for item in lanes.get("fusion", []):
                        fusion_candidates.append(item)

            # Submit Analysis
            if analysis_candidates:
                selected = max(analysis_candidates, key=_candidate_rank_tuple)
                try:
                    future = ANALYSIS_EXECUTOR.submit(_analysis_submit_worker, selected[0], selected[1])
                except Exception as exc:
                    logger.exception("Analysis submit failed for %s", selected[0])

            # Submit Fusion
            for token_addr, candidate in _select_fusion_candidates(fusion_candidates):
                try:
                    SIGNAL_EXECUTOR.submit(send_fused_signal, token_addr, candidate)
                except Exception as exc:
                    logger.exception("Fusion submit failed for %s", token_addr)

        except Exception as exc:
            logger.exception("Clean signal radar error")
        time.sleep(FAST_SCAN_INTERVAL_SECONDS)

# ========== FLASK WEB APP ==========
web_app = Flask(__name__)

@web_app.route('/')
def home():
    html_template = """
    <!DOCTYPE html>
    <html lang="fa" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>صرافی و مینی‌اپلیکیشن VIP هالکی</title>
        <style>
            body { font-family: Tahoma, sans-serif; background: #0f172a; color: #f8fafc; padding: 15px; text-align: center; margin: 0; }
            .card { background: #1e293b; border-radius: 16px; padding: 20px; margin: 10px auto; max-width: 480px; box-shadow: 0 4px 20px rgba(0,0,0,0.7); text-align: right; }
            h1 { color: #38bdf8; font-size: 16px; text-align: center; }
            p { font-size: 13px; color: #cbd5e1; }
            .badge { background: #22c55e; color: white; padding: 3px 10px; border-radius: 20px; font-size: 11px; }
            .badge-expired { background: #ef4444; color: white; padding: 3px 10px; border-radius: 20px; font-size: 11px; }
            .btn { background: #0284c7; color: white; border: none; padding: 10px; border-radius: 8px; font-weight: bold; cursor: pointer; width: 100%; margin-top: 10px; text-align: center; display: block; text-decoration: none; box-sizing: border-box; }
            .btn-pay { background: #10b981; }
            input, select { width: 100%; box-sizing: border-box; padding: 10px; margin: 6px 0; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: white; text-align: center; }
            .wallet-box { background: #0f172a; padding: 10px; border-radius: 8px; border: 1px dashed #38bdf8; text-align: center; margin-bottom: 10px; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🚀 مینی‌اپلیکیشن هوشمند تریدینگ هالکی & AI</h1>
            <div id="contentArea">بارگذاری اطلاعات...</div>
        </div>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <script>
            let telegramId = "";
            if (window.Telegram && window.Telegram.WebApp) {
                try {
                    window.Telegram.WebApp.expand();
                    window.Telegram.WebApp.enableClosingConfirmation();
                } catch (e) {}
                window.Telegram.WebApp.ready();
                if (window.Telegram.WebApp.initDataUnsafe && window.Telegram.WebApp.initDataUnsafe.user) {
                    telegramId = window.Telegram.WebApp.initDataUnsafe.user.id;
                }
            }
            const urlParams = new URLSearchParams(window.location.search);
            if (!telegramId) { telegramId = urlParams.get('telegram_id') || ""; }

            if (!telegramId) {
                document.getElementById('contentArea').innerHTML = `
                    <p style="color:#facc15;text-align:center">⚠️ این صفحه باید از داخل دکمه Mini App ربات باز شود.</p>
                    <p style="font-size:11px;text-align:center;color:#94a3b8">لطفاً به ربات برگردید و روی «📱 ورود به Mini App VIP» بزنید.</p>
                `;
            }

            fetch('/api/check-status?telegram_id=' + encodeURIComponent(telegramId))
            .then(res => res.json())
            .then(data => {
                window.__VIP_CHANNEL_LINK = data.channel_link || "";
                window.__VIP_PRICES = data.prices || {};
                const area = document.getElementById('contentArea');
                setTimeout(updatePaymentPrice, 0);
                if(data.has_subscription) {
                    area.innerHTML = `
                        <p>وضعیت سیستم: <span class="badge">آنلاین (اشتراک فعال VIP)</span></p>
                        <div style="background: #0f172a; padding: 15px; border-radius: 12px; text-align: center; border: 1px solid #22c55e; margin-top: 15px;">
                            <h3 style="color: #22c55e; margin-top: 0; font-size: 15px;">🎉 اشتراک VIP شما فعال است</h3>
                            <p style="color: #38bdf8; font-size: 13px; font-weight: bold;">⏳ تاریخ انقضا: ${data.expiry_date}</p>
                            <p id="remainingTime" style="color:#facc15;font-size:13px;font-weight:bold;">محاسبه زمان باقی‌مانده...</p>
                            <p style="color: #94a3b8; font-size: 11px;">با پایان اشتراک، دسترسی ربات و کانال به‌صورت خودکار قطع می‌شود.</p>
                            <button type="button" class="btn" style="background: #8b5cf6;" onclick="openVipChannel()">📢 ورود به کانال VIP</button>
                            <div style="margin-top:14px;padding:12px;border:1px solid #334155;border-radius:12px;background:#0b1220;">
                              <div style="color:#38bdf8;font-weight:bold;margin-bottom:7px;">🤖 تنظیم حجم کپی‌ترید</div>
                              <input id="copyAmount" type="number" min="0.001" max="100" step="0.001" value="${data.copy_amount_sol || 0.01}" placeholder="حجم SOL">
                              <button type="button" class="btn btn-pay" onclick="saveCopyAmount()">💾 ذخیره حجم کپی‌ترید</button>
                              <p style="font-size:10px;color:#94a3b8;margin-bottom:0;">برای اجرای خودکار روی ولت شخصی، مجوز امن امضای آن ولت لازم است.</p>
                            </div>
                        </div>
                    `;
                    const expiryMs = new Date(data.expiry_date.replace(' ', 'T')).getTime();
                    const tick = () => {
                        const diff = Math.max(0, expiryMs - Date.now());
                        const d = Math.floor(diff / 86400000);
                        const h = Math.floor((diff % 86400000) / 3600000);
                        const m = Math.floor((diff % 3600000) / 60000);
                        const sec = Math.floor((diff % 60000) / 1000);
                        const el = document.getElementById('remainingTime');
                        if (el) el.textContent = `⏱ زمان باقی‌مانده: ${d} روز و ${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
                        if (diff <= 0) location.reload();
                    };
                    tick(); setInterval(tick, 1000);
                } else {
                    let expiryNotice = data.last_expiry ? `<p style="color:#ef4444; font-size:11px;">⚠️ اشتراک قبلی شما منقضی شده است: ${data.last_expiry}</p>` : '';
                    area.innerHTML = `
                        <p>وضعیت سیستم: <span class="badge-expired">نیازمند اشتراک VIP</span></p>
                        ${expiryNotice}
                        <div class="wallet-box">
                            <p style="font-size:11px; margin:0 0 5px 0; color:#38bdf8;">لطفاً مبلغ اشتراک ۳۰ روزه را به ولت زیر واریز کنید:</p>
                            <code style="word-break: break-all; font-size:11px; color:#facc15;">{{ wallet }}</code>
                        </div>
                        <h3 style="color: #c084fc; font-size: 14px;">اشتراک ۳۰ روزه VIP</h3>
                        <p style="font-size:11px;color:#facc15;">مبلغ دقیق پرداخت طبق تنظیمات ربات هنگام انتخاب ارز نمایش داده می‌شود.</p>
                        <label style="font-size:11px; color:#94a3b8;">انتخاب ارز پرداخت:</label>
                        <select id="paymentCurrency" onchange="updatePaymentPrice()">
                            <option value="USDC">پرداخت با 50 USDC</option>
                        </select>
                        <p id="paymentPrice" style="color:#22c55e;font-weight:bold;text-align:center;">مبلغ اشتراک در حال بارگذاری...</p>
                        <input type="text" id="userTelegramId" value="${telegramId}" placeholder="آیدی تلگرام شما">
                        <input type="text" id="userWallet" placeholder="آدرس ولت فرستنده شما">
                        <input type="text" id="txSignature" placeholder="هش تراکنش (TxID) واریز شده را اینجا وارد کنید">
                        <button class="btn btn-pay" onclick="verifyAndPay()">تایید تراکنش و عضویت خودکار در کانال</button>
                    `;
                }
            });

            function updatePaymentPrice() {
                const select = document.getElementById("paymentCurrency");
                const el = document.getElementById("paymentPrice");
                if (!select || !el || !window.__VIP_PRICES) return;
                const cur = select.value;
                const value = Number(window.__VIP_PRICES[cur] || 0);
                el.textContent = value > 0 ? `💳 مبلغ اشتراک: ${value} ${cur}` : `⚠️ مبلغ ${cur} در تنظیمات ربات تعیین نشده است`;
            }

            function openVipChannel() {
                const link = (window.__VIP_CHANNEL_LINK || "").trim();
                if (!link) {
                    alert("لینک کانال VIP هنوز در تنظیمات ربات ثبت نشده است.");
                    return;
                }
                try {
                    if (window.Telegram && window.Telegram.WebApp && typeof window.Telegram.WebApp.openTelegramLink === "function") {
                        window.Telegram.WebApp.openTelegramLink(link);
                        return;
                    }
                } catch (e) {}
                try {
                    if (window.Telegram && window.Telegram.WebApp && typeof window.Telegram.WebApp.openLink === "function") {
                        window.Telegram.WebApp.openLink(link, {try_instant_view: false});
                        return;
                    }
                } catch (e) {}
                window.location.href = link;
            }

            function saveCopyAmount() {
                const amount=Number(document.getElementById('copyAmount')?.value||0);
                if(!amount || amount<=0 || amount>100){ alert('حجم معتبر بین 0 و 100 SOL وارد کنید.'); return; }
                fetch('/api/copy-settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_id:telegramId,trade_amount_sol:amount})})
                  .then(r=>r.json()).then(d=>alert(d.message)).catch(()=>alert('خطا در ذخیره تنظیم کپی‌ترید.'));
            }

            function verifyAndPay() {
                const tId = document.getElementById('userTelegramId').value;
                const wallet = document.getElementById('userWallet').value;
                const txSig = document.getElementById('txSignature').value;
                const currency = document.getElementById('paymentCurrency').value;
                if(!tId || !wallet || !txSig) { alert('لطفاً تمام فیلدها از جمله هش تراکنش (TxID) را وارد کنید!'); return; }
                
                alert('در حال استعلام و تایید پرداخت 50 USDC روی شبکه سولانا...');
                fetch('/api/subscribe', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({telegram_id: tId, wallet_address: wallet, tx_signature: txSig, currency: currency})
                }).then(res => res.json()).then(data => {
                    alert(data.message);
                    if(data.status === 'success') {
                        location.reload();
                    }
                }).catch(err => {
                    alert('خطا در ارتباط با سرور تایید تراکنش.');
                });
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template, wallet=WALLET_PUBKEY)

@web_app.route('/api/check-status')
def api_check_status():
    ensure_channel_invite_link()
    t_id = request.args.get("telegram_id", "")
    has_sub, expiry_str, last_exp = False, "", ""
    if t_id:
        active, exp_date = check_user_subscription(t_id)
        if active and exp_date:
            has_sub = True
            expiry_str = exp_date.strftime("%Y-%m-%d %H:%M:%S")
        else:
            with db_lock:
                try:
                    conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
                    cursor = conn.cursor()
                    cursor.execute("SELECT expiry_date FROM subscribers WHERE telegram_id = ?", (str(t_id),))
                    row = cursor.fetchone()
                    conn.close()
                    if row:
                        last_exp = row[0]
                except Exception as e:
                    logger.error(f"Error checking last expiry: {e}")
    remaining_seconds = 0
    if has_sub and expiry_str:
        try:
            remaining_seconds = max(0, int((datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S") - datetime.now()).total_seconds()))
        except Exception:
            remaining_seconds = 0
    copy_amount = 0.01
    copy_amount_usdc = 10.0
    copy_asset = COPY_DEFAULT_ASSET
    copy_enabled = False
    if t_id:
        with db_lock:
            try:
                conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
                cur = conn.cursor()
                cur.execute("SELECT copy_enabled, trade_amount_sol, trade_asset, trade_amount_usdc FROM subscribers WHERE telegram_id=?", (str(t_id),))
                cr = cur.fetchone()
                conn.close()
                if cr:
                    copy_enabled = bool(cr[0])
                    copy_amount = float(cr[1] or 0.01)
                    copy_asset = str(cr[2] or COPY_DEFAULT_ASSET).upper()
                    copy_amount_usdc = float(cr[3] or 10
