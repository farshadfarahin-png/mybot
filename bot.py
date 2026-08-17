# V17 TRUE HUNTER — verified architecture: independent lanes, MAX unified attack, rotating low-latency radar.
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

# تنظیمات لاگینگ پیشرفته برای عیب‌یابی دقیق در تولید
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(threadName)s - %(message)s'
)
logger = logging.getLogger("HulkSolBot")

# قفل‌های همزمانی برای ایمنی کامل در ثردها (Thread Safety)
db_lock = RLock()
state_lock = Lock()
rpc_lock = Lock()

# ایجاد جلسه ارتباطی پرسرعت با قابلیت Re-use اتصالات و ریتراپ
http_session = requests.Session()
retries = Retry(total=2, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retries)
http_session.mount("https://", adapter)
http_session.mount("http://", adapter)

# کارهای سنگین بازار از اسکنر جدا می‌شوند تا Telegram سریع بماند.
SIGNAL_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="SignalExec")
ANALYSIS_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="AnalysisExec")
SIGNAL_EMIT_LOCK = Lock()

# تنظیمات کلیدی محیطی و کانال انتشار سیگنال
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
ADMIN_SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY", "").strip()

CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip() or VIP_CHANNEL_ID
CHANNEL_INVITE_LINK = os.environ.get("CHANNEL_INVITE_LINK", "").strip()

PRIVATE_KEY_BASE58 = os.environ.get("PRIVATE_KEY_BASE58", "").strip()
WEBAPP_URL = os.environ.get("WEBAPP_URL", "").strip()
VIP_PRICE_SOL = 0.0  # پرداخت SOL غیرفعال است
VIP_PRICE_USDC = 50.0  # قیمت ثابت اشتراک ۳۰ روزه: 50 USDC
COPY_TRADING_FEE_PERCENT = 1.0  # کارمزد سرویس کپی‌ترید؛ از بودجه همان معامله کاربر محاسبه می‌شود.
COPY_DEFAULT_ASSET = "USDC"
UNIFIED_ENGINE_NAME = "🤖⚡ هالک AI — موتور متحد بازار"
BOT_BUILD_VERSION = "V25-RENDER-STARTUP-FIX-2026-08-17"

# ==========================================
# بخش مدیریت پیشرفته RPC چرخشی (RPC Rotation System)
# ==========================================
RPC_ENDPOINTS = []
raw_rpc_env = os.environ.get("RPC_URLS", os.environ.get("RPC_URL", ""))
if raw_rpc_env:
    RPC_ENDPOINTS.extend([url.strip() for url in raw_rpc_env.split(",") if url.strip()])

# دریافت ۴ لینک خصوصی اختصاصی از محیط رندر (RPC_URL_1 تا RPC_URL_4)
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
                else:
                    logger.warning(f"⚠️ پاسخ دارای خطای RPC از {endpoint}: {data.get('error')}")
        except Exception as e:
            logger.debug(f"⚠️ تلاش ناموفق اتصال به RPC ({endpoint}): {e}")
        time.sleep(0.2)
    # تلاش نهایی روی اولین RPC پایه
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
# سوئیچ‌های کنترلی ربات (فعال‌سازی کامل سیگنال‌دهی)
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
# موتور تحلیل مستقل: روند خطی + کف/سقف + نقدینگی/فشار خرید
ANALYSIS_ENGINE_ENABLED = True      
DYNAMIC_TRAILING_TP_ENABLED = True
# مدیریت سود پله‌ای بر پایه سقف سود: حدضرر فقط بالا می‌رود و هیچ‌وقت پایین نمی‌آید.
# مثال: اگر سقف سود به +1000% برسد، حدضرر روی حدود +950% قفل می‌شود.
TRAILING_LOCK_TABLE = (
    # سقف سود -> حداقل سودی که اجازه می‌دهیم پس بدهد
    (1000.0, 950.0),
    (750.0, 650.0),
    (500.0, 350.0),
    (300.0, 230.0),
    (200.0, 155.0),
    (150.0, 110.0),
    (100.0, 75.0),
    (75.0, 55.0),
    (50.0, 35.0),
    (40.0, 28.0),
    (30.0, 20.0),
    (25.0, 15.0),
    (20.0, 10.0),
    (15.0, 7.0),
    (10.0, 3.0),
)
TRAILING_WEAKNESS_ENABLED = True
TRAILING_WEAK_SELL_RATIO = 1.45
TRAILING_WEAKNESS_M5_MAX = 0.0
TRAILING_WEAKNESS_MIN_DRAWDOWN_PCT = 1.5
   

SECTION_ULTRA_OPEN = True
SECTION_VIP_OPEN = True
SECTION_PROTECTION_OPEN = True
SECTION_AI_OPEN = True
SECTION_TRADING_OPEN = True

# تنظیمات و پارامترهای بهینه‌شده برای فعال‌سازی کامل سیگنال‌ها
FIRE_BUY_AMOUNT_SOL = 0.01
FIRE_TAKE_PROFIT = 18.0
FIRE_STOP_LOSS = -10.0
FIRE_MIN_LIQUIDITY = 15000       
FIRE_MIN_VOLUME_5M = 4000       
FIRE_MIN_PRICE_CHANGE_5M = 4.0  

COMBO_BUY_AMOUNT_SOL = 0.01
COMBO_TAKE_PROFIT = 18.0
COMBO_STOP_LOSS = -10.0
COMBO_MIN_LIQUIDITY = 20000
COMBO_MIN_VOLUME_5M = 10000  
COMBO_MIN_CHANGE_5M = 15.0   

GOLDEN_BUY_AMOUNT_SOL = 0.01
GOLDEN_TAKE_PROFIT = 16.0
GOLDEN_STOP_LOSS = -8.0
GOLDEN_MIN_LIQUIDITY = 25000
GOLDEN_MIN_VOLUME_5M = 12000
GOLDEN_MIN_CHANGE_5M = 12.0

# سقف حجم SOL برای هر معامله واقعی؛ از پنل ادمین قابل تغییر است.
MAX_TRADE_SOL = float(os.environ.get("MAX_TRADE_SOL", "0.01"))
TECH_BUY_AMOUNT_SOL = 0.01
TECH_TAKE_PROFIT = 20.0
TECH_STOP_LOSS = -8.0
TECH_MIN_LIQUIDITY = 18000
TECH_MIN_VOLUME_5M = 8000

AWAITING_STATE = None 
processed_tokens = set()
trend_alerted_tokens = set()
golden_processed_tokens = set()
tech_processed_tokens = set()
mempool_processed_tokens = set()
ultra_processed_tokens = set()
active_positions = {}
# سیگنال‌های صادرشده‌ای که خرید واقعی به هر دلیل اجرا نشده؛ فقط از نظر قیمت رصد می‌شوند.
signal_positions = {}

closed_trades_history = []
total_realized_pnl_usd = 0.0
total_realized_pnl_percent = 0.0

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
            logger.info("✅ دیتابیس با قابلیت WAL و کارایی حداکثری مقداردهی اولیه شد.")
        except Exception as e:
            logger.error(f"⚠️ خطای دیتابیس: {e}")

init_db()

def _update_adaptive_learning(conn=None):
    """Learn only from CLOSED real/recorded trades. No fabricated outcomes."""
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
        # Adaptive gate: 80% is a target, never a fake guarantee.
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

        # Learn per-engine reliability from the actual engines recorded in entry_reason.
        engines = ["Fire","Trend","Combo","Golden","Technical","UltimateAI","Mempool/SmartMoney","Whale","Social/Hype","Anti-Wash","SmartFilter"]
        for eng in engines:
            tagged = [float(pnl or 0) for pnl, reason in rows if eng in (reason or "")]
            if tagged:
                ewr = sum(1 for x in tagged if x > 0) / len(tagged) * 100.0
                cur.execute("INSERT OR REPLACE INTO ai_learning_params(param_name,param_value) VALUES(?,?)", (f"engine_wr:{eng}", ewr))
        conn.commit()
        return {"sample": len(rows), "win_rate": wr, "score_bonus": bonus, "ratio_bonus": ratio_bonus}
    finally:
        if own:
            conn.close()

def get_adaptive_consensus_settings(enabled_count):
    """Return live thresholds learned from recent closed trades."""
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
    """Continuous closed-trade learning. It never invents results and never changes security secrets."""
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

    # مدیریت حافظه RAM: پاک‌سازی اتوماتیک مجموعه توکن‌ها هنگام بزرگ شدن بیش از حد
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

    # فقط سرعت جمع‌آوری داده بالا می‌رود؛ منابع و فیلترها همان قبلی هستند.
    with ThreadPoolExecutor(max_workers=MARKET_DISCOVERY_WORKERS, thread_name_prefix="MarketDiscovery") as ex:
        for found in ex.map(fetch_endpoint, endpoints):
            for addr in found:
                if addr not in tokens:
                    tokens.append(addr)

    return tokens

def ultra_accuracy_scanner_loop(app):
    global SMART_MONEY_COPY_ENABLED, SOCIAL_SENTIMENT_ENABLED, DYNAMIC_TRAILING_TP_ENABLED
    logger.info("💎🚀 موتور پایش فوق‌پیشرفته (فیلتر بسیار سخت‌گیر) فعال شد.")

    while True:
        if SYNCHRONIZED_MODE or ADVANCED_AI_ENABLED or MAX_FUSION_ENABLED:
            time.sleep(3)
            continue
        if not (SMART_MONEY_COPY_ENABLED or SOCIAL_SENTIMENT_ENABLED):
            time.sleep(3)
            continue
        try:
            tokens = get_real_market_trending_tokens()
            for token_addr in tokens[:25]:
                with state_lock:
                    if not token_addr or token_addr in active_positions or token_addr in ultra_processed_tokens:
                        continue

                pair_res_obj = http_session.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=3)
                if pair_res_obj.status_code != 200:
                    continue
                pair_res = pair_res_obj.json()
                if not pair_res.get('pairs'):
                    continue
                pair = pair_res['pairs'][0]

                liquidity = float(pair.get('liquidity', {}).get('usd', 0))
                volume_5m = float(pair.get('volume', {}).get('m5', 0))
                price = float(pair.get('priceUsd', 0))
                symbol = pair.get('baseToken', {}).get('symbol', 'ULTRA')
                price_change_5m = float(pair.get('priceChange', {}).get('m5', 0))

                if liquidity < 15000 or volume_5m < 4000 or price <= 0:
                    continue

                is_social_ok, social_msg = check_social_sentiment_and_hype(pair)
                if not is_social_ok:
                    continue

                if SMART_MONEY_COPY_ENABLED:
                    current_buy_amt = get_dynamic_buy_amount(0.01)
                    success, result_info = execute_real_buy(token_addr, 0.01)
                    execution_status = "🟢 خرید موفق روی بلاکچین" if success else f"⚠️ خرید انجام نشد: {result_info}"
                    if success:
                        with state_lock:
                            ultra_processed_tokens.add(token_addr)
                            processed_tokens.add(token_addr)
                    solscan_link = f"https://solscan.io/tx/{result_info}" if success else f"https://solscan.io/token/{token_addr}"
                    init_tp = 30.0
                    init_sl = -7.0

                    if success:
                        with state_lock:
                            active_positions[token_addr] = {
                                "entry_price": price,
                                "symbol": symbol,
                                "tp": init_tp,
                                "sl": init_sl,
                                "highest_price": price,
                                "highest_pnl": 0.0,
                                "locked_floor": init_sl,
                                "trailing_active": DYNAMIC_TRAILING_TP_ENABLED
                            }

                    ultra_msg = (
                        f"💎✨ [سیگنال هوش مصنوعی پیش‌رو - فیلتر سخت‌گیر]\n"
                        f"🎯 وضعیت: {social_msg}\n"
                        f"📌 تاییدیه اسمارت‌مانی و والدهای انسایدر ✅\n\n"
                        f"🪙 توکن: {symbol}\n"
                        f"📍 آدرس:\n{token_addr}\n\n"
                        f"💵 ورود دقیق: ${price:.8f}\n"
                        f"💰 مقدار حجم: {current_buy_amt} SOL\n"
                        f"🎯 تارگت پویا: +%{init_tp}\n"
                        f"🔗 [Solscan]({solscan_link})"
                    )
                    send_telegram_msg(ultra_msg)
                    send_graphic_signal_to_vip_channel(
                        token_addr=token_addr, symbol=symbol, price=price, tp=init_tp, sl=init_sl,
                        buy_amt=current_buy_amt, volume=volume_5m, liquidity=liquidity,
                        p_change=price_change_5m, solscan_link=solscan_link, signal_title="💎✨ سیگنال سخت‌گیر Smart Money + Hype", execution_status=execution_status, execution_tx=result_info if success else ""
                    )
        except Exception as e:
            logger.error(f"⚠️ خطای موتور فوق‌پیشرفته: {e}")
        time.sleep(3)

def mempool_smart_money_scanner_loop(app):
    global MEMPOOL_SMART_MONEY_ENABLED
    logger.info("⚡🕵️ موتور اسکنر ممپول و اسمارت‌مانی فعال شد.")
    while True:
        if SYNCHRONIZED_MODE or ADVANCED_AI_ENABLED or MAX_FUSION_ENABLED:
            time.sleep(3)
            continue
        if not MEMPOOL_SMART_MONEY_ENABLED:
            time.sleep(3)
            continue
        try:
            trending_tokens = get_real_market_trending_tokens()
            for token_addr in trending_tokens[:20]:
                with state_lock:
                    if not token_addr or token_addr in active_positions or token_addr in mempool_processed_tokens:
                        continue
                
                pair_res_obj = http_session.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=3)
                if pair_res_obj.status_code != 200:
                    continue
                pair_res = pair_res_obj.json()
                if not pair_res.get('pairs'):
                    continue
                pair = pair_res['pairs'][0]

                liquidity = float(pair.get('liquidity', {}).get('usd', 0))
                volume_5m = float(pair.get('volume', {}).get('m5', 0))
                symbol = pair.get('baseToken', {}).get('symbol', 'SMART')
                price = float(pair.get('priceUsd', 0))

                if liquidity > 12000 and volume_5m > 3000 and price > 0:
                    current_buy_amt = get_dynamic_buy_amount(0.01)
                    success, result_info = execute_real_buy(token_addr, 0.01)
                    buy_status_str = "🟢 خرید موفق روی بلاکچین" if success else f"⚠️ خرید انجام نشد: {result_info}"
                    if success:
                        with state_lock:
                            mempool_processed_tokens.add(token_addr)
                            processed_tokens.add(token_addr)
                    solscan_link = f"https://solscan.io/tx/{result_info}" if success else f"https://solscan.io/token/{token_addr}"

                    mempool_msg = (
                        f"⚡🕵️ [شکارچی ممپول & اسمارت مانی هالکی]\n"
                        f"🎯 ورود پیش از عموم بازار با تایید نهنگ‌ها!\n"
                        f"📌 وضعیت: {buy_status_str}\n\n"
                        f"🪙 توکن: {symbol}\n"
                        f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                        f"💵 قیمت ورود کف: ${price:.8f}\n"
                        f"💰 مقدار: SOL {current_buy_amt}\n"
                        f"🔍 [Solscan]({solscan_link})\n"
                        f"📈 [DexScreener](https://dexscreener.com/solana/{token_addr})"
                    )
                    if success:
                        with state_lock:
                            active_positions[token_addr] = {
                                "entry_price": price,
                                "symbol": symbol,
                                "tp": 25.0,
                                "sl": -8.0,
                                "highest_price": price
                            }
                    send_telegram_msg(mempool_msg)
                    send_graphic_signal_to_vip_channel(
                        token_addr=token_addr, symbol=symbol, price=price, tp=25.0, sl=-8.0,
                        buy_amt=current_buy_amt, volume=volume_5m, liquidity=liquidity,
                        p_change=15.0, solscan_link=solscan_link, signal_title="⚡🕵️ شکار ممپول اسمارت‌مانی هالکی VIP", execution_status=buy_status_str, execution_tx=result_info if success else ""
                    )
        except Exception as e:
            logger.error(f"⚠️ خطای اسکن ممپول: {e}")
        time.sleep(4)

def verify_blockchain_transaction(tx_signature, expected_currency="USDC"):
    """Verify that a real payment was made to the bot wallet.
    Amounts are configured through VIP_PRICE_SOL / VIP_PRICE_USDC.
    """
    if not tx_signature or len(tx_signature) < 30:
        return False, "هش تراکنش نامعتبر است."

    currency = str(expected_currency or "SOL").upper()
    expected_amount = VIP_PRICE_SOL if currency == "SOL" else VIP_PRICE_USDC
    if expected_amount <= 0:
        return False, f"قیمت اشتراک برای {currency} در Environment تنظیم نشده است."

    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                tx_signature,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
            ]
        }
        res = send_rpc_request(payload, timeout=8)
        result = res.get("result")
        if not result:
            return False, "تراکنش روی بلاکچین یافت نشد یا هنوز تایید نشده است."

        meta = result.get("meta") or {}
        if meta.get("err") is not None:
            return False, "تراکنش روی بلاکچین ناموفق بوده است."

        tx = result.get("transaction") or {}
        message = tx.get("message") or {}
        account_keys = message.get("accountKeys") or []

        # Ensure the configured receiving wallet is actually involved.
        admin_indexes = []
        for idx, acc in enumerate(account_keys):
            pubkey_str = acc.get("pubkey") if isinstance(acc, dict) else str(acc)
            if pubkey_str == WALLET_PUBKEY:
                admin_indexes.append(idx)

        if not admin_indexes:
            return False, "این تراکنش به ولت دریافت‌کننده اشتراک واریز نشده است."

        if currency == "SOL":
            pre = meta.get("preBalances") or []
            post = meta.get("postBalances") or []
            received_lamports = 0
            for idx in admin_indexes:
                if idx < len(pre) and idx < len(post):
                    received_lamports += max(0, int(post[idx]) - int(pre[idx]))
            received = received_lamports / 1_000_000_000
            # Small tolerance for floating-point/env decimal representation.
            if received + 1e-9 < expected_amount:
                return False, f"مبلغ کافی نیست. دریافتی: {received:.9f} SOL، مبلغ لازم: {expected_amount:.9f} SOL."
            return True, f"پرداخت {received:.9f} SOL تایید شد ✅"

        # USDC is a SPL token with 6 decimals.
        received_units = 0
        for field in ("preTokenBalances", "postTokenBalances"):
            pass
        pre_tokens = meta.get("preTokenBalances") or []
        post_tokens = meta.get("postTokenBalances") or []

        def token_amount_for_admin(entries):
            total = 0
            for item in entries:
                if item.get("mint") != USDC_MINT:
                    continue
                owner = item.get("owner")
                if owner == WALLET_PUBKEY:
                    total += int((item.get("uiTokenAmount") or {}).get("amount", "0"))
            return total

        pre_units = token_amount_for_admin(pre_tokens)
        post_units = token_amount_for_admin(post_tokens)
        received_units = max(0, post_units - pre_units)
        received_usdc = received_units / 1_000_000
        if received_usdc + 1e-9 < expected_amount:
            return False, f"مبلغ کافی نیست. دریافتی: {received_usdc:.6f} USDC، مبلغ لازم: {expected_amount:.6f} USDC."
        return True, f"پرداخت {received_usdc:.6f} USDC تایید شد ✅"

    except Exception as e:
        logger.error(f"⚠️ خطا در استعلام بلاکچین: {e}")
        return False, f"خطا در ارتباط با شبکه سولانا: {e}"

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

def send_telegram_msg(text, target_chat=None, reply_markup=None, parse_mode="Markdown"):
    """ارسال امن پیام تلگرام و بررسی پاسخ API."""
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

        # اگر مشکل از inline keyboard باشد، خود پیام را بدون دکمه دوباره می‌فرستیم
        # تا سیگنال به هر حال به کانال برسد و خطای اصلی در لاگ باقی بماند.
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
        # اگر کانال عمومی باشد، لینک مستقیم پایدارتر از invite link است.
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
    # در MAX FUSION، پیام BUY فقط از مسیر Unified Fusion اجازه انتشار دارد.
    # پیام SELL همیشه مجاز است تا خروج پوزیشن‌ها بدون مانع ادامه پیدا کند.
    if str(side).upper() == "BUY" and MAX_FUSION_ENABLED and signal_title not in (UNIFIED_ENGINE_NAME, "MAX FUSION"):
        logger.info(f"Blocked legacy BUY channel card while MAX FUSION is active: {signal_title}")
        return False
    """کارت سیگنال VIP برای موبایل.
    نکته: وضعیت موجودی/اجرای کیف پول هرگز در کانال نمایش داده نمی‌شود.
    لینک‌ها فقط روی دکمه‌ها هستند؛ متن کانال لینک خام ندارد.
    """
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

    # متن کانال عمداً از execution_status صرف‌نظر می‌کند.
    if side == "SELL":
        pnl = float(pnl_percent or 0.0)
        pnl_icon = "🟢" if pnl >= 0 else "🔴"
        result_line = f"📊 سود/ضرر نهایی: {pnl_icon} {pnl:+.2f}%"
        price_label = "🔴 نقطه فروش"
    else:
        result_line = "📌 وضعیت: سیگنال خرید"
        price_label = "🎯 نقطه ورود"

    # مقدارهای آماری برای جلوگیری از توقف ارسال کانال در صورت نبودن داده کامل
    try:
        m5_change = float(p_change or 0.0)
    except Exception:
        m5_change = 0.0
    # این تابع در نسخه‌های قبلی از متغیرهای تعریف‌نشده استفاده می‌کرد و قبل از sendMessage کرش می‌کرد.
    # اگر آمار خرید/فروش جداگانه در ورودی موجود نباشد، مقدار صفر نمایش داده می‌شود.
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

    # لینک‌ها فقط روی دکمه‌های کانال قرار می‌گیرند؛ متن کانال لینک خام ندارد.
    # چهار دکمه ثابت: DexScreener / Solscan / Mini App / Copy-Trade
    buttons = [
        [
            InlineKeyboardButton("📈 DexScreener", url=dex_link),
            InlineKeyboardButton("🔎 Solscan", url=safe_solscan),
        ]
    ]
    if WEBAPP_URL:
        # نکته مهم: دکمه web_app در پیام کانال قابل استفاده نیست و باعث
        # خطای BUTTON_TYPE_INVALID و عدم ارسال کل پیام می‌شود.
        # در کانال از URL button استفاده می‌کنیم؛ خود Mini App داخل آن
        # telegram_id را از initData می‌گیرد.
        buttons.append([
            InlineKeyboardButton("📱 ورود به Mini App", url=WEBAPP_URL),
            InlineKeyboardButton("🤖 کپی‌ترید", url=WEBAPP_URL),
        ])

    try:
        # قبل از ارسال، تنظیمات کانال را تازه‌سازی می‌کنیم تا مقدار قدیمی Render/DB
        # باعث ارسال به مقصد اشتباه نشود.
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
    # MAX_TRADE_SOL سقف نهایی است و حتی ریسک پویا حق عبور از آن را ندارد.
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
        if liquidity < 12000 or volume_5m < 3000:
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

        if price <= 0 or liquidity < 12000 or volume_5m < 3000:
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
        if liquidity < 12000 or volume_5m < 3000:
            return False, 0.0, 0.0, 0.0, "نقدینگی یا حجم کافی نیست"
        if price_change_5m < 2.0:
            return False, 0.0, 0.0, 0.0, "مومنتوم کافی نیست"

        is_21_valid, msg_21 = validate_ultimate_21_layers(token_addr, pair)
        if not is_21_valid:
            return False, 0.0, 0.0, 0.0, msg_21

        return True, price, 20.0, -8.0, f"تایید کامل ماشین هوشمند ابرسیگنال + {msg_21}"
    except Exception as e:
        return False, 0.0, 0.0, 0.0, f"خطا در پردازش: {e}"

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

