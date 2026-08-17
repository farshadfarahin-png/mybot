# V31 FINAL MASTER TRADING BOT — $25K Min Liquidity, Independent/MAX Lanes, Trailing Lock & Full UI Preservation
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

# تنظیمات لاگینگ پیشرفته
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(threadName)s - %(message)s'
)
logger = logging.getLogger("HulkSolBot")

# قفل‌های همزمانی برای ایمنی کامل در ثردها
db_lock = RLock()
state_lock = Lock()
rpc_lock = Lock()

# ایجاد جلسه ارتباطی پرسرعت با قابلیت Re-use اتصالات
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
BOT_BUILD_VERSION = "V31-FINAL-MASTER-2026"

# ==========================================
# بخش مدیریت پیشرفته RPC چرخشی
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
# سوئیچ‌های کنترلی ربات
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

# جدول قفل سود پله‌ای و حد ضرر متحرک (Trailing Stop صعودی)
TRAILING_LOCK_TABLE = (
    (1000.0, 950.0), (750.0, 650.0), (500.0, 350.0), (300.0, 230.0),
    (200.0, 155.0), (150.0, 110.0), (100.0, 75.0), (75.0, 55.0),
    (50.0, 35.0), (40.0, 28.0), (30.0, 20.0), (25.0, 15.0), (20.0, 10.0),
    (15.0, 7.0), (10.0, 3.0),
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

FIRE_BUY_AMOUNT_SOL = 0.01
FIRE_TAKE_PROFIT = 18.0
FIRE_STOP_LOSS = -10.0
FIRE_MIN_LIQUIDITY = 25000       
FIRE_MIN_VOLUME_5M = 4000       
FIRE_MIN_PRICE_CHANGE_5M = 4.0  

COMBO_BUY_AMOUNT_SOL = 0.01
COMBO_TAKE_PROFIT = 18.0
COMBO_STOP_LOSS = -10.0
COMBO_MIN_LIQUIDITY = 25000
COMBO_MIN_VOLUME_5M = 10000  
COMBO_MIN_CHANGE_5M = 15.0   

GOLDEN_BUY_AMOUNT_SOL = 0.01
GOLDEN_TAKE_PROFIT = 16.0
GOLDEN_STOP_LOSS = -8.0
GOLDEN_MIN_LIQUIDITY = 25000
GOLDEN_MIN_VOLUME_5M = 12000
GOLDEN_MIN_CHANGE_5M = 12.0

MAX_TRADE_SOL = float(os.environ.get("MAX_TRADE_SOL", "0.01"))
TECH_BUY_AMOUNT_SOL = 0.01
TECH_TAKE_PROFIT = 20.0
TECH_STOP_LOSS = -8.0
TECH_MIN_LIQUIDITY = 25000
TECH_MIN_VOLUME_5M = 8000

AWAITING_STATE = None 
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
            logger.info("✅ دیتابیس با قابلیت WAL مقداردهی اولیه شد.")
        except Exception as e:
            logger.error(f"⚠️ خطای دیتابیس: {e}")

init_db()

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
    logger.info("🧠 موتور یادگیری تطبیقی فعال شد.")
    while True:
        if SELF_LEARNING_AI_ENABLED:
            try:
                with db_lock:
                    conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
                    state = _update_adaptive_learning(conn)
                    conn.close()
            except Exception as e:
                logger.error(f"⚠️ خطای موتور یادگیری: {e}")
        time.sleep(180)

def check_social_sentiment_and_hype(pair):
    if not SOCIAL_SENTIMENT_ENABLED:
        return True, "فیلتر سنتیمنت غیرفعال"
    try:
        txns = pair.get('txns', {}).get('m5', {})
        buys = txns.get('buys', 0)
        sells = txns.get('sells', 0)
        if sells == 0 or buys >= (sells * 1.15):
            return True, "تایید سنتیمنت و هجوم خریداران 🚀"
        return True, "گذر از سنتیمنت پایه"
    except Exception as e:
        return True, "گذر از سنتیمنت"

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
                        if addr: found.append(addr)
            elif isinstance(res, dict):
                for pair in res.get("pairs", []):
                    if pair.get("chainId") == "solana":
                        addr = pair.get("baseToken", {}).get("address")
                        if addr: found.append(addr)
            return found
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=MARKET_DISCOVERY_WORKERS, thread_name_prefix="MarketDiscovery") as ex:
        for found in ex.map(fetch_endpoint, endpoints):
            for addr in found:
                if addr not in tokens:
                    tokens.append(addr)
    return tokens

# ==========================================================
# تنظیمات نقدینگی استخر روی ۲۵۰۰۰ دلار
# ==========================================================
CONSENSUS_MIN_SCORE = 4.0
CONSENSUS_MIN_RATIO = 0.55
CONSENSUS_COOLDOWN_SECONDS = 120
DAILY_SIGNAL_LIMIT = 25
GLOBAL_SIGNAL_COOLDOWN_SECONDS = 3 * 60
SIGNAL_BUDGET_MIN = 1
SIGNAL_BUDGET_MAX = 50
last_global_signal_time = 0.0
UNIFIED_LAST_EMIT_TIME = 0.0

CONSENSUS_MIN_LIQUIDITY = 25000.0    # حداقل نقدینگی پایه: ۲۵۰۰۰ دلار
CONSENSUS_MIN_VOLUME_5M = 3000.0     # حداقل حجم ۵ دقیقه: ۳۰۰۰ دلار
CONSENSUS_MIN_CHANGE_5M = 0.5
CONSENSUS_MAX_CHANGE_5M = 40.0
CONSENSUS_MIN_BUY_RATIO = 1.15

CANDIDATE_MIN_LIQUIDITY = 25000.0
CANDIDATE_MIN_VOLUME_5M = 1500.0
CANDIDATE_MIN_BUY_RATIO = 1.10
CANDIDATE_MIN_BUYS = 2

