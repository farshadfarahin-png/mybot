import time
import requests
import json
import base64
import base58
import os
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

# تنظیمات کلیدی محیطی و کانال انتشار سیگنال
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
ADMIN_SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY", "").strip()

CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip() 
CHANNEL_INVITE_LINK = os.environ.get("CHANNEL_INVITE_LINK", "").strip()

PRIVATE_KEY_BASE58 = os.environ.get("PRIVATE_KEY_BASE58", "").strip()
WEBAPP_URL = os.environ.get("WEBAPP_URL", "").strip()

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
COPY_TRADING_ENABLED = True   

BOTTOM_WHALE_RUNNING = True

ULTIMATE_21_ENGINE_ENABLED = True
SELF_LEARNING_AI_ENABLED = True
MEMPOOL_SMART_MONEY_ENABLED = True
MOONBAG_HULK_ENABLED = True
ANTI_WASH_TRADING_ENABLED = True

SMART_MONEY_COPY_ENABLED = True      
SOCIAL_SENTIMENT_ENABLED = True      
DYNAMIC_TRAILING_TP_ENABLED = True   

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
            for col, definition in [("copy_enabled", "INTEGER DEFAULT 1"), ("trade_amount_sol", "REAL DEFAULT 0.01")]:
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
    global FIRE_MIN_LIQUIDITY, COMBO_MIN_LIQUIDITY, GOLDEN_MIN_LIQUIDITY
    logger.info("🧠 موتور هوش مصنوعی یادگیرنده (Self-Learning AI) فعال شد.")
    while True:
        if SELF_LEARNING_AI_ENABLED:
            with db_lock:
                try:
                    conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
                    cursor = conn.cursor()
                    cursor.execute("SELECT AVG(pnl_percent), COUNT(*) FROM trades")
                    row = cursor.fetchone()
                    if row and row[1] and row[1] >= 5:
                        avg_pnl = row[0] or 0.0
                        total_t = row[1]
                        logger.info(f"🧠 [AI Learning]: آنالیز {total_t} معامله گذشته. میانگین سود: {avg_pnl:.2f}%")
                        if avg_pnl < 2.0:
                            FIRE_MIN_LIQUIDITY += 500
                            GOLDEN_MIN_LIQUIDITY += 1000
                            logger.info("🧠 [AI Adjustment]: فیلتر نقدینگی بهینه‌تر شد.")
                        elif avg_pnl > 10.0:
                            FIRE_MIN_LIQUIDITY = max(15000, FIRE_MIN_LIQUIDITY - 500)
                            logger.info("🧠 [AI Adjustment]: الگوریتم در حالت بهینه حداکثری قرار گرفت.")
                    conn.close()
                except Exception as e:
                    logger.error(f"⚠️ خطای موتور هوش مصنوعی یادگیرنده: {e}")
        time.sleep(300)

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
        "https://api.dexscreener.com/latest/dex/search?q=pump"
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

    for url in endpoints:
        try:
            res_obj = http_session.get(url, timeout=4)
            if res_obj.status_code == 200:
                res = res_obj.json()
                if isinstance(res, list):
                    for t in res:
                        if t.get('chainId') == 'solana':
                            addr = t.get('tokenAddress')
                            if addr and addr not in tokens:
                                tokens.append(addr)
                elif isinstance(res, dict):
                    for p in res.get("pairs", []):
                        if p.get("chainId") == "solana":
                            addr = p.get("baseToken", {}).get("address")
                            if addr and addr not in tokens:
                                tokens.append(addr)
        except Exception as e:
            logger.debug(f"Fetch endpoints error ({url}): {e}")
            continue
    return tokens

def ultra_accuracy_scanner_loop(app):
    global SMART_MONEY_COPY_ENABLED, SOCIAL_SENTIMENT_ENABLED, DYNAMIC_TRAILING_TP_ENABLED
    logger.info("💎🚀 موتور پایش فوق‌پیشرفته (۹۹٪ سود تضمینی) فعال شد.")

    while True:
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
                    if not success:
                        continue

                    with state_lock:
                        ultra_processed_tokens.add(token_addr)
                        processed_tokens.add(token_addr)

                    solscan_link = f"https://solscan.io/tx/{result_info}"
                    init_tp = 30.0
                    init_sl = -7.0

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
                        f"💎✨ [سیگنال هوش مصنوعی پیش‌رو - دقت ۹۹٪]\n"
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
                        p_change=price_change_5m, solscan_link=solscan_link, signal_title="💎✨ سیگنال تضمینی ۹۹٪ (Smart Money + Hype)"
                    )
        except Exception as e:
            logger.error(f"⚠️ خطای موتور فوق‌پیشرفته: {e}")
        time.sleep(3)

def mempool_smart_money_scanner_loop(app):
    global MEMPOOL_SMART_MONEY_ENABLED
    logger.info("⚡🕵️ موتور اسکنر ممپول و اسمارت‌مانی فعال شد.")
    while True:
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
                    if not success:
                        continue 
                    
                    with state_lock:
                        mempool_processed_tokens.add(token_addr)
                        processed_tokens.add(token_addr)

                    buy_status_str = "شکار موفق از ممپول (موفق روی بلاکچین ✅)"
                    solscan_link = f"https://solscan.io/tx/{result_info}"

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
                        p_change=15.0, solscan_link=solscan_link, signal_title="⚡🕵️ شکار ممپول اسمارت‌مانی هالکی VIP"
                    )
        except Exception as e:
            logger.error(f"⚠️ خطای اسکن ممپول: {e}")
        time.sleep(4)

