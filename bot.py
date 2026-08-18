# ==============================================================================
# HULK SOLANA VIP BOT - V30 MASTER ULTIMATE BATCH VIP (2026 EDITION)
# FULL UNIFIED CODE - FIXED SYNTAX & ONE-FILE DEPLOYMENT FOR RENDER
# ==============================================================================

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

# قفل‌های همزمانی (Thread Safety)
db_lock = RLock()
state_lock = Lock()
rpc_lock = Lock()

# جلسه ارتباطی پرسرعت
http_session = requests.Session()
retries = Retry(total=2, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retries)
http_session.mount("https://", adapter)
http_session.mount("http://", adapter)

SIGNAL_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="SignalExec")
ANALYSIS_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="AnalysisExec")
SIGNAL_EMIT_LOCK = Lock()

# تنظیمات محیطی
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
# سیستم چرخشی RPC
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

TRAILING_LOCK_TABLE = (
    (1000.0, 950.0), (750.0, 650.0), (500.0, 350.0), (300.0, 230.0),
    (200.0, 155.0), (150.0, 110.0), (100.0, 75.0), (75.0, 55.0),
    (50.0, 35.0), (40.0, 28.0), (30.0, 20.0), (25.0, 15.0), (20.0, 10.0),
    (15.0, 7.0), (10.0, 3.0),
)
TRAILING_WEAKNESS_ENABLED = True
TRAILING_WEAK_SELL_RATIO = 1.35
TRAILING_WEAKNESS_M5_MAX = 0.0
TRAILING_WEAKNESS_MIN_DRAWDOWN_PCT = 1.2

SECTION_ULTRA_OPEN = True
SECTION_VIP_OPEN = True
SECTION_PROTECTION_OPEN = True
SECTION_AI_OPEN = True
SECTION_TRADING_OPEN = True

FIRE_BUY_AMOUNT_SOL = 0.01
FIRE_TAKE_PROFIT = 18.0
FIRE_STOP_LOSS = -8.0
FIRE_MIN_LIQUIDITY = 25000       
FIRE_MIN_VOLUME_5M = 4000       
FIRE_MIN_PRICE_CHANGE_5M = 4.0  

COMBO_BUY_AMOUNT_SOL = 0.01
COMBO_TAKE_PROFIT = 18.0
COMBO_STOP_LOSS = -8.0
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

# تنظیمات اجماع و اسکنر
CONSENSUS_MIN_SCORE = 4.0
CONSENSUS_MIN_RATIO = 0.55
CONSENSUS_COOLDOWN_SECONDS = 120
DAILY_SIGNAL_LIMIT = 25
GLOBAL_SIGNAL_COOLDOWN_SECONDS = 3 * 60
last_global_signal_time = 0.0
UNIFIED_LAST_EMIT_TIME = 0.0
CONSENSUS_MIN_LIQUIDITY = 25000.0
CONSENSUS_MIN_VOLUME_5M = 3000.0
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

FAST_SCAN_INTERVAL_SECONDS = 0.50
MARKET_DISCOVERY_WORKERS = 4
PAIR_SCAN_WORKERS = 16

ELITE_DISCOVERY_REFRESH_SECONDS = 2.50
ELITE_PAIR_TIMEOUT_SECONDS = 3.00
ELITE_VOTE_WORKERS = 12
ELITE_MAX_UNIQUE_TOKENS = 1200
_elite_market_cache = []
_elite_market_cache_time = 0.0
_elite_market_refresh_lock = Lock()
_elite_market_refresh_thread = None

_SENTINEL_MEMORY_TTL = 120.0
_SENTINEL_MAX_TOKENS = 5000
TRUE_HUNTER_BATCH_SIZE = 30
_TRUE_HUNTER_CURSOR = 0
_TRUE_HUNTER_CURSOR_LOCK = Lock()
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

# بارگذاری کلید عمومی ولت
try:
    decoded_key = base58.b58decode(PRIVATE_KEY_BASE58)
    sender_keypair = Keypair.from_bytes(decoded_key)
    WALLET_PUBKEY = str(sender_keypair.pubkey())
    logger.info(f"✅ ولت با موفقیت لود شد: {WALLET_PUBKEY}")