FINAL_ANALYSIS_MIN_LIQUIDITY = 25000.0
FINAL_ANALYSIS_MIN_VOLUME_5M = 3000.0
FINAL_ANALYSIS_MIN_BUY_RATIO = 1.15
FINAL_BREAKOUT_MIN_VOLUME_5M = 4000.0
FINAL_SUPPORT_MIN_VOLUME_5M = 3000.0
ADAPTIVE_TARGET_WIN_RATE = 80.0
ADAPTIVE_LOOKBACK = 20
ADAPTIVE_MIN_SAMPLE = 10
consensus_last_signal = {}

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

def _diag_reject(category, reason, token_addr=""):
    logger.debug(f"⛔ رد سیگنال [{category}] - دلیل: {reason} | توکن: {token_addr}")

def _analysis_diag(stage, token_addr=""):
    logger.debug(f"🔍 مرحله تحلیل [{stage}] | توکن: {token_addr}")

# تابع ایمن دریافت پِیر با حل کامل باگ Unpack
def _fetch_best_solana_pair(token_addr):
    try:
        res = http_session.get(
            f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}",
            timeout=2.5
        )
        if res.status_code != 200:
            return token_addr, []
        data = res.json() or {}
        pairs = data.get("pairs") or []
        sol_pairs = [p for p in pairs if isinstance(p, dict) and p.get("chainId") == "solana"]
        if not sol_pairs:
            return token_addr, []
        sol_pairs.sort(key=lambda x: float((x.get("liquidity") or {}).get("usd") or 0), reverse=True)
        return token_addr, sol_pairs[:3]
    except Exception as e:
        logger.debug(f"Fetch pair error for {token_addr}: {e}")
        return token_addr, []

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

        # نقدینگی باید بالای ۲۵۰۰۰ دلار باشد
        if liq < STRUCTURE_MIN_SUPPORT_LIQUIDITY or vol < STRUCTURE_MIN_SUPPORT_VOLUME_5M or buy_ratio < STRUCTURE_MIN_SUPPORT_BUY_RATIO:
            return False, {"structure": "WEAK_STRUCTURE_FLOW", "structure_score": 0.0}

        return True, {"structure": "PASSED", "structure_score": 3.0}
    except Exception as e:
        logger.error(f"⚠️ خطای تحلیل ساختار بازار: {e}")
        return True, {"structure": "ERROR_BYPASS", "structure_score": 0.0}

FAST_SCAN_INTERVAL_SECONDS = 0.20
MARKET_DISCOVERY_WORKERS = 16
PAIR_SCAN_WORKERS = 32
ELITE_DISCOVERY_REFRESH_SECONDS = 0.40
ELITE_PAIR_TIMEOUT_SECONDS = 1.50
ELITE_VOTE_WORKERS = 12
ELITE_MAX_UNIQUE_TOKENS = 1200
_elite_market_cache = []
_elite_market_cache_time = 0.0
_elite_market_refresh_lock = Lock()
_elite_market_refresh_thread = None

TRUE_HUNTER_BATCH_SIZE = 64
_TRUE_HUNTER_CURSOR = 0
_TRUE_HUNTER_CURSOR_LOCK = Lock()
_sentinel_memory = {}
_sentinel_lock = Lock()

def _sentinel_ratio(buys, sells):
    return float(buys) / max(1.0, float(sells))

def _sentinel_rank_pair(pair):
    try:
        liq = float(((pair.get("liquidity") or {}).get("usd")) or 0)
        vol = float(((pair.get("volume") or {}).get("m5")) or 0)
        chg = float(((pair.get("priceChange") or {}).get("m5")) or 0)
        tx = (pair.get("txns") or {}).get("m5", {}) or {}
        buys = int(tx.get("buys", 0) or 0)
        sells = int(tx.get("sells", 0) or 0)
        br = _sentinel_ratio(buys, sells)
        return (
            min(5.0, math.log10(max(1.0, liq)) - 3.0) +
            min(5.0, math.log10(max(1.0, vol)) - 2.0) +
            min(4.0, max(0.0, chg) / 5.0) +
            min(3.0, max(0.0, br - 1.0))
        )
    except Exception:
        return -999.0

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
            _sentinel_memory[token_addr] = {"ts": now, "score": base, "chg": chg, "vol": vol, "liq": liq, "br": br}
        if not old or now - old.get("ts", 0) > 120.0:
            return 0.0
        return 1.0
    except Exception:
        return 0.0

def _active_subengine_votes(token_addr, pair):
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
            return name if fn() else None
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
        with ThreadPoolExecutor(max_workers=min(ELITE_VOTE_WORKERS, len(advanced_jobs)), thread_name_prefix="AdvVote") as ex:
            for result in ex.map(lambda job: run_advanced(job[0], job[1]), advanced_jobs):
                if result: advanced_votes.append(result)

    if IS_RUNNING and chg >= 3 and vol >= 3000: hulk_votes.append("Fire")
    if TREND_ALERT_RUNNING and chg >= 5 and buys >= max(1, sells): hulk_votes.append("Trend")
    if COMBO_RUNNING and buys > sells and vol >= 5000 and liq >= 25000: hulk_votes.append("Combo")
    if GOLDEN_OPTION and chg >= 8 and vol >= 7000 and liq >= 25000: hulk_votes.append("Golden")
    if MEMPOOL_SMART_MONEY_ENABLED and buys >= max(2, int(sells * 1.20) + 1) and vol >= 5000 and liq >= 25000: hulk_votes.append("Mempool/SmartMoney")
    if BOTTOM_WHALE_RUNNING and buys >= max(3, sells + 2) and vol >= 5000: hulk_votes.append("Whale")
    if ANTI_WASH_TRADING_ENABLED and not (sells > 0 and buys < sells * 0.8): hulk_votes.append("Anti-Wash")

    all_votes = advanced_votes + hulk_votes
    return {
        "advanced_votes": advanced_votes, "hulk_votes": hulk_votes, "votes": all_votes,
        "advanced_count": len(advanced_votes), "hulk_count": len(hulk_votes), "all_count": len(all_votes),
    }

