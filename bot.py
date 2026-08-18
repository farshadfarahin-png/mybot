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
VIP_PRICE_SOL = 0.0  
VIP_PRICE_USDC = 50.0  
COPY_TRADING_FEE_PERCENT = 1.0  
COPY_DEFAULT_ASSET = "USDC"
UNIFIED_ENGINE_NAME = "🤖⚡ هالک AI — موتور متحد بازار"
BOT_BUILD_VERSION = "V30-MASTER-ULTIMATE-BATCH-VIP-2026"

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
SYNCHRONIZED_MODE = False   # غیرفعال جهت فعال‌سازی خروجی مستقیم سیگنال‌دهی‌ها
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
TRAILING_WEAK_SELL_RATIO = 1.45
TRAILING_WEAKNESS_M5_MAX = 0.0
TRAILING_WEAKNESS_MIN_DRAWDOWN_PCT = 1.5

MARKET_DISCOVERY_WORKERS = 4

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
            logger.info("✅ دیتابیس با موفقیت فعال و مقداردهی شد.")
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
                return False, f"مبلغ کافی نیست. دریافتی: {received:.9f} SOL، مبلغ لازم: {expected_amount:.9f} SOL."
            return True, f"پرداخت {received:.9f} SOL تایید شد ✅"

        received_units = 0
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
    if TRAILING_WEAKNESS_ENABLED and highest_pnl >= 20.0:
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

def _mark_token_closed(token_addr):
    with state_lock:
        processed_tokens.discard(token_addr)
        tech_processed_tokens.discard(token_addr)
        mempool_processed_tokens.discard(token_addr)
        ultra_processed_tokens.discard(token_addr)

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

PARTIAL_TP_LEVELS = ((1.0, 0.30), (2.0, 0.30))

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

                    invested_sol = float(pos.get("buy_amt", 0.01) or 0.01)
                    pnl_usd_val = invested_sol * pnl_percent / 100.0

                    if success:
                        closed_trades_history.append({"symbol": symbol, "percent": pnl_percent, "usd": pnl_usd_val})
                        total_realized_pnl_percent += pnl_percent
                        total_realized_pnl_usd += pnl_usd_val
                        log_trade_to_db(token_addr, symbol, entry_price, current_price, pnl_percent, pnl_usd_val, reason)

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
                        send_telegram_msg(
                            f"⚠️ تلاش فروش انجام نشد\n"
                            f"🪙 {symbol}\n"
                            f"📍 آدرس: {token_addr}\n"
                            f"📊 وضعیت فعلی: {pnl_percent:+.2f}%\n"
                            f"📌 علت داخلی: {sell_res_info}\n"
                            f"🔄 پوزیشن همچنان تحت مدیریت است."
                        )

                    if success:
                        tokens_to_close.append((token_addr, current_price))

                except Exception as inner_e:
                    logger.error(f"⚠️ خطا در پوزیشن {token_addr}: {inner_e}")

            if tokens_to_close:
                with state_lock:
                    for t_addr, exit_price in tokens_to_close:
                        active_positions.pop(t_addr, None)
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
# تنظیمات پیش‌فرض موتور اتحاد سریع (Consensus Fusion)
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
ADAPTIVE_MAX_SCORE_BONUS = 2
ADAPTIVE_MAX_RATIO_BONUS = 0.10
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

        if price <= 0 or liq < FINAL_ANALYSIS_MIN_LIQUIDITY or vol < FINAL_ANALYSIS_MIN_VOLUME_5M:
            return False, {"structure": "LOW_LIQUIDITY_OR_VOLUME", "structure_score": -1.0}

        buy_ratio = (buys / float(sells)) if sells > 0 else float(buys)
        if buy_ratio < FINAL_ANALYSIS_MIN_BUY_RATIO:
            return False, {"structure": "WEAK_BUY_RATIO", "structure_score": -0.5}

        return True, {"structure": "PASSED", "structure_score": 1.0}
    except Exception as e:
        logger.debug(f"Structure gate error: {e}")
        return True, {"structure": "ERROR_PASS", "structure_score": 0.0}

if __name__ == "__main__":
    logger.info("🚀 ربات هوشمند صراف/سیگنال‌دهی سولانا در حال راه‌اندازی است...")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build() if TELEGRAM_BOT_TOKEN else None

    # راه‌اندازی ترد‌های مانیتورینگ و اسکنرهای بازار
    threading.Thread(target=subscription_monitor_loop, daemon=True).start()
    threading.Thread(target=check_positions_loop, daemon=True).start()
    threading.Thread(target=self_learning_ai_optimizer_loop, daemon=True).start()

    if app:
        threading.Thread(target=ultra_accuracy_scanner_loop, args=(app,), daemon=True).start()
        threading.Thread(target=mempool_smart_money_scanner_loop, args=(app,), daemon=True).start()
        threading.Thread(target=technical_analysis_scanner_loop, args=(app,), daemon=True).start()

    logger.info("🟢 تمام زیرسیستم‌ها، اسکنرها و موتورهای سیگنال‌دهی با موفقیت فعال شدند.")
    
    if app:
        app.run_polling()