except Exception as e:
    logger.error(f"❌ خطا در بارگذاری کلید خصوصی از Environment: {e}")
    WALLET_PUBKEY = None
    sender_keypair = None

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
            logger.info("✅ دیتابیس با موفقیت فعال شد.")
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

        engines = ["Fire","Trend","Combo","Golden","Technical","UltimateAI","Mempool/SmartMoney","Whale","Social/Hype","Anti-Wash","SmartFilter","Analysis"]
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
    logger.info("🧠 موتور یادگیری تطبیقی فعال شد.")
    while True:
        if SELF_LEARNING_AI_ENABLED:
            try:
                with db_lock:
                    conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
                    state = _update_adaptive_learning(conn)
                    conn.close()
                if state.get("sample", 0) >= ADAPTIVE_MIN_SAMPLE:
                    logger.info(f"🧠 Adaptive Learning: {state['sample']} معاملات اخیر | Win Rate={state['win_rate']:.1f}%")
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
        if (len(socials) > 0 or len(websites) > 0) or (sells == 0 or buys >= (sells * 1.15)):
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
            logger.info("🧹 حافظه رم از توکن‌های قدیمی پاک‌سازی شد.")

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

def verify_blockchain_transaction(tx_signature, expected_currency="USDC"):
    if not tx_signature or len(tx_signature) < 30:
        return False, "هش تراکنش نامعتبر است."

    currency = str(expected_currency or "SOL").upper()
    expected_amount = VIP_PRICE_SOL if currency == "SOL" else VIP_PRICE_USDC
    if expected_amount <= 0:
        return False, f"قیمت اشتراک برای {currency} تنظیم نشده است."

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
            if received + 1e-9 < expected_amount:
                return False, f"مبلغ کافی نیست. دریافتی: {received:.9f} SOL"
            return True, f"پرداخت {received:.9f} SOL تایید شد ✅"

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
            return False, f"مبلغ کافی نیست. دریافتی: {received_usdc:.6f} USDC"
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
    logger.info("🔄 مانیتورینگ خودکار انقضای اشتراک‌ها فعال شد.")
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
    chat_target = target_chat if target_chat is not None else TELEGRAM_CHAT_ID
    if not TELEGRAM_BOT_TOKEN or not chat_target:
        logger.error("❌ Telegram config ناقص است")
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
                return True
        if payload.get("reply_markup") is not None:
            payload.pop("reply_markup", None)
            retry2 = http_session.post(url, json=payload, timeout=8)
            retry2_data = retry2.json()
            if retry2_data.get("ok"):
                return True
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
            return link
    except Exception as e:
        logger.error(f"❌ خطای ساخت لینک VIP: {e}")
    return ""