def _candidate_prefilter(pair):
    try:
        price = float(pair.get("priceUsd", 0) or 0)
        liq = float((pair.get("liquidity") or {}).get("usd", 0) or 0)
        vol = float((pair.get("volume") or {}).get("m5", 0) or 0)
        tx = (pair.get("txns") or {}).get("m5", {}) or {}
        buys = int(tx.get("buys", 0) or 0)
        sells = int(tx.get("sells", 0) or 0)
        ratio = buys / max(1, sells)
        token_addr = (pair.get("baseToken") or {}).get("address", "")
        if price <= 0 or liq < CANDIDATE_MIN_LIQUIDITY or vol < CANDIDATE_MIN_VOLUME_5M or buys < CANDIDATE_MIN_BUYS or ratio < CANDIDATE_MIN_BUY_RATIO:
            return False
        return True
    except Exception:
        return False

def _mode_market_quality(pair):
    price = float(pair.get("priceUsd", 0) or 0)
    liq = float((pair.get("liquidity") or {}).get("usd", 0) or 0)
    vol = float((pair.get("volume") or {}).get("m5", 0) or 0)
    chg = float((pair.get("priceChange") or {}).get("m5", 0) or 0)
    txns = (pair.get("txns") or {}).get("m5", {}) or {}
    buys = int(txns.get("buys", 0) or 0)
    sells = int(txns.get("sells", 0) or 0)
    if price <= 0 or liq < CONSENSUS_MIN_LIQUIDITY or vol < CONSENSUS_MIN_VOLUME_5M or chg < CONSENSUS_MIN_CHANGE_5M or chg > CONSENSUS_MAX_CHANGE_5M or buys <= 0 or (sells > 0 and buys < max(1, int(sells * CONSENSUS_MIN_BUY_RATIO))):
        return None
    return {"price": price, "liq": liq, "vol": vol, "chg": chg, "buys": buys, "sells": sells}

def build_consensus_signal(token_addr, pair):
    try:
        q = _mode_market_quality(pair)
        if not q: return None
        structure_ok, structure = _market_structure_gate(token_addr, pair)
        if not structure_ok: return None

        evidence = _active_subengine_votes(token_addr, pair)
        adv = evidence["advanced_count"]
        hulk = evidence["hulk_count"]

        if MAX_FUSION_ENABLED:
            mode = "MAX FUSION"
            if adv < 1 or hulk < 1: return None
            strength = adv * 1.25 + hulk * 1.35
        elif ADVANCED_AI_ENABLED:
            mode = "سیستم پیشرفته AI"
            if adv < 1: return None
            strength = adv * 1.35 + (hulk * 0.15)
        elif SYNCHRONIZED_MODE:
            mode = "اتحاد هالک AI"
            if hulk < 1: return None
            strength = hulk * 1.40 + (adv * 0.15)
        else:
            return None

        buy_ratio = q["buys"] / max(1, q["sells"])
        score = strength + min(5.0, q["chg"] / 5.0) + min(4.0, q["vol"] / 10000.0) + min(3.0, q["liq"] / 50000.0)
        score += min(3.0, max(0.0, buy_ratio - 1.0))
        score += float(structure.get("structure_score", 0.0) or 0.0)

        now = time.time()
        if now - consensus_last_signal.get(token_addr, 0) < CONSENSUS_COOLDOWN_SECONDS:
            return None

        return {
            "score": float(score), "strength": float(strength),
            "votes": evidence["votes"], "advanced_votes": evidence["advanced_votes"],
            "hulk_votes": evidence["hulk_votes"], "engines": evidence["votes"],
            "mode": mode, **q,
            "symbol": (pair.get("baseToken") or {}).get("symbol", "TOKEN"),
            "tp": max(15.0, min(30.0, 14.0 + min(12.0, score))), "sl": -8.0,
            "structure": structure.get("structure", "UNKNOWN"),
            "support": float(structure.get("support", 0.0) or 0.0),
            "resistance": float(structure.get("resistance", 0.0) or 0.0),
            "breakout": bool(structure.get("breakout", False)),
        }
    except Exception:
        return None

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

# سیستم یادگیری و مدیریت پوزیشن‌ها
LEARNING_FILE = "fusion_learning.json"
MAX_HISTORY = 5000
MAX_CONSECUTIVE_LOSSES = 4
RISK_MIN_MULTIPLIER = 0.25
RISK_MAX_MULTIPLIER = 1.25
LEARNING_ALPHA = 0.12

learning_state = {"trades": [], "engines": {}, "consecutive_losses": 0, "paused_until": 0.0}

def _load_learning_state():
    global learning_state
    try:
        p = Path(LEARNING_FILE)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict): learning_state.update(data)
    except Exception: pass