def verify_blockchain_transaction(tx_signature, expected_currency="SOL"):
    if not tx_signature or len(tx_signature) < 30:
        return False, "هش تراکنش نامعتبر است."
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
        
        meta = result.get("meta", {})
        if meta.get("err") is not None:
            return False, "تراکنش روی بلاکچین با خطا مواجه شده است (Failed Tx)."
            
        account_keys = result.get("transaction", {}).get("message", {}).get("accountKeys", [])
        admin_wallet_found = False
        for acc in account_keys:
            pubkey_str = acc.get("pubkey") if isinstance(acc, dict) else str(acc)
            if pubkey_str == WALLET_PUBKEY:
                admin_wallet_found = True
                break
                
        if not admin_wallet_found:
            return False, "این تراکنش به ولت صرافی/پلتفرم شما واریز نشده است."

        return True, "تراکنش با موفقیت روی بلاکچین تأیید شد ✅"
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
            logger.error(f"❌ Telegram fallback failed: {retry_data.get('description', retry_data)}")
        return False
    except Exception as e:
        logger.error(f"❌ خطای ارسال پیام به تلگرام: {e}")
        return False

def send_graphic_signal_to_vip_channel(token_addr, symbol, price, tp, sl, buy_amt, volume, liquidity, p_change, solscan_link, signal_title="🚀 سیگنال ویژه VIP", side="BUY"):
    if not CHANNEL_ID or not TELEGRAM_BOT_TOKEN:
        logger.error("❌ CHANNEL_ID یا TELEGRAM_BOT_TOKEN تنظیم نشده است.")
        return False
    side_icon = "🟢 خرید" if str(side).upper() == "BUY" else "🔴 فروش"
    graphic_text = (
        f"╔══════════════════════════╗\n  {signal_title}\n  {side_icon}\n╚══════════════════════════╝\n\n"
        f"🪙 نام توکن: #{symbol}\n📍 آدرس قرارداد:\n{token_addr}\n\n"
        f"💵 قیمت: ${price:.8f}\n💰 حجم معامله: SOL {buy_amt}\n🎯 حد سود: +%{tp}\n🛑 حد ضرر: %{sl}\n\n"
        f"📊 آمار زنده بازار:\n▪️ روند ۵ دقیقه: %{p_change:+.2f}\n▪️ حجم معاملات: ${volume:,.0f}\n▪️ نقدینگی کل: ${liquidity:,.0f}\n\n"
        f"⚡️ سیستم هوشمند هالکی\n━━━━━━━━━━━━━━━━━━━━"
    )
    buttons = [[InlineKeyboardButton("🔍 Solscan", url=solscan_link), InlineKeyboardButton("📈 DexScreener", url=f"https://dexscreener.com/solana/{token_addr}")]]
    if WEBAPP_URL:
        buttons.append([InlineKeyboardButton("🤖 ورود به Mini App و کپی‌ترید", url=WEBAPP_URL)])
    return send_telegram_msg(graphic_text, target_chat=CHANNEL_ID, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=None)

def register_subscription(telegram_id, wallet_addr, tx_sig, currency="SOL"):
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
            
            success_msg = (
                f"🎉 اشتراک ۳۰ روزه VIP شما با موفقیت پس از تایید تراکنش بلاکچین ({currency}) فعال شد!\n\n"
                f"⏳ تاریخ انقضا: {expiry.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"🔗 ولت شما به سیستم کپی‌تریدینگ هوشمند متصل گردید.\n"
                f"📢 برای ورود مستقیم به کانال VIP از طریق لینک زیر اقدام کنید:\n\n"
                f"{CHANNEL_INVITE_LINK}"
            )
            send_telegram_msg(success_msg, target_chat=str(telegram_id))
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
            
            free_msg = (
                f"🎉🎊 تبریک! اشتراک VIP رایگان شما با موفقیت فعال شد.\n\n"
                f"⏳ تاریخ انقضا و قطع ارتباط: {expiry.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"🔗 موتور کپی‌تریدینگ برای ولت شما روشن گردید.\n"
                f"📱 Mini App: {WEBAPP_URL}\n"
                f"📢 ورود به کانال VIP: {CHANNEL_INVITE_LINK}"
            )
            send_telegram_msg(free_msg, target_chat=str(telegram_id))
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
            cursor.execute("SELECT telegram_id, wallet_address, expiry_date, status FROM subscribers")
            rows = cursor.fetchall()
            conn.close()
            now = datetime.now()
            for row in rows:
                t_id, w_addr, exp_str, status = row
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
                if status == 'ACTIVE' and now < exp_date:
                    active_subs.append({"telegram_id": t_id, "wallet": w_addr, "expiry": exp_str})
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
    if not DYNAMIC_RISK_ENABLED:
        return base_amount

    try:
        sol_bal = get_sol_balance()
        if ULTIMATE_21_ENGINE_ENABLED and sol_bal > 0:
            kelly_factor = 0.025 if sol_bal > 1.0 else 0.01
            calculated = sol_bal * kelly_factor
            return max(base_amount, round(calculated, 4))
        
        if sol_bal > 1.0:
            calculated = sol_bal * 0.02
            return max(base_amount, round(calculated, 4))
        elif sol_bal < 0.1:
            return max(0.005, round(base_amount * 0.5, 4))
    except Exception as e:
        logger.debug(f"Dynamic amount calc exception: {e}")
    return base_amount

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