def send_graphic_signal_to_vip_channel(token_addr, symbol, price, tp, sl, buy_amt, volume, liquidity, p_change, solscan_link, signal_title="🚀 سیگنال ویژه VIP", side="BUY", execution_status="", execution_tx="", pnl_percent=None):
    is_analysis_card = str(signal_title or "").strip() == "سیستم تحلیل مستقل" or "Analysis" in str(signal_title or "") or "تحلیل مستقل" in str(signal_title or "")
    if str(side).upper() == "BUY" and MAX_FUSION_ENABLED and not is_analysis_card and signal_title not in (UNIFIED_ENGINE_NAME, "MAX FUSION"):
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
        f"📈 تغییر ۵ دقیقه: {m5_change:+.2f}%\n"
        f"🎯 TP: +{tp:.1f}%\n"
        f"🛑 SL: {sl:.1f}%\n"
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
            return False

        keyboard = InlineKeyboardMarkup(buttons)
        ok = send_telegram_msg(
            graphic_text, target_chat=CHANNEL_ID,
            reply_markup=keyboard, parse_mode=None
        )
        return ok
    except Exception as e:
        logger.exception(f"❌ خطای ارسال کارت سیگنال به کانال: {e}")
        return False

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

    weakness = False
    if TRAILING_WEAKNESS_ENABLED and highest_pnl >= 10.0:
        ratio_bad = sells >= max(2, int(buys * TRAILING_WEAK_SELL_RATIO))
        momentum_bad = m5 <= TRAILING_WEAKNESS_M5_MAX
        if ratio_bad and momentum_bad and drawdown_from_high >= TRAILING_WEAKNESS_MIN_DRAWDOWN_PCT:
            weakness = True
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
                _mark_token_closed(finished_addr)

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
                    locked_floor, weakness = _update_trailing_state(pos, current_price, pnl_percent, pair)
                    pos["volume"] = float((pair.get("volume") or {}).get("m5") or 0.0)
                    pos["liquidity"] = float((pair.get("liquidity") or {}).get("usd") or 0.0)
                    pos["p_change"] = float(pair.get("priceChange", {}).get("m5") or 0.0)
                    highest_pnl = float(pos.get("highest_pnl", pnl_percent))

                    should_exit = False
                    if pnl_percent <= sl and highest_pnl < 10.0:
                        should_exit = True
                        exit_reason_text = "فروش خودکار حد ضرر اولیه (SL) فعال شد 🛑"
                    elif pnl_percent <= locked_floor and highest_pnl >= 10.0:
                        should_exit = True
                        exit_reason_text = f"Trailing Stop پله‌ای فعال شد؛ سقف سود {highest_pnl:+.2f}% و حدضرر قفل‌شده {locked_floor:+.2f}% 🎯"
                    elif weakness and pnl_percent <= locked_floor:
                        should_exit = True
                        exit_reason_text = "تشخیص ضعف بازار و افزایش فشار فروش؛ خروج اضطراری و سیو سود ⚠️"
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

                    invested_sol = float(pos.get("buy_amt", 0.01) or 0.01)
                    pnl_usd_val = invested_sol * pnl_percent / 100.0

                    if success:
                        closed_trades_history.append({"symbol": symbol, "percent": pnl_percent, "usd": pnl_usd_val})
                        total_realized_pnl_percent += pnl_percent
                        total_realized_pnl_usd += pnl_usd_val
                        log_trade_to_db(token_addr, symbol, entry_price, current_price, pnl_percent, pnl_usd_val, exit_reason_text)

                    if success:
                        send_signal_outcome(
                            token_addr, pos, current_price, "SELL_SUCCESS", pnl_percent,
                            tx_signature=sell_res_info,
                            extra_text=f"📌 دلیل خروج: {exit_reason_text}"
                        )
                        tokens_to_close.append((token_addr, current_price))

                except Exception as inner_e:
                    logger.error(f"⚠️ خطا در پوزیشن {token_addr}: {inner_e}")

            if tokens_to_close:
                with state_lock:
                    for t_addr, exit_price in tokens_to_close:
                        pos_snapshot = active_positions.get(t_addr)
                        learning_record_exit(t_addr, pos_snapshot, exit_price, "POSITION_CLOSED")
                        active_positions.pop(t_addr, None)
                        _mark_token_closed(t_addr)
        except Exception as e:
            logger.error(f"⚠️ خطای حلقه پوزیشن‌ها: {e}")
        time.sleep(1)

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
                f"🎉 تبریک! اشتراک ۳۰ روزه VIP شما با موفقیت فعال شد!\n\n"
                f"⏳ تاریخ انقضا: {expiry.strftime('%Y-%m-%d %H:%M:%S')}\n"
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
                f"🎉🎊 تبریک! اشتراک VIP رایگان شما فعال شد.\n\n"
                f"⏳ تاریخ انقضا: {expiry.strftime('%Y-%m-%d %H:%M:%S')}"
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