def _save_learning_state():
    try:
        tmp = Path(LEARNING_FILE + ".tmp")
        tmp.write_text(json.dumps(learning_state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(LEARNING_FILE)
    except Exception: pass

def record_closed_trade(token_addr, symbol, side, entry, exit_price, pnl_pct, reason="", engine_names=None, hold_seconds=0, regime="UNKNOWN"):
    try:
        pnl = float(pnl_pct)
        item = {
            "ts": time.time(), "token": token_addr, "symbol": symbol, "side": side,
            "entry": float(entry or 0), "exit": float(exit_price or 0), "pnl_pct": pnl,
            "reason": reason, "engines": list(engine_names or []), "hold_seconds": int(hold_seconds or 0)
        }
        learning_state["trades"].append(item)
        learning_state["trades"] = learning_state["trades"][-MAX_HISTORY:]
        if pnl < 0:
            learning_state["consecutive_losses"] = int(learning_state.get("consecutive_losses", 0) or 0) + 1
        else:
            learning_state["consecutive_losses"] = 0
        _save_learning_state()
    except Exception: pass

def learning_is_in_circuit_breaker():
    return time.time() < float(learning_state.get("paused_until", 0) or 0) or int(learning_state.get("consecutive_losses", 0) or 0) >= MAX_CONSECUTIVE_LOSSES

def learning_risk_multiplier():
    losses = int(learning_state.get("consecutive_losses", 0) or 0)
    mult = 1.0 - min(0.75, losses * 0.12)
    return max(RISK_MIN_MULTIPLIER, min(RISK_MAX_MULTIPLIER, mult))

def learning_stats():
    trades = learning_state.get("trades", [])
    wins = sum(1 for t in trades if float(t.get("pnl_pct", 0) or 0) > 0)
    pnl = sum(float(t.get("pnl_pct", 0) or 0) for t in trades)
    return {"trades": len(trades), "wins": wins, "win_rate": (wins / len(trades) * 100.0) if trades else 0.0, "net_pnl_pct_sum": pnl, "loss_streak": int(learning_state.get("consecutive_losses", 0) or 0)}

_load_learning_state()

V12_REAL_AUDIT = {"scans": 0, "tokens_seen": 0, "pairs_seen": 0, "fusion_candidates": 0, "analysis_candidates": 0, "real_buy_success": 0, "real_buy_failed": 0, "channel_sent": 0, "channel_failed": 0, "last_scan": 0.0, "last_signal": 0.0}
for _k in ("analysis_selected", "analysis_submit_attempted", "analysis_submit_called", "analysis_submit_failed", "analysis_worker_exception", "analysis_execution_success", "analysis_execution_failed"):
    V12_REAL_AUDIT.setdefault(_k, 0)

V13_SIGNAL_DIAGNOSTICS = {"total": 0, "candidate_prefilter_pass": 0, "candidate_prefilter_reject": 0, "candidate_prefilter_reasons": {}, "analysis": {"scanned": 0, "selected": 0, "candidates": 0, "submitted": 0, "rejected": 0, "reasons": {}}, "reasons": {}, "stages": {}}

def _audit_signal_decision(reason):
    pass

# ==========================================================
# استقلال کامل موتورها برای جستجو و صدور سیگنال
# ==========================================================
def _active_independent_engine_names():
    adv_names = ["Technical", "UltimateAI/21", "Social/Hype", "SmartFilter"]
    special_names = ["Analysis"]
    hulk_names = ["Fire", "Trend", "Combo", "Golden", "Mempool/SmartMoney", "Whale", "Anti-Wash"]
    active = []
    for name in adv_names + hulk_names + special_names:
        var = next((v for n, v, _ in ENGINE_SWITCHES if n == name), None)
        if var and bool(globals().get(var)):
            active.append(name)
    return active

def _candidate_rank_tuple(item):
    _, c = item
    return (float(c.get("rank_score", c.get("score", 0.0)) or 0.0), float(c.get("score", 0.0) or 0.0), float(c.get("chg", 0.0) or 0.0))

def _independent_engine_candidate(token_addr, pair, engine_name):
    q = _mode_market_quality(pair)
    if not q: return None
    structure_ok, structure = _market_structure_gate(token_addr, pair)
    if not structure_ok: return None
    chg, vol, liq = q["chg"], q["vol"], q["liq"]
    buys, sells = q["buys"], q["sells"]
    try:
        ok = False
        strength = 0.0
        if engine_name == "Technical": ok = bool(TECHNICAL_RUNNING and check_major_support_resistance_pa(pair)[0]); strength = 6.0
        elif engine_name == "UltimateAI/21": ok = bool(ULTIMATE_21_ENGINE_ENABLED and evaluate_ultimate_super_signal(token_addr, pair)[0]); strength = 7.0
        elif engine_name == "Social/Hype": ok = bool(SOCIAL_SENTIMENT_ENABLED and check_social_sentiment_and_hype(pair)[0]); strength = 6.0
        elif engine_name == "SmartFilter": ok = bool(SMART_FILTER_ENABLED and is_token_worthy(pair)); strength = 6.0
        elif engine_name == "Fire": ok = bool(IS_RUNNING and chg >= 3 and vol >= 3000); strength = 5.5
        elif engine_name == "Trend": ok = bool(TREND_ALERT_RUNNING and chg >= 5 and buys >= max(1, sells)); strength = 6.0
        elif engine_name == "Combo": ok = bool(COMBO_RUNNING and buys > sells and vol >= 5000 and liq >= 25000); strength = 6.5
        elif engine_name == "Golden": ok = bool(GOLDEN_OPTION and chg >= 8 and vol >= 7000 and liq >= 25000); strength = 7.0
        elif engine_name == "Mempool/SmartMoney": ok = bool(MEMPOOL_SMART_MONEY_ENABLED and buys >= max(2, int(sells * 1.20) + 1) and vol >= 5000 and liq >= 25000); strength = 7.0
        elif engine_name == "Whale": ok = bool(BOTTOM_WHALE_RUNNING and buys >= max(3, sells + 2) and vol >= 5000); strength = 7.0
        elif engine_name == "Anti-Wash": ok = bool(ANTI_WASH_TRADING_ENABLED and not (sells > 0 and buys < sells * 0.8)); strength = 5.5
        if not ok: return None

        buy_ratio = buys / max(1, sells)
        score = (strength + min(5.0, chg / 5.0) + min(4.0, vol / 10000.0) + min(3.0, liq / 50000.0) + min(3.0, max(0.0, buy_ratio - 1.0)))
        if score < 4.0: return None
        now = time.time()
        cooldown_key = f"{token_addr}:{engine_name}"
        if now - consensus_last_signal.get(cooldown_key, 0) < CONSENSUS_COOLDOWN_SECONDS: return None
        group = "ADVANCED" if engine_name in ("Technical", "UltimateAI/21", "Social/Hype", "SmartFilter") else "HULK"
        return {
            "score": float(score), "strength": float(strength), "votes": [engine_name],
            "advanced_votes": [engine_name] if group == "ADVANCED" else [],
            "hulk_votes": [engine_name] if group == "HULK" else [], "engines": [engine_name],
            "mode": f"سیستم پیشرفته AI — {engine_name}" if group == "ADVANCED" else f"اتحاد هالک AI — {engine_name}",
            "hunter_group": group, **q, "symbol": (pair.get("baseToken") or {}).get("symbol", "TOKEN"),
            "tp": max(15.0, min(30.0, 14.0 + min(12.0, score))), "sl": -8.0,
            "structure": structure.get("structure", "UNKNOWN"), "support": float(structure.get("support", 0.0) or 0.0),
            "resistance": float(structure.get("resistance", 0.0) or 0.0), "breakout": bool(structure.get("breakout", False))
        }
    except Exception:
        return None

def _analysis_engine_candidate(token_addr, pair):
    if not ANALYSIS_ENGINE_ENABLED: return None
    try:
        price = float(pair.get("priceUsd", 0) or 0)
        liq = float((pair.get("liquidity") or {}).get("usd", 0) or 0)
        vol = float((pair.get("volume") or {}).get("m5", 0) or 0)
        chg = float((pair.get("priceChange") or {}).get("m5", 0) or 0)
        tx = (pair.get("txns") or {}).get("m5", {}) or {}
        buys = int(tx.get("buys", 0) or 0)
        sells = int(tx.get("sells", 0) or 0)
        buy_ratio = buys / max(1, sells)
        if price <= 0 or liq < CANDIDATE_MIN_LIQUIDITY or vol < CANDIDATE_MIN_VOLUME_5M or buys < 1 or buy_ratio < CANDIDATE_MIN_BUY_RATIO:
            return None

        samples = _update_structure_memory(token_addr, price)
        score = 6.0 + min(2.0, buy_ratio - 1.0) + min(1.5, vol / 10000.0) + min(1.0, liq / 50000.0)
        now = time.time()
        if now - consensus_last_signal.get(f"{token_addr}:Analysis", 0) < CONSENSUS_COOLDOWN_SECONDS: return None
        q = {"price": price, "liq": liq, "vol": vol, "chg": chg, "buys": buys, "sells": sells}
        return {
            "score": float(score), "strength": float(score), "votes": ["Analysis"],
            "advanced_votes": [], "hulk_votes": [], "engines": ["Analysis"], "hunter_group": "ANALYSIS",
            "mode": "📈 موتور تحلیل", "reason": "تأیید ساختار بازار + نقدینگی استخر بالای ۲۵k", **q,
            "symbol": (pair.get("baseToken") or {}).get("symbol", "TOKEN"),
            "tp": max(15.0, min(28.0, 16.0 + min(10.0, score))), "sl": -8.0,
            "structure": "ANALYSIS_SUPPORT_BOUNCE", "support": float(price), "resistance": float(price), "breakout": False
        }
    except Exception:
        return None

def _evaluate_token_for_active_modes(token_addr):
    token_addr, pairs = _fetch_best_solana_pair(token_addr)
    result = {"analysis": [], "fusion": []}
    if not pairs: return token_addr, result

    active = _active_independent_engine_names()
    analysis_enabled = ("Analysis" in active) and ANALYSIS_ENGINE_ENABLED

    for pair in pairs:
        # ۱. موتور تحلیل مستقل
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
            except Exception: pass

        # ۲. سایر موتورها یا حالت MAX Fusion
        if not _candidate_prefilter(pair): continue
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
                    if engine_name == "Analysis": continue
                    is_adv = engine_name in ("Technical", "UltimateAI/21", "Social/Hype", "SmartFilter")
                    if is_adv and not ADVANCED_AI_ENABLED: continue
                    if (not is_adv) and not SYNCHRONIZED_MODE: continue
                    fusion = _independent_engine_candidate(token_addr, pair, engine_name)
                    if fusion and fusion_quality_gate(fusion):
                        fusion = dict(fusion)
                        fusion["rank_score"] = _candidate_rank_tuple(fusion)[0]
                        result["fusion"].append((token_addr, fusion))
        except Exception: pass

    return token_addr, result

def _select_fusion_candidates(candidates):
    if not candidates: return []
    if MAX_FUSION_ENABLED: return [max(candidates, key=_candidate_rank_tuple)]
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
        return False, f"WORKER_EXCEPTION:{exc}"

def unified_market_scanner_loop(app):
    global _TRUE_HUNTER_CURSOR
    logger.info("%s / %s: CLEAN SIGNAL CORE started", UNIFIED_ENGINE_NAME, BOT_BUILD_VERSION)
    send_telegram_msg(f"🚀 رادار {BOT_BUILD_VERSION} فعال شد")

    def inc_audit(key, amount=1):
        try:
            V12_REAL_AUDIT[key] = int(V12_REAL_AUDIT.get(key, 0) or 0) + amount
        except Exception: pass

    while True:
        if not new_trade_system_enabled():
            time.sleep(FAST_SCAN_INTERVAL_SECONDS)
            continue
        try:
            V12_REAL_AUDIT["scans"] = int(V12_REAL_AUDIT.get("scans", 0) or 0) + 1
            V12_REAL_AUDIT["last_scan"] = time.time()
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

            V12_REAL_AUDIT["tokens_seen"] = int(V12_REAL_AUDIT.get("tokens_seen", 0) or 0) + len(scan_tokens)
            analysis_candidates = []
            fusion_candidates = []

            with ThreadPoolExecutor(max_workers=PAIR_SCAN_WORKERS, thread_name_prefix="RadarEval") as ex:
                futures = {ex.submit(_evaluate_token_for_active_modes, token): token for token in scan_tokens if token and not _token_lock_is_open(token)}
                for future in __import__("concurrent.futures").as_completed(futures):
                    try:
                        token_addr, lanes = future.result()
                        for item in lanes.get("analysis", []):
                            analysis_candidates.append(item)
                            inc_audit("analysis_candidates")
                            V12_REAL_AUDIT["pairs_seen"] = int(V12_REAL_AUDIT.get("pairs_seen", 0) or 0) + 1
                        for item in lanes.get("fusion", []):
                            fusion_candidates.append(item)
                            inc_audit("fusion_candidates")
                    except Exception: pass

            if analysis_candidates:
                selected_analysis = max(analysis_candidates, key=lambda item: _candidate_rank_tuple(item[1]))
                inc_audit("analysis_selected")
                try:
                    inc_audit("analysis_submit_attempted")
                    future = ANALYSIS_EXECUTOR.submit(_analysis_submit_worker, selected_analysis[0], selected_analysis[1])
                    inc_audit("analysis_submit_called")
                    def _done(fut, addr=selected_analysis[0]):
                        try:
                            ok, _ = fut.result()
                            if ok: inc_audit("analysis_execution_success")
                            else: inc_audit("analysis_execution_failed")
                        except Exception: inc_audit("analysis_worker_exception")
                    future.add_done_callback(_done)
                except Exception:
                    inc_audit("analysis_submit_failed")

            for token_addr, candidate in _select_fusion_candidates(fusion_candidates):
                try:
                    SIGNAL_EXECUTOR.submit(send_fused_signal, token_addr, candidate)
                except Exception: pass
        except Exception: pass
        time.sleep(FAST_SCAN_INTERVAL_SECONDS)

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
                try { window.Telegram.WebApp.expand(); window.Telegram.WebApp.enableClosingConfirmation(); } catch (e) {}
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
                            <button type="button" class="btn" style="background: #8b5cf6;" onclick="openVipChannel()">📢 ورود به کانال VIP</button>
                            <div style="margin-top:14px;padding:12px;border:1px solid #334155;border-radius:12px;background:#0b1220;">
                              <div style="color:#38bdf8;font-weight:bold;margin-bottom:7px;">🤖 تنظیم حجم کپی‌ترید</div>
                              <input id="copyAmount" type="number" min="0.001" max="100" step="0.001" value="${data.copy_amount_sol || 0.01}" placeholder="حجم SOL">
                              <button type="button" class="btn btn-pay" onclick="saveCopyAmount()">💾 ذخیره حجم کپی‌ترید</button>
                            </div>
                        </div>
                    `;
                } else {
                    area.innerHTML = `
                        <p>وضعیت سیستم: <span class="badge-expired">نیازمند اشتراک VIP</span></p>
                        <div class="wallet-box">
                            <p style="font-size:11px; margin:0 0 5px 0; color:#38bdf8;">لطفاً مبلغ اشتراک ۳۰ روزه را به ولت زیر واریز کنید:</p>
                            <code style="word-break: break-all; font-size:11px; color:#facc15;">{{ wallet }}</code>
                        </div>
                        <h3 style="color: #c084fc; font-size: 14px;">اشتراک ۳۰ روزه VIP</h3>
                        <label style="font-size:11px; color:#94a3b8;">انتخاب ارز پرداخت:</label>
                        <select id="paymentCurrency" onchange="updatePaymentPrice()">
                            <option value="USDC">پرداخت با 50 USDC</option>
                        </select>
                        <p id="paymentPrice" style="color:#22c55e;font-weight:bold;text-align:center;"></p>
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
                el.textContent = `💳 مبلغ اشتراک: 50 USDC`;
            }
            function openVipChannel() {
                const link = (window.__VIP_CHANNEL_LINK || "").trim();
                if (link) window.location.href = link;
            }
            function saveCopyAmount() {
                const amount = Number(document.getElementById('copyAmount')?.value||0);
                fetch('/api/copy-settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({telegram_id:telegramId, trade_amount:amount})})
                .then(r=>r.json()).then(d=>alert(d.message));
            }
            function verifyAndPay() {
                const tId = document.getElementById('userTelegramId').value;
                const wallet = document.getElementById('userWallet').value;
                const txSig = document.getElementById('txSignature').value;
                fetch('/api/subscribe', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({telegram_id:tId, wallet_address:wallet, tx_signature:txSig, currency:'USDC'})})
                .then(res=>res.json()).then(data => { alert(data.message); if(data.status==='success') location.reload(); });
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
        except Exception: pass
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
    rows_html = "".join(f"<div class='row'>🆔 {r[0]}<br>💳 ولت: <span class='mono'>{r[1] or '-'}</span><br>⏳ انقضا: {r[2]}<br>📌 وضعیت: {r[4]}</div>" for r in subs) or "<div class='row'>هنوز کاربری ثبت نشده است.</div>"
    return f"""<!doctype html><html lang='fa' dir='rtl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>پنل مدیریت هالکی</title><style>body{{background:#07111f;color:#fff;font-family:Tahoma;padding:14px}}.wrap{{max-width:720px;margin:auto}}.card{{background:#101c2d;border:1px solid #24364f;border-radius:18px;padding:16px;margin:10px 0;box-shadow:0 8px 30px #0008}}h1,h2{{text-align:center}}h1{{font-size:20px;color:#38bdf8}}h2{{font-size:14px;color:#c084fc}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}}.stat{{background:#0b1524;border-radius:14px;padding:12px;text-align:center}}.value{{font-size:19px;font-weight:bold;color:#22c55e}}.row{{background:#0b1524;border-radius:12px;padding:10px;margin:7px 0;font-size:11px;line-height:1.8}}.mono{{word-break:break-all;color:#94a3b8}}</style></head><body><div class='wrap'><div class='card'><h1>👑 پنل مدیریت هوشمند هالکی</h1></div><div class='card'><h2>📊 آمار معاملات</h2><div class='grid'><div class='stat'>کل معاملات<br><span class='value'>{analytics['total_trades']}</span></div><div class='stat'>Win Rate<br><span class='value'>{analytics['win_rate']:.2f}%</span></div><div class='stat'>سود/زیان<br><span class='value'>{analytics['total_pct']:+.2f}%</span></div><div class='stat'>P/L دلاری<br><span class='value'>${analytics['total_usd']:+.2f}</span></div></div><p>🏆 بهترین: {best_str}</p><p>📉 بدترین: {worst_str}</p></div><div class='card'><h2>💼 ولت اصلی</h2><p>موجودی: <b>{wallet['sol']:.6f} SOL</b></p><p class='mono'>{wallet['pubkey']}</p></div><div class='card'><h2>👥 کاربران و اشتراک‌ها</h2>{rows_html}</div></div></body></html>"""

@web_app.route('/api/copy-settings', methods=['POST'])
def api_copy_settings():
    data = request.json or {}
    t_id = str(data.get('telegram_id') or '').strip()
    try: amount = float(data.get('trade_amount'))
    except Exception: return jsonify({'status':'error','message':'حجم نامعتبر'}), 400
    with db_lock:
        conn = sqlite3.connect('bot_analytics.db', timeout=30.0, check_same_thread=False)
        cur = conn.cursor()
        cur.execute('UPDATE subscribers SET trade_amount_sol=?, copy_enabled=1 WHERE telegram_id=?', (amount, t_id))
        conn.commit(); conn.close()
    return jsonify({'status':'success', 'message':'تنظیمات کپی‌ترید ذخیره شد.'})

@web_app.route('/api/check-status')
def api_check_status():
    ensure_channel_invite_link()
    t_id = request.args.get("telegram_id", "")
    has_sub, expiry_str = False, ""
    if t_id:
        active, exp_date = check_user_subscription(t_id)
        if active and exp_date:
            has_sub = True; expiry_str = exp_date.strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({"has_subscription": has_sub, "expiry_date": expiry_str, "channel_link": CHANNEL_INVITE_LINK, "prices": {"USDC": VIP_PRICE_USDC}})

@web_app.route('/api/subscribe', methods=['POST'])
def api_subscribe():
    data = request.json or {}
    t_id = data.get("telegram_id"); wallet = data.get("wallet_address"); tx_sig = data.get("tx_signature")
    if not (t_id and wallet and tx_sig): return jsonify({"status": "error", "message": "اطلاعات ناقص است."}), 400
    success = register_subscription(t_id, wallet, tx_sig, "USDC")
    if success: return jsonify({"status": "success", "message": "اشتراک فعال شد!"})
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
    return f"🤖⚡ **{UNIFIED_ENGINE_NAME}**\n\nموتورهای فعال: `{active}/{len(components)}`\n\n{detail}"

def _main_keyboard(is_admin=False):
    rows=[[InlineKeyboardButton("📊 وضعیت موتورها",callback_data="engines"),InlineKeyboardButton("💼 وضعیت ولت",callback_data="wallet")],[InlineKeyboardButton("📈 آمار معاملات",callback_data="stats"),InlineKeyboardButton("🎛 کنترل موتورها",callback_data="controls")]]
    if WEBAPP_URL: rows.append([InlineKeyboardButton("📱 Mini App VIP",web_app=WebAppInfo(url=WEBAPP_URL))])
    elif CHANNEL_INVITE_LINK: rows.append([InlineKeyboardButton("📢 کانال VIP",url=CHANNEL_INVITE_LINK)])
    if is_admin:
        rows.append([InlineKeyboardButton("👑 پنل مدیریت",callback_data="admin"),InlineKeyboardButton("🔐 امنیت/وضعیت",callback_data="security")])
        rows.append([InlineKeyboardButton(f"🎯 سقف روزانه: {daily_signal_status_text()}", callback_data="daily_signal_limit")])
        rows.append([InlineKeyboardButton(f"📈 موتور تحلیل: {'🟢 ON' if ANALYSIS_ENGINE_ENABLED else '🔴 OFF'}", callback_data="toggle_engine_analysis")])
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
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ وارد کردن مقدار دلخواه SOL", callback_data="trade_limit_manual")],
        [InlineKeyboardButton("🔙 بازگشت به کنترل موتورها", callback_data="controls")]
    ])