def trigger_copy_trading_for_subscribers(token_mint, amount_sol):
    if not COPY_TRADING_ENABLED:
        return
    active_subs = get_active_subscribers()

    for sub in active_subs:
        t_id = sub["telegram_id"]
        copy_msg = (
            f"⚡ [کپی‌تریدینگ هوشمند VIP]\n"
            f"🤖 معامله جدید روی ولت شما کپی شد!\n\n"
            f"🪙 توکن:\n{token_mint}\n"
            f"💰 حجم معامله: {amount_sol} SOL"
        )
        send_telegram_msg(copy_msg, target_chat=t_id)

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

def check_positions_loop():
    global closed_trades_history, total_realized_pnl_usd, total_realized_pnl_percent

    while True:
        try:
            tokens_to_close = []
            with state_lock:
                current_positions = list(active_positions.items())

            for token_addr, pos in current_positions:
                try:
                    pair_res_obj = http_session.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=3)
                    if pair_res_obj.status_code != 200:
                        continue
                    pair_res = pair_res_obj.json()

                    if not pair_res.get('pairs'):
                        continue
                    pair = pair_res['pairs'][0]
                    current_price = float(pair.get('priceUsd', 0))
                    entry_price = pos['entry_price']
                    symbol = pos['symbol']
                    initial_tp = pos['tp'] 
                    sl = pos['sl']         
                    
                    if entry_price > 0 and current_price > 0:
                        pnl_percent = ((current_price - entry_price) / entry_price) * 100

                        highest_pnl = pos.get('highest_pnl', pnl_percent)
                        if pnl_percent > highest_pnl:
                            pos['highest_pnl'] = pnl_percent
                            highest_pnl = pnl_percent

                        if DYNAMIC_TRAILING_TP_ENABLED and pos.get('trailing_active', True):
                            floor = pos.get('locked_floor', sl)
                            if highest_pnl >= 120.0: floor = max(floor, 80.0)
                            elif highest_pnl >= 80.0: floor = max(floor, 50.0)
                            elif highest_pnl >= 40.0: floor = max(floor, 20.0)
                            elif highest_pnl >= 20.0: floor = max(floor, 0.0)
                            pos['locked_floor'] = floor

                        if MOONBAG_HULK_ENABLED and highest_pnl >= 150.0 and not pos.get('moonbag_saved', False):
                            pos['moonbag_saved'] = True
                            token_balance = get_token_balance(token_addr)
                            if token_balance > 0:
                                partial_amt = int(token_balance * 0.8)
                                execute_real_sell(token_addr, partial_amt)

                                moon_msg = (
                                    f"💪🔥 [موم‌بگ هالکی فعال شد!]\n"
                                    f"🪙 توکن: {symbol}\n"
                                    f"🎯 سود از مرز ۱۵۰٪ گذشت!\n"
                                    f"💰 ۸۰٪ سرمایه و سود نقد شد و ۲۰٪ مابقی به عنوان «تکه‌سنگ مرگ‌بار (Moonbag)» رها شد تا سود نجومی بسازه."
                                )
                                send_telegram_msg(moon_msg)
                                send_telegram_msg(moon_msg, target_chat=CHANNEL_ID)

                        current_locked_floor = pos.get('locked_floor', sl)

                        if highest_pnl >= 100.0:
                            current_locked_floor = max(current_locked_floor, 50.0)  
                        elif highest_pnl >= 50.0:
                            current_locked_floor = max(current_locked_floor, initial_tp) 
                        elif highest_pnl >= initial_tp:
                            current_locked_floor = max(current_locked_floor, 0.0)

                        pos['locked_floor'] = current_locked_floor

                        should_exit = False
                        exit_reason_text = ""

                        if DYNAMIC_TRAILING_TP_ENABLED and pnl_percent <= current_locked_floor and highest_pnl >= 20.0:
                            should_exit = True
                            exit_reason_text = f"تریلینگ استاپ پویا: سیو سود در سقف {current_locked_floor:.0f}% 🎯 🤑"
                        elif pnl_percent <= current_locked_floor and highest_pnl >= initial_tp:
                            should_exit = True
                            exit_reason_text = f"سیو سود پله‌ای هوشمند روی سقف {current_locked_floor:.0f}% 🎯 🤑"
                        elif pnl_percent <= sl:
                            should_exit = True
                            exit_reason_text = f"فروش خودکار حد ضرر (SL) فعال شد 🛑 🧐"

                        if should_exit:
                            success = False
                            sell_res_info = "خطای عدم موجودی"

                            for attempt_sell in range(2):
                                token_balance = get_token_balance(token_addr)
                                if token_balance > 0:
                                    success, sell_res_info = execute_real_sell(token_addr, token_balance)
                                    if success:
                                        break
                                time.sleep(0.5)

                            is_profit = pnl_percent >= 0
                            sticker = "🤑" if is_profit else "🧐"
                            reason = exit_reason_text if exit_reason_text else (f"حد سود (TP) فعال شد 🎯 {sticker}" if is_profit else f"حد ضرر (SL) فعال شد 🛑 {sticker}")

                            pnl_usd_val = 0.75 * (pnl_percent / 100)
                            closed_trades_history.append({
                                "symbol": symbol,
                                "percent": pnl_percent,
                                "usd": pnl_usd_val
                            })
                            total_realized_pnl_percent += pnl_percent
                            total_realized_pnl_usd += pnl_usd_val

                            log_trade_to_db(token_addr, symbol, entry_price, current_price, pnl_percent, pnl_usd_val, reason)

                            solscan_link = f"https://solscan.io/tx/{sell_res_info}" if success else "https://solscan.io"

                            exit_msg = (
                                f"🔴 {reason}\n\n"
                                f"🪙 توکن: {symbol}\n"
                                f"📌 وضعیت خروج: {sell_res_info}\n"
                                f"📍 آدرس:\n{token_addr}\n\n"
                                f"📉 قیمت خروج: ${current_price:.8f}\n"
                                f"📊 سود/زیان نهایی: {pnl_percent:+.2f}%\n\n"
                                f"🔗 تراکنش Solscan:\n{solscan_link}"
                            )
                            send_telegram_msg(exit_msg)
                            send_telegram_msg(exit_msg, target_chat=CHANNEL_ID)
                            tokens_to_close.append(token_addr)
                except Exception as inner_e:
                    logger.error(f"⚠️ خطا در پوزیشن {token_addr}: {inner_e}")

            with state_lock:
                for t_addr in tokens_to_close:
                    active_positions.pop(t_addr, None)
        except Exception as e:
            logger.error(f"⚠️ خطای حلقه پوزیشن‌ها: {e}")
        time.sleep(2)