def trigger_copy_trading_for_subscribers(token_mint, amount_sol, side="BUY", tx_signature=""):
    if EMERGENCY_STOP or not COPY_TRADING_ENABLED:
        return
    for sub in get_active_subscribers():
        try:
            t_id = sub["telegram_id"]
            if not sub.get("copy_enabled", True):
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
                f"💰 حجم: <b>{amount:g} {asset}</b>\n"
            )
            if tx_signature:
                msg += f"\n🔗 معامله مرجع: https://solscan.io/tx/{tx_signature}"
            send_telegram_msg(msg, target_chat=t_id, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Copy-trade dispatch error: {e}")

# ==========================================
# اسکنرها و موتورهای سیگنال‌دهی
# ==========================================
TOKEN_ENTRY_LOCKS = {}

def _token_lock_is_open(token_addr):
    try:
        with state_lock:
            pos = TOKEN_ENTRY_LOCKS.get(token_addr)
            if pos: return True
            if token_addr in active_positions or token_addr in signal_positions:
                return True
        return False
    except Exception:
        return True

def _lock_token_entry(token_addr, kind="OPEN"):
    if not token_addr: return
    with state_lock:
        TOKEN_ENTRY_LOCKS[token_addr] = {"status": kind, "opened_at": time.time()}

def _unlock_token_entry(token_addr):
    if not token_addr: return
    with state_lock:
        TOKEN_ENTRY_LOCKS.pop(token_addr, None)

def _mark_token_closed(token_addr):
    _unlock_token_entry(token_addr)

def _load_daily_signal_state():
    global DAILY_SIGNAL_LIMIT
    today = time.strftime("%Y-%m-%d")
    try:
        saved_limit = _get_bot_setting("daily_signal_limit", "")
        if saved_limit:
            DAILY_SIGNAL_LIMIT = max(1, min(50, int(saved_limit)))
    except Exception:
        DAILY_SIGNAL_LIMIT = 25

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

def new_trade_system_enabled():
    return (SYNCHRONIZED_MODE or ADVANCED_AI_ENABLED or MAX_FUSION_ENABLED) and not EMERGENCY_STOP

def send_fused_signal(token_addr, fusion):
    global last_global_signal_time, UNIFIED_LAST_EMIT_TIME
    is_analysis_signal = bool(fusion.get("force_independent") or fusion.get("hunter_group") == "ANALYSIS")
    emit_lane = "ANALYSIS" if is_analysis_signal else ("MAX" if MAX_FUSION_ENABLED else str(fusion.get("hunter_group", "ENGINE")))
    emit_engine = (fusion.get("engines") or fusion.get("votes") or [emit_lane])[0]
    emit_key = f"{emit_lane}:{emit_engine}"

    with SIGNAL_EMIT_LOCK:
        if _token_lock_is_open(token_addr) or daily_signal_cap_reached() or EMERGENCY_STOP:
            return False, "REJECTED"
        
        now_global = time.time()
        if MAX_FUSION_ENABLED and not is_analysis_signal:
            if now_global - max(last_global_signal_time, UNIFIED_LAST_EMIT_TIME) < GLOBAL_SIGNAL_COOLDOWN_SECONDS:
                return False, "GLOBAL_SIGNAL_COOLDOWN"
        elif is_analysis_signal:
            if now_global - consensus_last_signal.get(emit_key, 0) < CONSENSUS_COOLDOWN_SECONDS:
                return False, "ANALYSIS_COOLDOWN"

        if MAX_FUSION_ENABLED and not is_analysis_signal:
            last_global_signal_time = now_global
            UNIFIED_LAST_EMIT_TIME = now_global
        consensus_last_signal[emit_key] = now_global
        _increment_daily_signal_count()
        _lock_token_entry(token_addr, "OPEN_PENDING")

    amount = get_dynamic_buy_amount(0.01)
    reason = " + ".join(fusion.get("votes") or [])
    mode_name = fusion.get("mode", UNIFIED_ENGINE_NAME)
    symbol = fusion["symbol"]
    price = fusion["price"]
    tp = fusion["tp"]
    sl = fusion["sl"]
    dex_link = f"https://dexscreener.com/solana/{token_addr}"

    success, result = execute_real_buy(token_addr, amount)
    execution_status = "🟢 خرید موفق روی بلاکچین" if success else f"⚠️ خرید واقعی انجام نشد: {result}"
    solscan_link = f"https://solscan.io/tx/{result}" if success else f"https://solscan.io/token/{token_addr}"

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
        f"🔗 Solscan: {solscan_link}\n"
        f"📈 DexScreener: {dex_link}"
    )
    send_telegram_msg(msg)

    send_graphic_signal_to_vip_channel(
        token_addr=token_addr, symbol=symbol, price=price, tp=tp, sl=sl,
        buy_amt=amount, volume=fusion['vol'], liquidity=fusion['liq'],
        p_change=fusion['chg'], solscan_link=solscan_link,
        signal_title=mode_name, side="BUY",
        execution_status=execution_status, execution_tx=result if success else ""
    )

    if success:
        with state_lock:
            processed_tokens.add(token_addr)
            active_positions[token_addr] = {
                "entry_price": price, "symbol": symbol,
                "tp": tp, "sl": sl, "highest_price": price,
                "highest_pnl": 0.0, "locked_floor": sl,
                "trailing_active": DYNAMIC_TRAILING_TP_ENABLED,
                "side": "BUY", "reason": f"{mode_name} | {reason}", "opened_at": time.time(), "buy_amt": amount,
                "volume": float(fusion.get("vol", 0.0) or 0.0),
                "liquidity": float(fusion.get("liq", 0.0) or 0.0),
                "p_change": float(fusion.get("chg", 0.0) or 0.0)
            }
        trigger_copy_trading_for_subscribers(token_addr, amount, side="BUY", tx_signature=result)
    else:
        track_signal_only(
            token_addr, symbol, price, tp, sl, fusion['vol'], fusion['liq'],
            fusion['chg'], reason, amount, execution_status
        )
    return success, result