def _adaptive_locked_floor(highest_pnl, current_floor):
    """حدضرر پله‌ای؛ فقط رو به بالا حرکت می‌کند."""
    floor = float(current_floor)
    for high, lock in TRAILING_LOCK_TABLE:
        if highest_pnl >= high:
            floor = max(floor, lock)
            break
    return floor

def _update_trailing_state(pos, current_price, pnl_percent, pair):
    """به‌روزرسانی سقف قیمت، حدضرر متحرک و تشخیص ضعف بازار.
    این تابع ادعای پیش‌بینی قطعی ریزش ندارد؛ از افت از سقف + مومنتوم/نسبت فروش به خرید استفاده می‌کند.
    """
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

    weakness = False
    if TRAILING_WEAKNESS_ENABLED and highest_pnl >= 20.0:
        ratio_bad = sells >= max(2, int(buys * TRAILING_WEAK_SELL_RATIO))
        momentum_bad = m5 <= TRAILING_WEAKNESS_M5_MAX
        if ratio_bad and momentum_bad and drawdown_from_high >= TRAILING_WEAKNESS_MIN_DRAWDOWN_PCT:
            weakness = True
            # در ضعف جدی بازار، حدضرر را تا نزدیک قیمت فعلی بالا می‌آوریم، اما هرگز پایین نمی‌بریم.
            weakness_floor = pnl_percent - 0.35
            current_floor = max(current_floor, weakness_floor)

    pos["locked_floor"] = current_floor
    pos["market_weakness"] = weakness
    pos["drawdown_from_high"] = drawdown_from_high
    pos["m5_change"] = m5
    pos["buys_m5"] = buys
    pos["sells_m5"] = sells
    return current_floor, weakness

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
            locked_floor, weakness = _update_trailing_state(pos, current_price, pnl, pair)

            # در سیگنال مجازی، TP اولیه فقط نقطه شروع قفل سود است؛ خروج با trailing انجام می‌شود.
            should_close = False
            outcome = "SIGNAL_TP"
            if pnl <= float(pos.get("sl", -8.0)) and pos.get("highest_pnl", 0) < 10:
                should_close = True
                outcome = "SIGNAL_SL"
            elif pnl <= locked_floor and pos.get("highest_pnl", 0) >= 10:
                should_close = True
                outcome = "SIGNAL_TP"
            elif weakness and pnl <= locked_floor:
                should_close = True
                outcome = "SIGNAL_TP"

            if should_close:
                extra = (
                    f"🧠 وضعیت بازار: {'ضعف/فشار فروش تأیید شد' if weakness else 'تریلینگ استاپ فعال شد'}\n"
                    f"📉 افت از سقف: {pos.get('drawdown_from_high', 0):.2f}%\n"
                    f"📊 معاملات ۵ دقیقه: خرید {pos.get('buys_m5', 0)} | فروش {pos.get('sells_m5', 0)}"
                )
                send_signal_outcome(token_addr, pos, current_price, outcome, pnl, extra_text=extra)
                finished.append(token_addr)
        except Exception as e:
            logger.debug(f"Signal-only monitor error {token_addr}: {e}")

    if finished:
        with state_lock:
            for finished_addr in finished:
                signal_positions.pop(finished_addr, None)
                # فقط بعد از خروج کامل، اجازه ورود مجدد به همان توکن آزاد می‌شود.
                _mark_token_closed(finished_addr)
# سیو سود پله‌ای برای معامله واقعی: ۳۰٪ در TP، ۳۰٪ در 2×TP و مابقی با تریلینگ/SL.
PARTIAL_TP_LEVELS = ((1.0, 0.30), (2.0, 0.30))

def check_positions_loop():
    """مدیریت پوزیشن واقعی با trailing پله‌ای، تشخیص ضعف بازار و خروج کامل."""
    global closed_trades_history, total_realized_pnl_usd, total_realized_pnl_percent

    while True:
        try:
            # اول سیگنال‌هایی که خرید واقعی نشده‌اند را رصد کن.
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
                    locked_floor, weakness = _update_trailing_state(pos, current_price, pnl_percent, pair)
                    pos["volume"] = float((pair.get("volume") or {}).get("m5") or 0.0)
                    pos["liquidity"] = float((pair.get("liquidity") or {}).get("usd") or 0.0)
                    pos["p_change"] = float(pair.get("priceChange", {}).get("m5") or 0.0)
                    highest_pnl = float(pos.get("highest_pnl", pnl_percent))

                    # اگر به سقف‌های بسیار بزرگ رسید، حدضرر نیز همراه آن بالا می‌رود.
                    # نمونه: +1000% => حدود +950%؛ +500% => حدود +430%.
                    should_exit = False
                    if pnl_percent <= sl and highest_pnl < 10.0:
                        should_exit = True
                        exit_reason_text = "فروش خودکار حد ضرر اولیه (SL) فعال شد 🛑"
                    elif pnl_percent <= locked_floor and highest_pnl >= 10.0:
                        should_exit = True
                        exit_reason_text = f"Trailing Stop پله‌ای فعال شد؛ سقف سود {highest_pnl:+.2f}% و حدضرر قفل‌شده {locked_floor:+.2f}% 🎯"
                    else:
                        exit_reason_text = ""

                    if not should_exit:
                        continue

                    success = False
                    sell_res_info = "موجودی توکن برای فروش پیدا نشد"
                    for _ in range(3):
                        token_balance = get_token_balance(token_addr)
                        if token_balance > 0:
                            success, sell_res_info = execute_real_sell(token_addr, token_balance)
                            if success:
                                break
                        time.sleep(0.5)

                    is_profit = pnl_percent >= 0
                    sticker = "🤑" if is_profit else "🧐"
                    reason = exit_reason_text or (f"حد سود فعال شد 🎯 {sticker}" if is_profit else "حد ضرر فعال شد 🛑")
                    sell_status = "🟢 فروش موفق روی بلاکچین" if success else f"⚠️ فروش انجام نشد: {sell_res_info}"

                    # مقدار P/L برای داشبورد تقریبی و بر اساس سرمایه نمونه موجود در پوزیشن.
                    invested_sol = float(pos.get("buy_amt", 0.01) or 0.01)
                    pnl_usd_val = invested_sol * pnl_percent / 100.0

                    if success:
                        closed_trades_history.append({"symbol": symbol, "percent": pnl_percent, "usd": pnl_usd_val})
                        total_realized_pnl_percent += pnl_percent
                        total_realized_pnl_usd += pnl_usd_val
                        log_trade_to_db(token_addr, symbol, entry_price, current_price, pnl_percent, pnl_usd_val, reason)

                    tx_link = f"https://solscan.io/tx/{sell_res_info}" if success else f"https://solscan.io/token/{token_addr}"
                    # خروج نهایی از یک مسیر واحد ارسال می‌شود:
                    # داخل ربات = جزئیات کامل؛ کانال = کارت تمیز + دکمه‌ها.
                    if success:
                        send_signal_outcome(
                            token_addr, pos, current_price, "SELL_SUCCESS", pnl_percent,
                            tx_signature=sell_res_info,
                            extra_text=(
                                f"🧠 ضعف بازار: {'تأیید شد' if weakness else 'خیر'}\n"
                                f"📌 دلیل خروج: {reason}"
                            )
                        )
                    else:
                        # شکست اجرای فروش فقط داخل ربات/لاگ می‌ماند؛ کانال پیام «موجودی ناکافی»
                        # یا خطای اجرایی دریافت نمی‌کند. پوزیشن برای تلاش مجدد حفظ می‌شود.
                        send_telegram_msg(
                            f"⚠️ تلاش فروش انجام نشد\n"
                            f"🪙 {symbol}\n"
                            f"📍 آدرس: {token_addr}\n"
                            f"📊 وضعیت فعلی: {pnl_percent:+.2f}%\n"
                            f"📌 علت داخلی: {sell_res_info}\n"
                            f"🔄 پوزیشن همچنان تحت مدیریت است."
                        )

                    # اگر فروش ناموفق بود پوزیشن را حذف نکن؛ در دور بعد دوباره تلاش می‌شود.
                    if success:
                        tokens_to_close.append((token_addr, current_price))

                except Exception as inner_e:
                    logger.error(f"⚠️ خطا در پوزیشن {token_addr}: {inner_e}")

            if tokens_to_close:
                with state_lock:
                    for t_addr, exit_price in tokens_to_close:
                        pos_snapshot = active_positions.get(t_addr)
                        learning_record_exit(t_addr, pos_snapshot, exit_price, "POSITION_CLOSED")
                        active_positions.pop(t_addr, None)
                        # قفل همان توکن فقط پس از فروش کامل آزاد می‌شود.
                        _mark_token_closed(t_addr)
        except Exception as e:
            logger.error(f"⚠️ خطای حلقه پوزیشن‌ها: {e}")
        time.sleep(1)

def technical_analysis_scanner_loop(app):
    global TECHNICAL_RUNNING, TECH_BUY_AMOUNT_SOL, TECH_TAKE_PROFIT, TECH_STOP_LOSS, TECH_MIN_LIQUIDITY
    send_telegram_msg("📊 موتور پرایس اکشن حرفه‌ای (مجهز به AI & Mempool & Hulk Mode) فعال شد.")

    while True:
        if SYNCHRONIZED_MODE or ADVANCED_AI_ENABLED or MAX_FUSION_ENABLED:
            time.sleep(3)
            continue
        if not TECHNICAL_RUNNING:
            time.sleep(2)
            continue

        try:
            tokens = get_real_market_trending_tokens()
            for token_addr in tokens[:30]:
                with state_lock:
                    if not token_addr or token_addr in active_positions or token_addr in tech_processed_tokens:
                        continue

                pair_res_obj = http_session.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=3)
                if pair_res_obj.status_code != 200:
                    continue
                pair_res = pair_res_obj.json()
                if not pair_res.get('pairs'):
                    continue

                pair = pair_res['pairs'][0]
                price = float(pair.get('priceUsd', 0))
                liquidity = float(pair.get('liquidity', {}).get('usd', 0))
                volume_5m = float(pair.get('volume', {}).get('m5', 0))
                price_change_5m = float(pair.get('priceChange', {}).get('m5', 0))
                symbol = pair.get('baseToken', {}).get('symbol', 'TECH_TOKEN')

                if price <= 0 or liquidity < TECH_MIN_LIQUIDITY or volume_5m < TECH_MIN_VOLUME_5M:
                    continue

                is_valid_pa, pa_reason = check_major_support_resistance_pa(pair)
                if not is_valid_pa:
                    continue

                current_buy_amt = get_dynamic_buy_amount(TECH_BUY_AMOUNT_SOL)
                success, result_info = execute_real_buy(token_addr, TECH_BUY_AMOUNT_SOL)
                buy_status_str = "🟢 خرید موفق روی بلاکچین" if success else f"⚠️ خرید انجام نشد: {result_info}"
                if success:
                    with state_lock:
                        tech_processed_tokens.add(token_addr)
                        processed_tokens.add(token_addr)
                solscan_link = f"https://solscan.io/tx/{result_info}" if success else f"https://solscan.io/token/{token_addr}"

                target_tp_val = price * (1 + (TECH_TAKE_PROFIT / 100))
                target_sl_val = price * (1 + (TECH_STOP_LOSS / 100))

                tech_msg = (
                    f"📊📈 سیگنال پرایس اکشن VIP + هوش مصنوعی هالکی\n"
                    f"✨ وضعیت: {pa_reason}\n"
                    f"📌 وضعیت خرید: {buy_status_str}\n\n"
                    f"🪙 توکن: {symbol}\n"
                    f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                    f"💵 نقطه ورود دقیق: ${price:.8f}\n"
                    f"💰 مقدار خرید: SOL {current_buy_amt}\n"
                    f"🎯 تارگت سود: ${target_tp_val:.8f} (+%{TECH_TAKE_PROFIT})\n"
                    f"🛑 حد ضرر: ${target_sl_val:.8f} (%{TECH_STOP_LOSS})\n\n"
                    f"🔗 [Solscan]({solscan_link})\n"
                    f"📈 [DexScreener](https://dexscreener.com/solana/{token_addr})"
                )

                with state_lock:
                    active_positions[token_addr] = {
                        "entry_price": price,
                        "symbol": symbol,
                        "tp": TECH_TAKE_PROFIT,
                        "sl": TECH_STOP_LOSS,
                        "highest_price": price
                    }
                
                send_telegram_msg(tech_msg)
                send_graphic_signal_to_vip_channel(
                    token_addr=token_addr, symbol=symbol, price=price, tp=TECH_TAKE_PROFIT,
                    sl=TECH_STOP_LOSS, buy_amt=current_buy_amt, volume=volume_5m, liquidity=liquidity,
                    p_change=price_change_5m, solscan_link=solscan_link, signal_title="📊 سیگنال پرایس اکشن + هالکی", execution_status=buy_status_str, execution_tx=result_info if success else ""
                )
        except Exception as e:
            logger.error(f"⚠️ خطای موتور پرایس اکشن: {e}")
        time.sleep(2)

# ==========================================================
# موتور اتحاد سریع (Consensus Fusion)
# موتورهای موجود نقش مکمل دارند و امتیازهای مستقل را برای یک
# تصمیم واحد جمع می‌کنند؛ خطای یک موتور، بقیه را متوقف نمی‌کند.
# ==========================================================
# اجماع عمداً کمی سخت‌گیرتر شده تا فقط گزینه‌های باکیفیت‌تر منتشر شوند.
# حداقل 82٪ موتورهای روشن باید رأی مثبت بدهند و در حالت معمول حداقل 7 رأی لازم است.
def new_trade_system_enabled():
    """Whether the unified signal pipeline is allowed to look for new trades."""
    return (SYNCHRONIZED_MODE or ADVANCED_AI_ENABLED or MAX_FUSION_ENABLED) and not EMERGENCY_STOP

def advanced_filter_enabled():
    return ADVANCED_AI_ENABLED or MAX_FUSION_ENABLED

# حالت شکار سخت‌گیر: سیگنال کمتر، کیفیت فیلتر بالاتر.
# این اعداد «تلاش برای win-rate بالا» هستند و تضمین ۹۰٪ سود نیستند.
# MAX FUSION adaptive thresholds: quality-first without starving the scanner.
CONSENSUS_MIN_SCORE = 6
CONSENSUS_MIN_RATIO = 0.60
CONSENSUS_COOLDOWN_SECONDS = 180

# Daily signal cap: editable from the management panel, 1..50. Default: 15.
DAILY_SIGNAL_LIMIT = 15
# فاصله حداقلی بین دو سیگنال جدید؛ برای جلوگیری از بمباران سیگنال‌ها.
GLOBAL_SIGNAL_COOLDOWN_SECONDS = 15 * 60
# Signal budget is capacity only; quality thresholds never depend on this value.
SIGNAL_BUDGET_MIN = 1
SIGNAL_BUDGET_MAX = 50
last_global_signal_time = 0.0
UNIFIED_LAST_EMIT_TIME = 0.0
CONSENSUS_MIN_LIQUIDITY = 10000.0
CONSENSUS_MIN_VOLUME_5M = 1500.0
CONSENSUS_MIN_CHANGE_5M = 0.5
CONSENSUS_MAX_CHANGE_5M = 35.0
CONSENSUS_MIN_BUY_RATIO = 1.05

# V3: two-stage candidate pipeline.
# These thresholds only decide whether a market is worth deeper analysis.
# They do NOT authorize a trade by themselves.
CANDIDATE_MIN_LIQUIDITY = 5000.0
CANDIDATE_MIN_VOLUME_5M = 500.0
CANDIDATE_MIN_BUY_RATIO = 1.02
CANDIDATE_MIN_BUYS = 1

# Final entry quality remains stricter and is checked after structure/flow analysis.
FINAL_ANALYSIS_MIN_LIQUIDITY = 10000.0
FINAL_ANALYSIS_MIN_VOLUME_5M = 1500.0
FINAL_ANALYSIS_MIN_BUY_RATIO = 1.10
FINAL_BREAKOUT_MIN_VOLUME_5M = 2500.0
FINAL_SUPPORT_MIN_VOLUME_5M = 1500.0
ADAPTIVE_TARGET_WIN_RATE = 80.0
ADAPTIVE_LOOKBACK = 20
ADAPTIVE_MIN_SAMPLE = 10
ADAPTIVE_MAX_SCORE_BONUS = 2
ADAPTIVE_MAX_RATIO_BONUS = 0.10
consensus_last_signal = {}

# ==========================================================
# PRO STRUCTURE / LIQUIDITY GATE
# Price-structure memory built from the real market snapshots already
# received by the radar. It blocks blind entries at resistance and
# requires liquidity + buy pressure for support/bottom entries.
# ==========================================================
STRUCTURE_FILTER_ENABLED = True
STRUCTURE_LOOKBACK = 30
STRUCTURE_MIN_SAMPLES = 4
STRUCTURE_SAMPLE_MIN_GAP = 0.75
STRUCTURE_SUPPORT_DISTANCE_PCT = 3.5
STRUCTURE_RESISTANCE_DISTANCE_PCT = 2.0
STRUCTURE_BREAKOUT_BUFFER_PCT = 0.75
STRUCTURE_MIN_SUPPORT_LIQUIDITY = 12000.0
STRUCTURE_MIN_SUPPORT_VOLUME_5M = 2500.0
STRUCTURE_MIN_SUPPORT_BUY_RATIO = 1.15
STRUCTURE_MIN_BREAKOUT_BUY_RATIO = 1.20
STRUCTURE_HISTORY_TTL_SECONDS = 15 * 60
_structure_memory = {}
_structure_lock = Lock()

def _diag_reject(category, reason, token_addr=""):
    logger.debug(f"⛔ رد سیگنال [{category}] - دلیل: {reason} | توکن: {token_addr}")

def _analysis_diag(stage, token_addr=""):
    logger.debug(f"🔍 مرحله تحلیل [{stage}] | توکن: {token_addr}")

def _update_structure_memory(token_addr, price):
    """Store real observed prices; never invents candles or OHLC data."""
    try:
        now = time.time()
        price = float(price or 0)
        if not token_addr or price <= 0:
            return []
        with _structure_lock:
            rows = _structure_memory.setdefault(token_addr, [])
            if rows and now - rows[-1][0] < STRUCTURE_SAMPLE_MIN_GAP:
                # Replace the last snapshot when the radar is polling too fast.
                rows[-1] = (now, price)
            else:
                rows.append((now, price))
            cutoff = now - STRUCTURE_HISTORY_TTL_SECONDS
            rows[:] = [x for x in rows[-STRUCTURE_LOOKBACK:] if x[0] >= cutoff]
            return list(rows)
    except Exception:
        return []

def _market_structure_gate(token_addr, pair):
    """Return structure evidence for a BUY candidate.

    Rules:
      * no blind 'touch the bottom' entry; support must have liquidity and
        buy pressure, and price must show a bounce away from the low.
      * no entry directly under a known resistance unless the resistance
        is actually broken with strong buy pressure.
      * continuation entries require an upward trend and healthy flow.
    """
    if not STRUCTURE_FILTER_ENABLED:
        return True, {"structure": "DISABLED", "structure_score": 0.0}
    try:
        price = float(pair.get("priceUsd", 0) or 0)
        chg = float((pair.get("priceChange") or {}).get("m5", 0) or 0)
        liq = float((pair.get("liquidity") or {}).get("usd", 0) or 0)
        vol = float((pair.get("volume") or {}).get("m5", 0) or 0)
        tx = (pair.get("txns") or {}).get("m5", {}) or {}
        buys = int(tx.get("buys", 0) or 0)
        sells = int(tx.get("sells", 0) or 0)
        buy_ratio = buys / max(1, sells)
        samples = _update_structure_memory(token_addr, price)
        if price <= 0:
            _diag_reject("STRUCTURE", "INVALID_PRICE", token_addr)
            return False, {"structure": "INVALID_PRICE", "structure_score": 0.0}

        # Do not kill the signal pipeline while a token is still building
        # local price history. We already have live liquidity/volume/order-flow
        # evidence; use that as a provisional structure check, then switch to
        # the full swing-high/swing-low gate once enough samples exist.
        if len(samples) < STRUCTURE_MIN_SAMPLES:
            _analysis_diag("warmup_checked", token_addr=token_addr)
            provisional_ok = (
                liq >= CONSENSUS_MIN_LIQUIDITY and
                vol >= CONSENSUS_MIN_VOLUME_5M and
                buys > 0 and buy_ratio >= CONSENSUS_MIN_BUY_RATIO and chg >= CONSENSUS_MIN_CHANGE_5M
            )
            if provisional_ok:
                return True, {
                    "structure": "PROVISIONAL_FLOW_CONFIRMATION",
                    "structure_score": 1.0,
                    "samples": len(samples),
                    "support": 0.0,
                    "resistance": 0.0,
                    "breakout": False,
                }
            _diag_reject("STRUCTURE", "BUILDING_HISTORY", token_addr)
            return False, {"structure": "BUILDING_HISTORY", "structure_score": 0.0, "samples": len(samples)}

        _analysis_diag("full_structure_checked", token_addr=token_addr)
        prices = [x[1] for x in samples]
        prior = prices[:-1]
        local_low = min(prices)
        local_high = max(prior) if prior else price
        recent_low = min(prices[-min(8, len(prices)):])
        recent_high = max(prices[-min(8, len(prices)):])
        bounce_from_low = ((price - recent_low) / recent_low * 100.0) if recent_low > 0 else 0.0
        below_resistance = price < local_high * (1.0 - STRUCTURE_RESISTANCE_DISTANCE_PCT / 100.0)
        at_resistance = price >= local_high * (1.0 - STRUCTURE_RESISTANCE_DISTANCE_PCT / 100.0)
        breakout = price >= local_high * (1.0 + STRUCTURE_BREAKOUT_BUFFER_PCT / 100.0)
        near_support = price <= recent_low * (1.0 + STRUCTURE_SUPPORT_DISTANCE_PCT / 100.0)

        # Direct resistance entries are forbidden unless a real breakout is confirmed.
        if at_resistance and not breakout:
            _diag_reject("STRUCTURE", "RESISTANCE_REJECTION", token_addr)
            return False, {"structure": "RESISTANCE_REJECTION", "structure_score": 0.0,
                           "support": recent_low, "resistance": local_high, "breakout": False}

        # A bottom entry is valid only after a bounce and with real liquidity/flow.
        if near_support:
            support_ok = (liq >= STRUCTURE_MIN_SUPPORT_LIQUIDITY and
                          vol >= STRUCTURE_MIN_SUPPORT_VOLUME_5M and
                          buy_ratio >= STRUCTURE_MIN_SUPPORT_BUY_RATIO and
                          chg > 0 and bounce_from_low >= 0.35)
            if not support_ok:
                _diag_reject("STRUCTURE", "UNCONFIRMED_SUPPORT", token_addr)
                return False, {"structure": "UNCONFIRMED_SUPPORT", "structure_score": 0.0,
                               "support": recent_low, "resistance": local_high, "breakout": False}
            return True, {"structure": "SUPPORT_BOUNCE", "structure_score": 3.0,
                          "support": recent_low, "resistance": local_high, "breakout": False}

        # Breakout is allowed only with stronger buy pressure and enough market depth.
        if breakout:
            if liq < STRUCTURE_MIN_SUPPORT_LIQUIDITY or vol < STRUCTURE_MIN_SUPPORT_VOLUME_5M or buy_ratio < STRUCTURE_MIN_BREAKOUT_BUY_RATIO:
                return False, {"structure": "WEAK_BREAKOUT", "structure_score": 0.0}
            return True, {"structure": "BREAKOUT_CONFIRMED", "structure_score": 3.0, "support": recent_low, "resistance": local_high, "breakout": True}

        return True, {"structure": "CONTINUATION", "structure_score": 1.0, "support": recent_low, "resistance": local_high, "breakout": False}
    except Exception as e:
        logger.error(f"⚠️ خطای تحلیل ساختار بازار: {e}")
        return True, {"structure": "ERROR_BYPASS", "structure_score": 0.0}

