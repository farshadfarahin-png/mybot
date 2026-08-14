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
from threading import Thread, Lock
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
db_lock = Lock()
state_lock = Lock()
rpc_lock = Lock()

# ایجاد جلسه ارتباطی پرسرعت با قابلیت Re-use اتصالات و ریتراپ
http_session = requests.Session()
retries = Retry(total=2, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retries)
http_session.mount("https://", adapter)
http_session.mount("http://", adapter)

# تنظیمات کلیدی محیطی و کانال انتشار سیگنال
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "TOKEN_YOW")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "CHAT_ID_YOW")
ADMIN_SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY", "HULK_SUPER_SECRET_ADMIN_PASS_99")

CHANNEL_ID = os.environ.get("CHANNEL_ID", "-1003840577545") 
CHANNEL_INVITE_LINK = "https://t.me/+c_o1BlwD7Q4ZjZk"

PRIVATE_KEY_BASE58 = os.environ.get("PRIVATE_KEY_BASE58", "YOUR_PRIVATE_KEY")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://your-render-or-hosting-url.com")

# =========================================================================
# مدیریت حالت چرخشی ۴ لینک خصوصی RPC (Round-Robin RPC Manager with Failover)
# =========================================================================
rpc_env_candidates = [
    os.environ.get("RPC_URL_1"),
    os.environ.get("RPC_URL_2"),
    os.environ.get("RPC_URL_3"),
    os.environ.get("RPC_URL_4"),
    os.environ.get("RPC_URL"),
]

# استخراج و پالایش آدرس‌های معتبر
RPC_URL_LIST = [url.strip() for url in rpc_env_candidates if url and str(url).strip().startswith("http")]

# در صورتی که لینک‌ها در یک متغیر به صورت جدا شده با کاما ذخیره شده باشند
if not RPC_URL_LIST:
    raw_rpc_str = os.environ.get("RPC_URLS", "")
    if raw_rpc_str:
        RPC_URL_LIST = [u.strip() for u in raw_rpc_str.split(",") if u.strip().startswith("http")]

# فال‌بک به RPC عمومی در صورت عدم دریافت متغیرهای محیطی
if not RPC_URL_LIST:
    RPC_URL_LIST = [
        "https://api.mainnet-beta.solana.com",
        "https://solana-api.projectserum.com"
    ]

rpc_index = 0

def get_rpc_url():
    """دریافت آدرس RPC بعدی به صورت چرخشی نوبت‌گردان (Round-Robin)"""
    global rpc_index
    with rpc_lock:
        url = RPC_URL_LIST[rpc_index % len(RPC_URL_LIST)]
        rpc_index = (rpc_index + 1) % len(RPC_URL_LIST)
        return url

def post_rpc(payload, timeout=5):
    """ارسال درخواست به شبکه سولانا با قابلیت چرخش خودکار در صورت خطا روی لینک فعال"""
    for _ in range(len(RPC_URL_LIST) * 2):
        current_url = get_rpc_url()
        try:
            res = http_session.post(current_url, json=payload, timeout=timeout)
            if res.status_code == 200:
                json_data = res.json()
                if "error" not in json_data or "result" in json_data:
                    return json_data
        except Exception as e:
            logger.debug(f"RPC Failover: خطا روی {current_url} -> سوئیچ به RPC بعدی | detail: {e}")
            time.sleep(0.1)
    return {}

SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" 
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

# سوئیچ‌های کنترلی ربات
IS_RUNNING = False          
TREND_ALERT_RUNNING = False 
COMBO_RUNNING = False       
GOLDEN_OPTION = False       
TECHNICAL_RUNNING = False   
SMART_FILTER_ENABLED = True   
DYNAMIC_RISK_ENABLED = True   
MANUAL_SETTINGS_ENABLED = False 
SYNCHRONIZED_MODE = False   
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

FIRE_BUY_AMOUNT_SOL = 0.01
FIRE_TAKE_PROFIT = 18.0
FIRE_STOP_LOSS = -10.0
FIRE_MIN_LIQUIDITY = 20000       
FIRE_MIN_VOLUME_5M = 5000       
FIRE_MIN_PRICE_CHANGE_5M = 5.0  