def _fetch_best_solana_pairs_batch(token_addrs):
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
            if res.status_code != 200:
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
            logger.debug(f"DexScreener batch fetch error: {e}")

    with _dex_batch_lock:
        _dex_batch_cache = dict(result)
        _dex_batch_cache_time = time.time()
    return result

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

def _analysis_engine_candidate(token_addr, pair):
    if not ANALYSIS_ENGINE_ENABLED:
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

        if price <= 0 or liq < CANDIDATE_MIN_LIQUIDITY or vol < CANDIDATE_MIN_VOLUME_5M or buys < 1:
            return None

        score = 6.0 + min(2.0, buy_ratio - 1.0) + min(1.5, vol / 10000.0) + min(1.0, liq / 50000.0)
        q = {"price": price, "liq": liq, "vol": vol, "chg": chg, "buys": buys, "sells": sells}
        return {
            "score": float(score), "strength": float(score),
            "votes": ["Analysis"], "advanced_votes": [], "hulk_votes": [],
            "engines": ["Analysis"], "hunter_group": "ANALYSIS",
            "mode": "📈 موتور تحلیل",
            "reason": "تأیید تحلیل: نقدینگی بالای ۲۵k + جریان خرید فعال",
            **q,
            "symbol": (pair.get("baseToken") or {}).get("symbol", "TOKEN"),
            "tp": max(15.0, min(28.0, 16.0 + min(10.0, score))),
            "sl": -8.0, "structure": "ANALYSIS_BUY_FLOW"
        }
    except Exception as e:
        logger.debug(f"Analysis engine failed for {token_addr}: {e}")
        return None

def unified_market_scanner_loop(app):
    global _TRUE_HUNTER_CURSOR
    logger.info("🚀 رادار اسکنر یکپارچه فعال شد.")

    while True:
        if not new_trade_system_enabled() or daily_signal_cap_reached():
            time.sleep(FAST_SCAN_INTERVAL_SECONDS)
            continue

        try:
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

            for token_addr in scan_tokens:
                if not token_addr or _token_lock_is_open(token_addr):
                    continue
                pairs = pair_cache.get(token_addr, [])
                for pair in pairs:
                    candidate = _analysis_engine_candidate(token_addr, pair)
                    if candidate:
                        candidate["force_independent"] = True
                        candidate["hunter_group"] = "ANALYSIS"
                        ANALYSIS_EXECUTOR.submit(send_fused_signal, token_addr, candidate)
                        break

        except Exception as exc:
            logger.exception(f"Clean signal radar error: {exc}")

        time.sleep(FAST_SCAN_INTERVAL_SECONDS)

# ==========================================
# Flask Server & Telegram App Initialization
# ==========================================
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
            .btn { background: #0284c7; color: white; border: none; padding: 10px; border-radius: 8px; font-weight: bold; cursor: pointer; width: 100%; margin-top: 10px; text-align: center; display: block; text-decoration: none; box-sizing: border-box; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🚀 مینی‌اپلیکیشن هوشمند تریدینگ هالکی & AI</h1>
            <p>سیستم فعال و آنلاین است.</p>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_template)

@web_app.route('/admin-panel')
def admin_panel():
    t_id = request.args.get("telegram_id", "")
    secret_key = request.args.get("secret", "")
    if not ((TELEGRAM_CHAT_ID and str(t_id) == str(TELEGRAM_CHAT_ID)) or (ADMIN_SECRET_KEY and secret_key == ADMIN_SECRET_KEY)):
        return "<h3 style='color:red;text-align:center'>⛔ دسترسی غیرمجاز</h3>", 403
    analytics = get_advanced_trade_analytics()
    return f"<h1>👑 پنل مدیریت - معاملات: {analytics['total_trades']}</h1>"