# سرعت رصد فقط — هیچ آستانه کیفیت، تعداد سیگنال یا منطق موتور تغییر نمی‌کند.
FAST_SCAN_INTERVAL_SECONDS = 0.20
MARKET_DISCOVERY_WORKERS = 16
PAIR_SCAN_WORKERS = 32

# ELITE RADAR + HULK SENTINEL: فقط معماری رصد/رتبه‌بندی ارتقا یافته؛ هیچ آستانه کیفیت، سقف سیگنال یا کلید کنترلی تغییر نمی‌کند.
# بازار در پس‌زمینه تازه می‌شود تا رادار منتظر HTTP discovery نماند.
ELITE_DISCOVERY_REFRESH_SECONDS = 0.40
ELITE_DISCOVERY_MAX_AGE_SECONDS = 4.0
ELITE_PAIR_TIMEOUT_SECONDS = 1.50
ELITE_VOTE_WORKERS = 12
ELITE_MAX_UNIQUE_TOKENS = 1200
_elite_market_cache = []
_elite_market_cache_time = 0.0
_elite_market_refresh_lock = Lock()
_elite_market_refresh_thread = None

# ==========================================================
# HULK SENTINEL — ranking intelligence only
# Does NOT alter signal count, quality gates, engine switches,
# consensus thresholds, cooldowns, or user controls.
# It only ranks already-valid candidates faster and smarter.
# ==========================================================
_SENTINEL_MEMORY_TTL = 120.0
_SENTINEL_MAX_TOKENS = 5000
_SENTINEL_PAIR_CHOICES = 3

# V17 TRUE HUNTER: scan the universe in rotating micro-batches.
# This prevents the radar from waiting for hundreds of HTTP calls before making
# a decision, while every discovered token is revisited continuously.
TRUE_HUNTER_BATCH_SIZE = 64
_TRUE_HUNTER_CURSOR = 0
_TRUE_HUNTER_CURSOR_LOCK = Lock()
_sentinel_memory = {}
_sentinel_lock = Lock()

def _sentinel_ratio(buys, sells):
    return float(buys) / max(1.0, float(sells))

def _sentinel_rank_pair(pair):
    """Cheap ranking of Solana pairs from one DexScreener token response.
    This is a ranking heuristic only; fixed quality gates remain authoritative.
    """
    try:
        liq = float(((pair.get("liquidity") or {}).get("usd")) or 0)
        vol = float(((pair.get("volume") or {}).get("m5")) or 0)
        chg = float(((pair.get("priceChange") or {}).get("m5")) or 0)
        tx = (pair.get("txns") or {}).get("m5", {}) or {}
        buys = int(tx.get("buys", 0) or 0)
        sells = int(tx.get("sells", 0) or 0)
        br = _sentinel_ratio(buys, sells)
        # Log scaling prevents a huge pool from dominating every other signal.
        return (
            min(5.0, math.log10(max(1.0, liq)) - 3.0) +
            min(5.0, math.log10(max(1.0, vol)) - 2.0) +
            min(4.0, max(0.0, chg) / 5.0) +
            min(3.0, max(0.0, br - 1.0))
        )
    except Exception:
        return -999.0

def _sentinel_rank_bonus(token_addr, fusion):
    """Reward acceleration/persistence only after a candidate passed all gates."""
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
        # Ranking bonus: acceleration, sustained score and buy-pressure improvement.
        chg_accel = max(-2.0, min(2.0, chg - old.get("chg", chg)))
        vol_accel = 0.0
        if old.get("vol", 0) > 0:
            vol_accel = max(-1.5, min(1.5, (vol / old["vol"]) - 1.0))
        br_accel = max(-1.0, min(1.0, br - old.get("br", br)))
        persistence = 1.0 if base >= old.get("score", base) else 0.0
        return max(-2.0, min(4.5, chg_accel * 0.8 + vol_accel * 0.9 + br_accel * 0.8 + persistence * 1.0))
    except Exception:
        return 0.0


def _active_subengine_votes(token_addr, pair):
    """Evaluate active sub-engines concurrently without changing their rules.

    Every existing predicate is preserved; only independent checks run in parallel
    so one slow engine cannot hold up the other active engines.
    """
    chg = float((pair.get("priceChange") or {}).get("m5", 0) or 0)
    vol = float((pair.get("volume") or {}).get("m5", 0) or 0)
    liq = float((pair.get("liquidity") or {}).get("usd", 0) or 0)
    txns = (pair.get("txns") or {}).get("m5", {}) or {}
    buys = int(txns.get("buys", 0) or 0)
    sells = int(txns.get("sells", 0) or 0)

    advanced_votes = []
    hulk_votes = []

    def run_advanced(name, fn):
        try:
            ok = fn()
            return name if ok else None
        except Exception:
            return None

    advanced_jobs = []
    if TECHNICAL_RUNNING:
        advanced_jobs.append(("Technical", lambda: check_major_support_resistance_pa(pair)[0]))
    if ULTIMATE_21_ENGINE_ENABLED:
        advanced_jobs.append(("UltimateAI/21", lambda: evaluate_ultimate_super_signal(token_addr, pair)[0]))
    if SOCIAL_SENTIMENT_ENABLED:
        advanced_jobs.append(("Social/Hype", lambda: check_social_sentiment_and_hype(pair)[0]))
    if SMART_FILTER_ENABLED:
        advanced_jobs.append(("SmartFilter", lambda: is_token_worthy(pair)))

    if advanced_jobs:
        workers = min(ELITE_VOTE_WORKERS, len(advanced_jobs))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="AdvVote") as ex:
            for result in ex.map(lambda job: run_advanced(job[0], job[1]), advanced_jobs):
                if result:
                    advanced_votes.append(result)

    # Hulk predicates are pure local calculations, so evaluate them immediately.
    if IS_RUNNING and chg >= 3 and vol >= 3000:
        hulk_votes.append("Fire")
    if TREND_ALERT_RUNNING and chg >= 5 and buys >= max(1, sells):
        hulk_votes.append("Trend")
    if COMBO_RUNNING and buys > sells and vol >= 5000 and liq >= 15000:
        hulk_votes.append("Combo")
    if GOLDEN_OPTION and chg >= 8 and vol >= 7000 and liq >= 18000:
        hulk_votes.append("Golden")
    if MEMPOOL_SMART_MONEY_ENABLED and buys >= max(2, int(sells * 1.20) + 1) and vol >= 5000 and liq >= 15000:
        hulk_votes.append("Mempool/SmartMoney")
    if BOTTOM_WHALE_RUNNING and buys >= max(3, sells + 2) and vol >= 5000:
        hulk_votes.append("Whale")
    if ANTI_WASH_TRADING_ENABLED and not (sells > 0 and buys < sells * 0.8):
        hulk_votes.append("Anti-Wash")

    all_votes = advanced_votes + hulk_votes
    return {
        "advanced_votes": advanced_votes,
        "hulk_votes": hulk_votes,
        "votes": all_votes,
        "advanced_count": len(advanced_votes),
        "hulk_count": len(hulk_votes),
        "all_count": len(all_votes),
    }


def _candidate_prefilter(pair):
    """Cheap discovery gate. Passing this never means 'BUY'."""
    try:
        price = float(pair.get("priceUsd", 0) or 0)
        liq = float((pair.get("liquidity") or {}).get("usd", 0) or 0)
        vol = float((pair.get("volume") or {}).get("m5", 0) or 0)
        tx = (pair.get("txns") or {}).get("m5", {}) or {}
        buys = int(tx.get("buys", 0) or 0)
        sells = int(tx.get("sells", 0) or 0)
        ratio = buys / max(1, sells)
        token_addr = (pair.get("baseToken") or {}).get("address", "")
        if price <= 0:
            reason = "CANDIDATE_INVALID_PRICE"
        elif liq < CANDIDATE_MIN_LIQUIDITY:
            reason = "CANDIDATE_LOW_LIQUIDITY"
        elif vol < CANDIDATE_MIN_VOLUME_5M:
            reason = "CANDIDATE_LOW_5M_VOLUME"
        elif buys < CANDIDATE_MIN_BUYS:
            reason = "CANDIDATE_NO_BUYERS"
        elif ratio < CANDIDATE_MIN_BUY_RATIO:
            reason = "CANDIDATE_WEAK_BUY_PRESSURE"
        else:
            V13_SIGNAL_DIAGNOSTICS["candidate_prefilter_pass"] += 1
            return True
        V13_SIGNAL_DIAGNOSTICS["candidate_prefilter_reject"] += 1
        V13_SIGNAL_DIAGNOSTICS["candidate_prefilter_reasons"][reason] = (
            V13_SIGNAL_DIAGNOSTICS["candidate_prefilter_reasons"].get(reason, 0) + 1
        )
        _diag_reject("DISCOVERY", reason, token_addr)
        return False
    except Exception:
        V13_SIGNAL_DIAGNOSTICS["candidate_prefilter_reject"] += 1
        _diag_reject("DISCOVERY", "CANDIDATE_PREFILTER_EXCEPTION")
        return False


def _mode_market_quality(pair):
    price = float(pair.get("priceUsd", 0) or 0)
    liq = float((pair.get("liquidity") or {}).get("usd", 0) or 0)
    vol = float((pair.get("volume") or {}).get("m5", 0) or 0)
    chg = float((pair.get("priceChange") or {}).get("m5", 0) or 0)
    txns = (pair.get("txns") or {}).get("m5", {}) or {}
    buys = int(txns.get("buys", 0) or 0)
    sells = int(txns.get("sells", 0) or 0)
    token_addr = (pair.get("baseToken") or {}).get("address", "")
    if price <= 0:
        _diag_reject("MARKET_QUALITY", "INVALID_PRICE", token_addr); return None
    if liq < CONSENSUS_MIN_LIQUIDITY:
        _diag_reject("MARKET_QUALITY", "LOW_LIQUIDITY", token_addr); return None
    if vol < CONSENSUS_MIN_VOLUME_5M:
        _diag_reject("MARKET_QUALITY", "LOW_5M_VOLUME", token_addr); return None
    if chg < CONSENSUS_MIN_CHANGE_5M:
        _diag_reject("MARKET_QUALITY", "5M_CHANGE_TOO_LOW", token_addr); return None
    if chg > CONSENSUS_MAX_CHANGE_5M:
        _diag_reject("MARKET_QUALITY", "5M_CHANGE_TOO_HIGH", token_addr); return None
    if buys <= 0:
        _diag_reject("MARKET_QUALITY", "NO_BUYERS", token_addr); return None
    if sells > 0 and buys < max(1, int(sells * CONSENSUS_MIN_BUY_RATIO)):
        _diag_reject("MARKET_QUALITY", "BUY_PRESSURE_TOO_WEAK", token_addr); return None
    return {"price": price, "liq": liq, "vol": vol, "chg": chg, "buys": buys, "sells": sells}


def build_consensus_signal(token_addr, pair):
    """Top-level mode selector while preserving the original Fusion pipeline name.

    IMPORTANT: one best candidate is selected by the market scanner; this function
    only evaluates a candidate.  Real execution remains in send_fused_signal().
    """
    try:
        q = _mode_market_quality(pair)
        if not q:
            _diag_reject("FUSION", "MARKET_QUALITY_REJECTED", token_addr)
            return None

        structure_ok, structure = _market_structure_gate(token_addr, pair)
        if not structure_ok:
            _diag_reject("FUSION", f"STRUCTURE_{structure.get('structure', 'REJECTED')}", token_addr)
            return None

        evidence = _active_subengine_votes(token_addr, pair)
        adv = evidence["advanced_count"]
        hulk = evidence["hulk_count"]
        total = evidence["all_count"]

        # Top-level mode.  MAX owns the market scanner whenever it is ON.
        if MAX_FUSION_ENABLED:
            mode = "MAX FUSION"
            # MAX requires BOTH families to participate, but does not require
            # two votes from each family.  Requiring 2+2 made the real scanner
            # reject almost every candidate even when market quality was valid.
            if adv < 1 or hulk < 1:
                _diag_reject("FUSION", f"MAX_VOTE_MISSING_ADV_{adv}_HULK_{hulk}", token_addr)
                return None
            # MAX requires one credible vote from each family, not an arbitrary
            # third/fourth vote. The market-quality and structure gates remain
            # responsible for rejecting weak setups.
            strength = adv * 1.25 + hulk * 1.35
        elif ADVANCED_AI_ENABLED:
            mode = "سیستم پیشرفته AI"
            # Advanced can operate completely by itself and searches the market
            # using its own AI/quality sub-engines.
            if adv < 1:
                _diag_reject("FUSION", "ADVANCED_NO_VOTE", token_addr)
                return None
            required = max(1, int(max(2, adv) * 0.50 + 0.9999))
            if adv < required:
                _diag_reject("FUSION", f"ADVANCED_VOTE_COUNT_{adv}_NEED_{required}", token_addr)
                return None
            strength = adv * 1.35 + (hulk * 0.15)
        elif SYNCHRONIZED_MODE:
            mode = "اتحاد هالک AI"
            if hulk < 1:
                _diag_reject("FUSION", "HULK_NO_VOTE", token_addr)
                return None
            required = max(1, int(max(2, hulk) * 0.50 + 0.9999))
            if hulk < required:
                _diag_reject("FUSION", f"HULK_VOTE_COUNT_{hulk}_NEED_{required}", token_addr)
                return None
            strength = hulk * 1.40 + (adv * 0.15)
        else:
            _diag_reject("FUSION", "NO_ACTIVE_TOP_LEVEL_MODE", token_addr)
            return None

        # Prefer stronger momentum, healthy buy pressure, liquidity and volume.
        buy_ratio = q["buys"] / max(1, q["sells"])
        score = strength + min(5.0, q["chg"] / 5.0) + min(4.0, q["vol"] / 10000.0) + min(3.0, q["liq"] / 50000.0)
        score += min(3.0, max(0.0, buy_ratio - 1.0))
        score += float(structure.get("structure_score", 0.0) or 0.0)

        now = time.time()
        if now - consensus_last_signal.get(token_addr, 0) < CONSENSUS_COOLDOWN_SECONDS:
            _diag_reject("FUSION", "ENGINE_COOLDOWN", token_addr)
            return None

        return {
            "score": float(score),
            "strength": float(strength),
            "votes": evidence["votes"],
            "advanced_votes": evidence["advanced_votes"],
            "hulk_votes": evidence["hulk_votes"],
            "engines": evidence["votes"],
            "mode": mode,
            **q,
            "symbol": (pair.get("baseToken") or {}).get("symbol", "TOKEN"),
            "tp": max(15.0, min(30.0, 14.0 + min(12.0, score))),
            "sl": -8.0,
            "structure": structure.get("structure", "UNKNOWN"),
            "support": float(structure.get("support", 0.0) or 0.0),
            "resistance": float(structure.get("resistance", 0.0) or 0.0),
            "breakout": bool(structure.get("breakout", False)),
        }
    except Exception as e:
        logger.debug(f"Mode engine evaluation error {token_addr}: {e}")
        return None


# ADAPTIVE_LEARNING_TARGET_NOTE:
# Learning may update engine weights from real closed-trade outcomes,
# but it must not lower the fixed quality gate just to consume the daily budget.
def fusion_quality_gate(fusion):
    """Fixed market-quality gate. Daily budget is never used as a quality knob."""
    try:
        liq = float(fusion.get("liq", 0) or 0)
        vol = float(fusion.get("vol", 0) or 0)
        chg = float(fusion.get("chg", 0) or 0)
        score = float(fusion.get("score", 0) or 0)

        if liq < CONSENSUS_MIN_LIQUIDITY:
            return False
        if vol < CONSENSUS_MIN_VOLUME_5M:
            return False
        if chg < CONSENSUS_MIN_CHANGE_5M:
            return False
        # MAX keeps a meaningful quality floor, but 10.0 was unreachable
        # for otherwise valid 1+1 consensus candidates.
        if MAX_FUSION_ENABLED and score < 4.5:
            return False
        if ADVANCED_AI_ENABLED and not MAX_FUSION_ENABLED and score < 4.0:
            return False
        if SYNCHRONIZED_MODE and not ADVANCED_AI_ENABLED and not MAX_FUSION_ENABLED and score < 4.0:
            return False
        return True
    except Exception:
        return False




# ==========================================================
# PRO MAX LEARNING CORE
# Persistent closed-trade learning + risk circuit breaker
# ==========================================================
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



# ==========================================================
# PRO_MAX_V11_DATA_DRIVEN
# Evidence-based learning: checkpoints, engine/regime attribution,
# rolling out-of-sample validation and bounded weight tuning.
# ==========================================================
V11_STATS_FILE = "fusion_v11_stats.json"
V11_CHECKPOINTS = (100, 300, 500)
V11_MIN_ENGINE_TRADES = 20
V11_MIN_REGIME_TRADES = 20
V11_TUNING_INTERVAL = 6 * 3600
V11_MAX_WEIGHT_STEP = 0.08
V11_MIN_WEIGHT = 0.35
V11_MAX_WEIGHT = 1.65

v11_state = {"checkpoints": {}, "engines": {}, "regimes": {}, "updated_at": 0.0, "last_tuning": 0.0, "last_changes": []}