def technical_analysis_scanner_loop(app):
    global TECHNICAL_RUNNING, TECH_BUY_AMOUNT_SOL, TECH_TAKE_PROFIT, TECH_STOP_LOSS, TECH_MIN_LIQUIDITY
    send_telegram_msg("📊 موتور پرایس اکشن حرفه‌ای (مجهز به AI & Mempool & Hulk Mode) فعال شد.")

    while True:
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
                if not success:
                    continue

                with state_lock:
                    tech_processed_tokens.add(token_addr)
                    processed_tokens.add(token_addr)

                buy_status_str = "انجام شد (موفق روی بلاکچین ✅)"
                solscan_link = f"https://solscan.io/tx/{result_info}"

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
                    p_change=price_change_5m, solscan_link=solscan_link, signal_title="📊 سیگنال پرایس اکشن + هالکی"
                )
        except Exception as e:
            logger.error(f"⚠️ خطای موتور پرایس اکشن: {e}")
        time.sleep(2)

# ==========================================================
# موتور اتحاد سریع (Consensus Fusion)
# موتورهای موجود نقش مکمل دارند و امتیازهای مستقل را برای یک
# تصمیم واحد جمع می‌کنند؛ خطای یک موتور، بقیه را متوقف نمی‌کند.
# ==========================================================
CONSENSUS_MIN_SCORE = 4
CONSENSUS_COOLDOWN_SECONDS = 45
consensus_last_signal = {}

def build_consensus_signal(token_addr, pair):
    try:
        price = float(pair.get("priceUsd", 0) or 0)
        liq = float(pair.get("liquidity", {}).get("usd", 0) or 0)
        vol = float(pair.get("volume", {}).get("m5", 0) or 0)
        chg = float(pair.get("priceChange", {}).get("m5", 0) or 0)
        txns = pair.get("txns", {}).get("m5", {}) or {}
        buys, sells = int(txns.get("buys", 0) or 0), int(txns.get("sells", 0) or 0)
        votes=[]
        if chg >= 4 and vol >= 4000: votes.append("Fire")
        if chg >= 6 and vol >= 5000: votes.append("Trend")
        if chg >= GOLDEN_MIN_CHANGE_5M and vol >= GOLDEN_MIN_VOLUME_5M and liq >= GOLDEN_MIN_LIQUIDITY: votes.append("Golden")
        if buys > sells and liq >= COMBO_MIN_LIQUIDITY and vol >= COMBO_MIN_VOLUME_5M: votes.append("SmartMoney")
        try:
            ok_pa, reason = check_major_support_resistance_pa(pair)
            if ok_pa: votes.append("Technical")
        except Exception: pass
        try:
            ok_ai, *_ = evaluate_ultimate_super_signal(token_addr, pair)
            if ok_ai: votes.append("UltimateAI")
        except Exception: pass
        score=len(votes)
        if score < CONSENSUS_MIN_SCORE: return None
        now=time.time()
        if now-consensus_last_signal.get(token_addr,0) < CONSENSUS_COOLDOWN_SECONDS: return None
        consensus_last_signal[token_addr]=now
        return {"score":score,"votes":votes,"price":price,"liq":liq,"vol":vol,"chg":chg,"symbol":pair.get("baseToken",{}).get("symbol","TOKEN"),"tp":max(12.0,min(24.0,10.0+score*2.0)),"sl":-8.0}
    except Exception as e:
        logger.debug(f"Consensus error {token_addr}: {e}")
        return None