@web_app.route('/api/check-status')
def api_check_status():
    t_id = request.args.get("telegram_id", "")
    has_sub = False
    expiry_str = ""
    if t_id:
        active, exp_date = check_user_subscription(t_id)
        if active and exp_date:
            has_sub = True
            expiry_str = exp_date.strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({
        "has_subscription": has_sub,
        "expiry_date": expiry_str,
        "channel_link": CHANNEL_INVITE_LINK
    })

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
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="controls")])
    return InlineKeyboardMarkup(rows)

def _control_keyboard():
    rows = [
        [InlineKeyboardButton(f"👑 MAX FUSION: {'🟢 ON' if MAX_FUSION_ENABLED else '🔴 OFF'}", callback_data="toggle_max_fusion")],
        [InlineKeyboardButton(f"🛑 توقف اضطراری: {'🔴 فعال' if EMERGENCY_STOP else '🟢 آماده'}", callback_data="toggle_emergency")],
        [InlineKeyboardButton("⚙️ مدیریت موتورها", callback_data="engine_manage")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="home")]
    ]
    return InlineKeyboardMarkup(rows)

def start_telegram_bot():
    try:
        if not TELEGRAM_BOT_TOKEN:
            logger.error("❌ TELEGRAM_BOT_TOKEN تنظیم نشده است."); return
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        _load_daily_signal_state()

        async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id
            is_admin = bool(TELEGRAM_CHAT_ID and str(chat_id) == str(TELEGRAM_CHAT_ID))
            await update.message.reply_text("🤖⚡ **هالک AI — مرکز ربات هوشمند ترید**", reply_markup=_main_keyboard(is_admin), parse_mode="Markdown")

        async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            global MAX_FUSION_ENABLED, EMERGENCY_STOP
            q = update.callback_query
            await q.answer()
            cid = str(q.from_user.id)
            is_admin = bool(TELEGRAM_CHAT_ID and cid == str(TELEGRAM_CHAT_ID))
            data = q.data

            if data == "home":
                await q.edit_message_text("🤖⚡ **هالک AI — مرکز ربات هوشمند ترید**", reply_markup=_main_keyboard(is_admin), parse_mode="Markdown")
            elif data == "engines":
                await q.edit_message_text(_engine_status_lines(), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="home")]]), parse_mode="Markdown")
            elif data == "controls":
                await q.edit_message_text("🎛 **کنترل موتورها**", reply_markup=_control_keyboard(), parse_mode="Markdown")
            elif data == "engine_manage":
                await q.edit_message_text("⚙️ **مدیریت موتورهای مستقل**", reply_markup=_engine_control_keyboard(), parse_mode="Markdown")
            elif data.startswith("toggle_"):
                if not is_admin:
                    await q.edit_message_text("⛔ دسترسی غیرمجاز.", reply_markup=_main_keyboard(False))
                    return
                if data == "toggle_max_fusion":
                    MAX_FUSION_ENABLED = not MAX_FUSION_ENABLED
                elif data == "toggle_emergency":
                    EMERGENCY_STOP = not EMERGENCY_STOP
                else:
                    engine_map = {callback: var_name for _, var_name, callback in ENGINE_SWITCHES}
                    name = engine_map.get(data)
                    if name:
                        globals()[name] = not bool(globals()[name])
                await q.edit_message_text("⚙️ **موتورهای مستقل**\n\n" + _engine_status_lines(), reply_markup=_engine_control_keyboard(), parse_mode="Markdown")

        app.add_handler(CommandHandler("start", start_cmd))
        app.add_handler(CallbackQueryHandler(button_handler))
        logger.info("🤖 ربات تلگرام استارت شد.")
        app.run_polling(drop_pending_updates=False)
    except Exception as e:
        logger.exception(f"Telegram bot runtime error: {e}")

def learning_record_exit(token_addr, position, exit_price, reason=""):
    try:
        if not position:
            return
        entry = float(position.get("entry_price") or position.get("price") or 0)
        if entry <= 0 or float(exit_price or 0) <= 0:
            return
        pnl = (float(exit_price) - entry) / entry * 100.0
        log_trade_to_db(
            token_addr,
            position.get("symbol", ""),
            entry,
            exit_price,
            pnl,
            0.0,
            reason
        )
    except Exception as e:
        logger.warning(f"Learning exit bridge failed: {e}")

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