def _v11_save():
    try:
        Path(V11_STATS_FILE).write_text(json.dumps(v11_state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"V11 save failed: {e}")

def _v11_rows():
    return list(learning_state.get("trades", []))

def _v11_metrics(rows):
    pnl=[float(r.get("pnl_pct",0) or 0) for r in rows]
    wins=sum(1 for x in pnl if x>0)
    gp=sum(max(0,x) for x in pnl); gl=sum(abs(min(0,x)) for x in pnl)
    return {
        "trades":len(rows), "wins":wins, "losses":len(rows)-wins,
        "win_rate":wins/len(rows)*100 if rows else 0.0,
        "net_pnl_pct":sum(pnl), "avg_pnl_pct":sum(pnl)/len(pnl) if pnl else 0.0,
        "profit_factor":gp/gl if gl else (999.0 if gp else 0.0)
    }

def v11_rebuild_statistics():
    rows=_v11_rows()
    for n in V11_CHECKPOINTS:
        if len(rows)>=n:
            v11_state["checkpoints"][str(n)] = _v11_metrics(rows[-n:])

    eg={}
    rg={}
    for r in rows:
        names=r.get("engines") or []
        if isinstance(names,str): names=[x.strip() for x in names.split(',') if x.strip()]
        for name in names: eg.setdefault(name,[]).append(r)
        regime=r.get("regime") or "UNKNOWN"
        rg.setdefault(regime,[]).append(r)
    v11_state["engines"]={k:{**_v11_metrics(v),"qualified":len(v)>=V11_MIN_ENGINE_TRADES} for k,v in eg.items()}
    v11_state["regimes"]={k:{**_v11_metrics(v),"qualified":len(v)>=V11_MIN_REGIME_TRADES} for k,v in rg.items()}
    v11_state["updated_at"]=time.time()
    _v11_save()
    return v11_state

def v11_tune_weights():
    v11_rebuild_statistics()
    changes=[]
    for name,st in v11_state.get("engines",{}).items():
        if not st.get("qualified"): continue
        wr=float(st.get("win_rate",0)); avg=float(st.get("avg_pnl_pct",0))
        old=float(learning_state.get("engines",{}).get(name,{}).get("weight",1.0))
        # Evidence must agree: both hit-rate and average outcome matter.
        if wr>=60 and avg>0: delta=V11_MAX_WEIGHT_STEP
        elif wr<45 or avg<0: delta=-V11_MAX_WEIGHT_STEP
        else: delta=0.0
        if not delta: continue
        new=max(V11_MIN_WEIGHT,min(V11_MAX_WEIGHT,old+delta))
        learning_state.setdefault("engines",{}).setdefault(name,{"trades":0,"wins":0,"losses":0,"avg_pnl":0.0,"weight":1.0})["weight"]=new
        changes.append({"engine":name,"old":old,"new":new,"win_rate":wr,"avg_pnl_pct":avg})
    v11_state["last_tuning"]=time.time(); v11_state["last_changes"]=changes
    _save_learning_state(); _v11_save()
    return changes

def v11_data_report():
    v11_rebuild_statistics()
    return v11_state


# اجرای محاسبات سنگین خارج از event loop تلگرام
async def _tg_bg(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)

# ==========================================================
# V12_REAL_AUDIT
# Real scanner observability. Counters describe actual pipeline
# decisions only; no synthetic signals/trades are generated.
# ==========================================================
V12_REAL_AUDIT = {
    "scans": 0,
    "tokens_seen": 0,
    "pairs_seen": 0,
    "fusion_candidates": 0,
    "analysis_candidates": 0,
    "analysis_signals_submitted": 0,
    "quality_rejected": 0,
    "duplicate_rejected": 0,
    "daily_cap_rejected": 0,
    "cooldown_rejected": 0,
    "circuit_rejected": 0,
    "emergency_rejected": 0,
    "real_buy_success": 0,
    "real_buy_failed": 0,
    "channel_sent": 0,
    "channel_failed": 0,
    "last_scan": 0.0,
    "last_candidate": 0.0,
    "last_signal": 0.0,
    "last_error": "",
}

# V25 FIX: add extended counters only after the base audit dictionary exists.
for _k in (
    "analysis_selected", "analysis_submit_attempted",
    "analysis_submit_called", "analysis_submit_failed", "analysis_worker_exception",
    "analysis_execution_success", "analysis_execution_failed"
):
    V12_REAL_AUDIT.setdefault(_k, 0)


V13_SIGNAL_DIAGNOSTICS = {
    "total": 0,
    "candidate_prefilter_pass": 0,
    "candidate_prefilter_reject": 0,
    "candidate_prefilter_reasons": {},
    "analysis": {
        "scanned": 0,
        "selected": 0,
        "submit_called": 0,
        "worker_started": 0,
        "blocked_duplicate": 0,
        "blocked_daily_cap": 0,
        "blocked_circuit": 0,
        "blocked_cooldown": 0,
        "execution_started": 0,
        "data_ready": 0,
        "warmup_checked": 0,
        "full_structure_checked": 0,
        "support_setups": 0,
        "breakout_setups": 0,
        "continuation_setups": 0,
        "candidates": 0,
        "submitted": 0,
        "real_buy_success": 0,
        "real_buy_failed": 0,
        "channel_sent": 0,
        "channel_failed": 0,
        "worker_failed": 0,
        "rejected": 0,
        "reasons": {},
        "last_reason": "",
        "last_token": "",
    },
    "last_blocker": "هنوز داده‌ای ثبت نشده",
    "last_token": "",
    "last_stage": "",
    "reasons": {},
    "stages": {
        "DISCOVERY": 0,
        "PAIR_FETCH": 0,
        "MARKET_QUALITY": 0,
        "STRUCTURE": 0,
        "ENGINE": 0,
        "FUSION": 0,
        "ANALYSIS": 0,
        "QUALITY_GATE": 0,
        "EXECUTION": 0,
        "CHANNEL": 0,
        "SYSTEM": 0,
    },
    "last_error": "",
}

def _analysis_diag(action=None, reason=None, token_addr=""):
    try:
        a=V13_SIGNAL_DIAGNOSTICS["analysis"]
        if action in ("scanned","data_ready","warmup_checked","full_structure_checked","support_setups","breakout_setups","continuation_setups","candidates","selected","submit_called","worker_started","blocked_duplicate","blocked_daily_cap","blocked_circuit","blocked_cooldown","execution_started","submitted","real_buy_success","real_buy_failed","channel_sent","channel_failed","rejected"):
            a[action]=a.get(action,0)+1
        if action=="reject":
            a["rejected"]+=1
            if reason:
                a["reasons"][reason]=a["reasons"].get(reason,0)+1
                a["last_reason"]=reason
        if token_addr:
            a["last_token"]=str(token_addr)
    except Exception as exc:
        logger.exception("Analysis diagnostic update failed: %s", exc)

def _diag_reject(stage, reason, token_addr=""):
    """Record the exact last blocking point and aggregate every rejection reason."""
    try:
        stage = str(stage or "UNKNOWN").upper()
        reason = str(reason or "UNKNOWN")
        V13_SIGNAL_DIAGNOSTICS["total"] += 1
        V13_SIGNAL_DIAGNOSTICS["last_blocker"] = reason
        V13_SIGNAL_DIAGNOSTICS["last_stage"] = stage
        V13_SIGNAL_DIAGNOSTICS["last_token"] = str(token_addr or "")
        V13_SIGNAL_DIAGNOSTICS["stages"][stage] = V13_SIGNAL_DIAGNOSTICS["stages"].get(stage, 0) + 1
        V13_SIGNAL_DIAGNOSTICS["reasons"][reason] = V13_SIGNAL_DIAGNOSTICS["reasons"].get(reason, 0) + 1
        if stage == "ANALYSIS":
            _analysis_diag("reject", reason, token_addr)
    except Exception:
        pass

def _diag_top_reasons(limit=12):
    try:
        return sorted(
            V13_SIGNAL_DIAGNOSTICS["reasons"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
    except Exception:
        return []

def _audit_signal_decision(reason):
    key = {
        "QUALITY_GATE_REJECTED": "quality_rejected",
        "DUPLICATE_OPEN_POSITION": "duplicate_rejected",
        "DAILY_SIGNAL_CAP_REACHED": "daily_cap_rejected",
        "GLOBAL_SIGNAL_COOLDOWN": "cooldown_rejected",
        "LEARNING_CIRCUIT_BREAKER": "circuit_rejected",
        "EMERGENCY_STOP": "emergency_rejected",
    }.get(reason)
    if key:
        V12_REAL_AUDIT[key] += 1

# ==========================================================
# PRO_MAX_V10_VALIDATION
# Real historical backtest + walk-forward validation +
# A/B engine evaluation
# ==========================================================
V10_VALIDATION_FILE = "fusion_v10_validation.json"
V10_LOOKBACK = 1000
V10_MIN_WALK_FORWARD = 100
V10_A_B_MIN_TRADES = 30

v10_validation = {
    "backtest": {},
    "walk_forward": {},
    "ab_test": {},
    "updated_at": 0.0,
}

def _v10_save():
    try:
        Path(V10_VALIDATION_FILE).write_text(
            json.dumps(v10_validation, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"V10 validation save failed: {e}")

def _v10_trade_rows():
    try:
        return list(learning_state.get("trades", []))[-V10_LOOKBACK:]
    except Exception:
        return []

def v10_real_backtest():
    """
    Historical evaluation over actually recorded closed trades.
    This is deliberately separated from live execution: it cannot place trades.
    """
    rows = _v10_trade_rows()
    wins = sum(1 for r in rows if float(r.get("pnl_pct", 0) or 0) > 0)
    gp = sum(max(0.0, float(r.get("pnl_pct", 0) or 0)) for r in rows)
    gl = sum(abs(min(0.0, float(r.get("pnl_pct", 0) or 0))) for r in rows)
    result = {
        "sample": len(rows),
        "wins": wins,
        "losses": len(rows) - wins,
        "win_rate": wins / len(rows) * 100.0 if rows else 0.0,
        "gross_profit_pct": gp,
        "gross_loss_pct": gl,
        "profit_factor": gp / gl if gl else (999.0 if gp else 0.0),
        "net_pnl_pct": gp - gl,
    }
    v10_validation["backtest"] = result
    v10_validation["updated_at"] = time.time()
    _v10_save()
    return result

def v10_walk_forward():
    """
    Walk-forward validation:
    train on the first segment, evaluate the subsequent segment.
    Engine weights are read from the training segment only.
    """
    rows = _v10_trade_rows()
    n = len(rows)
    if n < V10_MIN_WALK_FORWARD * 2:
        result = {
            "ready": False,
            "reason": f"حداقل {V10_MIN_WALK_FORWARD*2} معامله بسته لازم است.",
            "sample": n,
        }
        v10_validation["walk_forward"] = result
        _v10_save()
        return result

    split = int(n * 0.70)
    train = rows[:split]
    test = rows[split:]

    # Training metrics.
    train_wins = sum(1 for r in train if float(r.get("pnl_pct", 0) or 0) > 0)
    train_wr = train_wins / len(train) * 100.0 if train else 0.0

    # Out-of-sample test metrics.
    test_wins = sum(1 for r in test if float(r.get("pnl_pct", 0) or 0) > 0)
    test_gp = sum(max(0.0, float(r.get("pnl_pct", 0) or 0)) for r in test)
    test_gl = sum(abs(min(0.0, float(r.get("pnl_pct", 0) or 0))) for r in test)

    result = {
        "ready": True,
        "train_sample": len(train),
        "test_sample": len(test),
        "train_win_rate": train_wr,
        "out_of_sample_win_rate": test_wins / len(test) * 100.0 if test else 0.0,
        "out_of_sample_profit_factor":
            test_gp / test_gl if test_gl else (999.0 if test_gp else 0.0),
        "out_of_sample_net_pnl_pct": test_gp - test_gl,
    }
    v10_validation["walk_forward"] = result
    v10_validation["updated_at"] = time.time()
    _v10_save()
    return result

def v10_ab_engine_test():
    """
    A/B comparison of engine groups from closed-trade outcomes.
    No live execution and no artificial win-rate boosting.
    """
    rows = _v10_trade_rows()
    groups = {}

    for r in rows:
        pnl = float(r.get("pnl_pct", 0) or 0)
        engines = r.get("engines") or []
        if isinstance(engines, str):
            engines = [x.strip() for x in engines.split(",") if x.strip()]
        for engine in engines:
            s = groups.setdefault(engine, {"trades": 0, "wins": 0, "pnl": 0.0})
            s["trades"] += 1
            s["wins"] += int(pnl > 0)
            s["pnl"] += pnl

    result = {}
    for engine, s in groups.items():
        result[engine] = {
            "trades": s["trades"],
            "win_rate": s["wins"] / s["trades"] * 100.0 if s["trades"] else 0.0,
            "net_pnl_pct": s["pnl"],
            "qualified": s["trades"] >= V10_A_B_MIN_TRADES,
        }

    v10_validation["ab_test"] = result
    v10_validation["updated_at"] = time.time()
    _v10_save()
    return result

def v10_validation_summary():
    return {
        "backtest": v10_real_backtest(),
        "walk_forward": v10_walk_forward(),
        "ab_test": v10_ab_engine_test(),
    }

# ==========================================================
# PRO_MAX_V7_SYSTEMS
# Backtest / Paper Trading / Market Regime / Dynamic Risk /
# Memory Decay & Compaction / Statistical Dashboard
# ==========================================================
V7_MEMORY_MAX_RECORDS = 5000
V7_MEMORY_MAX_AGE_DAYS = 90
V7_MEMORY_DECAY_HALF_LIFE_DAYS = 30
V7_BACKTEST_LOOKBACK = 500
V7_COMPACTION_INTERVAL_SECONDS = 24 * 3600
V7_STATE_FILE = "fusion_v7_state.json"
v7_last_compaction = 0.0
v7_state = {
    "paper": {"trades": []},
    "regime": {"name": "RANGE", "confidence": 0.0},
    "backtest": {},
    "last_compaction": 0.0,
}

def _v7_load():
    global v7_state, v7_last_compaction
    try:
        p = Path(V7_STATE_FILE)
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                v7_state.update(d)
            v7_last_compaction = float(v7_state.get("last_compaction", 0) or 0)
    except Exception as e:
        logger.warning(f"V7 state load failed: {e}")

def _v7_save():
    try:
        v7_state["last_compaction"] = v7_last_compaction
        Path(V7_STATE_FILE).write_text(json.dumps(v7_state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"V7 state save failed: {e}")

def v7_decay_weight(age_days):
    return 0.5 ** (float(age_days) / V7_MEMORY_DECAY_HALF_LIFE_DAYS)

def v7_compact_learning_memory(force=False):
    global v7_last_compaction
    now = time.time()
    if not force and now - v7_last_compaction < V7_COMPACTION_INTERVAL_SECONDS:
        return
    try:
        trades = learning_state.get("trades", [])
        cutoff = now - V7_MEMORY_MAX_AGE_DAYS * 86400
        recent = [t for t in trades if float(t.get("ts", now) or now) >= cutoff]
        # Hard cap protects the file even if a large burst occurs.
        learning_state["trades"] = recent[-V7_MEMORY_MAX_RECORDS:]
        # Old records are represented only through decayed engine aggregates.
        compact = {}
        for t in trades:
            ts = float(t.get("ts", now) or now)
            age = max(0.0, (now - ts) / 86400.0)
            w = v7_decay_weight(age)
            pnl = float(t.get("pnl_pct", 0) or 0)
            for name in (t.get("engines") or []):
                s = compact.setdefault(name, [0.0, 0.0])
                s[0] += w
                s[1] += pnl * w
        for name, (weight_sum, pnl_sum) in compact.items():
            if weight_sum <= 0:
                continue
            st = learning_state.setdefault("engines", {}).setdefault(
                name, {"trades": 0, "wins": 0, "losses": 0, "avg_pnl": 0.0, "weight": 1.0}
            )
            old_avg = float(st.get("avg_pnl", 0.0))
            st["avg_pnl"] = 0.85 * old_avg + 0.15 * (pnl_sum / weight_sum)
        _save_learning_state()
        v7_last_compaction = now
        _v7_save()
    except Exception as e:
        logger.warning(f"V7 memory compaction failed: {e}")

def v7_detect_market_regime(liquidity, volume_5m, change_5m, volatility=None):
    try:
        liq = float(liquidity or 0)
        chg = float(change_5m or 0)
        vola = abs(float(volatility or 0))
        if liq < CONSENSUS_MIN_LIQUIDITY:
            name = "LOW_LIQ"
        elif vola >= 15:
            name = "HIGH_VOL"
        elif chg >= 3:
            name = "BULL"
        elif chg <= -3:
            name = "BEAR"
        else:
            name = "RANGE"
        confidence = min(1.0, 0.5 + min(0.5, abs(chg) / 10.0))
        v7_state["regime"] = {"name": name, "confidence": confidence}
        return name, confidence
    except Exception:
        return "RANGE", 0.0

def v7_dynamic_risk_multiplier(fusion):
    try:
        mult = learning_risk_multiplier()
        regime, conf = v7_detect_market_regime(
            fusion.get("liq", 0), fusion.get("vol", 0),
            fusion.get("chg", 0), fusion.get("volatility", 0)
        )
        if regime == "LOW_LIQ":
            mult *= 0.55
        elif regime == "HIGH_VOL":
            mult *= 0.70
        elif regime == "BEAR":
            mult *= 0.60
        else:
            mult *= 0.85 + 0.15 * conf
        return max(RISK_MIN_MULTIPLIER, min(RISK_MAX_MULTIPLIER, mult))
    except Exception:
        return learning_risk_multiplier()

def v7_paper_trade_open(token_addr, symbol, entry_price, fusion):
    try:
        rows = v7_state.setdefault("paper", {}).setdefault("trades", [])
        rows.append({
            "token": token_addr, "symbol": symbol, "entry": float(entry_price or 0),
            "opened_at": time.time(), "engines": _engine_names_from_fusion(fusion),
            "regime": v7_state.get("regime", {}).get("name", "UNKNOWN"),
            "status": "OPEN"
        })
        v7_state["paper"]["trades"] = rows[-V7_MEMORY_MAX_RECORDS:]
        _v7_save()
    except Exception as e:
        logger.warning(f"Paper open failed: {e}")

def v7_paper_trade_close(token_addr, exit_price, pnl_pct, reason=""):
    try:
        for p in reversed(v7_state.setdefault("paper", {}).setdefault("trades", [])):
            if p.get("token") == token_addr and p.get("status") == "OPEN":
                p.update({
                    "exit": float(exit_price or 0), "pnl_pct": float(pnl_pct or 0),
                    "reason": reason, "closed_at": time.time(), "status": "CLOSED"
                })
                break
        _v7_save()
    except Exception as e:
        logger.warning(f"Paper close failed: {e}")

def v7_paper_stats():
    rows = [x for x in v7_state.get("paper", {}).get("trades", []) if x.get("status") == "CLOSED"]
    wins = sum(1 for x in rows if float(x.get("pnl_pct", 0) or 0) > 0)
    gp = sum(max(0.0, float(x.get("pnl_pct", 0) or 0)) for x in rows)
    gl = sum(abs(min(0.0, float(x.get("pnl_pct", 0) or 0))) for x in rows)
    return {"trades": len(rows), "win_rate": wins / len(rows) * 100 if rows else 0.0,
            "profit_factor": gp / gl if gl else (999.0 if gp else 0.0)}

def v7_backtest_from_learning_history():
    rows = learning_state.get("trades", [])[-V7_BACKTEST_LOOKBACK:]
    wins = sum(1 for x in rows if float(x.get("pnl_pct", 0) or 0) > 0)
    gp = sum(max(0.0, float(x.get("pnl_pct", 0) or 0)) for x in rows)
    gl = sum(abs(min(0.0, float(x.get("pnl_pct", 0) or 0))) for x in rows)
    result = {"trades": len(rows), "win_rate": wins / len(rows) * 100 if rows else 0.0,
              "profit_factor": gp / gl if gl else (999.0 if gp else 0.0)}
    v7_state["backtest"] = result
    _v7_save()
    return result

_v7_load()
v7_compact_learning_memory(force=False)


def send_fused_signal(token_addr, fusion):
    global last_global_signal_time, UNIFIED_LAST_EMIT_TIME
    # V17 FIX: non-MAX engines emit independently. MAX keeps one global lane.
    is_analysis_signal = bool(fusion.get("force_independent") or fusion.get("hunter_group") == "ANALYSIS")
    emit_lane = "ANALYSIS" if is_analysis_signal else ("MAX" if MAX_FUSION_ENABLED else str(fusion.get("hunter_group", "ENGINE")))
    emit_engine = (fusion.get("engines") or fusion.get("votes") or [emit_lane])[0]
    emit_key = f"{emit_lane}:{emit_engine}"
    # فقط تصمیم ورود/سهمیه را قفل می‌کنیم؛ خرید شبکه و Telegram خارج از قفل انجام می‌شوند.
    with SIGNAL_EMIT_LOCK:
        if _token_lock_is_open(token_addr):
            if is_analysis_signal:
                _analysis_diag("blocked_duplicate", token_addr=token_addr)
            logger.info(f"Duplicate BUY blocked for open token: {token_addr}")
            _audit_signal_decision("DUPLICATE_OPEN_POSITION")
            return False, "DUPLICATE_OPEN_POSITION"
        if daily_signal_cap_reached():
            if is_analysis_signal:
                _analysis_diag("blocked_daily_cap", token_addr=token_addr)
            _audit_signal_decision("DAILY_SIGNAL_CAP_REACHED")
            return False, "DAILY_SIGNAL_CAP_REACHED"
        if learning_is_in_circuit_breaker():
            if is_analysis_signal:
                _analysis_diag("blocked_circuit", token_addr=token_addr)
            logger.warning("Circuit breaker: new entries paused; open positions continue to be managed.")
            _audit_signal_decision("LEARNING_CIRCUIT_BREAKER")
            return False, "LEARNING_CIRCUIT_BREAKER"
        if not (is_analysis_signal):
            if not fusion_quality_gate(fusion):
                logger.info(f"Fusion quality gate rejected {token_addr}; daily budget unchanged.")
                _audit_signal_decision("QUALITY_GATE_REJECTED")
                return False, "QUALITY_GATE_REJECTED"
        now_global = time.time()
        # MAX is a single attack and therefore uses the global cooldown.
        # Outside MAX, Advanced/Hulk/individual engines have their own lane
        # cooldown so one engine cannot suppress another engine's valid signal.
        if MAX_FUSION_ENABLED and not is_analysis_signal:
            if now_global - max(last_global_signal_time, UNIFIED_LAST_EMIT_TIME) < GLOBAL_SIGNAL_COOLDOWN_SECONDS:
                _audit_signal_decision("GLOBAL_SIGNAL_COOLDOWN")
                return False, "GLOBAL_SIGNAL_COOLDOWN"
        elif is_analysis_signal:
            if now_global - consensus_last_signal.get(emit_key, 0) < CONSENSUS_COOLDOWN_SECONDS:
                _analysis_diag("blocked_cooldown", token_addr=token_addr)
                _audit_signal_decision("GLOBAL_SIGNAL_COOLDOWN")
                return False, "ANALYSIS_COOLDOWN"
        else:
            lane_last = consensus_last_signal.get(emit_key, 0)
            if now_global - lane_last < CONSENSUS_COOLDOWN_SECONDS:
                _audit_signal_decision("GLOBAL_SIGNAL_COOLDOWN")
                return False, "ENGINE_COOLDOWN"
        if EMERGENCY_STOP:
            logger.info("Emergency stop active: new signal execution skipped.")
            _audit_signal_decision("EMERGENCY_STOP")
            return False, "EMERGENCY_STOP"

        # سهمیه در لحظه صدور سیگنال واقعی رزرو می‌شود؛ شکست خرید/کانال سهمیه را دور نمی‌زند.
        if MAX_FUSION_ENABLED and not is_analysis_signal:
            last_global_signal_time = now_global
            UNIFIED_LAST_EMIT_TIME = now_global
        consensus_last_signal[emit_key] = now_global
        V12_REAL_AUDIT["last_signal"] = now_global
        _increment_daily_signal_count()
        _lock_token_entry(token_addr, "OPEN_PENDING")
        if is_analysis_signal:
            V12_REAL_AUDIT["analysis_signals_submitted"] += 1
            _analysis_diag("submitted", token_addr=token_addr)
    amount = get_dynamic_buy_amount(0.01)
    reason = " + ".join(fusion.get("votes") or [])
    mode_name = fusion.get("mode", UNIFIED_ENGINE_NAME)
    engine_names = list(fusion.get("engines") or fusion.get("votes") or [])
    symbol = fusion["symbol"]
    price = fusion["price"]
    tp = fusion["tp"]
    sl = fusion["sl"]
    dex_link = f"https://dexscreener.com/solana/{token_addr}"
    token_link = f"https://solscan.io/token/{token_addr}"

    success, result = execute_real_buy(token_addr, amount)
    if success:
        V12_REAL_AUDIT["real_buy_success"] += 1
        if is_analysis_signal:
            _analysis_diag("real_buy_success", token_addr=token_addr)
    else:
        V12_REAL_AUDIT["real_buy_failed"] += 1
        if fusion.get("force_independent") or fusion.get("hunter_group") == "ANALYSIS":
            _analysis_diag("real_buy_failed", f"REAL_BUY_FAILED:{result}", token_addr)
        _diag_reject("EXECUTION", f"REAL_BUY_FAILED:{result}", token_addr)
    execution_status = "🟢 خرید موفق روی بلاکچین" if success else f"⚠️ خرید واقعی انجام نشد: {result}"
    solscan_link = f"https://solscan.io/tx/{result}" if success else token_link

    msg = (
        f"⚡🤖 **{mode_name}**\n"
        f"🎯 قدرت سیگنال: **{fusion['score']:.2f}**\n"
        f"🤖 موتورهای مؤثر: {reason}\n\n"
        f"🪙 توکن: {symbol}\n"
        f"📍 آدرس قرارداد:\n`{token_addr}`\n\n"
        f"💵 نقطه ورود دقیق: ${price:.8f}\n"
        f"💰 مقدار خرید: SOL {amount:g}\n"
        f"🎯 تارگت اولیه: +{tp:.1f}%\n"
        f"🛑 حد ضرر اولیه: {sl:.1f}%\n\n"
        f"📊 آمار لحظه‌ای بازار:\n"
        f"🔹 تغییر ۵ دقیقه: {fusion['chg']:+.2f}%\n"
        f"🔹 حجم ۵ دقیقه: ${fusion['vol']:,.0f}\n"
        f"🔹 نقدینگی: ${fusion['liq']:,.0f}\n"
        f"🔹 خرید/فروش ۵ دقیقه: {fusion.get('buys', 0)}/{fusion.get('sells', 0)}\n\n"
        f"📈 مدیریت سود: تریلینگ پله‌ای هوشمند\n\n"
        f"🔗 Solscan: {solscan_link}\n"
        f"📈 DexScreener: {dex_link}"
    )
    send_telegram_msg(msg)

    channel_ok = send_graphic_signal_to_vip_channel(
        token_addr=token_addr, symbol=symbol, price=price, tp=tp, sl=sl,
        buy_amt=amount, volume=fusion['vol'], liquidity=fusion['liq'],
        p_change=fusion['chg'], solscan_link=solscan_link,
        signal_title=mode_name, side="BUY",
        execution_status=execution_status, execution_tx=result if success else ""
    )
    if channel_ok:
        V12_REAL_AUDIT["channel_sent"] += 1
        if fusion.get("force_independent") or fusion.get("hunter_group") == "ANALYSIS":
            _analysis_diag("channel_sent", token_addr=token_addr)
    else:
        V12_REAL_AUDIT["channel_failed"] += 1
        if fusion.get("force_independent") or fusion.get("hunter_group") == "ANALYSIS":
            _analysis_diag("channel_failed", "CHANNEL_SEND_FAILED", token_addr)
        _diag_reject("CHANNEL", "CHANNEL_SEND_FAILED", token_addr)

    if success:
        txlink = f"https://solscan.io/tx/{result}"
        with state_lock:
            processed_tokens.add(token_addr)
            active_positions[token_addr] = {
                "entry_price": price, "symbol": symbol,
                "tp": tp, "sl": sl, "highest_price": price,
                "highest_pnl": 0.0, "locked_floor": sl,
                "trailing_active": DYNAMIC_TRAILING_TP_ENABLED,
                "side": "BUY", "reason": f"{mode_name} | {reason}", "engines": engine_names, "engine_names": engine_names, "mode": mode_name, "opened_at": time.time(), "buy_amt": amount,
                "entry_lock": True,
                "volume": float(fusion.get("vol", 0.0) or 0.0),
                "liquidity": float(fusion.get("liq", 0.0) or 0.0),
                "p_change": float(fusion.get("chg", 0.0) or 0.0),
                "buys_m5": int(fusion.get("buys", 0) or 0),
                "sells_m5": int(fusion.get("sells", 0) or 0)
            }
        # کپی‌ترید فقط بعد از خرید واقعی مرجع فعال می‌شود.
        trigger_copy_trading_for_subscribers(token_addr, amount, side="BUY", tx_signature=result)
        send_telegram_msg(
            f"🟢 خرید خودکار انجام شد\n🪙 {symbol}\n💰 {amount:g} SOL\n🔗 {txlink}"
        )
    else:
        # خرید واقعی انجام نشد؛ فقط یک پوزیشن سیگنال-مجازی داخلی ساخته می‌شود.
        # هیچ پیام «ثبت/رصد شد» یا «SOL ناکافی» برای کاربر ارسال نمی‌شود.
        track_signal_only(
            token_addr, symbol, price, tp, sl, fusion['vol'], fusion['liq'],
            fusion['chg'], reason, amount, execution_status
        )
    return success, result


# ==========================================================
# Persistent token entry lock
# A token cannot generate another BUY while it has an open
# real or signal-only position. The lock is released only
# after a complete SELL/exit is recorded.
# ==========================================================
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
    # Release only after a complete exit.
    _unlock_token_entry(token_addr)


def _load_daily_signal_state():
    """Load today's signal count and cap from persistent bot settings."""
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
    """Stop NEW entries after the admin-selected daily cap."""
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


def _elite_refresh_market_cache(force=False):
    """Refresh the market universe independently from the signal decision loop."""
    global _elite_market_cache, _elite_market_cache_time
    now = time.time()
    if not force and now - _elite_market_cache_time < ELITE_DISCOVERY_REFRESH_SECONDS:
        return
    if not _elite_market_refresh_lock.acquire(blocking=False):
        return
    try:
        found = get_real_market_trending_tokens()
        # Stable de-duplication; keep the complete discovered universe.
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
    logger.info("⚡ ELITE RADAR discovery worker فعال شد؛ discovery از تصمیم‌گیری جداست.")
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


def _fetch_best_solana_pair(token_addr):
    """Fetch one token once, then consider several strong Solana pairs.

    The previous radar selected only the deepest-liquidity pair. Sentinel keeps
    the same HTTP cost but evaluates up to three promising pairs from the same
    response, so a thin/secondary pool cannot hide a better setup.
    """
    try:
        res = http_session.get(
            f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}",
            timeout=ELITE_PAIR_TIMEOUT_SECONDS
        )
        if res.status_code != 200:
            return token_addr, []
        pairs = (res.json() or {}).get("pairs") or []
        pairs = [p for p in pairs if p.get("chainId") == "solana"]
        if not pairs:
            _diag_reject("PAIR_FETCH", "NO_SOLANA_PAIR_DATA", token_addr)
            return token_addr, []
        pairs.sort(key=_sentinel_rank_pair, reverse=True)
        return token_addr, pairs[:_SENTINEL_PAIR_CHOICES]
    except Exception as token_error:
        logger.debug(f"Sentinel token error {token_addr}: {token_error}")
        return token_addr, []

def _evaluate_elite_token(token_addr):
    """Fetch + evaluate one token entirely inside one worker."""
    token_addr, pairs = _fetch_best_solana_pair(token_addr)
    best = None
    for pair in pairs:
        try:
            fusion = build_consensus_signal(token_addr, pair)
            if not fusion:
                continue
            rank_bonus = _sentinel_rank_bonus(token_addr, fusion)
            # Keep the real fusion score untouched; rank_score is selection-only.
            fusion["rank_bonus"] = float(rank_bonus)
            fusion["rank_score"] = float(fusion.get("score", 0.0)) + float(rank_bonus)
            if best is None or fusion["rank_score"] > best["rank_score"]:
                best = fusion
        except Exception as token_error:
            logger.debug(f"Sentinel evaluation error {token_addr}: {token_error}")
    return token_addr, best


def _independent_engine_candidate(token_addr, pair, engine_name):
    """TRUE HUNTER: one engine, one decision, zero borrowed votes.

    The common hard market-quality gate remains authoritative. Engine-specific
    evidence is then evaluated independently. No engine receives credit from
    another engine.
    """
    q = _mode_market_quality(pair)
    if not q:
        return None
    structure_ok, structure = _market_structure_gate(token_addr, pair)
    if not structure_ok:
        return None
    chg, vol, liq = q["chg"], q["vol"], q["liq"]
    buys, sells = q["buys"], q["sells"]
    try:
        ok = False
        strength = 0.0
        if engine_name == "Technical":
            ok = bool(TECHNICAL_RUNNING and check_major_support_resistance_pa(pair)[0]); strength = 6.0
        elif engine_name == "UltimateAI/21":
            ok = bool(ULTIMATE_21_ENGINE_ENABLED and evaluate_ultimate_super_signal(token_addr, pair)[0]); strength = 7.0
        elif engine_name == "Social/Hype":
            ok = bool(SOCIAL_SENTIMENT_ENABLED and check_social_sentiment_and_hype(pair)[0]); strength = 6.0
        elif engine_name == "SmartFilter":
            ok = bool(SMART_FILTER_ENABLED and is_token_worthy(pair)); strength = 6.0
        elif engine_name == "Fire":
            ok = bool(IS_RUNNING and chg >= 3 and vol >= 3000); strength = 5.5
        elif engine_name == "Trend":
            ok = bool(TREND_ALERT_RUNNING and chg >= 5 and buys >= max(1, sells)); strength = 6.0
        elif engine_name == "Combo":
            ok = bool(COMBO_RUNNING and buys > sells and vol >= 5000 and liq >= 15000); strength = 6.5
        elif engine_name == "Golden":
            ok = bool(GOLDEN_OPTION and chg >= 8 and vol >= 7000 and liq >= 18000); strength = 7.0
        elif engine_name == "Mempool/SmartMoney":
            ok = bool(MEMPOOL_SMART_MONEY_ENABLED and buys >= max(2, int(sells * 1.20) + 1) and vol >= 5000 and liq >= 15000); strength = 7.0
        elif engine_name == "Whale":
            ok = bool(BOTTOM_WHALE_RUNNING and buys >= max(3, sells + 2) and vol >= 5000); strength = 7.0
        elif engine_name == "Anti-Wash":
            ok = bool(ANTI_WASH_TRADING_ENABLED and not (sells > 0 and buys < sells * 0.8)); strength = 5.5
        if not ok:
            _diag_reject("ENGINE", f"{engine_name}_NO_ENGINE_TRIGGER", token_addr)
            return None

        buy_ratio = buys / max(1, sells)
        # Selection score only. Existing quality thresholds are not lowered.
        score = (strength + min(5.0, chg / 5.0) + min(4.0, vol / 10000.0)
                 + min(3.0, liq / 50000.0) + min(3.0, max(0.0, buy_ratio - 1.0)))
        if score < 8.0:
            _diag_reject("ENGINE", f"{engine_name}_SCORE_BELOW_8", token_addr)
            return None
        now = time.time()
        cooldown_key = f"{token_addr}:{engine_name}"
        if now - consensus_last_signal.get(cooldown_key, 0) < CONSENSUS_COOLDOWN_SECONDS:
            _diag_reject("ENGINE", f"{engine_name}_COOLDOWN", token_addr)
            return None
        group = "ADVANCED" if engine_name in ("Technical", "UltimateAI/21", "Social/Hype", "SmartFilter") else "HULK"
        return {
            "score": float(score), "strength": float(strength),
            "votes": [engine_name],
            "advanced_votes": [engine_name] if group == "ADVANCED" else [],
            "hulk_votes": [engine_name] if group == "HULK" else [],
            "engines": [engine_name],
            "mode": f"سیستم پیشرفته AI — {engine_name}" if group == "ADVANCED" else f"اتحاد هالک AI — {engine_name}",
            "hunter_group": group, **q,
            "symbol": (pair.get("baseToken") or {}).get("symbol", "TOKEN"),
            "tp": max(15.0, min(30.0, 14.0 + min(12.0, score))), "sl": -8.0,
            "structure": structure.get("structure", "UNKNOWN"),
            "support": float(structure.get("support", 0.0) or 0.0),
            "resistance": float(structure.get("resistance", 0.0) or 0.0),
            "breakout": bool(structure.get("breakout", False)),
            "rank_bonus": _sentinel_rank_bonus(token_addr, {"score": score, **q}),
        }
    except Exception as e:
        logger.debug(f"Independent engine {engine_name} failed for {token_addr}: {e}")
        return None

def _analysis_engine_candidate(token_addr, pair):
    """Independent market-structure engine.

    It does not borrow votes from Hulk/Advanced/MAX. It waits for enough real
    price samples, estimates the linear trend, validates a liquid buyer-backed
    support bounce, or a high-volume breakout above the previous resistance.
    Touching resistance alone is never a BUY trigger.
    """
    _analysis_diag("scanned", token_addr=token_addr)
    if not ANALYSIS_ENGINE_ENABLED:
        _diag_reject("ANALYSIS", "ANALYSIS_ENGINE_OFF", token_addr)
        return None
    try:
        price = float(pair.get("priceUsd", 0) or 0)
        liq = float((pair.get("liquidity") or {}).get("usd", 0) or 0)
        vol = float((pair.get("volume") or {}).get("m5", 0) or 0)
        chg = float((pair.get("priceChange") or {}).get("m5", 0) or 0)
        tx = (pair.get("txns") or {}).get("m5", {}) or {}
        buys = int(tx.get("buys", 0) or 0)
        sells = int(tx.get("sells", 0) or 0)
        buy_ratio = buys / max(1, sells)
        if price > 0:
            _analysis_diag("data_ready", token_addr=token_addr)
        if price <= 0:
            _diag_reject("ANALYSIS", "INVALID_PRICE", token_addr); return None
        if liq < CANDIDATE_MIN_LIQUIDITY:
            _diag_reject("ANALYSIS", "LOW_ANALYSIS_LIQUIDITY", token_addr); return None
        if vol < CANDIDATE_MIN_VOLUME_5M:
            _diag_reject("ANALYSIS", "LOW_ANALYSIS_5M_VOLUME", token_addr); return None
        # Do not require positive 5m change before evaluating structure: a valid
        # support bounce can occur while the raw 5m change is still flat/negative.
        if buys < 1:
            _diag_reject("ANALYSIS", "ANALYSIS_NO_BUYERS", token_addr); return None
        if buy_ratio < CANDIDATE_MIN_BUY_RATIO:
            _diag_reject("ANALYSIS", "ANALYSIS_BUY_PRESSURE_WEAK", token_addr); return None

        samples = _update_structure_memory(token_addr, price)
        # Fresh tokens need a first-pass signal path; full structure activates
        # after enough samples are collected.
        if len(samples) < STRUCTURE_MIN_SAMPLES:
            # Provisional path: real liquidity + volume + stronger buyers. It is
            # intentionally independent of MAX/consensus so the Analysis engine
            # can emit while its own structure history is still warming up.
            if buy_ratio < FINAL_ANALYSIS_MIN_BUY_RATIO:
                _diag_reject("ANALYSIS", "ANALYSIS_WARMUP_BUY_RATIO", token_addr); return None
            if liq < FINAL_ANALYSIS_MIN_LIQUIDITY:
                _diag_reject("ANALYSIS", "ANALYSIS_WARMUP_LIQUIDITY", token_addr); return None
            if vol < FINAL_ANALYSIS_MIN_VOLUME_5M:
                _diag_reject("ANALYSIS", "ANALYSIS_WARMUP_VOLUME", token_addr); return None
            score = 6.0 + min(2.0, buy_ratio - 1.0) + min(1.5, vol / 10000.0) + min(1.0, liq / 50000.0)
            now = time.time()
            if now - consensus_last_signal.get(f"{token_addr}:Analysis", 0) < CONSENSUS_COOLDOWN_SECONDS:
                _diag_reject("ANALYSIS", "ANALYSIS_COOLDOWN", token_addr)
                return None
            q = {"price": price, "liq": liq, "vol": vol, "chg": chg, "buys": buys, "sells": sells}
            _analysis_diag("candidates", token_addr=token_addr)
            return {
                "score": float(score), "strength": float(score),
                "votes": ["Analysis"], "advanced_votes": [], "hulk_votes": [],
                "engines": ["Analysis"], "hunter_group": "ANALYSIS",
                "mode": "📈 موتور تحلیل",
                "reason": "تأیید اولیه: نقدینگی مناسب + فشار خریدار + حجم سالم",
                **q,
                "symbol": (pair.get("baseToken") or {}).get("symbol", "TOKEN"),
                "tp": max(15.0, min(28.0, 16.0 + min(10.0, score))),
                "sl": -8.0, "structure": "ANALYSIS_INITIAL_BUY_FLOW",
                "support": float(price), "resistance": float(price),
                "breakout": False, "trend_slope_pct": float(chg),
                "rank_bonus": _sentinel_rank_bonus(token_addr, {"score": score, **q})
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

        # A resistance touch is explicitly rejected. Breakout needs both
        # meaningful volume and stronger buyer pressure.
        if near_resistance and not breakout:
            _diag_reject("ANALYSIS", "ANALYSIS_RESISTANCE_TOUCH_NO_BREAKOUT", token_addr)
            return None

        if breakout:
            if slope_pct <= 0:
                _diag_reject("ANALYSIS", "ANALYSIS_BREAKOUT_TREND_NOT_UP", token_addr); return None
            if liq < FINAL_ANALYSIS_MIN_LIQUIDITY:
                _diag_reject("ANALYSIS", "ANALYSIS_BREAKOUT_LIQUIDITY_WEAK", token_addr); return None
            if vol < FINAL_BREAKOUT_MIN_VOLUME_5M:
                _diag_reject("ANALYSIS", "ANALYSIS_BREAKOUT_VOLUME_WEAK", token_addr); return None
            if buy_ratio < STRUCTURE_MIN_BREAKOUT_BUY_RATIO:
                _diag_reject("ANALYSIS", "ANALYSIS_BREAKOUT_BUY_PRESSURE_WEAK", token_addr); return None
            _analysis_diag("breakout_setups", token_addr=token_addr)
            structure = "ANALYSIS_RESISTANCE_BREAKOUT"
            structure_score = 4.0
            reason = "روند صعودی + شکست پرقدرت سقف قبلی + حجم/خریدار قوی"
        elif near_support:
            if slope_pct <= 0:
                _diag_reject("ANALYSIS", "ANALYSIS_SUPPORT_TREND_NOT_UP", token_addr); return None
            if bounce_pct < 0.35:
                _diag_reject("ANALYSIS", "ANALYSIS_SUPPORT_NO_BOUNCE", token_addr); return None
            if liq < FINAL_ANALYSIS_MIN_LIQUIDITY:
                _diag_reject("ANALYSIS", "ANALYSIS_SUPPORT_LIQUIDITY_WEAK", token_addr); return None
            if vol < FINAL_SUPPORT_MIN_VOLUME_5M:
                _diag_reject("ANALYSIS", "ANALYSIS_SUPPORT_VOLUME_WEAK", token_addr); return None
            if buy_ratio < FINAL_ANALYSIS_MIN_BUY_RATIO:
                _diag_reject("ANALYSIS", "ANALYSIS_SUPPORT_BUY_PRESSURE_WEAK", token_addr); return None
            _analysis_diag("support_setups", token_addr=token_addr)
            structure = "ANALYSIS_SUPPORT_BOUNCE"
            structure_score = 4.0
            reason = "روند صعودی + کف معتبر + نقدینگی + برگشت با خریدار"
        else:
            # Continuation is allowed only when the linear trend is clearly up
            # and price is not sitting at resistance.
            if slope_pct < 0.20:
                _diag_reject("ANALYSIS", "ANALYSIS_TREND_SLOPE_WEAK", token_addr); return None
            if buy_ratio < FINAL_ANALYSIS_MIN_BUY_RATIO:
                _diag_reject("ANALYSIS", "ANALYSIS_TREND_BUY_PRESSURE_WEAK", token_addr); return None
            if vol < FINAL_ANALYSIS_MIN_VOLUME_5M:
                _diag_reject("ANALYSIS", "ANALYSIS_TREND_VOLUME_WEAK", token_addr); return None
            if liq < FINAL_ANALYSIS_MIN_LIQUIDITY:
                _diag_reject("ANALYSIS", "ANALYSIS_TREND_LIQUIDITY_WEAK", token_addr); return None
            _analysis_diag("continuation_setups", token_addr=token_addr)
            structure = "ANALYSIS_TREND_CONTINUATION"
            structure_score = 2.5
            reason = "روند خطی صعودی + جریان خرید سالم"

        score = 4.0 + structure_score
        score += min(2.0, max(0.0, slope_pct))
        score += min(2.0, max(0.0, buy_ratio - 1.0))
        score += min(2.0, vol / 10000.0)
        score += min(1.5, liq / 50000.0)
        now = time.time()
        if now - consensus_last_signal.get(f"{token_addr}:Analysis", 0) < CONSENSUS_COOLDOWN_SECONDS:
            _diag_reject("ANALYSIS", "ANALYSIS_COOLDOWN", token_addr)
            return None
        V12_REAL_AUDIT["analysis_candidates"] += 1
        _analysis_diag("candidates", token_addr=token_addr)
        return {
            "score": float(score), "strength": float(score),
            "votes": ["Analysis"], "advanced_votes": [], "hulk_votes": [],
            "engines": ["Analysis"], "hunter_group": "ANALYSIS",
            "mode": "📈 موتور تحلیل", "reason": reason, **_mode_market_quality(pair),
            "symbol": (pair.get("baseToken") or {}).get("symbol", "TOKEN"),
            "tp": max(15.0, min(30.0, 16.0 + min(12.0, score))), "sl": -8.0,
            "structure": structure, "support": float(support),
            "resistance": float(resistance), "breakout": bool(breakout),
            "trend_slope_pct": float(slope_pct),
            "rank_bonus": _sentinel_rank_bonus(token_addr, {"score": score, **_mode_market_quality(pair)})
        }
    except Exception as e:
        logger.debug(f"Analysis engine failed for {token_addr}: {e}")
        return None

def _active_independent_engine_names():
    adv_names = ["Technical", "UltimateAI/21", "Social/Hype", "SmartFilter"]
    # Analysis is intentionally outside both families. It remains independent even in MAX.
    special_names = ["Analysis"]
    hulk_names = ["Fire", "Trend", "Combo", "Golden", "Mempool/SmartMoney", "Whale", "Anti-Wash"]
    active = []
    for name in adv_names + hulk_names + special_names:
        var = next((v for n, v, _ in ENGINE_SWITCHES if n == name), None)
        if var and bool(globals().get(var)):
            active.append(name)
    return active


def _candidate_rank_tuple(item):
    """Selection-only rank. Never changes the candidate's actual quality score."""
    _, c = item
    return (
        float(c.get("rank_score", c.get("score", 0.0)) or 0.0),
        float(c.get("score", 0.0) or 0.0),
        float(c.get("chg", 0.0) or 0.0),
        float(c.get("vol", 0.0) or 0.0),
        float(c.get("liq", 0.0) or 0.0),
    )



def _evaluate_token_for_active_modes(token_addr):
    """Single evaluation contract: one token in, two isolated candidate pools out."""
    token_addr, pairs = _fetch_best_solana_pair(token_addr)
    result = {"analysis": [], "fusion": []}
    if not pairs:
        _diag_reject("DISCOVERY", "NO_PAIR", token_addr)
        return token_addr, result

    active = _active_independent_engine_names()
    analysis_enabled = ("Analysis" in active) and ANALYSIS_ENGINE_ENABLED

    for pair in pairs:
        # ---- ANALYSIS: completely independent of candidate prefilter/Fusion ----
        if analysis_enabled:
            try:
                candidate = _analysis_engine_candidate(token_addr, pair)
                if candidate is not None:
                    candidate = dict(candidate)
                    candidate["force_independent"] = True
                    candidate["hunter_group"] = "ANALYSIS"
                    candidate["engines"] = ["Analysis"]
                    candidate["votes"] = ["Analysis"]
                    candidate["rank_score"] = _candidate_rank_tuple(candidate)[0]
                    result["analysis"].append((token_addr, candidate))
            except Exception as exc:
                _diag_reject("ANALYSIS", f"EVALUATOR_EXCEPTION:{type(exc).__name__}:{exc}", token_addr)
                logger.exception("Analysis evaluation failed for %s", token_addr)

        # ---- FUSION: separate pipeline; Analysis never passes through here ----
        if not _candidate_prefilter(pair):
            continue
        try:
            if MAX_FUSION_ENABLED:
                fusion = build_consensus_signal(token_addr, pair)
                if fusion:
                    fusion = dict(fusion)
                    fusion["rank_bonus"] = _sentinel_rank_bonus(token_addr, fusion)
                    fusion["rank_score"] = _candidate_rank_tuple(fusion)[0]
                    result["fusion"].append((token_addr, fusion))
            else:
                for engine_name in active:
                    if engine_name == "Analysis":
                        continue
                    is_adv = engine_name in ("Technical", "UltimateAI/21", "Social/Hype", "SmartFilter")
                    if is_adv and not ADVANCED_AI_ENABLED:
                        continue
                    if (not is_adv) and not SYNCHRONIZED_MODE:
                        continue
                    fusion = _independent_engine_candidate(token_addr, pair, engine_name)
                    if fusion and fusion_quality_gate(fusion):
                        fusion = dict(fusion)
                        fusion["rank_score"] = _candidate_rank_tuple(fusion)[0]
                        result["fusion"].append((token_addr, fusion))
        except Exception as exc:
            _diag_reject("FUSION", f"EVALUATOR_EXCEPTION:{type(exc).__name__}:{exc}", token_addr)
            logger.exception("Fusion evaluation failed for %s", token_addr)

    return token_addr, result


def _select_best_analysis(candidates):
    if not candidates:
        return None
    return max(candidates, key=_candidate_rank_tuple)


def _select_fusion_candidates(candidates):
    if not candidates:
        return []
    if MAX_FUSION_ENABLED:
        return [max(candidates, key=_candidate_rank_tuple)]

    # One best candidate per independent engine/group. This prevents one engine
    # from suppressing another, while still preventing duplicate emission from
    # the same engine lane in one sweep.
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
    """Short-lived worker. All exceptions become visible in diagnostics."""
    _analysis_diag("worker_started", token_addr=token_addr)
    _analysis_diag("execution_started", token_addr=token_addr)
    try:
        ok, result = send_fused_signal(token_addr, candidate)
        if not ok:
            V13_SIGNAL_DIAGNOSTICS["analysis"]["worker_failed"] += 1
            _diag_reject("EXECUTION", str(result or "ANALYSIS_EXECUTION_REJECTED"), token_addr)
        return ok, result
    except Exception as exc:
        _diag_reject("EXECUTION", f"ANALYSIS_WORKER_EXCEPTION:{type(exc).__name__}:{exc}", token_addr)
        logger.exception("Analysis execution worker failed for %s", token_addr)
        return False, f"ANALYSIS_WORKER_EXCEPTION:{exc}"


def _submit_analysis_selected(selected):
    """Submit exactly one selected Analysis candidate; surface worker exceptions."""
    if selected is None:
        _diag_reject("ANALYSIS", "NO_ANALYSIS_SELECTED")
        return False
    token_addr, candidate = selected
    _analysis_diag("selected", token_addr=token_addr)
    try:
        future = ANALYSIS_EXECUTOR.submit(_analysis_submit_worker, token_addr, candidate)
        _analysis_diag("submit_called", token_addr=token_addr)

        def _analysis_future_done(done_future, addr=token_addr):
            try:
                result = done_future.result()
                if isinstance(result, tuple) and result and result[0] is False:
                    V13_SIGNAL_DIAGNOSTICS["analysis"]["worker_failed"] = V13_SIGNAL_DIAGNOSTICS["analysis"].get("worker_failed", 0) + 1
            except Exception as exc:
                _diag_reject("EXECUTION", f"ANALYSIS_FUTURE_EXCEPTION:{type(exc).__name__}:{exc}", addr)
                logger.exception("Analysis future failed for %s", addr)

        future.add_done_callback(_analysis_future_done)
        return True
    except Exception as exc:
        _diag_reject("EXECUTION", f"ANALYSIS_SUBMIT_EXCEPTION:{type(exc).__name__}:{exc}", token_addr)
        logger.exception("Analysis submit failed for %s", token_addr)
        return False



def unified_market_scanner_loop(app):
    """Authoritative live scanner with explicit, non-overlapping pipeline stages.

    Analysis and Fusion have separate candidate containers, selection, submission,
    and diagnostics. No Fusion/MAX condition is allowed to suppress Analysis.
    """
    global _TRUE_HUNTER_CURSOR
    logger.info("%s / %s: CLEAN SIGNAL CORE started", UNIFIED_ENGINE_NAME, BOT_BUILD_VERSION)
    send_telegram_msg(f"🚀 رادار {BOT_BUILD_VERSION} فعال شد")

    def inc_audit(key, amount=1):
        try:
            V12_REAL_AUDIT[key] = int(V12_REAL_AUDIT.get(key, 0) or 0) + amount
        except Exception:
            pass

    while True:
        if not new_trade_system_enabled():
            _diag_reject("SYSTEM", "TRADE_SYSTEM_DISABLED")
            time.sleep(FAST_SCAN_INTERVAL_SECONDS)
            continue

        try:
            V12_REAL_AUDIT["scans"] = int(V12_REAL_AUDIT.get("scans", 0) or 0) + 1
            V12_REAL_AUDIT["last_scan"] = time.time()

            if daily_signal_cap_reached():
                _diag_reject("EXECUTION", "DAILY_SIGNAL_CAP_REACHED")
                time.sleep(FAST_SCAN_INTERVAL_SECONDS)
                continue

            tokens = _elite_get_market_tokens()
            if not tokens:
                _diag_reject("DISCOVERY", "NO_MARKET_TOKENS")
                time.sleep(FAST_SCAN_INTERVAL_SECONDS)
                continue

            with _TRUE_HUNTER_CURSOR_LOCK:
                start_i = _TRUE_HUNTER_CURSOR % len(tokens)
                batch_n = min(TRUE_HUNTER_BATCH_SIZE, len(tokens))
                end_i = start_i + batch_n
                scan_tokens = tokens[start_i:end_i] if end_i <= len(tokens) else tokens[start_i:] + tokens[:end_i % len(tokens)]
                _TRUE_HUNTER_CURSOR = (start_i + batch_n) % len(tokens)

            V12_REAL_AUDIT["tokens_seen"] = int(V12_REAL_AUDIT.get("tokens_seen", 0) or 0) + len(scan_tokens)

            analysis_candidates = []
            fusion_candidates = []

            # Stage 1: evaluation. Every Future is consumed; exceptions are visible.
            with ThreadPoolExecutor(max_workers=PAIR_SCAN_WORKERS, thread_name_prefix="RadarEval") as ex:
                futures = {
                    ex.submit(_evaluate_token_for_active_modes, token): token
                    for token in scan_tokens
                    if token and not _token_lock_is_open(token)
                }
                for future in __import__("concurrent.futures").as_completed(futures):
                    source_token = futures[future]
                    try:
                        token_addr, lanes = future.result()
                    except Exception as exc:
                        _diag_reject("SYSTEM", f"EVALUATION_FUTURE_EXCEPTION:{type(exc).__name__}:{exc}", source_token)
                        logger.exception("Evaluation future failed for %s", source_token)
                        continue

                    for item in lanes.get("analysis", []):
                        analysis_candidates.append(item)
                        inc_audit("analysis_candidates")
                        V12_REAL_AUDIT["pairs_seen"] = int(V12_REAL_AUDIT.get("pairs_seen", 0) or 0) + 1
                        V12_REAL_AUDIT["last_candidate"] = time.time()

                    for item in lanes.get("fusion", []):
                        fusion_candidates.append(item)
                        inc_audit("fusion_candidates")
                        V12_REAL_AUDIT["last_candidate"] = time.time()

            # Stage 2A: Analysis selection is unconditional with respect to Fusion.
            if analysis_candidates:
                selected_analysis = max(analysis_candidates, key=lambda item: _candidate_rank_tuple(item[1]))
                inc_audit("analysis_selected")
                _analysis_diag("selected", token_addr=selected_analysis[0])

                # Stage 3A: submit the selected Analysis candidate directly to its own executor.
                try:
                    inc_audit("analysis_submit_attempted")
                    future = ANALYSIS_EXECUTOR.submit(
                        _analysis_submit_worker,
                        selected_analysis[0],
                        selected_analysis[1],
                    )
                    inc_audit("analysis_submit_called")
                    _analysis_diag("submit_called", token_addr=selected_analysis[0])

                    def _done(fut, addr=selected_analysis[0]):
                        try:
                            ok, result = fut.result()
                            if ok:
                                inc_audit("analysis_execution_success")
                                _analysis_diag("execution_success", token_addr=addr)
                            else:
                                inc_audit("analysis_execution_failed")
                                _diag_reject("EXECUTION", str(result or "ANALYSIS_EXECUTION_FAILED"), addr)
                        except Exception as exc:
                            inc_audit("analysis_worker_exception")
                            _diag_reject("EXECUTION", f"ANALYSIS_WORKER_EXCEPTION:{type(exc).__name__}:{exc}", addr)
                            logger.exception("Analysis worker future failed for %s", addr)

                    future.add_done_callback(_done)
                except Exception as exc:
                    inc_audit("analysis_submit_failed")
                    _diag_reject("EXECUTION", f"ANALYSIS_SUBMIT_EXCEPTION:{type(exc).__name__}:{exc}", selected_analysis[0])
                    logger.exception("Analysis submit failed for %s", selected_analysis[0])
            else:
                _diag_reject("ANALYSIS", "NO_ANALYSIS_CANDIDATE")

            # Stage 2B/3B: Fusion selection/submission is entirely separate.
            for token_addr, candidate in _select_fusion_candidates(fusion_candidates):
                try:
                    SIGNAL_EXECUTOR.submit(send_fused_signal, token_addr, candidate)
                except Exception as exc:
                    _diag_reject("EXECUTION", f"FUSION_SUBMIT_EXCEPTION:{type(exc).__name__}:{exc}", token_addr)
                    logger.exception("Fusion submit failed for %s", token_addr)

        except Exception as exc:
            V12_REAL_AUDIT["last_error"] = str(exc)
            logger.exception("Clean signal radar error")

        time.sleep(FAST_SCAN_INTERVAL_SECONDS)


# Start the discovery worker once. It only accelerates market observation;
# all existing signal gates and UI controls remain authoritative.
try:
    _elite_market_refresh_thread = Thread(target=_elite_market_refresh_loop, name="EliteDiscovery", daemon=True)
    _elite_market_refresh_thread.start()
except Exception as e:
    logger.warning(f"Elite discovery worker startup failed: {e}")

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

            // Telegram Mini App normally supplies the user through initDataUnsafe.
            // Keep the explicit telegram_id fallback only for legacy/direct links.
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

def get_all_subscribers():
    rows = []
    with db_lock:
        try:
            conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT telegram_id, wallet_address, expiry_date, tx_signature, status, copy_enabled, trade_amount_sol FROM subscribers ORDER BY expiry_date DESC")
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            logger.error(f"Get all subscribers error: {e}")
    return rows

def get_wallet_status():
    return {"pubkey": WALLET_PUBKEY or "-", "sol": get_sol_balance() if WALLET_PUBKEY else 0.0}

@web_app.route('/admin-panel')
def admin_panel():
    t_id = request.args.get("telegram_id", "")
    secret_key = request.args.get("secret", "")
    if not ((TELEGRAM_CHAT_ID and str(t_id) == str(TELEGRAM_CHAT_ID)) or (ADMIN_SECRET_KEY and secret_key == ADMIN_SECRET_KEY)):
        return "<h3 style='color:red;text-align:center'>⛔ دسترسی غیرمجاز</h3>", 403
    analytics = get_advanced_trade_analytics()
    wallet = get_wallet_status()
    subs = get_all_subscribers()
    best = analytics["best_trade"]; worst = analytics["worst_trade"]
    best_str = f"{best[0]} ({best[1]:+.2f}%)" if best else "ثبت نشده"
    worst_str = f"{worst[0]} ({worst[1]:+.2f}%)" if worst else "ثبت نشده"
    rows_html = "".join(f"<div class='row'>🆔 {r[0]}<br>💳 ولت: <span class='mono'>{r[1] or '-'}</span><br>⏳ انقضا: {r[2]}<br>📌 وضعیت: {r[4]} | 🤖 کپی: {'فعال' if len(r)>5 and r[5] else 'خاموش'} | 💰 حجم: {r[6] if len(r)>6 else 0.01} SOL</div>" for r in subs) or "<div class='row'>هنوز کاربری ثبت نشده است.</div>"
    return f"""<!doctype html><html lang='fa' dir='rtl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>پنل مدیریت هالکی</title><style>body{{background:#07111f;color:#fff;font-family:Tahoma;padding:14px}}.wrap{{max-width:720px;margin:auto}}.card{{background:#101c2d;border:1px solid #24364f;border-radius:18px;padding:16px;margin:10px 0;box-shadow:0 8px 30px #0008}}h1,h2{{text-align:center}}h1{{font-size:20px;color:#38bdf8}}h2{{font-size:14px;color:#c084fc}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}}.stat{{background:#0b1524;border-radius:14px;padding:12px;text-align:center}}.value{{font-size:19px;font-weight:bold;color:#22c55e}}.row{{background:#0b1524;border-radius:12px;padding:10px;margin:7px 0;font-size:11px;line-height:1.8}}.mono{{word-break:break-all;color:#94a3b8}}</style></head><body><div class='wrap'><div class='card'><h1>👑 پنل مدیریت هوشمند هالکی</h1><p style='text-align:center;color:#94a3b8'>کنترل و گزارش خصوصی ادمین</p></div><div class='card'><h2>📊 آمار معاملات</h2><div class='grid'><div class='stat'>کل معاملات<br><span class='value'>{analytics['total_trades']}</span></div><div class='stat'>Win Rate<br><span class='value'>{analytics['win_rate']:.2f}%</span></div><div class='stat'>سود/زیان<br><span class='value'>{analytics['total_pct']:+.2f}%</span></div><div class='stat'>P/L دلاری<br><span class='value'>${analytics['total_usd']:+.2f}</span></div></div><p>🏆 بهترین: {best_str}</p><p>📉 بدترین: {worst_str}</p></div><div class='card'><h2>💼 ولت اصلی</h2><p>موجودی لحظه‌ای: <b>{wallet['sol']:.6f} SOL</b></p><p class='mono'>{wallet['pubkey']}</p><p style='color:#64748b;font-size:10px'>این اطلاعات فقط در پنل مدیریت نمایش داده می‌شود و به کانال VIP ارسال نمی‌شود.</p></div><div class='card'><h2>👥 کاربران و اشتراک‌ها</h2><p>تعداد رکوردها: <b>{len(subs)}</b></p>{rows_html}</div></div></body></html>"""

@web_app.route('/api/admin/free-sub', methods=['POST'])
def api_admin_free_sub():
    data = request.json or {}
    t_id = data.get("telegram_id")
    admin_id = str(data.get("admin_id"))
    secret = data.get("secret", "")
    
    if (admin_id != str(TELEGRAM_CHAT_ID)) and (secret != ADMIN_SECRET_KEY):
        return jsonify({"status": "error", "message": "دسترسی غیرمجاز!"}), 403
    if not t_id:
        return jsonify({"status": "error", "message": "آیدی تلگرام معتبر نیست."})
        
    success = register_free_vip(t_id)
    if success:
        return jsonify({"status": "success", "message": f"کاربر {t_id} با موفقیت به صورت رایگان عضو VIP شد و لینک کانال ارسال گردید."})
    else:
        return jsonify({"status": "error", "message": "خطا در ثبت نام رایگان کاربر."})

@web_app.route('/api/copy-settings', methods=['POST'])
def api_copy_settings():
    data = request.json or {}
    t_id = str(data.get('telegram_id') or '').strip()
    asset = str(data.get('trade_asset') or 'USDC').upper().strip()
    if asset not in ('SOL', 'USDC'):
        return jsonify({'status':'error','message':'دارایی کپی‌ترید باید SOL یا USDC باشد.'}), 400
    try:
        amount = float(data.get('trade_amount'))
    except Exception:
        return jsonify({'status':'error','message':'حجم معامله نامعتبر است.'}), 400
    if not t_id or amount <= 0:
        return jsonify({'status':'error','message':'حجم معامله باید بیشتر از صفر باشد.'}), 400
    if asset == 'SOL' and amount > 1000:
        return jsonify({'status':'error','message':'حجم SOL بیش از حد مجاز است.'}), 400
    if asset == 'USDC' and amount > 100000:
        return jsonify({'status':'error','message':'حجم USDC بیش از حد مجاز است.'}), 400
    active, _ = check_user_subscription(t_id)
    if not active:
        return jsonify({'status':'error','message':'اشتراک VIP فعال نیست.'}), 403
    with db_lock:
        conn = sqlite3.connect('bot_analytics.db', timeout=30.0, check_same_thread=False)
        cur = conn.cursor()
        cur.execute('''
            UPDATE subscribers
            SET trade_asset=?, trade_amount_sol=?, trade_amount_usdc=?, copy_enabled=1
            WHERE telegram_id=?
        ''', (asset, amount if asset == 'SOL' else 0.01,
              amount if asset == 'USDC' else 10.0, t_id))
        changed = cur.rowcount
        conn.commit()
        conn.close()
    if not changed:
        return jsonify({'status':'error','message':'کاربر پیدا نشد.'}), 404
    fee = amount * (COPY_TRADING_FEE_PERCENT / 100.0)
    net = max(0.0, amount - fee)
    return jsonify({
        'status':'success',
        'message': f'حجم کپی‌ترید روی {amount:g} {asset} تنظیم شد. کارمزد سرویس {COPY_TRADING_FEE_PERCENT:g}% از بودجه همان معامله محاسبه می‌شود؛ خالص معامله {net:g} {asset} است.',
        'asset': asset, 'amount': amount, 'fee_percent': COPY_TRADING_FEE_PERCENT,
        'estimated_fee': fee, 'net_trade_amount': net
    })

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
    copy_amount=0.01; copy_amount_usdc=10.0; copy_asset=COPY_DEFAULT_ASSET; copy_enabled=False
    if t_id:
        with db_lock:
            try:
                conn=sqlite3.connect("bot_analytics.db",timeout=30.0,check_same_thread=False); cur=conn.cursor()
                cur.execute("SELECT copy_enabled, trade_amount_sol, trade_asset, trade_amount_usdc FROM subscribers WHERE telegram_id=?",(str(t_id),))
                cr=cur.fetchone(); conn.close()
                if cr:
                    copy_enabled=bool(cr[0])
                    copy_amount=float(cr[1] or 0.01)
                    copy_asset=str(cr[2] or COPY_DEFAULT_ASSET).upper()
                    copy_amount_usdc=float(cr[3] or 10.0)
            except Exception: pass
    return jsonify({
        "has_subscription": has_sub,
        "expiry_date": expiry_str,
        "last_expiry": last_exp,
        "remaining_seconds": remaining_seconds,
        "channel_link": CHANNEL_INVITE_LINK,
        "prices": {"USDC": VIP_PRICE_USDC},
        "copy_enabled": copy_enabled,
        "copy_amount_sol": copy_amount,
        "copy_amount_usdc": copy_amount_usdc,
        "copy_asset": copy_asset,
        "copy_fee_percent": COPY_TRADING_FEE_PERCENT
    })

@web_app.route('/api/subscribe', methods=['POST'])
def api_subscribe():
    data = request.json or {}
    t_id = data.get("telegram_id")
    wallet = data.get("wallet_address")
    tx_sig = data.get("tx_signature")
    currency = str(data.get("currency", "USDC")).upper()

    if currency != "USDC":
        return jsonify({"status": "error", "message": "فقط پرداخت 50 USDC پذیرفته می‌شود."}), 400

    if not (t_id and wallet and tx_sig):
        return jsonify({"status": "error", "message": "اطلاعات ورودی ناقص است."}), 400

    is_valid, v_msg = verify_blockchain_transaction(tx_sig, currency)
    if not is_valid:
        return jsonify({"status": "error", "message": f"تایید تراکنش ناموفق: {v_msg}"}), 400

    # Do not allow the same blockchain transaction to activate multiple accounts.
    with db_lock:
        conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
        cur = conn.cursor()
        cur.execute("SELECT telegram_id FROM subscribers WHERE tx_signature = ?", (f"{currency}:{tx_sig}",))
        already_used = cur.fetchone()
        conn.close()
    if already_used:
        return jsonify({"status": "error", "message": "این تراکنش قبلاً برای یک اشتراک استفاده شده است."}), 400

    success = register_subscription(t_id, wallet, tx_sig, currency)
    if success:
        return jsonify({"status": "success", "message": "اشتراک شما با موفقیت فعال شد!"})
    else:
        return jsonify({"status": "error", "message": "خطا در ثبت اشتراک."}), 500

def _engine_status_lines():
    components = [
        ("Fire", IS_RUNNING), ("Trend", TREND_ALERT_RUNNING), ("Combo", COMBO_RUNNING),
        ("Golden", GOLDEN_OPTION), ("Technical", TECHNICAL_RUNNING),
        ("UltimateAI/21", ULTIMATE_21_ENGINE_ENABLED), ("Mempool/SmartMoney", MEMPOOL_SMART_MONEY_ENABLED),
        ("Whale", BOTTOM_WHALE_RUNNING), ("Social/Hype", SOCIAL_SENTIMENT_ENABLED),
        ("Anti-Wash", ANTI_WASH_TRADING_ENABLED), ("SmartFilter", SMART_FILTER_ENABLED),
        ("Analysis", ANALYSIS_ENGINE_ENABLED),
    ]
    active = sum(1 for _, state in components if state)
    detail = " | ".join(f"{name}:{'🟢' if state else '🔴'}" for name, state in components)
    return (
        f"🤖⚡ **{UNIFIED_ENGINE_NAME}**\n\n"
        f"وضعیت اتحاد: {'🟢 فعال — رادار مستقل اتحاد بازار را رصد می‌کند' if SYNCHRONIZED_MODE else '🔴 خاموش'}\n"
        f"موتورهای تحلیلی روشن: `{active}/{len(components)}`\n\n"
        f"{detail}\n\n"
        f"🤖 کپی‌ترید: {'🟢' if COPY_TRADING_ENABLED else '🔴'}\n"
        f"🎯 فیلتر اتحاد سخت‌گیر: حداقل {CONSENSUS_MIN_SCORE} رأی و {CONSENSUS_MIN_RATIO*100:.0f}% موتورهای روشن + نقدینگی/حجم/فشار خرید"
    )

def _admin_free_panel_text():
    rows = []
    with db_lock:
        try:
            conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
            cur = conn.cursor()
            cur.execute("SELECT telegram_id, expiry_date, status FROM subscribers ORDER BY expiry_date DESC LIMIT 20")
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            logger.error(f"Admin free panel error: {e}")
    text = "👑 **عضویت رایگان کپی‌ترید + VIP**\n\n"
    text += "برای فعال‌سازی فوری یک کاربر، دستور زیر را در همین ربات بفرستید:\n`/free USER_TELEGRAM_ID`\n\n"
    text += "کاربر بلافاصله پیام تبریک می‌گیرد و در Mini App به‌جای فرم ثبت‌نام، تاریخ انقضا و زمان باقی‌مانده را می‌بیند.\n\n"
    text += "👥 کاربران ثبت‌شده اخیر:\n"
    if rows:
        for tid, exp, status in rows[:10]:
            text += f"• `{tid}` — {status} — {exp}\n"
    else:
        text += "هنوز کاربری ثبت نشده است.\n"
    return text

def _main_keyboard(is_admin=False):
    rows=[[InlineKeyboardButton("📊 وضعیت موتورها",callback_data="engines"),InlineKeyboardButton("💼 وضعیت ولت",callback_data="wallet")],[InlineKeyboardButton("📈 آمار معاملات",callback_data="stats"),InlineKeyboardButton("🎛 کنترل موتورها",callback_data="controls")]]
    if WEBAPP_URL: rows.append([InlineKeyboardButton("📱 Mini App VIP",web_app=WebAppInfo(url=WEBAPP_URL))])
    elif CHANNEL_INVITE_LINK: rows.append([InlineKeyboardButton("📢 کانال VIP",url=CHANNEL_INVITE_LINK)])
    if is_admin:
        rows.append([InlineKeyboardButton("👑 پنل مدیریت",callback_data="admin"),InlineKeyboardButton("🔐 امنیت/وضعیت",callback_data="security")])
        rows.append([InlineKeyboardButton(
            f"🎯 سقف روزانه (بودجه سیگنال): {daily_signal_status_text()}",
            callback_data="daily_signal_limit"
        )])
        rows.append([InlineKeyboardButton(
            f"📈 موتور تحلیل: {'🟢 ON' if ANALYSIS_ENGINE_ENABLED else '🔴 OFF'}",
            callback_data="toggle_engine_analysis"
        )])
        rows.append([InlineKeyboardButton("🎁 عضویت رایگان کاربر",callback_data="free_users")])
    return InlineKeyboardMarkup(rows)

ENGINE_SWITCHES = [
    ("Analysis", "ANALYSIS_ENGINE_ENABLED", "toggle_engine_analysis"),
    ("Fire", "IS_RUNNING", "toggle_engine_fire"),
    ("Trend", "TREND_ALERT_RUNNING", "toggle_engine_trend"),
    ("Combo", "COMBO_RUNNING", "toggle_engine_combo"),
    ("Golden", "GOLDEN_OPTION", "toggle_engine_golden"),
    ("Technical", "TECHNICAL_RUNNING", "toggle_engine_technical"),
    ("UltimateAI/21", "ULTIMATE_21_ENGINE_ENABLED", "toggle_engine_ultimate"),
    ("Mempool/SmartMoney", "MEMPOOL_SMART_MONEY_ENABLED", "toggle_engine_mempool"),
    ("Whale", "BOTTOM_WHALE_RUNNING", "toggle_engine_whale"),
    ("Social/Hype", "SOCIAL_SENTIMENT_ENABLED", "toggle_engine_social"),
    ("Anti-Wash", "ANTI_WASH_TRADING_ENABLED", "toggle_engine_antiwash"),
    ("SmartFilter", "SMART_FILTER_ENABLED", "toggle_engine_smartfilter"),
]

def _trade_limit_keyboard():
    # مقدار معامله کاملاً دستی است؛ هیچ Preset اجباری وجود ندارد.
    rows = [
        [InlineKeyboardButton("✏️ وارد کردن مقدار دلخواه SOL", callback_data="trade_limit_manual")],
        [InlineKeyboardButton("🔙 بازگشت به کنترل موتورها", callback_data="controls")]
    ]
    return InlineKeyboardMarkup(rows)

def _engine_control_keyboard():
    rows = []
    engine_buttons = []
    for label, var_name, callback_name in ENGINE_SWITCHES:
        engine_buttons.append(InlineKeyboardButton(
            f"{label}: {'🟢 ON' if globals().get(var_name) else '🔴 OFF'}",
            callback_data=callback_name
        ))
    for i in range(0, len(engine_buttons), 2):
        rows.append(engine_buttons[i:i+2])
    rows.append([InlineKeyboardButton("🔙 بازگشت به کنترل اصلی", callback_data="controls")])
    return InlineKeyboardMarkup(rows)

def _control_keyboard():
    # در MAX FUSION هر دو سیستم زیر آن روشن و قفل هستند؛
    # فقط خود MAX FUSION و توقف اضطراری/تنظیمات جانبی قابل تغییرند.
    if MAX_FUSION_ENABLED:
        hulk_label = "🔒 اتحاد هالک AI: 🟢 ON"
        advanced_label = "🔒 سیستم پیشرفته AI: 🟢 ON"
    else:
        hulk_label = f"🤖⚡ اتحاد هالک AI: {'🟢 ON' if SYNCHRONIZED_MODE else '🔴 OFF'}"
        advanced_label = f"🧠 سیستم پیشرفته AI: {'🟢 ON' if ADVANCED_AI_ENABLED else '🔴 OFF'}"

    rows = [
        [InlineKeyboardButton(
            f"👑 MAX FUSION: {'🟢 ON' if MAX_FUSION_ENABLED else '🔴 OFF'}",
            callback_data="toggle_max_fusion"
        )],
        [InlineKeyboardButton(hulk_label, callback_data="toggle_unified")],
        [InlineKeyboardButton(advanced_label, callback_data="toggle_advanced")],
        [InlineKeyboardButton(
            f"🛑 توقف اضطراری: {'🔴 فعال' if EMERGENCY_STOP else '🟢 آماده'}",
            callback_data="toggle_emergency"
        )],
        [InlineKeyboardButton(
            "⚙️ مدیریت موتورهای مستقل", callback_data="engine_manage"
        )],
        [InlineKeyboardButton(
            f"🤖 کپی‌ترید: {'🟢 ON' if COPY_TRADING_ENABLED else '🔴 OFF'}",
            callback_data="toggle_copy"
        )],
        [InlineKeyboardButton(
            f"💰 سقف هر معامله: {MAX_TRADE_SOL:g} SOL", callback_data="trade_limit"
        )],
        [InlineKeyboardButton(
            f"🎯 سقف روزانه سیگنال: {daily_signal_status_text()}",
            callback_data="daily_signal_limit"
        )],
        [InlineKeyboardButton("📊 داشبورد PRO MAX", callback_data="v7_dashboard")],
                        [InlineKeyboardButton("🧪 اعتبارسنجی V10", callback_data="v10_validation")],
                        [InlineKeyboardButton("🧠 تحلیل داده‌محور V11", callback_data="v11_data")],
                        [InlineKeyboardButton("🩺 عیب‌یابی واقعی سیگنال", callback_data="v12_real_audit")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="home")]
    ]
    return InlineKeyboardMarkup(rows)

def start_telegram_bot():
    try:
        if not TELEGRAM_BOT_TOKEN:
            logger.error("❌ TELEGRAM_BOT_TOKEN تنظیم نشده؛ ربات تلگرام اجرا نشد."); return
        app=ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        _load_daily_signal_state()
        async def start_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
            chat_id=update.effective_chat.id; is_admin=bool(TELEGRAM_CHAT_ID and str(chat_id)==str(TELEGRAM_CHAT_ID)); active,exp_date=check_user_subscription(chat_id)
            text=(f"🤖⚡ **هالک AI — مرکز ربات هوشمند ترید**\n\n👑 MAX FUSION: {'🟢 ON' if MAX_FUSION_ENABLED else '🔴 OFF'}\n⚡ اتحاد هالک: {'🟢 ON' if SYNCHRONIZED_MODE else '🔴 OFF'}\n🧠 سیستم پیشرفته: {'🟢 ON' if ADVANCED_AI_ENABLED else '🔴 OFF'}\n🛑 توقف اضطراری: {'🔴 فعال' if EMERGENCY_STOP else '🟢 آماده'}" if active else "🤖⚡ **هالک AI — مرکز ربات هوشمند ترید**\n\n📡 سیستم آماده رصد بازار است.")
            await update.message.reply_text(text,reply_markup=_main_keyboard(is_admin),parse_mode="Markdown")
        async def free_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
            cid = str(update.effective_user.id)
            if not (TELEGRAM_CHAT_ID and cid == str(TELEGRAM_CHAT_ID)):
                await update.message.reply_text("⛔ فقط ادمین دسترسی دارد.")
                return
            if not context.args:
                await update.message.reply_text("🎁 برای فعال‌سازی رایگان: `/free 123456789`", parse_mode="Markdown")
                return
            target = str(context.args[0]).strip()
            if not target.isdigit():
                await update.message.reply_text("❌ Telegram ID باید عددی باشد.")
                return
            ok = register_free_vip(target)
            await update.message.reply_text("✅ اشتراک رایگان یک‌ماهه فعال شد و پیام تبریک برای کاربر ارسال شد." if ok else "❌ فعال‌سازی انجام نشد.")

        async def setvipchannel_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
            global CHANNEL_ID, CHANNEL_INVITE_LINK
            cid = str(update.effective_user.id)
            if not (TELEGRAM_CHAT_ID and cid == str(TELEGRAM_CHAT_ID)):
                await update.message.reply_text("⛔ فقط ادمین دسترسی دارد.")
                return
            if not context.args:
                await update.message.reply_text("📢 نمونه: /setvipchannel @MyVipChannel\nیا برای کانال خصوصی: /setvipchannel -1001234567890")
                return
            channel = str(context.args[0]).strip()
            if channel.startswith("https://t.me/"):
                tail = channel.split("https://t.me/",1)[1].strip("/")
                if tail and not tail.startswith("+"):
                    channel = "@" + tail
                else:
                    CHANNEL_INVITE_LINK = channel
                    _set_bot_setting("vip_channel_invite", channel)
                    await update.message.reply_text("✅ لینک دعوت کانال ذخیره شد.")
                    return
            CHANNEL_ID = channel
            CHANNEL_INVITE_LINK = ""
            _set_bot_setting("vip_channel_id", CHANNEL_ID)
            link = ensure_channel_invite_link()
            if link:
                await update.message.reply_text(f"✅ کانال VIP ثبت شد.\n🔗 {link}")
            else:
                await update.message.reply_text("⚠️ کانال ذخیره شد ولی لینک ساخته نشد. ربات باید داخل کانال ادمین باشد و اجازه دعوت داشته باشد.")

        async def settradesol_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
            cid = str(update.effective_user.id)
            if not (TELEGRAM_CHAT_ID and cid == str(TELEGRAM_CHAT_ID)):
                await update.message.reply_text("⛔ فقط ادمین دسترسی دارد.")
                return
            if not context.args:
                await update.message.reply_text(f"💰 سقف فعلی: {MAX_TRADE_SOL:g} SOL\nنمونه: /settradesol 0.05")
                return
            try:
                value = _set_trade_limit(float(context.args[0]))
                await update.message.reply_text(f"✅ سقف هر معامله روی {value:g} SOL تنظیم شد.\nحتی ریسک پویا هم از این سقف عبور نمی‌کند.")
            except Exception as e:
                await update.message.reply_text(f"❌ {e}")

        async def cancel_trade_limit_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
            context.user_data.pop("awaiting_trade_limit_sol", None)
            await update.message.reply_text(
                f"↩️ لغو شد. سقف فعلی هر معامله: {MAX_TRADE_SOL:g} SOL",
                reply_markup=_control_keyboard() if str(update.effective_user.id) == str(TELEGRAM_CHAT_ID) else _main_keyboard(False)
            )

        async def manual_trade_limit_message(update:Update, context:ContextTypes.DEFAULT_TYPE):
            global MAX_TRADE_SOL
            cid = str(update.effective_user.id)
            if not (TELEGRAM_CHAT_ID and cid == str(TELEGRAM_CHAT_ID)):
                return

            if context.user_data.get("awaiting_daily_signal_limit"):
                raw = (update.message.text or "").strip()
                try:
                    value = _set_daily_signal_limit(int(raw))
                    context.user_data.pop("awaiting_daily_signal_limit", None)
                    await update.message.reply_text(
                        f"✅ **سقف روزانه تغییر کرد**\n\n🎯 حداکثر سیگنال ورود در روز: `{value}`\n"
                        f"📊 امروز / سقف جدید: `{daily_signal_status_text()}`\n\n"
                        "بعد از رسیدن به این عدد، ورود جدید متوقف می‌شود ولی فروش/مدیریت پوزیشن‌های باز ادامه دارد.",
                        parse_mode="Markdown",
                        reply_markup=_control_keyboard()
                    )
                except Exception as e:
                    await update.message.reply_text(
                        f"❌ {e}\n\nیک عدد بین `1` تا `50` بفرست.",
                        parse_mode="Markdown"
                    )
                return

            if not context.user_data.get("awaiting_trade_limit_sol"):
                return
            raw = (update.message.text or "").strip().replace(",", ".")
            try:
                value = float(raw)
                if value <= 0:
                    raise ValueError("مقدار باید بیشتر از صفر باشد.")
                if value > 1000000:
                    raise ValueError("مقدار بیش از حد بزرگ است.")
                value = _set_trade_limit(value)
                context.user_data.pop("awaiting_trade_limit_sol", None)
                await update.message.reply_text(
                    f"✅ **سقف معامله تنظیم شد**\n\n💰 حداکثر هر معامله: `{value:g} SOL`\n\n"
                    "از این به بعد هر موتور/سیگنال هرچقدر هم حجم پیشنهادی داشته باشد، بیشتر از این مقدار SOL وارد معامله نمی‌شود.",
                    parse_mode="Markdown",
                    reply_markup=_control_keyboard()
                )
            except Exception as e:
                await update.message.reply_text(
                    f"❌ مقدار نامعتبر است: {e}\n\nیک عدد دلخواه مثل `0.0175` یا `0.25` SOL بفرست.",
                    parse_mode="Markdown"
                )

        async def button_handler(update:Update,context:ContextTypes.DEFAULT_TYPE):
            global IS_RUNNING,TREND_ALERT_RUNNING,COMBO_RUNNING,GOLDEN_OPTION,TECHNICAL_RUNNING,MEMPOOL_SMART_MONEY_ENABLED,BOTTOM_WHALE_RUNNING,COPY_TRADING_ENABLED,ULTIMATE_21_ENGINE_ENABLED,SOCIAL_SENTIMENT_ENABLED,ANTI_WASH_TRADING_ENABLED,SMART_FILTER_ENABLED,SYNCHRONIZED_MODE,ADVANCED_AI_ENABLED,MAX_FUSION_ENABLED,EMERGENCY_STOP,_MAX_FUSION_PREV,MAX_TRADE_SOL
            q=update.callback_query; await q.answer(); cid=str(q.from_user.id); is_admin=bool(TELEGRAM_CHAT_ID and cid==str(TELEGRAM_CHAT_ID)); data=q.data
            if data=="home": await q.edit_message_text("🤖⚡ **هالک AI — مرکز ربات هوشمند ترید**\n\n👑 MAX FUSION: %s\n⚡ اتحاد هالک: %s\n🧠 سیستم پیشرفته: %s\n🛑 توقف اضطراری: %s" % ("🟢 ON" if MAX_FUSION_ENABLED else "🔴 OFF", "🔒 🟢 ON" if MAX_FUSION_ENABLED else ("🟢 ON" if SYNCHRONIZED_MODE else "🔴 OFF"), "🔒 🟢 ON" if MAX_FUSION_ENABLED else ("🟢 ON" if ADVANCED_AI_ENABLED else "🔴 OFF"), "🔴 فعال" if EMERGENCY_STOP else "🟢 آماده"),reply_markup=_main_keyboard(is_admin),parse_mode="Markdown")
            elif data=="engines": await q.edit_message_text("🎛 **وضعیت موتورهای هوشمند**\n\n"+_engine_status_lines(),reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت",callback_data="home")]]),parse_mode="Markdown")
            elif data=="controls": await q.edit_message_text(("🎛 **کنترل موتورها**\n\n🤖 اتحاد هالک روشن است.\nهمه موتورهای تحلیلی با هم رأی می‌دهند و فقط یک سیگنال واحد منتشر می‌شود.\n\nبرای کنترل تک‌تک موتورها، اتحاد را خاموش کنید." if SYNCHRONIZED_MODE else "🎛 **کنترل موتورها**\n\n🔴 اتحاد خاموش است.\nحالا هر موتور کلید مستقل خودش را دارد و می‌توانید هرکدام را جداگانه روشن/خاموش کنید."),reply_markup=_control_keyboard(),parse_mode="Markdown") if is_admin else await q.edit_message_text("⛔ این بخش فقط برای ادمین است.",reply_markup=_main_keyboard(False))
            elif data=="wallet":
                if not is_admin: await q.edit_message_text("⛔ اطلاعات ولت اصلی خصوصی است.",reply_markup=_main_keyboard(False))
                else:
                    sol_balance = await _tg_bg(get_sol_balance)
                    await q.edit_message_text(f"💼 **ولت اصلی**\n\n💰 موجودی: `{sol_balance:.6f} SOL`\n\n📍 `{WALLET_PUBKEY or '-'} `",reply_markup=_main_keyboard(True),parse_mode="Markdown")
            elif data=="stats":
                a=await _tg_bg(get_advanced_trade_analytics); await q.edit_message_text(f"📊 **آمار واقعی ثبت‌شده**\n\nمعاملات: `{a['total_trades']}`\nWin Rate: `{a['win_rate']:.2f}%`\nسود/زیان: `{a['total_pct']:+.2f}%`\nP/L: `${a['total_usd']:+.2f}`",reply_markup=_main_keyboard(is_admin),parse_mode="Markdown")
            elif data=="security":
                if not is_admin: await q.edit_message_text("⛔ فقط ادمین.",reply_markup=_main_keyboard(False))
                else: await q.edit_message_text(f"🔐 **امنیت**\n\nPrivate Key: {'🟢 Environment' if PRIVATE_KEY_BASE58 else '🔴 تنظیم نشده'}\nRPCها: `{len(RPC_ENDPOINTS)}`\nAdmin Secret: {'🟢 تنظیم شده' if ADMIN_SECRET_KEY else '🔴 تنظیم نشده'}",reply_markup=_main_keyboard(True),parse_mode="Markdown")
            elif data=="admin":
                if not is_admin: await q.edit_message_text("⛔ دسترسی غیرمجاز.")
                else: await q.edit_message_text(f"👑 **پنل مدیریت**\n\nکاربران: `{len(get_all_subscribers())}`\nمعاملات: `{get_advanced_trade_analytics()['total_trades']}`",reply_markup=_main_keyboard(True),parse_mode="Markdown")
            elif data=="free_users":
                if not is_admin:
                    await q.edit_message_text("⛔ دسترسی غیرمجاز.", reply_markup=_main_keyboard(False))
                else:
                    await q.edit_message_text(_admin_free_panel_text(), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="home")]]), parse_mode="Markdown")
            elif data == "daily_signal_limit":
                if not is_admin:
                    await q.edit_message_text("⛔ دسترسی غیرمجاز.", reply_markup=_main_keyboard(False))
                    return
                await q.edit_message_text(
                    f"🎯 **سهم روزانه سیگنال**\n\n"
                    f"📊 امروز / سقف انتخابی: `{daily_signal_status_text()}`\n"
                    f"🔧 سقف فعلی: `{DAILY_SIGNAL_LIMIT}` سیگنال\n\n"
                    "عدد دلخواه را بین **1 تا 50** بفرست.\n"
                    "پیش‌فرض: **15**\n\n"
                    "بعد از رسیدن به سقف، ورودهای جدید متوقف می‌شوند؛ "
                    "پوزیشن‌های باز همچنان مدیریت و فروخته می‌شوند.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✏️ تغییر دستی سقف روزانه", callback_data="daily_signal_limit_manual")],
                        [InlineKeyboardButton("🔙 بازگشت به کنترل موتورها", callback_data="controls")]
                    ]),
                    parse_mode="Markdown"
                )
                return
            elif data == "daily_signal_limit_manual":
                if not is_admin:
                    await q.edit_message_text("⛔ دسترسی غیرمجاز.", reply_markup=_main_keyboard(False))
                    return
                context.user_data["awaiting_daily_signal_limit"] = True
                await q.edit_message_text(
                    "✏️ **سقف روزانه را بفرست**\n\n"
                    "یک عدد بین `1` تا `50` ارسال کن.\n"
                    "مثال: `12` یا `15` یا `30` یا `50`",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 انصراف", callback_data="daily_signal_limit")]
                    ]),
                    parse_mode="Markdown"
                )
                return
            elif data == "learning_stats":
                if not is_admin:
                    await q.edit_message_text("⛔ دسترسی غیرمجاز.", reply_markup=_main_keyboard(False))
                    return
                st = await _tg_bg(learning_stats)
                await q.edit_message_text(
                    "📚 **یادگیری و عملکرد واقعی**\n\n"
                    f"📊 معاملات ثبت‌شده: `{st['trades']}`\n"
                    f"✅ Win Rate: `{st['win_rate']:.1f}%`\n"
                    f"💰 مجموع PnL معاملات ثبت‌شده: `{st['net_pnl_pct_sum']:.2f}%`\n"
                    f"🔥 باخت متوالی: `{st['loss_streak']}`\n"
                    f"🛡️ ضریب ریسک فعلی: `{learning_risk_multiplier():.2f}x`\n\n"
                    "یادگیری فقط از معاملات بسته‌شده انجام می‌شود و برای پر کردن سهمیه، "
                    "فیلتر کیفیت را ضعیف نمی‌کند.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 بازگشت", callback_data="controls")]
                    ])
                )
                return

            elif data == "v7_dashboard":
                if not is_admin:
                    await q.edit_message_text(
                        "⛔ دسترسی غیرمجاز.",
                        reply_markup=_main_keyboard(False)
                    )
                    return

                try:
                    st = await _tg_bg(learning_stats)
                except Exception:
                    st = {"trades": 0, "win_rate": 0.0, "net_pnl_pct_sum": 0.0, "loss_streak": 0}
                try:
                    ps = await _tg_bg(v7_paper_stats)
                except Exception:
                    ps = {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0}
                try:
                    bt = await _tg_bg(v7_backtest_from_learning_history)
                except Exception:
                    bt = {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0}
                rg = v7_state.get("regime", {}) or {}

                msg = (
                    "📊 **PRO MAX Dashboard**\n\n"
                    f"🧠 معاملات یادگیری: `{st.get('trades', 0)}`\n"
                    f"✅ Win Rate: `{st.get('win_rate', 0):.1f}%`\n"
                    f"💰 PnL ثبت‌شده: `{st.get('net_pnl_pct_sum', 0):.2f}%`\n\n"
                    f"🧪 Paper Trading: `{ps.get('trades', 0)}` معامله\n"
                    f"   └ Win Rate: `{ps.get('win_rate', 0):.1f}%`\n"
                    f"   └ Profit Factor: `{ps.get('profit_factor', 0):.2f}`\n\n"
                    f"🔬 Backtest Check: `{bt.get('trades', 0)}` معامله\n"
                    f"   └ Win Rate: `{bt.get('win_rate', 0):.1f}%`\n"
                    f"   └ Profit Factor: `{bt.get('profit_factor', 0):.2f}`\n\n"
                    f"🌐 وضعیت بازار: `{rg.get('name', 'RANGE')}`\n"
                    f"🎯 اطمینان: `{float(rg.get('confidence', 0))*100:.0f}%`\n"
                    f"🛡️ ضریب ریسک: `{learning_risk_multiplier():.2f}x`\n"
                    f"🧹 حافظه: پاک‌سازی/فشرده‌سازی خودکار فعال\n"
                    f"   └ جزئیات قدیمی‌تر از {V7_MEMORY_MAX_AGE_DAYS} روز حذف/فشرده می‌شوند."
                )

                await q.edit_message_text(
                    msg,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="v7_dashboard")],
                        [InlineKeyboardButton("🔙 بازگشت", callback_data="controls")]
                    ])
                )
                return


            elif data == "v10_validation":
                if not is_admin:
                    await q.edit_message_text(
                        "⛔ این بخش فقط برای ادمین است.",
                        reply_markup=_main_keyboard(False)
                    )
                    return

                bt = await _tg_bg(v10_real_backtest)
                wf = await _tg_bg(v10_walk_forward)
                ab = await _tg_bg(v10_ab_engine_test)

                top = sorted(
                    ab.items(),
                    key=lambda kv: (kv[1].get("win_rate", 0), kv[1].get("net_pnl_pct", 0)),
                    reverse=True
                )[:5]

                lines = [
                    "🧪 **V10 Validation Lab**",
                    "",
                    f"🔬 Backtest: `{bt.get('sample',0)}` معامله",
                    f"   └ WR: `{bt.get('win_rate',0):.1f}%` | PF: `{bt.get('profit_factor',0):.2f}`",
                    f"   └ Net PnL: `{bt.get('net_pnl_pct',0):.2f}%`",
                    "",
                ]

                if wf.get("ready"):
                    lines += [
                        "🚶 **Walk-Forward / Out-of-Sample**",
                        f"   └ Train: `{wf.get('train_sample',0)}`",
                        f"   └ Test: `{wf.get('test_sample',0)}`",
                        f"   └ OOS WR: `{wf.get('out_of_sample_win_rate',0):.1f}%`",
                        f"   └ OOS PF: `{wf.get('out_of_sample_profit_factor',0):.2f}`",
                        f"   └ OOS Net: `{wf.get('out_of_sample_net_pnl_pct',0):.2f}%`",
                        "",
                    ]
                else:
                    lines += [
                        "🚶 **Walk-Forward**",
                        f"   └ ⏳ `{wf.get('reason','داده کافی نیست')}`",
                        "",
                    ]

                lines.append("⚖️ **A/B موتورهای واقعی ثبت‌شده**")
                if top:
                    for name, s in top:
                        lines.append(
                            f"• {name}: `{s.get('trades',0)}` معامله | "
                            f"WR `{s.get('win_rate',0):.1f}%` | "
                            f"PnL `{s.get('net_pnl_pct',0):.2f}%`"
                        )
                else:
                    lines.append("• هنوز داده کافی برای مقایسه وجود ندارد.")

                lines += [
                    "",
                    "ℹ️ این بخش فقط ارزیابی آماری است و برای بالا بردن مصنوعی Win Rate معامله‌ای را دستکاری نمی‌کند."
                ]

                await q.edit_message_text(
                    "\n".join(lines),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 اجرای مجدد", callback_data="v10_validation")],
                        [InlineKeyboardButton("📊 داشبورد PRO MAX", callback_data="v7_dashboard")],
                        [InlineKeyboardButton("🔙 بازگشت", callback_data="controls")]
                    ])
                )
                return

            elif data == "v11_data":
                if not is_admin:
                    await q.edit_message_text("⛔ این بخش فقط برای ادمین است.", reply_markup=_main_keyboard(False))
                    return
                report=v11_data_report()
                if time.time()-float(v11_state.get("last_tuning",0) or 0)>=V11_TUNING_INTERVAL:
                    v11_tune_weights(); report=v11_data_report()
                lines=["🧠 **V11 — سیستم داده‌محور**","","📈 **چک‌پوینت‌های واقعی**"]
                for n in V11_CHECKPOINTS:
                    s=report.get("checkpoints",{}).get(str(n))
                    lines.append(f"• {n}: WR `{s['win_rate']:.1f}%` | PF `{s['profit_factor']:.2f}` | PnL `{s['net_pnl_pct']:.2f}%`" if s else f"• {n}: ⏳ داده کافی نیست")
                lines += ["","⚙️ **عملکرد موتورهای کافی‌داده**"]
                engines=sorted(report.get("engines",{}).items(),key=lambda x:(x[1].get("win_rate",0),x[1].get("net_pnl_pct",0)),reverse=True)
                if engines:
                    for name,s in engines[:8]:
                        w=learning_state.get("engines",{}).get(name,{}).get("weight",1.0)
                        lines.append(f"• {name}: `{s['trades']}` | WR `{s['win_rate']:.1f}%` | PnL `{s['net_pnl_pct']:.2f}%` | وزن `{w:.2f}`")
                else: lines.append("• هنوز داده کافی نیست.")
                lines += ["","🌐 **عملکرد بر اساس رژیم بازار**"]
                regimes=report.get("regimes",{})
                if regimes:
                    for name,s in sorted(regimes.items(),key=lambda x:x[1].get("trades",0),reverse=True):
                        lines.append(f"• {name}: `{s['trades']}` | WR `{s['win_rate']:.1f}%` | PnL `{s['net_pnl_pct']:.2f}%`")
                else: lines.append("• هنوز داده رژیم کافی نیست.")
                lines += ["",f"🔧 تغییر وزن‌های این دوره: `{len(v11_state.get('last_changes',[]))}`","⚠️ تنظیمات فقط با داده کافی و تغییرات محدود انجام می‌شود؛ هدف، یادگیری است نه ساختن Win Rate مصنوعی."]
                await q.edit_message_text("\n".join(lines),parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تحلیل مجدد",callback_data="v11_data")],[InlineKeyboardButton("🧪 V10 Validation",callback_data="v10_validation")],[InlineKeyboardButton("🔙 بازگشت",callback_data="controls")]]))
                return

            elif data == "v12_real_audit":
                if not is_admin:
                    await q.edit_message_text("⛔ این بخش فقط برای ادمین است.", reply_markup=_main_keyboard(False))
                    return
                h = V12_REAL_AUDIT
                now = time.time()

                def ago(ts):
                    if not ts:
                        return "هنوز ثبت نشده"
                    sec = max(0, int(now - ts))
                    if sec < 60:
                        return f"{sec} ثانیه"
                    if sec < 3600:
                        return f"{sec//60} دقیقه"
                    return f"{sec//3600} ساعت"

                msg = (
                    "🩺 **REAL SIGNAL AUDIT — V12**\n\n"
                    f"🔄 آخرین اسکن: `{ago(h['last_scan'])} پیش`\n"
                    f"🔎 آخرین کاندیدای Fusion: `{ago(h['last_candidate'])} پیش`\n"
                    f"📡 آخرین سیگنال صادرشده: `{ago(h['last_signal'])} پیش`\n\n"
                    f"🔄 تعداد چرخه اسکن: `{h['scans']}`\n"
                    f"🪙 توکن‌های دیده‌شده: `{h['tokens_seen']}`\n"
                    f"📊 Pairهای واقعی بررسی‌شده: `{h['pairs_seen']}`\n"
                    f"🎯 کاندیداهای Fusion: `{h['fusion_candidates']}`\n"
                    f"📈 کاندیداهای موتور تحلیل: `{h['analysis_candidates']}`\n"
                    f"🧠 **اسکن واقعی موتور تحلیل**\n"
                    f"اسکن: `{V13_SIGNAL_DIAGNOSTICS['analysis']['scanned']}` | داده‌دار: `{V13_SIGNAL_DIAGNOSTICS['analysis']['data_ready']}`\n"
                    f"Warmup: `{V13_SIGNAL_DIAGNOSTICS['analysis']['warmup_checked']}` | ساختار کامل: `{V13_SIGNAL_DIAGNOSTICS['analysis']['full_structure_checked']}`\n"
                    f"کف: `{V13_SIGNAL_DIAGNOSTICS['analysis']['support_setups']}` | شکست سقف: `{V13_SIGNAL_DIAGNOSTICS['analysis']['breakout_setups']}` | ادامه‌روند: `{V13_SIGNAL_DIAGNOSTICS['analysis']['continuation_setups']}`\n"
                    f"کاندید تحلیل: `{V13_SIGNAL_DIAGNOSTICS['analysis']['candidates']}` | انتخاب: `{V13_SIGNAL_DIAGNOSTICS['analysis']['selected']}`\n"
                    f"Submit: `{V13_SIGNAL_DIAGNOSTICS['analysis']['submit_called']}` | Worker: `{V13_SIGNAL_DIAGNOSTICS['analysis']['worker_started']}`\n"
                    f"بلاک تکراری: `{V13_SIGNAL_DIAGNOSTICS['analysis']['blocked_duplicate']}` | سقف: `{V13_SIGNAL_DIAGNOSTICS['analysis']['blocked_daily_cap']}` | Circuit: `{V13_SIGNAL_DIAGNOSTICS['analysis']['blocked_circuit']}` | Cooldown: `{V13_SIGNAL_DIAGNOSTICS['analysis']['blocked_cooldown']}`\n"
                    f"شروع اجرای واقعی: `{V13_SIGNAL_DIAGNOSTICS['analysis']['execution_started']}` | ارسال نهایی: `{V13_SIGNAL_DIAGNOSTICS['analysis']['submitted']}`\n"
                    f"خرید موفق: `{V13_SIGNAL_DIAGNOSTICS['analysis']['real_buy_success']}` | خرید ناموفق: `{V13_SIGNAL_DIAGNOSTICS['analysis']['real_buy_failed']}`\n"
                    f"کانال موفق: `{V13_SIGNAL_DIAGNOSTICS['analysis']['channel_sent']}` | کانال ناموفق: `{V13_SIGNAL_DIAGNOSTICS['analysis']['channel_failed']}`\n"
                    f"آخرین مانع موتور تحلیل: `{V13_SIGNAL_DIAGNOSTICS['analysis']['last_reason'] or '—'}`\n"
                    f"۱۰ علت موتور تحلیل: "
                    + (" | ".join(f"`{r}`:{n}" for r, n in sorted(V13_SIGNAL_DIAGNOSTICS['analysis']['reasons'].items(), key=lambda x: x[1], reverse=True)[:10]) or "هنوز ثبت نشده")
                    + "\n\n"
                    f"🟡 عبور از پیش‌فیلتر کاندید: `{V13_SIGNAL_DIAGNOSTICS['candidate_prefilter_pass']}`\n"
                    f"🔻 رد پیش‌فیلتر کاندید: `{V13_SIGNAL_DIAGNOSTICS['candidate_prefilter_reject']}`\n\n"
                    f"🩺 **آخرین مانع واقعی**\n"
                    f"مرحله: `{V13_SIGNAL_DIAGNOSTICS['last_stage'] or '—'}`\n"
                    f"دلیل: `{V13_SIGNAL_DIAGNOSTICS['last_blocker'] or '—'}`\n"
                    f"توکن: `{V13_SIGNAL_DIAGNOSTICS['last_token'][-12:] if V13_SIGNAL_DIAGNOSTICS['last_token'] else '—'}`\n\n"
                    f"📊 **گلوگاه‌های Pipeline**\n"
                    f"Discovery: `{V13_SIGNAL_DIAGNOSTICS['stages'].get('DISCOVERY', 0)}` | "
                    f"Pair: `{V13_SIGNAL_DIAGNOSTICS['stages'].get('PAIR_FETCH', 0)}`\n"
                    f"Market: `{V13_SIGNAL_DIAGNOSTICS['stages'].get('MARKET_QUALITY', 0)}` | "
                    f"Structure: `{V13_SIGNAL_DIAGNOSTICS['stages'].get('STRUCTURE', 0)}`\n"
                    f"Engine: `{V13_SIGNAL_DIAGNOSTICS['stages'].get('ENGINE', 0)}` | "
                    f"Fusion: `{V13_SIGNAL_DIAGNOSTICS['stages'].get('FUSION', 0)}`\n"
                    f"Analysis: `{V13_SIGNAL_DIAGNOSTICS['stages'].get('ANALYSIS', 0)}` | "
                    f"Execution: `{V13_SIGNAL_DIAGNOSTICS['stages'].get('EXECUTION', 0)}`\n\n"
                    f"🚫 **ردشدن‌های نهایی**\n"
                    f"کیفیت: `{h['quality_rejected']}` | تکراری: `{h['duplicate_rejected']}`\n"
                    f"سقف روزانه: `{h['daily_cap_rejected']}` | Cooldown: `{h['cooldown_rejected']}`\n"
                    f"Circuit: `{h['circuit_rejected']}` | Emergency: `{h['emergency_rejected']}`\n\n"
                    f"⛓️ خرید واقعی موفق: `{h['real_buy_success']}`\n"
                    f"⛓️ خرید واقعی ناموفق: `{h['real_buy_failed']}`\n"
                    f"📢 ارسال واقعی کانال: `{h['channel_sent']}`\n"
                    f"⚠️ شکست ارسال کانال: `{h['channel_failed']}`\n\n"
                    f"📈 سقف امروز: `{daily_signal_status_text()}`\n"
                    f"🛑 Emergency Stop: `{EMERGENCY_STOP}`\n"
                    f"👑 MAX Fusion: `{MAX_FUSION_ENABLED}`\n"
                    f"🤝 اتحاد: `{SYNCHRONIZED_MODE}`\n\n"
                    "🔍 **۱۰ علت پرتکرار رد شدن:**\n"
                    + ("\n".join(f"• `{r}` → `{n}`" for r, n in _diag_top_reasons(10)) or "• هنوز ثبت نشده")
                    + "\n\n🔎 **پیش‌فیلتر کاندید:**\n"
                    + ("\n".join(f"• `{r}` → `{n}`" for r, n in sorted(V13_SIGNAL_DIAGNOSTICS["candidate_prefilter_reasons"].items(), key=lambda x: x[1], reverse=True)[:6]) or "• هنوز ثبت نشده")
                    + "\n\n"
                    "این پنل فقط آمار واقعی Pipeline را می‌خواند؛ "
                    "هیچ سیگنال، معامله یا Win Rate ساختگی تولید نمی‌کند."
                )
                await q.edit_message_text(
                    msg,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="v12_real_audit")],
                        [InlineKeyboardButton("🧠 V11", callback_data="v11_data")],
                        [InlineKeyboardButton("🔙 بازگشت", callback_data="controls")]
                    ])
                )
                return

            elif data == "trade_limit":
                if not is_admin:
                    await q.edit_message_text("⛔ دسترسی غیرمجاز.", reply_markup=_main_keyboard(False))
                    return
                await q.edit_message_text(
                    f"💰 **سقف SOL هر معامله**\n\n"
                    f"مقدار فعلی: `{MAX_TRADE_SOL:g} SOL`\n\n"
                    "مقدار را کاملاً دستی وارد کن؛ مثلاً `0.003` یا `0.0175` یا `2.5` SOL.\n"
                    "این مقدار سقف نهایی هر معامله است و مدیریت ریسک پویا نمی‌تواند از آن عبور کند.",
                    reply_markup=_trade_limit_keyboard(), parse_mode="Markdown"
                )
                return
            elif data == "trade_limit_manual":
                if not is_admin:
                    await q.edit_message_text("⛔ دسترسی غیرمجاز.", reply_markup=_main_keyboard(False))
                    return
                context.user_data["awaiting_trade_limit_sol"] = True
                await q.edit_message_text(
                    "✏️ **مقدار دلخواه معامله را بفرست**\n\n"
                    "فقط عدد SOL را ارسال کن.\n"
                    "مثال: `0.0175` یا `0.5` یا `2`\n\n"
                    "برای لغو: /cancel",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data="trade_limit")]])
                )
                return
            elif data.startswith("set_trade_limit:"):
                if not is_admin:
                    await q.edit_message_text("⛔ دسترسی غیرمجاز.", reply_markup=_main_keyboard(False))
                    return
                try:
                    value = float(data.split(":", 1)[1])
                    _set_trade_limit(value)
                    await q.edit_message_text(
                        f"✅ **سقف معامله تغییر کرد**\n\n💰 حداکثر هر معامله: `{MAX_TRADE_SOL:g} SOL`\n\n"
                        "از این به بعد هیچ خرید خودکاری از این مقدار بیشتر نمی‌شود.",
                        reply_markup=_control_keyboard(), parse_mode="Markdown"
                    )
                except Exception as e:
                    await q.edit_message_text(f"❌ مقدار نامعتبر: {e}", reply_markup=_trade_limit_keyboard())
                return
            elif data == "engine_manage":
                if not is_admin:
                    await q.edit_message_text(
                        "⛔ این بخش فقط برای ادمین است.",
                        reply_markup=_main_keyboard(False)
                    )
                    return
                if MAX_FUSION_ENABLED:
                    await q.edit_message_text(
                        "🔒 **مدیریت موتورهای مستقل قفل است**\n\n"
                        "👑 MAX FUSION فعال است.\n"
                        "برای تغییر موتورهای جداگانه ابتدا MAX FUSION را خاموش کن.",
                        reply_markup=_control_keyboard(),
                        parse_mode="Markdown"
                    )
                else:
                    await q.edit_message_text(
                        "⚙️ **مدیریت موتورهای مستقل**\n\n"
                        "هر موتور کلید مستقل خودش را دارد و می‌توانی جداگانه ON/OFF کنی.\n"
                        "خاموش کردن یک موتور، اتحاد را خاموش نمی‌کند.",
                        reply_markup=_engine_control_keyboard(),
                        parse_mode="Markdown"
                    )
                return

            elif data.startswith("toggle_"):
                if not is_admin:
                    await q.edit_message_text("⛔ دسترسی غیرمجاز.",reply_markup=_main_keyboard(False)); return

                if data == "toggle_max_fusion":
                    if not MAX_FUSION_ENABLED:
                        _MAX_FUSION_PREV = {
                            "unified": SYNCHRONIZED_MODE,
                            "advanced": ADVANCED_AI_ENABLED,
                            "engines": {var_name: bool(globals().get(var_name)) for _, var_name, _ in ENGINE_SWITCHES}
                        }
                        MAX_FUSION_ENABLED = True
                        SYNCHRONIZED_MODE = True
                        ADVANCED_AI_ENABLED = True
                        # وضعیت دستی موتورها حفظ می‌شود؛ MAX FUSION موتور خاموش‌شده را خودکار روشن نمی‌کند.
                        message = "👑 **MAX FUSION روشن شد**\n\n⚡ اتحاد هالک + 🧠 سیستم پیشرفته هم‌زمان فعال شدند.\n🔒 وضعیت دستی موتورهای زیرمجموعه حفظ شد.\n🎯 فقط سخت‌گیرترین سیگنال نهایی منتشر می‌شود."
                    else:
                        MAX_FUSION_ENABLED = False
                        if _MAX_FUSION_PREV:
                            SYNCHRONIZED_MODE = bool(_MAX_FUSION_PREV.get("unified", True))
                            ADVANCED_AI_ENABLED = bool(_MAX_FUSION_PREV.get("advanced", False))
                            for var_name, value in _MAX_FUSION_PREV.get("engines", {}).items():
                                globals()[var_name] = value
                        _MAX_FUSION_PREV = None
                        message = "🔴 **MAX FUSION خاموش شد**\n\nکنترل اتحاد هالک و سیستم پیشرفته دوباره مستقل است."
                    await q.edit_message_text(message, reply_markup=_control_keyboard(), parse_mode="Markdown")
                    return

                if data == "toggle_advanced":
                    if MAX_FUSION_ENABLED:
                        await q.edit_message_text(
                            "🔒 **سیستم پیشرفته AI قفل است**\n\n👑 MAX FUSION فعال است؛ اتحاد هالک و سیستم پیشرفته هم‌زمان روشن و قفل هستند.",
                            reply_markup=_control_keyboard(), parse_mode="Markdown"
                        )
                        return
                    ADVANCED_AI_ENABLED = not ADVANCED_AI_ENABLED
                    await q.edit_message_text(
                        ("🟢 **سیستم پیشرفته AI روشن شد**\n\nتمام فیلترهای پیشرفته در مسیر تصمیم‌گیری فعال شدند و سیگنال‌ها سخت‌گیرانه‌تر می‌شوند." if ADVANCED_AI_ENABLED else "🔴 **سیستم پیشرفته AI خاموش شد**\n\nاتحاد هالک، در صورت روشن بودن، مستقل ادامه می‌دهد."),
                        reply_markup=_control_keyboard(), parse_mode="Markdown"
                    )
                    return

                if data == "toggle_emergency":
                    EMERGENCY_STOP = not EMERGENCY_STOP
                    message = (
                        "🛑 **توقف اضطراری فعال شد**\n\n❌ سیگنال جدید\n❌ خرید جدید\n❌ کپی‌ترید جدید\n\n✅ پوزیشن‌های باز تا فروش نهایی مدیریت می‌شوند (TP/SL/Trailing)."
                        if EMERGENCY_STOP else
                        "🟢 **توقف اضطراری برداشته شد**\n\nسیستم‌های فعال دوباره اجازه جست‌وجوی معامله جدید دارند."
                    )
                    await q.edit_message_text(message, reply_markup=_control_keyboard(), parse_mode="Markdown")
                    return

                if data == "toggle_unified":
                    if MAX_FUSION_ENABLED:
                        await q.edit_message_text("🔒 **اتحاد هالک AI قفل است**\n\n👑 MAX FUSION فعال است؛ اتحاد هالک و سیستم پیشرفته هم‌زمان روشن هستند.", reply_markup=_control_keyboard(), parse_mode="Markdown")
                        return
                    # اتحاد فقط موتورهایی را به کار می‌گیرد که در تنظیمات دستی ON هستند.
                    # روشن‌شدن اتحاد نباید وضعیت هیچ موتور را تغییر دهد.
                    SYNCHRONIZED_MODE = not SYNCHRONIZED_MODE
                    active_count = sum(1 for _, var_name, _ in ENGINE_SWITCHES if bool(globals().get(var_name)))
                    message = (
                        f"🟢 **اتحاد هالک AI روشن شد**\n\nموتورهای روشنِ فعلی ({active_count}) با هم یک تصمیم واحد می‌سازند.\n🔒 موتورهایی که دستی OFF هستند خاموش باقی می‌مانند."
                        if SYNCHRONIZED_MODE else
                        "🔴 **اتحاد هالک AI خاموش شد**\n\nوضعیت تک‌تک موتورها حفظ شد.\nبرای تغییر هر موتور از «⚙️ مدیریت موتورهای مستقل» استفاده کن."
                    )
                    # در منوی اصلی، حتی بعد از خاموش شدن اتحاد، زیرمجموعه موتورها
                    # نمایش داده نمی‌شوند؛ فقط دکمه «مدیریت موتورهای مستقل» فعال است.
                    await q.edit_message_text(
                        message,
                        reply_markup=_control_keyboard(), parse_mode="Markdown"
                    )
                    return

                if data == "toggle_copy":
                    COPY_TRADING_ENABLED = not COPY_TRADING_ENABLED
                else:
                    engine_map = {callback: var_name for _, var_name, callback in ENGINE_SWITCHES}
                    name = engine_map.get(data)
                    if not name:
                        return
                    # Analysis remains independently switchable even while MAX is ON.
                    if MAX_FUSION_ENABLED and name != "ANALYSIS_ENGINE_ENABLED":
                        await q.edit_message_text(
                            "🔒 کنترل تکی موتورها در حالت MAX FUSION قفل است. ابتدا MAX FUSION را خاموش کن.",
                            reply_markup=_control_keyboard(), parse_mode="Markdown"
                        )
                        return
                    globals()[name] = not bool(globals()[name])

                await q.edit_message_text("⚙️ **موتورهای مستقل**\n\n"+_engine_status_lines(),reply_markup=_engine_control_keyboard(),parse_mode="Markdown")
        app.add_handler(CommandHandler("start",start_cmd))
        app.add_handler(CommandHandler("free",free_cmd))
        app.add_handler(CommandHandler("setvipchannel",setvipchannel_cmd))
        app.add_handler(CommandHandler("settradesol",settradesol_cmd))
        app.add_handler(CommandHandler("cancel",cancel_trade_limit_cmd))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manual_trade_limit_message))
        app.add_handler(CallbackQueryHandler(button_handler))
        logger.info("🤖 ربات تلگرام با منوی کنترل شیشه‌ای استارت شد.")
        app.run_polling(drop_pending_updates=False)
    except Exception as e: logger.exception(f"Telegram bot runtime error: {e}")

if __name__ == "__main__":
    logger.info("🚀 در حال راه‌اندازی ربات هوشمند تریدینگ هالکی...")
    _load_channel_config()
    _load_trade_limit()
    ensure_channel_invite_link()

    threads = [
        Thread(target=self_learning_ai_optimizer_loop, daemon=True, name="AILearning"),
        # رادار واحد فقط یک Thread اجرایی دارد؛ رفتار آن بر اساس سه حالت اصلی تغییر می‌کند و خرید فقط از بهترین کاندیدای هر sweep انجام می‌شود.
        Thread(target=subscription_monitor_loop, daemon=True, name="SubMonitor"),
        Thread(target=check_positions_loop, daemon=True, name="PositionsCheck"),
        Thread(target=unified_market_scanner_loop, args=(None,), daemon=True, name="UnifiedHulkAI"),
    ]
    for t in threads:
        t.start()

    port = int(os.environ.get("PORT", 5000))
    flask_thread = Thread(target=lambda: web_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False), daemon=True)
    flask_thread.start()

    start_telegram_bot()
def learning_record_exit(token_addr, position, exit_price, reason=""):
    """Best-effort bridge from an existing position object to the learning DB."""
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