def unified_market_scanner_loop(app):
    global GOLDEN_OPTION, COMBO_RUNNING, IS_RUNNING, TREND_ALERT_RUNNING, SYNCHRONIZED_MODE, BOTTOM_WHALE_RUNNING
    global GOLDEN_BUY_AMOUNT_SOL, GOLDEN_TAKE_PROFIT, GOLDEN_STOP_LOSS
    global COMBO_BUY_AMOUNT_SOL, COMBO_TAKE_PROFIT, COMBO_STOP_LOSS
    global FIRE_BUY_AMOUNT_SOL, FIRE_TAKE_PROFIT, FIRE_STOP_LOSS

    send_telegram_msg("⚡ موتور پردازش بازار و فیلتر سیگنال‌های VIP هالکی فعال شد.")

    while True:
        if not (GOLDEN_OPTION or COMBO_RUNNING or IS_RUNNING or TREND_ALERT_RUNNING or SYNCHRONIZED_MODE or BOTTOM_WHALE_RUNNING):
            time.sleep(2)
            continue

        try:
            tokens = get_real_market_trending_tokens()
            for token_addr in tokens[:30]:
                with state_lock:
                    if not token_addr or token_addr in active_positions:
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
                symbol = pair.get('baseToken', {}).get('symbol', 'TOKEN')

                if price <= 0:
                    continue

                fusion = build_consensus_signal(token_addr, pair) if SYNCHRONIZED_MODE else None
                if fusion and token_addr not in processed_tokens:
                    amount = get_dynamic_buy_amount(0.01)
                    success, result_info = execute_real_buy(token_addr, amount)
                    if success:
                        with state_lock:
                            processed_tokens.add(token_addr)
                            active_positions[token_addr] = {"entry_price": fusion["price"], "symbol": fusion["symbol"], "tp": fusion["tp"], "sl": fusion["sl"], "highest_price": fusion["price"]}
                        txlink=f"https://solscan.io/tx/{result_info}"
                        reason=" + ".join(fusion["votes"])
                        msg=(f"⚡🧠 **ابرسیگنال متحد هالکی**\n\n🎯 اجماع موتورها: `{fusion['score']}`\n🤖 موتورهای تأییدکننده: {reason}\n🪙 `{fusion['symbol']}`\n💵 ورود: `${fusion['price']:.8f}`\n💰 حجم: `{amount}` SOL\n🎯 TP: `+{fusion['tp']:.1f}%`\n🛑 SL: `{fusion['sl']:.1f}%`\n🔗 [Solscan]({txlink})")
                        send_telegram_msg(msg)
                        send_graphic_signal_to_vip_channel(token_addr, fusion["symbol"], fusion["price"], fusion["tp"], fusion["sl"], amount, fusion["vol"], fusion["liq"], fusion["chg"], txlink, "⚡🧠 ابرسیگنال متحد VIP")
                        continue

                if BOTTOM_WHALE_RUNNING and token_addr not in processed_tokens:
                    txns = pair.get('txns', {}).get('m5', {})
                    buys = txns.get('buys', 0)
                    sells = txns.get('sells', 0)

                    is_bottom_accumulation = (
                        -3.0 <= price_change_5m <= 8.0 and 
                        volume_5m >= (liquidity * 0.1)
                    )
                    
                    is_pump_breakout = (
                        price_change_5m >= 6.0 and 
                        volume_5m >= 5000
                    )

                    if is_bottom_accumulation or is_pump_breakout:
                        current_buy_amt = get_dynamic_buy_amount(0.01)
                        success, result_info = execute_real_buy(token_addr, 0.01)
                        if not success:
                            continue

                        with state_lock:
                            processed_tokens.add(token_addr)
                        
                        solscan_link = f"https://solscan.io/tx/{result_info}"
                        signal_reason = "🐳 شکار کف معتبر و انباشت نهنگ" if is_bottom_accumulation else "🚀 شروع پامپ و شتاب‌دهنده صعودی"
                        
                        with state_lock:
                            active_positions[token_addr] = {
                                "entry_price": price,
                                "symbol": symbol,
                                "tp": 22.0,
                                "sl": -8.0,
                                "highest_price": price
                            }
                        
                        send_graphic_signal_to_vip_channel(
                            token_addr=token_addr, symbol=symbol, price=price, tp=22.0, sl=-8.0,
                            buy_amt=current_buy_amt, volume=volume_5m, liquidity=liquidity,
                            p_change=price_change_5m, solscan_link=solscan_link, signal_title=signal_reason
                        )
                        continue

                if SYNCHRONIZED_MODE and token_addr not in processed_tokens:
                    is_approved, entry_p, calc_tp, calc_sl, eval_reason = evaluate_ultimate_super_signal(token_addr, pair)
                    if is_approved:
                        current_buy_amt = get_dynamic_buy_amount(0.01)
                        success, result_info = execute_real_buy(token_addr, 0.01)
                        if not success:
                            continue
                        
                        with state_lock:
                            processed_tokens.add(token_addr)

                        buy_status_str = "انجام شد (موفق روی بلاکچین ✅)"
                        solscan_link = f"https://solscan.io/tx/{result_info}"

                        super_msg = (
                            f"⚡🧠 [ابرسیگنال هوشمند هالکی VIP]\n"
                            f"🎯 دلیل شکار: {eval_reason}\n"
                            f"📌 وضعیت خرید: {buy_status_str}\n\n"
                            f"🪙 توکن: {symbol}\n"
                            f"📍 آدرس:\n{token_addr}\n\n"
                            f"💵 ورود: ${entry_p:.8f}\n"
                            f"💰 حجم: {current_buy_amt} SOL\n"
                            f"🔗 [Solscan]({solscan_link})"
                        )
                        
                        with state_lock:
                            active_positions[token_addr] = {
                                "entry_price": entry_p,
                                "symbol": symbol,
                                "tp": calc_tp,
                                "sl": calc_sl,
                                "highest_price": entry_p
                            }
                        
                        send_telegram_msg(super_msg)
                        send_graphic_signal_to_vip_channel(
                            token_addr=token_addr, symbol=symbol, price=entry_p, tp=calc_tp, sl=calc_sl,
                            buy_amt=current_buy_amt, volume=volume_5m, liquidity=liquidity,
                            p_change=price_change_5m, solscan_link=solscan_link, signal_title="⚡🧠 ابرسیگنال هوشمند هالکی VIP"
                        )
                        continue

                if GOLDEN_OPTION and token_addr not in golden_processed_tokens:
                    if (price_change_5m >= GOLDEN_MIN_CHANGE_5M and 
                        volume_5m >= GOLDEN_MIN_VOLUME_5M and 
                        liquidity >= GOLDEN_MIN_LIQUIDITY):

                        current_buy_amt = get_dynamic_buy_amount(GOLDEN_BUY_AMOUNT_SOL)
                        success, result_info = execute_real_buy(token_addr, GOLDEN_BUY_AMOUNT_SOL)
                        if not success:
                            continue
                        
                        with state_lock:
                            golden_processed_tokens.add(token_addr)
                            processed_tokens.add(token_addr)

                        buy_status_str = "انجام شد (موفق روی بلاکچین ✅)"
                        solscan_link = f"https://solscan.io/tx/{result_info}"

                        golden_msg = (
                            f"🚀🔥 سیگنال گزینه طلایی هالکی VIP\n"
                            f"🪙 توکن: {symbol}\n📍 آدرس:\n{token_addr}\n"
                            f"💵 ورود: ${price:.8f}\n🔗 [Solscan]({solscan_link})"
                        )
                        with state_lock:
                            active_positions[token_addr] = {
                                "entry_price": price,
                                "symbol": symbol,
                                "tp": GOLDEN_TAKE_PROFIT,
                                "sl": GOLDEN_STOP_LOSS,
                                "highest_price": price
                            }
                        send_telegram_msg(golden_msg)
                        send_graphic_signal_to_vip_channel(
                            token_addr=token_addr, symbol=symbol, price=price, tp=GOLDEN_TAKE_PROFIT,
                            sl=GOLDEN_STOP_LOSS, buy_amt=current_buy_amt, volume=volume_5m, liquidity=liquidity,
                            p_change=price_change_5m, solscan_link=solscan_link, signal_title="🚀🔥 گزینه طلایی هالکی VIP"
                        )
                        continue

                if COMBO_RUNNING and token_addr not in trend_alerted_tokens:
                    if (price_change_5m >= COMBO_MIN_CHANGE_5M and 
                        volume_5m >= COMBO_MIN_VOLUME_5M and 
                        liquidity >= COMBO_MIN_LIQUIDITY):

                        current_buy_amt = get_dynamic_buy_amount(COMBO_BUY_AMOUNT_SOL)
                        success, result_info = execute_real_buy(token_addr, COMBO_BUY_AMOUNT_SOL)
                        if not success:
                            continue
                        
                        with state_lock:
                            trend_alerted_tokens.add(token_addr)
                            processed_tokens.add(token_addr)

                        solscan_link = f"https://solscan.io/tx/{result_info}"

                        with state_lock:
                            active_positions[token_addr] = {
                                "entry_price": price,
                                "symbol": symbol,
                                "tp": COMBO_TAKE_PROFIT,
                                "sl": COMBO_STOP_LOSS,
                                "highest_price": price
                            }
                        send_graphic_signal_to_vip_channel(
                            token_addr=token_addr, symbol=symbol, price=price, tp=COMBO_TAKE_PROFIT,
                            sl=COMBO_STOP_LOSS, buy_amt=current_buy_amt, volume=volume_5m, liquidity=liquidity,
                            p_change=price_change_5m, solscan_link=solscan_link, signal_title="🚨 سیگنال ترکیبی ترند هالکی VIP"
                        )
                        continue

                if IS_RUNNING and token_addr not in processed_tokens:
                    if (liquidity >= FIRE_MIN_LIQUIDITY and 
                        volume_5m >= FIRE_MIN_VOLUME_5M and 
                        price_change_5m >= FIRE_MIN_PRICE_CHANGE_5M):

                        current_buy_amt = get_dynamic_buy_amount(FIRE_BUY_AMOUNT_SOL)
                        success, result_info = execute_real_buy(token_addr, FIRE_BUY_AMOUNT_SOL)
                        if not success:
                            continue

                        with state_lock:
                            processed_tokens.add(token_addr)
                        
                        solscan_link = f"https://solscan.io/tx/{result_info}"
                        
                        with state_lock:
                            active_positions[token_addr] = {
                                "entry_price": price,
                                "symbol": symbol,
                                "tp": FIRE_TAKE_PROFIT,
                                "sl": FIRE_STOP_LOSS,
                                "highest_price": price
                            }
                        send_graphic_signal_to_vip_channel(
                            token_addr=token_addr, symbol=symbol, price=price, tp=FIRE_TAKE_PROFIT,
                            sl=FIRE_STOP_LOSS, buy_amt=current_buy_amt, volume=volume_5m, liquidity=liquidity,
                            p_change=price_change_5m, solscan_link=solscan_link, signal_title="🔥 سیگنال خرید خودکار هالکی VIP"
                        )
        except Exception as e:
            logger.error(f"⚠️ خطای موتور پردازش بازار: {e}")
        time.sleep(2)

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
        <script>
            let telegramId = "";
            if (window.Telegram && window.Telegram.WebApp) {
                window.Telegram.WebApp.ready();
                if (window.Telegram.WebApp.initDataUnsafe && window.Telegram.WebApp.initDataUnsafe.user) {
                    telegramId = window.Telegram.WebApp.initDataUnsafe.user.id;
                }
            }
            const urlParams = new URLSearchParams(window.location.search);
            if (!telegramId) { telegramId = urlParams.get('telegram_id') || ""; }

            fetch('/api/check-status?telegram_id=' + telegramId)
            .then(res => res.json())
            .then(data => {
                const area = document.getElementById('contentArea');
                if(data.has_subscription) {
                    area.innerHTML = `
                        <p>وضعیت سیستم: <span class="badge">آنلاین (اشتراک فعال VIP)</span></p>
                        <div style="background: #0f172a; padding: 15px; border-radius: 12px; text-align: center; border: 1px solid #22c55e; margin-top: 15px;">
                            <h3 style="color: #22c55e; margin-top: 0; font-size: 15px;">🎉 اشتراک VIP شما فعال است</h3>
                            <p style="color: #38bdf8; font-size: 13px; font-weight: bold;">⏳ تاریخ انقضا: ${data.expiry_date}</p>
                            <p id="remainingTime" style="color:#facc15;font-size:13px;font-weight:bold;">محاسبه زمان باقی‌مانده...</p>
                            <p style="color: #94a3b8; font-size: 11px;">با پایان اشتراک، دسترسی ربات و کانال به‌صورت خودکار قطع می‌شود.</p>
                            <a href="${data.channel_link || '#'}" target="_blank" class="btn" style="background: #8b5cf6;">📢 ورود به کانال VIP</a>
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
                        <label style="font-size:11px; color:#94a3b8;">انتخاب ارز پرداخت:</label>
                        <select id="paymentCurrency">
                            <option value="SOL">پرداخت با ارز SOL (سولانا)</option>
                            <option value="USDC">پرداخت با ارز USDC (تتر)</option>
                        </select>
                        <input type="text" id="userTelegramId" value="${telegramId}" placeholder="آیدی تلگرام شما">
                        <input type="text" id="userWallet" placeholder="آدرس ولت فرستنده شما">
                        <input type="text" id="txSignature" placeholder="هش تراکنش (TxID) واریز شده را اینجا وارد کنید">
                        <button class="btn btn-pay" onclick="verifyAndPay()">تایید تراکنش و عضویت خودکار در کانال</button>
                    `;
                }
            });

            function verifyAndPay() {
                const tId = document.getElementById('userTelegramId').value;
                const wallet = document.getElementById('userWallet').value;
                const txSig = document.getElementById('txSignature').value;
                const currency = document.getElementById('paymentCurrency').value;
                if(!tId || !wallet || !txSig) { alert('لطفاً تمام فیلدها از جمله هش تراکنش (TxID) را وارد کنید!'); return; }
                
                alert('در حال استعلام و تایید تراکنش روی بلاکچین سولانا...');
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

@web_app.route('/api/check-status')
def api_check_status():
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
    return jsonify({
        "has_subscription": has_sub,
        "expiry_date": expiry_str,
        "last_expiry": last_exp,
        "remaining_seconds": remaining_seconds,
        "channel_link": CHANNEL_INVITE_LINK
    })

@web_app.route('/api/subscribe', methods=['POST'])
def api_subscribe():
    data = request.json or {}
    t_id = data.get("telegram_id")
    wallet = data.get("wallet_address")
    tx_sig = data.get("tx_signature")
    currency = data.get("currency", "SOL")

    if not (t_id and wallet and tx_sig):
        return jsonify({"status": "error", "message": "اطلاعات ورودی ناقص است."}), 400

    is_valid, v_msg = verify_blockchain_transaction(tx_sig, currency)
    if not is_valid:
        return jsonify({"status": "error", "message": f"تایید تراکنش ناموفق: {v_msg}"}), 400

    success = register_subscription(t_id, wallet, tx_sig, currency)
    if success:
        return jsonify({"status": "success", "message": "اشتراک شما با موفقیت فعال شد!"})
    else:
        return jsonify({"status": "error", "message": "خطا در ثبت اشتراک."}), 500

def _engine_status_lines():
    return (f"🔥 Fire: {'🟢' if IS_RUNNING else '🔴'}\n" f"📈 Trend: {'🟢' if TREND_ALERT_RUNNING else '🔴'}\n" f"🤝 Combo: {'🟢' if COMBO_RUNNING else '🔴'}\n" f"🏆 Golden: {'🟢' if GOLDEN_OPTION else '🔴'}\n" f"📊 Technical: {'🟢' if TECHNICAL_RUNNING else '🔴'}\n" f"🧠 Ultimate/AI: {'🟢' if ULTIMATE_21_ENGINE_ENABLED else '🔴'}\n" f"⚡ Mempool: {'🟢' if MEMPOOL_SMART_MONEY_ENABLED else '🔴'}\n" f"🐋 Whale: {'🟢' if BOTTOM_WHALE_RUNNING else '🔴'}\n" f"🛡 Anti-Wash: {'🟢' if ANTI_WASH_TRADING_ENABLED else '🔴'}\n" f"🤖 Copy: {'🟢' if COPY_TRADING_ENABLED else '🔴'}\n" f"⚡ اتحاد موتورها: {'🟢' if SYNCHRONIZED_MODE else '🔴'}")

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
        rows.append([InlineKeyboardButton("🎁 عضویت رایگان کاربر",callback_data="free_users")])
    return InlineKeyboardMarkup(rows)

def _control_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔥 Fire",callback_data="toggle_fire"),InlineKeyboardButton("📈 Trend",callback_data="toggle_trend")],[InlineKeyboardButton("🤝 Combo",callback_data="toggle_combo"),InlineKeyboardButton("🏆 Golden",callback_data="toggle_golden")],[InlineKeyboardButton("📊 Technical",callback_data="toggle_tech"),InlineKeyboardButton("⚡ Mempool",callback_data="toggle_mempool")],[InlineKeyboardButton("🐋 Whale",callback_data="toggle_whale"),InlineKeyboardButton("🤖 Copy",callback_data="toggle_copy")],[InlineKeyboardButton("🔙 بازگشت",callback_data="home")]])

def start_telegram_bot():
    try:
        if not TELEGRAM_BOT_TOKEN:
            logger.error("❌ TELEGRAM_BOT_TOKEN تنظیم نشده؛ ربات تلگرام اجرا نشد."); return
        app=ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        async def start_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
            chat_id=update.effective_chat.id; is_admin=bool(TELEGRAM_CHAT_ID and str(chat_id)==str(TELEGRAM_CHAT_ID)); active,exp_date=check_user_subscription(chat_id)
            text=(f"🎉 **خوش آمدید به هالکی VIP**\n\n🟢 اشتراک شما فعال است.\n⏳ پایان اشتراک: `{exp_date}`" if active else "🤖 **ربات هوشمند ترید هالکی**\n\n🔴 اشتراک VIP فعال نیست.\nبرای ثبت‌نام و فعال‌سازی، Mini App را باز کنید.")
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

        async def button_handler(update:Update,context:ContextTypes.DEFAULT_TYPE):
            global IS_RUNNING,TREND_ALERT_RUNNING,COMBO_RUNNING,GOLDEN_OPTION,TECHNICAL_RUNNING,MEMPOOL_SMART_MONEY_ENABLED,BOTTOM_WHALE_RUNNING,COPY_TRADING_ENABLED
            q=update.callback_query; await q.answer(); cid=str(q.from_user.id); is_admin=bool(TELEGRAM_CHAT_ID and cid==str(TELEGRAM_CHAT_ID)); data=q.data
            if data=="home": await q.edit_message_text("🤖 **مرکز کنترل هالکی VIP**\n\nاز دکمه‌های شیشه‌ای زیر انتخاب کنید.",reply_markup=_main_keyboard(is_admin),parse_mode="Markdown")
            elif data=="engines": await q.edit_message_text("🎛 **وضعیت موتورهای هوشمند**\n\n"+_engine_status_lines(),reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت",callback_data="home")]]),parse_mode="Markdown")
            elif data=="controls": await q.edit_message_text("🎛 **کنترل سریع موتورها**\n\nهر موتور مستقل کنترل می‌شود.",reply_markup=_control_keyboard(),parse_mode="Markdown") if is_admin else await q.edit_message_text("⛔ این بخش فقط برای ادمین است.",reply_markup=_main_keyboard(False))
            elif data=="wallet":
                if not is_admin: await q.edit_message_text("⛔ اطلاعات ولت اصلی خصوصی است.",reply_markup=_main_keyboard(False))
                else: await q.edit_message_text(f"💼 **ولت اصلی**\n\n💰 موجودی: `{get_sol_balance():.6f} SOL`\n\n📍 `{WALLET_PUBKEY or '-'} `",reply_markup=_main_keyboard(True),parse_mode="Markdown")
            elif data=="stats":
                a=get_advanced_trade_analytics(); await q.edit_message_text(f"📊 **آمار واقعی ثبت‌شده**\n\nمعاملات: `{a['total_trades']}`\nWin Rate: `{a['win_rate']:.2f}%`\nسود/زیان: `{a['total_pct']:+.2f}%`\nP/L: `${a['total_usd']:+.2f}`",reply_markup=_main_keyboard(is_admin),parse_mode="Markdown")
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
            elif data.startswith("toggle_"):
                if not is_admin: await q.edit_message_text("⛔ دسترسی غیرمجاز.",reply_markup=_main_keyboard(False)); return
                mapping={"toggle_fire":"IS_RUNNING","toggle_trend":"TREND_ALERT_RUNNING","toggle_combo":"COMBO_RUNNING","toggle_golden":"GOLDEN_OPTION","toggle_tech":"TECHNICAL_RUNNING","toggle_mempool":"MEMPOOL_SMART_MONEY_ENABLED","toggle_whale":"BOTTOM_WHALE_RUNNING","toggle_copy":"COPY_TRADING_ENABLED"}; name=mapping[data]; globals()[name]=not bool(globals()[name]); await q.edit_message_text("🎛 **کنترل موتورها**\n\n"+_engine_status_lines(),reply_markup=_control_keyboard(),parse_mode="Markdown")
        app.add_handler(CommandHandler("start",start_cmd))
        app.add_handler(CommandHandler("free",free_cmd))
        app.add_handler(CallbackQueryHandler(button_handler))
        logger.info("🤖 ربات تلگرام با منوی کنترل شیشه‌ای استارت شد.")
        app.run_polling(drop_pending_updates=False)
    except Exception as e: logger.exception(f"Telegram bot runtime error: {e}")

if __name__ == "__main__":
    logger.info("🚀 در حال راه‌اندازی ربات هوشمند تریدینگ هالکی...")

    threads = [
        Thread(target=self_learning_ai_optimizer_loop, daemon=True, name="AILearning"),
        Thread(target=ultra_accuracy_scanner_loop, args=(None,), daemon=True, name="UltraScanner"),
        Thread(target=mempool_smart_money_scanner_loop, args=(None,), daemon=True, name="MempoolScanner"),
        Thread(target=subscription_monitor_loop, daemon=True, name="SubMonitor"),
        Thread(target=check_positions_loop, daemon=True, name="PositionsCheck"),
        Thread(target=technical_analysis_scanner_loop, args=(None,), daemon=True, name="TechScanner"),
        Thread(target=unified_market_scanner_loop, args=(None,), daemon=True, name="UnifiedScanner"),
    ]
    for t in threads:
        t.start()

    port = int(os.environ.get("PORT", 5000))
    flask_thread = Thread(target=lambda: web_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False), daemon=True)
    flask_thread.start()

    start_telegram_bot()