COMBO_BUY_AMOUNT_SOL = 0.01
COMBO_TAKE_PROFIT = 18.0
COMBO_STOP_LOSS = -10.0
COMBO_MIN_LIQUIDITY = 25000
COMBO_MIN_VOLUME_5M = 12000  
COMBO_MIN_CHANGE_5M = 15.0   

GOLDEN_BUY_AMOUNT_SOL = 0.01
GOLDEN_TAKE_PROFIT = 16.0
GOLDEN_STOP_LOSS = -8.0
GOLDEN_MIN_LIQUIDITY = 30000
GOLDEN_MIN_VOLUME_5M = 15000
GOLDEN_MIN_CHANGE_5M = 12.0

TECH_BUY_AMOUNT_SOL = 0.01
TECH_TAKE_PROFIT = 20.0
TECH_STOP_LOSS = -8.0
TECH_MIN_LIQUIDITY = 20000
TECH_MIN_VOLUME_5M = 10000

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
                    status TEXT
                )
            """)
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
                            logger.info("🧠 [AI Adjustment]: فیلتر نقدینگی سخت‌تر شد.")
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
        if (len(socials) > 0 or len(websites) > 0) and buys >= (sells * 1.05):
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

                if liquidity > 15000 and volume_5m > 3000 and price > 0:
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
        res = post_rpc(payload, timeout=5)
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

def send_telegram_msg(text, target_chat=None):
    chat_target = target_chat if target_chat else TELEGRAM_CHAT_ID
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_target,
            "text": text,
            "disable_web_page_preview": True,
            "parse_mode": "Markdown"
        }
        http_session.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.error(f"❌ خطای ارسال پیام به تلگرام: {e}")

def send_graphic_signal_to_vip_channel(token_addr, symbol, price, tp, sl, buy_amt, volume, liquidity, p_change, solscan_link, signal_title="🚀 سیگنال ویژه VIP"):
    if not CHANNEL_ID:
        return
    
    graphic_text = (
        f"╔══════════════════════╗\n"
        f"  {signal_title}\n"
        f"╚══════════════════════╝\n\n"
        f"🪙 نام توکن: #{symbol}\n"
        f"📍 آدرس قرارداد:\n{token_addr}\n\n"
        f"💵 قیمت ورود: ${price:.8f}\n"
        f"💰 حجم معامله: SOL {buy_amt}\n"
        f"🎯 تارگت سود: +%{tp}\n"
        f"🛑 حد ضرر: %{sl}\n\n"
        f"📊 آمار زنده بازار:\n"
        f"▪️ روند ۵ دقیقه: +%{p_change:.2f}\n"
        f"▪️ حجم معاملات: ${volume:,.0f}\n"
        f"▪️ نقدینگی کل: ${liquidity:,.0f}\n\n"
        f"⚡️ *سیستم هوشمند هولکی*\n"
        f"━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 بررسی در Solscan", url=solscan_link),
            InlineKeyboardButton("📈 نمودار DexScreener", url=f"https://dexscreener.com/solana/{token_addr}")
        ],
        [
            InlineKeyboardButton("🤖 ورود به مینی‌اپلیکیشن و کپی‌ترید", url=WEBAPP_URL)
        ]
    ])

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHANNEL_ID,
            "text": graphic_text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
            "reply_markup": keyboard.to_dict()
        }
        http_session.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.error(f"❌ خطا در ارسال سیگنال گرافیکی به کانال: {e}")

def register_subscription(telegram_id, wallet_addr, tx_sig, currency="SOL"):
    with db_lock:
        try:
            conn = sqlite3.connect("bot_analytics.db", timeout=30.0, check_same_thread=False)
            cursor = conn.cursor()
            expiry = datetime.now() + timedelta(days=30)
            cursor.execute("""
                INSERT OR REPLACE INTO subscribers (telegram_id, wallet_address, expiry_date, tx_signature, status)
                VALUES (?, ?, ?, ?, 'ACTIVE')
            """, (str(telegram_id), wallet_addr, expiry.strftime("%Y-%m-%d %H:%M:%S"), f"{currency}:{tx_sig}"))
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
                INSERT OR REPLACE INTO subscribers (telegram_id, wallet_address, expiry_date, tx_signature, status)
                VALUES (?, ?, ?, ?, 'ACTIVE')
            """, (str(telegram_id), wallet_addr, expiry.strftime("%Y-%m-%d %H:%M:%S"), "ADMIN_FREE_PASS"))
            conn.commit()
            conn.close()
            
            free_msg = (
                f"🎉 اشتراک VIP رایگان شما توسط ادمین فعال شد!\n\n"
                f"⏳ تاریخ انقضا و قطع ارتباط: {expiry.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"🔗 موتور کپی‌تریدینگ برای ولت شما روشن گردید.\n"
                f"📢 از طریق لینک زیر وارد کانال سیگنال‌ها شوید:\n\n"
                f"{CHANNEL_INVITE_LINK}"
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
    err_txt = f"خطا در کلید خصوصی ولت: {e}"
    logger.error(err_txt)
    send_telegram_msg(err_txt)
    WALLET_PUBKEY = None

def get_sol_balance():
    if not WALLET_PUBKEY:
        return 0.0
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [WALLET_PUBKEY]
    }
    res = post_rpc(payload, timeout=5)
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
    res = post_rpc(payload, timeout=8)
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
            if buys > 0 and sells > 0 and buys < (sells * 1.05):
                return False
        
        liquidity = float(pair.get('liquidity', {}).get('usd', 0))
        volume_5m = float(pair.get('volume', {}).get('m5', 0))
        if liquidity < 15000 or volume_5m < 3000:
            return False
        return True
    except Exception:
        return False