def _engine_control_keyboard():
    rows = []
    engine_buttons = []
    for label, var_name, callback_name in ENGINE_SWITCHES:
        engine_buttons.append(InlineKeyboardButton(f"{label}: {'🟢 ON' if globals().get(var_name) else '🔴 OFF'}", callback_data=callback_name))
    for i in range(0, len(engine_buttons), 2):
        rows.append(engine_buttons[i:i+2])
    rows.append([InlineKeyboardButton("🔙 بازگشت به کنترل اصلی", callback_data="controls")])
    return InlineKeyboardMarkup(rows)

def _control_keyboard():
    if MAX_FUSION_ENABLED:
        hulk_label = "🔒 اتحاد هالک AI: 🟢 ON"
        advanced_label = "🔒 سیستم پیشرفته AI: 🟢 ON"
    else:
        hulk_label = f"🤖⚡ اتحاد هالک AI: {'🟢 ON' if SYNCHRONIZED_MODE else '🔴 OFF'}"
        advanced_label = f"🧠 سیستم پیشرفته AI: {'🟢 ON' if ADVANCED_AI_ENABLED else '🔴 OFF'}"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"👑 MAX FUSION: {'🟢 ON' if MAX_FUSION_ENABLED else '🔴 OFF'}", callback_data="toggle_max_fusion")],
        [InlineKeyboardButton(hulk_label, callback_data="toggle_unified")],
        [InlineKeyboardButton(advanced_label, callback_data="toggle_advanced")],
        [InlineKeyboardButton(f"🛑 توقف اضطراری: {'🔴 فعال' if EMERGENCY_STOP else '🟢 آماده'}", callback_data="toggle_emergency")],
        [InlineKeyboardButton("⚙️ مدیریت موتورهای مستقل", callback_data="engine_manage")],
        [InlineKeyboardButton(f"🤖 کپی‌ترید: {'🟢 ON' if COPY_TRADING_ENABLED else '🔴 OFF'}", callback_data="toggle_copy")],
        [InlineKeyboardButton(f"💰 سقف هر معامله: {MAX_TRADE_SOL:g} SOL", callback_data="trade_limit")],
        [InlineKeyboardButton(f"🎯 سقف روزانه سیگنال: {daily_signal_status_text()}", callback_data="daily_signal_limit")],
        [InlineKeyboardButton("📊 داشبورد PRO MAX", callback_data="v7_dashboard")],
        [InlineKeyboardButton("🧪 اعتبارسنجی V10", callback_data="v10_validation")],
        [InlineKeyboardButton("🧠 تحلیل داده‌محور V11", callback_data="v11_data")],
        [InlineKeyboardButton("🩺 عیب‌یابی واقعی سیگنال", callback_data="v12_real_audit")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="home")]
    ])