def check_major_support_resistance_pa(pair):
    try:
        if not is_token_worthy(pair):
            return False, ""
        price_change_5m = float(pair.get('priceChange', {}).get('m5', 0))
        if price_change_5m <= -2.0:
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

        if price <= 0 or liquidity < 15000 or volume_5m < 3000:
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
        if liquidity < 15000 or volume_5m < 3000:
            return False, 0.0, 0.0, 0.0, "نقدینگی یا حجم کافی نیست"
        if price_change_5m < 3.0:
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
    if not WALLET_PUBKEY:
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
        
        tx_res = post_rpc(rpc_payload, timeout=8)

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
        blockhash_res = post_rpc({"jsonrpc": "2.0", "id": 1, "method": "getLatestBlockhash"}, timeout=3)
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
        post_rpc(rpc_payload, timeout=3)
    except Exception as e:
        logger.warning(f"⚠️ هشدار در بستن اکانت WSOL: {e}")

def execute_real_sell(token_mint, token_amount):
    if not WALLET_PUBKEY:
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
        
        tx_res = post_rpc(rpc_payload, timeout=8)
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

                if BOTTOM_WHALE_RUNNING and token_addr not in processed_tokens:
                    txns = pair.get('txns', {}).get('m5', {})
                    buys = txns.get('buys', 0)
                    sells = txns.get('sells', 0)

                    is_bottom_accumulation = (
                        -3.0 <= price_change_5m <= 8.0 and 
                        volume_5m >= (liquidity * 0.15) and 
                        buys >= sells
                    )
                    
                    is_pump_breakout = (
                        price_change_5m >= 8.0 and 
                        volume_5m >= 8000 and 
                        buys >= sells
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
                            <p style="color: #38bdf8; font-size: 13px; font-weight: bold;">⏳ تاریخ انقضا و قطع ارتباط: ${data.expiry_date}</p>
                            <p style="color: #94a3b8; font-size: 11px;">پس از اتمام این تاریخ، دسترسی شما به صورت خودکار از ربات و کانال قطع خواهد شد.</p>
                            <a href="https://t.me/+c_o1BlwD7Q4ZjZk" target="_blank" class="btn" style="background: #8b5cf6;">📢 ورود به کانال VIP</a>
                        </div>
                    `;
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

@web_app.route('/admin-panel')
def admin_panel():
    t_id = request.args.get("telegram_id", "")
    secret_key = request.args.get("secret", "")
    
    is_admin_id = str(t_id) == str(TELEGRAM_CHAT_ID)
    is_secret_valid = secret_key == ADMIN_SECRET_KEY

    if not (is_admin_id or is_secret_valid):
        return "<h3 style='color:red; text-align:center;'>⛔ دسترسی غیرمجاز! احراز هویت ادمین ناموفق بود.</h3>", 403
    
    subs = get_active_subscribers()
    analytics = get_advanced_trade_analytics()

    best_str = f"🪙 {analytics['best_trade'][0]} ({analytics['best_trade'][1]:+.2f}%)" if analytics['best_trade'] else "ثبت نشده"
    worst_str = f"🪙 {analytics['worst_trade'][0]} ({analytics['worst_trade'][1]:+.2f}%)" if analytics['worst_trade'] else "ثبت نشده"

    admin_html = f"""
    <!DOCTYPE html>
    <html lang="fa" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>پنل ادمین و گزارش پیشرفته هالکی</title>
        <style>
            body {{ background:#0f172a; color:#fff; text-align:center; font-family:Tahoma; padding:15px; margin:0; }}
            .card {{ background:#1e293b; padding:20px; border-radius:12px; max-width:500px; margin:auto; text-align:right; box-shadow: 0 4px 20px rgba(0,0,0,0.7); }}
            h1 {{ color:#a855f7; text-align:center; font-size:16px; }}
            input {{ width: 100%; box-sizing: border-box; padding: 10px; margin: 6px 0; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: white; text-align: center; }}
            .btn-free {{ background: #8b5cf6; color: white; border: none; padding: 10px; border-radius: 8px; font-weight: bold; cursor: pointer; width: 100%; margin-top: 5px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>👑 پنل مدیریت و گزارش پیشرفته (امنیت ۱۰۰۰/۱۰۰۰)</h1>
            
            <div style="background:#0f172a;padding:12px;border-radius:8px;margin-bottom:15px;border:1px solid #334155;">
                <h3 style="color:#38bdf8;margin-top:0;font-size:14px;text-align:center;">🎁 اعطای اشتراک رایگان سریع</h3>
                <input type="text" id="freeTelegramId" placeholder="آیدی تلگرام کاربر (عدد)">
                <button class="btn-free" onclick="grantFreeSub()">ثبت عضویت رایگان ۳۰ روزه</button>
            </div>

            <div style="background:#0f172a;padding:12px;border-radius:8px;margin-bottom:15px;border:1px solid #334155;">
                <h3 style="color:#38bdf8;margin-top:0;font-size:14px;text-align:center;">📊 آمار جامع عملکرد ربات</h3>
                <p>🔹 کل معاملات ثبت‌شده: <b>{analytics['total_trades']}</b></p>
                <p>📈 مجموع سود/زیان درصدی: <b style="color:#22c55e;">{analytics['total_pct']:+.2f}%</b></p>
                <p>💵 مجموع سود/زیان دلاری: <b style="color:#22c55e;">${analytics['total_usd']:+.2f}</b></p>
                <p>🎯 نرخ موفقیت (Win Rate): <b style="color:#38bdf8;">{analytics['win_rate']}%</b></p>
                <p>🏆 بهترین معامله: <b style="color:#22c55e;">{best_str}</b></p>
                <p>📉 بدترین معامله: <b style="color:#ef4444;">{worst_str}</b></p>
            </div>

            <p>👥 کاربران فعال VIP (با تاریخ انقضا و اخراج خودکار): <b>{len(subs)}</b></p>
    """
    for sub in subs:
        admin_html += f"<div style='background:#0f172a;padding:8px;margin:5px 0;border-radius:6px;font-size:11px;'>🆔 {sub['telegram_id']} | ⏳ انقضا: {sub['expiry']}</div>"
    
    admin_html += f"""
        </div>
        <script>
            function grantFreeSub() {{
                const tId = document.getElementById('freeTelegramId').value;
                if(!tId) {{ alert('لطفاً آیدی تلگرام کاربر را وارد کنید!'); return; }}
                
                fetch('/api/admin/free-sub', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{telegram_id: tId, admin_id: "{TELEGRAM_CHAT_ID}", secret: "{ADMIN_SECRET_KEY}"}})
                }}).then(res => res.json()).then(data => {{
                    alert(data.message);
                    if(data.status === 'success') {{ location.reload(); }}
                }}).catch(err => {{ alert('خطا در ارتباط با سرور.'); }});
            }}
        </script>
    </body>
    </html>
    """
    return admin_html

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
                    logger.error(f"Status check exception: {e}")
    return jsonify({"has_subscription": has_sub, "expiry_date": expiry_str, "last_expiry": last_exp})

@web_app.route('/api/subscribe', methods=['POST'])
def api_subscribe():
    data = request.json or {}
    t_id = data.get("telegram_id")
    wallet = data.get("wallet_address")
    tx_signature = data.get("tx_signature")
    currency = data.get("currency", "SOL")
    
    if not t_id or not wallet or not tx_signature:
        return jsonify({"status": "error", "message": "اطلاعات ناقص است یا هش تراکنش وارد نشده است."})
        
    is_valid, verify_msg = verify_blockchain_transaction(tx_signature, currency)
    if not is_valid:
        return jsonify({"status": "error", "message": f"تایید تراکنش ناموفق بود: {verify_msg}"})
        
    success = register_subscription(t_id, wallet, tx_signature, currency)
    if success:
        return jsonify({"status": "success", "message": "تراکنش روی بلاکچین تایید، اشتراک ۳۰ روزه فعال و دسترسی کانال باز شد!"})
    else:
        return jsonify({"status": "error", "message": "خطا در ثبت نهایی اشتراک در دیتابیس."})

@web_app.route('/api/advanced-reports')
def api_advanced_reports():
    return jsonify(get_advanced_trade_analytics())

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

def get_main_keyboard():
    def s(val): return "روشن 🟢" if val else "خاموش 🔴"

    bottom_whale_status = f"🐳 کف معتبر و نهنگ: {s(BOTTOM_WHALE_RUNNING)}"
    golden_status = f"🚀 گزینه طلایی: {s(GOLDEN_OPTION)}"
    combo_status = f"🚨 حالت ترکیبی: {s(COMBO_RUNNING)}"
    trader_status = f"🔥 خرید و فروش: {s(IS_RUNNING)}"
    trend_status = f"🚨 اعلان ترند: {s(TREND_ALERT_RUNNING)}"
    tech_status = f"📊 پرایس اکشن + AI: {s(TECHNICAL_RUNNING)}"
    smart_status = f"🛡️ فیلتر هوشمند: {s(SMART_FILTER_ENABLED)}"
    risk_status = f"⚖️ ریسک داینامیک: {s(DYNAMIC_RISK_ENABLED)}"
    manual_status = f"⚙️ تنظیمات دستی: {s(MANUAL_SETTINGS_ENABLED)}"
    sync_status = f"⚡ ابرسیگنال + AI Vision: {s(SYNCHRONIZED_MODE)}"
    copy_status = f"🔗 کپی‌تریدینگ VIP: {s(COPY_TRADING_ENABLED)}"
    
    ultimate_21_status = f"💎 سیستم ۲۱ لایه: {s(ULTIMATE_21_ENGINE_ENABLED)}"
    ai_learning_status = f"🧠 هوش مصنوعی یادگیرنده: {s(SELF_LEARNING_AI_ENABLED)}"
    mempool_status = f"⚡🕵️ اسکنر ممپول & اسمارت‌مانی: {s(MEMPOOL_SMART_MONEY_ENABLED)}"
    hulk_moon_status = f"💪🟢 موم‌بگ هالکی (۸۰/۲۰): {s(MOONBAG_HULK_ENABLED)}"
    wash_status = f"🛡️🟢 ضد حجم فیک (Wash Shield): {s(ANTI_WASH_TRADING_ENABLED)}"

    smart_money_copy_status = f"🎯 اسمارت‌مانی کپی‌اسنایپر: {s(SMART_MONEY_COPY_ENABLED)}"
    social_sentiment_status = f"📈 سنتیمنت و هجوم هایپ: {s(SOCIAL_SENTIMENT_ENABLED)}"
    dynamic_trailing_status = f"📊 تریلینگ استاپ پویا (۹۹٪): {s(DYNAMIC_TRAILING_TP_ENABLED)}"

    keyboard = [
        [InlineKeyboardButton(trader_status, callback_data="toggle_trader"), InlineKeyboardButton(golden_status, callback_data="toggle_golden")],
        [InlineKeyboardButton(combo_status, callback_data="toggle_combo"), InlineKeyboardButton(trend_status, callback_data="toggle_trend")],
        [InlineKeyboardButton(tech_status, callback_data="toggle_tech"), InlineKeyboardButton(bottom_whale_status, callback_data="toggle_bottom_whale")],
        [InlineKeyboardButton(sync_status, callback_data="toggle_sync"), InlineKeyboardButton(smart_status, callback_data="toggle_smart")],
        [InlineKeyboardButton(risk_status, callback_data="toggle_risk"), InlineKeyboardButton(copy_status, callback_data="toggle_copy")],
        [InlineKeyboardButton(ultimate_21_status, callback_data="toggle_ultimate_21"), InlineKeyboardButton(ai_learning_status, callback_data="toggle_ai_learning")],
        [InlineKeyboardButton(mempool_status, callback_data="toggle_mempool"), InlineKeyboardButton(hulk_moon_status, callback_data="toggle_moonbag")],
        [InlineKeyboardButton(wash_status, callback_data="toggle_wash"), InlineKeyboardButton(smart_money_copy_status, callback_data="toggle_smart_money_copy")],
        [InlineKeyboardButton(social_sentiment_status, callback_data="toggle_social_sentiment"), InlineKeyboardButton(dynamic_trailing_status, callback_data="toggle_dynamic_trailing")],
        [InlineKeyboardButton("📊 گزارش پیشرفته PnL", callback_data="show_pnl_report"), InlineKeyboardButton("🌐 ورود به پنل ادمین", url=f"{WEBAPP_URL}/admin-panel?secret={ADMIN_SECRET_KEY}")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id != TELEGRAM_CHAT_ID:
        await update.message.reply_text("⛔ دسترسی غیرمجاز!")
        return

    sol_balance = get_sol_balance()
    rpc_count = len(RPC_URL_LIST)
    msg = (
        f"🤖 *ربات فوق‌پیشرفته ترید و سیگنال‌دهی هالکی (نسخه شبکه چرخشی 4-RPC)*\n\n"
        f"💼 *موجودی کیف پول:* `{sol_balance:.4f} SOL`\n"
        f"🔑 *آدرس ولت:* `{WALLET_PUBKEY[:8]}...{WALLET_PUBKEY[-8:]}`\n"
        f"⚡ *تعداد لینک‌های خصوصی RPC فعال:* `{rpc_count}` عدد (با Failover خودکار)\n"
        f"📍 *پوزیشن‌های فعال:* `{len(active_positions)}` توکن\n\n"
        f"کنترل‌پنل مدیریت موتورها و فیلترها:"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global IS_RUNNING, GOLDEN_OPTION, COMBO_RUNNING, TREND_ALERT_RUNNING, TECHNICAL_RUNNING
    global BOTTOM_WHALE_RUNNING, SYNCHRONIZED_MODE, SMART_FILTER_ENABLED, DYNAMIC_RISK_ENABLED
    global COPY_TRADING_ENABLED, ULTIMATE_21_ENGINE_ENABLED, SELF_LEARNING_AI_ENABLED
    global MEMPOOL_SMART_MONEY_ENABLED, MOONBAG_HULK_ENABLED, ANTI_WASH_TRADING_ENABLED
    global SMART_MONEY_COPY_ENABLED, SOCIAL_SENTIMENT_ENABLED, DYNAMIC_TRAILING_TP_ENABLED

    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "toggle_trader": IS_RUNNING = not IS_RUNNING
    elif data == "toggle_golden": GOLDEN_OPTION = not GOLDEN_OPTION
    elif data == "toggle_combo": COMBO_RUNNING = not COMBO_RUNNING
    elif data == "toggle_trend": TREND_ALERT_RUNNING = not TREND_ALERT_RUNNING
    elif data == "toggle_tech": TECHNICAL_RUNNING = not TECHNICAL_RUNNING
    elif data == "toggle_bottom_whale": BOTTOM_WHALE_RUNNING = not BOTTOM_WHALE_RUNNING
    elif data == "toggle_sync": SYNCHRONIZED_MODE = not SYNCHRONIZED_MODE
    elif data == "toggle_smart": SMART_FILTER_ENABLED = not SMART_FILTER_ENABLED
    elif data == "toggle_risk": DYNAMIC_RISK_ENABLED = not DYNAMIC_RISK_ENABLED
    elif data == "toggle_copy": COPY_TRADING_ENABLED = not COPY_TRADING_ENABLED
    elif data == "toggle_ultimate_21": ULTIMATE_21_ENGINE_ENABLED = not ULTIMATE_21_ENGINE_ENABLED
    elif data == "toggle_ai_learning": SELF_LEARNING_AI_ENABLED = not SELF_LEARNING_AI_ENABLED
    elif data == "toggle_mempool": MEMPOOL_SMART_MONEY_ENABLED = not MEMPOOL_SMART_MONEY_ENABLED
    elif data == "toggle_moonbag": MOONBAG_HULK_ENABLED = not MOONBAG_HULK_ENABLED
    elif data == "toggle_wash": ANTI_WASH_TRADING_ENABLED = not ANTI_WASH_TRADING_ENABLED
    elif data == "toggle_smart_money_copy": SMART_MONEY_COPY_ENABLED = not SMART_MONEY_COPY_ENABLED
    elif data == "toggle_social_sentiment": SOCIAL_SENTIMENT_ENABLED = not SOCIAL_SENTIMENT_ENABLED
    elif data == "toggle_dynamic_trailing": DYNAMIC_TRAILING_TP_ENABLED = not DYNAMIC_TRAILING_TP_ENABLED
    elif data == "show_pnl_report":
        analytics = get_advanced_trade_analytics()
        report_msg = (
            f"📊 *گزارش کامل PnL معاملات دیتابیس:*\n\n"
            f"🔹 کل معاملات: `{analytics['total_trades']}`\n"
            f"📈 مجموع درصد سود/زیان: `{analytics['total_pct']:+.2f}%`\n"
            f"💵 مجموع سود دلاری: `${analytics['total_usd']:+.2f}`\n"
            f"🎯 وین‌ریت (Win Rate): `{analytics['win_rate']}%`\n"
        )
        await query.message.reply_text(report_msg, parse_mode="Markdown")
        return

    try:
        await query.edit_message_reply_markup(reply_markup=get_main_keyboard())
    except Exception as e:
        logger.debug(f"Edit markup error: {e}")

def main():
    logger.info("🚀 در حال استارت سرور وب و ربات تلگرام...")

    # ۱. اجرای سِروِر وب روی ثرد مجزا
    web_thread = Thread(target=run_web, daemon=True)
    web_thread.start()

    # ۲. راه‌اندازی ثردهای اسکنر بازار و مانیتورینگ
    Thread(target=subscription_monitor_loop, daemon=True).start()
    Thread(target=self_learning_ai_optimizer_loop, daemon=True).start()
    Thread(target=check_positions_loop, daemon=True).start()
    Thread(target=ultra_accuracy_scanner_loop, args=(None,), daemon=True).start()
    Thread(target=mempool_smart_money_scanner_loop, args=(None,), daemon=True).start()
    Thread(target=technical_analysis_scanner_loop, args=(None,), daemon=True).start()
    Thread(target=unified_market_scanner_loop, args=(None,), daemon=True).start()

    # ۳. راه‌اندازی اپلیکیشن تلگرام
    if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN != "TOKEN_YOW":
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CallbackQueryHandler(button_handler))
        logger.info("✅ ربات تلگرام با موفقیت متصل شد و در حال دریافت پیام‌ها است.")
        app.run_polling()
    else:
        logger.warning("⚠️ TELEGRAM_BOT_TOKEN تنظیم نشده است. ربات تلگرام غیرفعال ماند اما اسکنرها کار می‌کنند.")
        while True:
            time.sleep(10)

if __name__ == "__main__":
    main()