def start_telegram_bot():
    try:
        if not TELEGRAM_BOT_TOKEN:
            logger.error("❌ TELEGRAM_BOT_TOKEN تنظیم نشده است."); return
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        _load_daily_signal_state()
        
        async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id
            is_admin = bool(TELEGRAM_CHAT_ID and str(chat_id) == str(TELEGRAM_CHAT_ID))
            active, _ = check_user_subscription(chat_id)
            text = f"🤖⚡ **هالک AI — مرکز ربات هوشمند ترید**\n\n👑 MAX FUSION: {'🟢 ON' if MAX_FUSION_ENABLED else '🔴 OFF'}" if active else "🤖⚡ **هالک AI — سیستم هوشمند ترید**\n\n📡 سیستم آماده رصد بازار است."
            await update.message.reply_text(text, reply_markup=_main_keyboard(is_admin), parse_mode="Markdown")

        async def free_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
            cid = str(update.effective_user.id)
            if not (TELEGRAM_CHAT_ID and cid == str(TELEGRAM_CHAT_ID)): return
            if context.args: register_free_vip(str(context.args[0]).strip())

        async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            global IS_RUNNING, TREND_ALERT_RUNNING, COMBO_RUNNING, GOLDEN_OPTION, TECHNICAL_RUNNING, MEMPOOL_SMART_MONEY_ENABLED, BOTTOM_WHALE_RUNNING, COPY_TRADING_ENABLED, ULTIMATE_21_ENGINE_ENABLED, SOCIAL_SENTIMENT_ENABLED, ANTI_WASH_TRADING_ENABLED, SMART_FILTER_ENABLED, SYNCHRONIZED_MODE, ADVANCED_AI_ENABLED, MAX_FUSION_ENABLED, EMERGENCY_STOP, _MAX_FUSION_PREV, MAX_TRADE_SOL
            q = update.callback_query; await q.answer(); cid = str(q.from_user.id); is_admin = bool(TELEGRAM_CHAT_ID and cid == str(TELEGRAM_CHAT_ID)); data = q.data
            
            if data == "home":
                await q.edit_message_text("🤖⚡ **هالک AI — مرکز ربات هوشمند ترید**", reply_markup=_main_keyboard(is_admin), parse_mode="Markdown")
            elif data == "engines":
                await q.edit_message_text("🎛 **وضعیت موتورهای هوشمند**\n\n" + _engine_status_lines(), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="home")]]), parse_mode="Markdown")
            elif data == "controls":
                await q.edit_message_text("🎛 **کنترل موتورها**", reply_markup=_control_keyboard(), parse_mode="Markdown")
            elif data == "wallet" and is_admin:
                sol = get_sol_balance()
                await q.edit_message_text(f"💼 **ولت اصلی**\n\n💰 موجودی: `{sol:.6f} SOL`", reply_markup=_main_keyboard(True), parse_mode="Markdown")
            elif data == "stats":
                a = get_advanced_trade_analytics()
                await q.edit_message_text(f"📊 **آمار واقعی**\n\nمعاملات: `{a['total_trades']}`\nWin Rate: `{a['win_rate']:.2f}%`", reply_markup=_main_keyboard(is_admin), parse_mode="Markdown")
            elif data == "admin" and is_admin:
                await q.edit_message_text(f"👑 **پنل مدیریت**\n\nکاربران: `{len(get_all_subscribers())}`", reply_markup=_main_keyboard(True), parse_mode="Markdown")
            elif data == "engine_manage" and is_admin:
                await q.edit_message_text("⚙️ **مدیریت موتورهای مستقل**", reply_markup=_engine_control_keyboard(), parse_mode="Markdown")
            elif data.startswith("toggle_"):
                if not is_admin: return
                if data == "toggle_max_fusion":
                    MAX_FUSION_ENABLED = not MAX_FUSION_ENABLED
                    SYNCHRONIZED_MODE = MAX_FUSION_ENABLED
                    ADVANCED_AI_ENABLED = MAX_FUSION_ENABLED
                elif data == "toggle_advanced": ADVANCED_AI_ENABLED = not ADVANCED_AI_ENABLED
                elif data == "toggle_unified": SYNCHRONIZED_MODE = not SYNCHRONIZED_MODE
                elif data == "toggle_emergency": EMERGENCY_STOP = not EMERGENCY_STOP
                elif data == "toggle_copy": COPY_TRADING_ENABLED = not COPY_TRADING_ENABLED
                else:
                    engine_map = {callback: var_name for _, var_name, callback in ENGINE_SWITCHES}
                    name = engine_map.get(data)
                    if name: globals()[name] = not bool(globals()[name])
                await q.edit_message_text("🎛 **کنترل موتورها**", reply_markup=_control_keyboard(), parse_mode="Markdown")

        app.add_handler(CommandHandler("start", start_cmd))
        app.add_handler(CommandHandler("free", free_cmd))
        app.add_handler(CallbackQueryHandler(button_handler))
        logger.info("🤖 ربات تلگرام با موفقیت راه‌اندازی شد.")
        app.run_polling(drop_pending_updates=False)
    except Exception as e:
        logger.exception(f"Telegram bot runtime error: {e}")

if __name__ == "__main__":
    logger.info("🚀 در حال راه‌اندازی ربات هوشمند تریدینگ هالکی...")
    _load_channel_config()
    _load_trade_limit()
    ensure_channel_invite_link()

    threads = [
        Thread(target=self_learning_ai_optimizer_loop, daemon=True, name="AILearning"),
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
    try:
        if not position: return
        entry = float(position.get("entry_price") or position.get("price") or 0)
        if entry <= 0 or float(exit_price or 0) <= 0: return
        pnl = (float(exit_price) - entry) / entry * 100.0
        record_closed_trade(
            token_addr=token_addr, symbol=position.get("symbol", ""), side=position.get("side", "BUY"),
            entry=entry, exit_price=exit_price, pnl_pct=pnl, reason=reason,
            engine_names=position.get("engines") or position.get("engine_names") or [],
            hold_seconds=max(0, int(time.time() - float(position.get("opened_at", time.time()))))
        )
    except Exception as e:
        logger.warning(f"Learning exit bridge failed: {e}")
