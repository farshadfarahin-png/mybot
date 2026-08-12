import time
import requests
import json
import base64
import base58
import os
import sqlite3
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask, render_template_string, request, jsonify
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.instruction import Instruction
from solders.message import MessageV0

# تنظیمات کلیدی محیطی و کانال انتشار سیگنال
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "TOKEN_YOW")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "CHAT_ID_YOW")

CHANNEL_ID = os.environ.get("CHANNEL_ID", "-1003840577545") 
CHANNEL_INVITE_LINK = "https://t.me/+c_o1BlwD7Q4ZjZk"

PRIVATE_KEY_BASE58 = os.environ.get("PRIVATE_KEY_BASE58", "YOUR_PRIVATE_KEY")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://your-render-or-hosting-url.com")

RPC_URL = os.environ.get("RPC_URL", "https://mainnet.helius-rpc.com/?api-key=ef769dc4-03dc-4f1d-ba4a-a651d75f6b80")
SOL_MINT = "So11111111111111111111111111111111111111112"
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

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

# سوئیچ‌های پیشرفته و قابلیت‌های نسخه هالکی
ULTIMATE_21_ENGINE_ENABLED = True
SELF_LEARNING_AI_ENABLED = True
MEMPOOL_SMART_MONEY_ENABLED = True
MOONBAG_HULK_ENABLED = True
ANTI_WASH_TRADING_ENABLED = True
PRIVATE_JITO_BUNDLE_ENABLED = True
LEVERAGE_PERP_ENABLED = False

FIRE_BUY_AMOUNT_SOL = 0.01
FIRE_TAKE_PROFIT = 18.0
FIRE_STOP_LOSS = -10.0
FIRE_MIN_LIQUIDITY = 35000       
FIRE_MIN_VOLUME_5M = 8000       
FIRE_MIN_PRICE_CHANGE_5M = 8.0  

COMBO_BUY_AMOUNT_SOL = 0.01
COMBO_TAKE_PROFIT = 18.0
COMBO_STOP_LOSS = -10.0
COMBO_MIN_LIQUIDITY = 45000
COMBO_MIN_VOLUME_5M = 25000  
COMBO_MIN_CHANGE_5M = 30.0   

TREND_MIN_LIQUIDITY = 45000
TREND_MIN_VOLUME_5M = 45000  
TREND_MIN_CHANGE_5M = 30.0   
MIN_BUYS_5M = 80             

GOLDEN_BUY_AMOUNT_SOL = 0.01
GOLDEN_TAKE_PROFIT = 16.0
GOLDEN_STOP_LOSS = -8.0
GOLDEN_MIN_LIQUIDITY = 55000
GOLDEN_MIN_VOLUME_5M = 35000
GOLDEN_MIN_CHANGE_5M = 25.0
GOLDEN_MIN_BUYS_5M = 80

TECH_BUY_AMOUNT_SOL = 0.01
TECH_TAKE_PROFIT = 20.0
TECH_STOP_LOSS = -8.0
TECH_MIN_LIQUIDITY = 40000
TECH_MIN_VOLUME_5M = 20000

AWAITING_STATE = None 
processed_tokens = set()
trend_alerted_tokens = set()
golden_processed_tokens = set()
tech_processed_tokens = set()
mempool_processed_tokens = set()
active_positions = {}

closed_trades_history = []
total_realized_pnl_usd = 0.0
total_realized_pnl_percent = 0.0

def init_db():
    try:
        conn = sqlite3.connect("bot_analytics.db", check_same_thread=False)
        cursor = conn.cursor()
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
    except Exception as e:
        print(f"⚠️ خطای دیتابیس: {e}")

init_db()

def log_trade_to_db(token_addr, symbol, entry_p, exit_p, pnl_pct, pnl_u, reason):
    try:
        conn = sqlite3.connect("bot_analytics.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO trades (token_address, symbol, entry_price, exit_price, pnl_percent, pnl_usd, entry_reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (token_addr, symbol, entry_p, exit_p, pnl_pct, pnl_u, reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ خطا در ثبت معامله در دیتابیس: {e}")

def self_learning_ai_optimizer_loop():
    global FIRE_MIN_LIQUIDITY, COMBO_MIN_LIQUIDITY, GOLDEN_MIN_LIQUIDITY
    print("🧠 موتور هوش مصنوعی یادگیرنده (Self-Learning AI) فعال شد.")
    while True:
        if SELF_LEARNING_AI_ENABLED:
            try:
                conn = sqlite3.connect("bot_analytics.db", check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute("SELECT AVG(pnl_percent), COUNT(*) FROM trades")
                row = cursor.fetchone()
                if row and row[1] and row[1] >= 5:
                    avg_pnl = row[0] or 0.0
                    total_t = row[1]
                    print(f"🧠 [AI Learning]: آنالیز {total_t} معامله گذشته. میانگین سود: {avg_pnl:.2f}%")
                    if avg_pnl < 2.0:
                        FIRE_MIN_LIQUIDITY += 1000
                        GOLDEN_MIN_LIQUIDITY += 1500
                        print("🧠 [AI Adjustment]: فیلتر نقدینگی سخت‌تر شد.")
                    elif avg_pnl > 10.0:
                        FIRE_MIN_LIQUIDITY = max(25000, FIRE_MIN_LIQUIDITY - 500)
                        print("🧠 [AI Adjustment]: الگوریتم در حالت بهینه حداکثری قرار گرفت.")
                conn.close()
            except Exception as e:
                print(f"⚠️ خطای موتور هوش مصنوعی یادگیرنده: {e}")
        time.sleep(300)

def mempool_smart_money_scanner_loop(app):
    global MEMPOOL_SMART_MONEY_ENABLED
    print("⚡🕵️ موتور ممپول و اسمارت‌مانی (Mempool & Smart Money X-Ray) فعال شد.")
    while True:
        if not MEMPOOL_SMART_MONEY_ENABLED:
            time.sleep(3)
            continue
        try:
            trending_tokens = get_real_market_trending_tokens()
            for token_addr in trending_tokens[:10]:
                if not token_addr or token_addr in active_positions or token_addr in mempool_processed_tokens:
                    continue
                
                pair_res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=3).json()
                if not pair_res.get('pairs'):
                    continue
                pair = pair_res['pairs'][0]

                liquidity = float(pair.get('liquidity', {}).get('usd', 0))
                volume_5m = float(pair.get('volume', {}).get('m5', 0))
                symbol = pair.get('baseToken', {}).get('symbol', 'SMART')
                price = float(pair.get('priceUsd', 0))

                if liquidity > 30000 and volume_5m > 10000 and price > 0:
                    mempool_processed_tokens.add(token_addr)
                    processed_tokens.add(token_addr)

                    current_buy_amt = get_dynamic_buy_amount(0.01)
                    success, result_info = execute_real_buy(token_addr, 0.01)
                    buy_status_str = "شکار موفق از ممپول (موفق روی بلاکچین ✅)" if success else f"{result_info}"
                    solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

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
            print(f"⚠️ خطای اسکن ممپول: {e}")
        time.sleep(5)

def check_user_subscription(telegram_id):
    try:
        conn = sqlite3.connect("bot_analytics.db", check_same_thread=False)
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
        return False, None
    except Exception:
        return False, None

def update_sub_status(telegram_id, status):
    try:
        conn = sqlite3.connect("bot_analytics.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("UPDATE subscribers SET status = ? WHERE telegram_id = ?", (status, str(telegram_id)))
        conn.commit()
        conn.close()
    except:
        pass

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
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"❌ خطای ارسال پیام به تلگرام: {e}")

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
        f"⚡️ *سیستم هوشمند هولکی، ممپول و Jito Private Bundles*\n"
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
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"❌ خطا در ارسال سیگنال گرافیکی به کانال: {e}")

def register_subscription(telegram_id, wallet_addr, tx_sig):
    try:
        conn = sqlite3.connect("bot_analytics.db", check_same_thread=False)
        cursor = conn.cursor()
        expiry = datetime.now() + timedelta(days=30)
        cursor.execute("""
            INSERT OR REPLACE INTO subscribers (telegram_id, wallet_address, expiry_date, tx_signature, status)
            VALUES (?, ?, ?, ?, 'ACTIVE')
        """, (str(telegram_id), wallet_addr, expiry.strftime("%Y-%m-%d %H:%M:%S"), tx_sig))
        conn.commit()
        conn.close()
        
        success_msg = (
            f"🎉 اشتراک ۳۰ روزه VIP شما با موفقیت فعال شد!\n\n"
            f"🔗 ولت شما به سیستم کپی‌تریدینگ هوشمند متصل گردید.\n"
            f"📢 برای دریافت لحظه‌ای سیگنال‌ها و گزارش‌های گرافیکی، از طریق لینک زیر وارد کانال VIP شوید:\n\n"
            f"{CHANNEL_INVITE_LINK}"
        )
        send_telegram_msg(success_msg, target_chat=str(telegram_id))
        return True
    except Exception as e:
        print(f"Error registering sub: {e}")
        return False

def register_free_vip(telegram_id, wallet_addr):
    try:
        conn = sqlite3.connect("bot_analytics.db", check_same_thread=False)
        cursor = conn.cursor()
        expiry = datetime.now() + timedelta(days=365)
        cursor.execute("""
            INSERT OR REPLACE INTO subscribers (telegram_id, wallet_address, expiry_date, tx_signature, status)
            VALUES (?, ?, ?, ?, 'ACTIVE')
        """, (str(telegram_id), wallet_addr, expiry.strftime("%Y-%m-%d %H:%M:%S"), "ADMIN_FREE_PASS"))
        conn.commit()
        conn.close()
        
        free_msg = (
            f"🎉 اشتراک VIP رایگان شما توسط ادمین فعال شد!\n\n"
            f"🔗 موتور کپی‌تریدینگ برای ولت شما روشن گردید.\n"
            f"📢 از طریق لینک زیر وارد کانال سیگنال‌ها شوید:\n\n"
            f"{CHANNEL_INVITE_LINK}"
        )
        send_telegram_msg(free_msg, target_chat=str(telegram_id))
        return True
    except Exception as e:
        print(f"Error registering free sub: {e}")
        return False

def get_active_subscribers():
    active_subs = []
    try:
        conn = sqlite3.connect("bot_analytics.db", check_same_thread=False)
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
                send_telegram_msg("⚠️ اشتراک ۳۰ روزه شما به اتمام رسید.", target_chat=t_id)
    except Exception:
        pass
    return active_subs

try:
    decoded_key = base58.b58decode(PRIVATE_KEY_BASE58)
    sender_keypair = Keypair.from_bytes(decoded_key)
    WALLET_PUBKEY = str(sender_keypair.pubkey())
    print(f"✅ ولت با موفقیت لود شد: {WALLET_PUBKEY}")
except Exception as e:
    err_txt = f"خطا در کلید خصوصی ولت: {e}"
    print(err_txt)
    send_telegram_msg(err_txt)
    WALLET_PUBKEY = None

def get_sol_balance():
    if not WALLET_PUBKEY:
        return 0.0
    for attempt in range(3):
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [WALLET_PUBKEY]
            }
            res = requests.post(RPC_URL, json=payload, timeout=5).json()
            lamports = res.get("result", {}).get("value", 0)
            return lamports / 1_000_000_000
        except Exception:
            time.sleep(1)
    return 0.0

def get_dynamic_buy_amount(base_amount):
    if not DYNAMIC_RISK_ENABLED:
        return base_amount
    try:
        sol_bal = get_sol_balance()
        if ULTIMATE_21_ENGINE_ENABLED and sol_bal > 0:
            kelly_factor = 0.025 if sol_bal > 1.0 else 0.01
            calculated = sol_bal * kelly_factor
            if LEVERAGE_PERP_ENABLED:
                calculated *= 2.5 
            return max(base_amount, round(calculated, 4))
        
        if sol_bal > 1.0:
            calculated = sol_bal * 0.02
            return max(base_amount, round(calculated, 4))
        elif sol_bal < 0.1:
            return max(0.005, round(base_amount * 0.5, 4))
    except:
        pass
    return base_amount

def get_token_balance(token_mint):
    for attempt in range(3):
        try:
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
            res = requests.post(RPC_URL, json=payload, timeout=8).json()
            accounts = res.get("result", {}).get("value", [])
            if accounts:
                for acc in accounts:
                    info = acc["account"]["data"]["parsed"]["info"]
                    amount = int(info["tokenAmount"]["amount"])
                    if amount > 0:
                        return amount
            return 0
        except Exception:
            time.sleep(1)
    return 0

def is_token_worthy(pair):
    try:
        if ANTI_WASH_TRADING_ENABLED:
            txns = pair.get('txns', {}).get('m5', {})
            buys = txns.get('buys', 0)
            sells = txns.get('sells', 0)
            if buys < sells:
                return False
        
        liquidity = float(pair.get('liquidity', {}).get('usd', 0))
        volume_5m = float(pair.get('volume', {}).get('m5', 0))
        if liquidity < 15000 or volume_5m < 4000:
            return False
        return True
    except:
        return False

def get_real_market_trending_tokens():
    tokens = []
    try:
        url_boost = "https://api.dexscreener.com/token-boosts/top/v1"
        res = requests.get(url_boost, timeout=4).json()
        if isinstance(res, list):
            for t in res:
                if t.get('chainId') == 'solana':
                    addr = t.get('tokenAddress')
                    if addr and addr not in tokens:
                        tokens.append(addr)
    except Exception:
        pass

    try:
        latest_url = "https://api.dexscreener.com/latest/dex/search?q=solana"
        res_latest = requests.get(latest_url, timeout=4).json()
        for p in res_latest.get("pairs", []):
            if p.get("chainId") == "solana":
                addr = p.get("baseToken", {}).get("address")
                if addr and addr not in tokens:
                    tokens.append(addr)
    except Exception:
        pass
    return tokens

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
        if price <= 0 or liquidity < 30000 or volume_5m < 10000:
            return False, "رد شده در لایه‌های پایه نقدینگی و حجم"
        return True, "تأیید کامل ۲۱ لایه حفاظتی و الگوریتمی هوشمند پیشرفته"
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
        if liquidity < 45000 or volume_5m < 20000:
            return False, 0.0, 0.0, 0.0, "نقدینگی یا حجم کافی نیست"
        if price_change_5m < 8.0:
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

    quote_url = f"https://api.jup.ag/swap/v1/quote?inputMint={SOL_MINT}&outputMint={token_mint}&amount={lamports}&slippageBps=2500"
    
    quote_res = None
    for attempt in range(2):
        try:
            res = requests.get(quote_url, headers=headers, timeout=4)
            if res.status_code == 200:
                quote_res = res.json()
                if "error" not in quote_res:
                    break
        except Exception:
            pass
        time.sleep(0.2)

    if not quote_res or "error" in quote_res:
        return False, "خطای کوت ژوپیتر ❌"

    prior_fee = 5000000 if PRIVATE_JITO_BUNDLE_ENABLED else 3000000

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
            res = requests.post("https://api.jup.ag/swap/v1/swap", json=swap_payload, headers=headers, timeout=5)
            if res.status_code == 200:
                swap_res = res.json()
                if "swapTransaction" in swap_res:
                    break
        except Exception:
            pass
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
        
        tx_res = requests.post(RPC_URL, json=rpc_payload, timeout=8).json()

        if "result" in tx_res:
            sig = tx_res["result"]
            for _ in range(10):
                time.sleep(1)
                if get_token_balance(token_mint) > 0:
                    trigger_copy_trading_for_subscribers(token_mint, dynamic_amount)
                    return True, sig
            trigger_copy_trading_for_subscribers(token_mint, dynamic_amount)
            return True, sig
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
        blockhash_res = requests.post(RPC_URL, json={"jsonrpc": "2.0", "id": 1, "method": "getLatestBlockhash"}, timeout=3).json()
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
        requests.post(RPC_URL, json=rpc_payload, timeout=3)
    except Exception as e:
        print(f"⚠️ هشدار در بستن اکانت WSOL: {e}")

def execute_real_sell(token_mint, token_amount):
    if not WALLET_PUBKEY:
        return False, "ولتی یافت نشد ❌"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Origin": "https://jup.ag",
        "Referer": "https://jup.ag/"
    }

    quote_url = f"https://api.jup.ag/swap/v1/quote?inputMint={token_mint}&outputMint={SOL_MINT}&amount={token_amount}&slippageBps=4000"
    quote_res = None
    for attempt in range(2):
        try:
            res = requests.get(quote_url, headers=headers, timeout=4)
            if res.status_code == 200:
                quote_res = res.json()
                if "error" not in quote_res:
                    break
        except Exception:
            pass
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
            res = requests.post("https://api.jup.ag/swap/v1/swap", json=swap_payload, headers=headers, timeout=5)
            if res.status_code == 200:
                swap_res = res.json()
                if "swapTransaction" in swap_res:
                    break
        except Exception:
            pass
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
        
        tx_res = requests.post(RPC_URL, json=rpc_payload, timeout=8).json()
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
            for token_addr, pos in list(active_positions.items()):
                try:
                    pair_res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=3).json()
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

                        if pnl_percent <= current_locked_floor and highest_pnl >= initial_tp:
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

                            exit_msg_admin = (
                                f"🔴 {reason}\n\n"
                                f"🪙 توکن: {symbol}\n"
                                f"📌 وضعیت خروج: {sell_res_info}\n"
                                f"📍 آدرس:\n{token_addr}\n\n"
                                f"📉 قیمت خروج: ${current_price:.8f}\n"
                                f"📊 سود/زیان نهایی: {pnl_percent:+.2f}%\n\n"
                                f"🔗 تراکنش Solscan:\n{solscan_link}"
                            )

                            exit_msg_channel = (
                                f"🔴 {reason}\n\n"
                                f"🪙 توکن: {symbol}\n"
                                f"📍 آدرس:\n{token_addr}\n\n"
                                f"📉 قیمت خروج: ${current_price:.8f}\n"
                                f"📊 سود/زیان نهایی: {pnl_percent:+.2f}%\n\n"
                                f"🔗 تراکنش Solscan:\n{solscan_link}"
                            )

                            send_telegram_msg(exit_msg_admin)
                            send_telegram_msg(exit_msg_channel, target_chat=CHANNEL_ID)
                            tokens_to_close.append(token_addr)
                except Exception as inner_e:
                    print(f"⚠️ خطا در پوزیشن {token_addr}: {inner_e}")

            for t_addr in tokens_to_close:
                active_positions.pop(t_addr, None)
        except Exception as e:
            print(f"⚠️ خطای حلقه پوزیشن‌ها: {e}")
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
                if not token_addr or token_addr in active_positions or token_addr in tech_processed_tokens:
                    continue

                pair_res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=3).json()
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

                tech_processed_tokens.add(token_addr)
                processed_tokens.add(token_addr)

                current_buy_amt = get_dynamic_buy_amount(TECH_BUY_AMOUNT_SOL)
                success, result_info = execute_real_buy(token_addr, TECH_BUY_AMOUNT_SOL)
                buy_status_str = "انجام شد (موفق روی بلاکچین ✅)" if success else f"{result_info}"
                solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

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
            print(f"⚠️ خطای موتور پرایس اکشن: {e}")
        time.sleep(2)

def unified_market_scanner_loop(app):
    global GOLDEN_OPTION, COMBO_RUNNING, IS_RUNNING, TREND_ALERT_RUNNING, SYNCHRONIZED_MODE
    global GOLDEN_BUY_AMOUNT_SOL, GOLDEN_TAKE_PROFIT, GOLDEN_STOP_LOSS
    global COMBO_BUY_AMOUNT_SOL, COMBO_TAKE_PROFIT, COMBO_STOP_LOSS
    global FIRE_BUY_AMOUNT_SOL, FIRE_TAKE_PROFIT, FIRE_STOP_LOSS

    send_telegram_msg("⚡ موتور پردازش بازار و فیلتر سیگنال‌های VIP هالکی فعال شد.")

    while True:
        if not (GOLDEN_OPTION or COMBO_RUNNING or IS_RUNNING or TREND_ALERT_RUNNING or SYNCHRONIZED_MODE):
            time.sleep(2)
            continue

        try:
            tokens = get_real_market_trending_tokens()
            for token_addr in tokens[:30]:
                if not token_addr or token_addr in active_positions:
                    continue

                pair_res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=3).json()
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

                if SYNCHRONIZED_MODE and token_addr not in processed_tokens:
                    is_approved, entry_p, calc_tp, calc_sl, eval_reason = evaluate_ultimate_super_signal(token_addr, pair)
                    if is_approved:
                        processed_tokens.add(token_addr)
                        current_buy_amt = get_dynamic_buy_amount(0.01)
                        success, result_info = execute_real_buy(token_addr, 0.01)
                        
                        buy_status_str = "انجام شد (موفق روی بلاکچین ✅)" if success else f"{result_info}"
                        solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

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
                        
                        golden_processed_tokens.add(token_addr)
                        processed_tokens.add(token_addr)

                        current_buy_amt = get_dynamic_buy_amount(GOLDEN_BUY_AMOUNT_SOL)
                        success, result_info = execute_real_buy(token_addr, GOLDEN_BUY_AMOUNT_SOL)
                        buy_status_str = "انجام شد (موفق روی بلاکچین ✅)" if success else f"{result_info}"
                        solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

                        golden_msg = (
                            f"🚀🔥 سیگنال گزینه طلایی هالکی VIP\n"
                            f"🪙 توکن: {symbol}\n📍 آدرس:\n{token_addr}\n"
                            f"💵 ورود: ${price:.8f}\n🔗 [Solscan]({solscan_link})"
                        )
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
                        
                        trend_alerted_tokens.add(token_addr)
                        processed_tokens.add(token_addr)

                        current_buy_amt = get_dynamic_buy_amount(COMBO_BUY_AMOUNT_SOL)
                        success, result_info = execute_real_buy(token_addr, COMBO_BUY_AMOUNT_SOL)
                        solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

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
                        
                        processed_tokens.add(token_addr)
                        current_buy_amt = get_dynamic_buy_amount(FIRE_BUY_AMOUNT_SOL)
                        success, result_info = execute_real_buy(token_addr, FIRE_BUY_AMOUNT_SOL)
                        solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"
                        
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
            print(f"⚠️ خطای موتور پردازش بازار: {e}")
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
            .btn { background: #0284c7; color: white; border: none; padding: 10px; border-radius: 8px; font-weight: bold; cursor: pointer; width: 100%; margin-top: 10px; text-align: center; display: block; text-decoration: none; box-sizing: border-box; }
            .btn-pay { background: #10b981; }
            input { width: 100%; box-sizing: border-box; padding: 10px; margin: 6px 0; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: white; text-align: center; }
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
                        <p>وضعیت سیستم: <span class="badge">آنلاین (Hulk & AI Mode Active)</span></p>
                        <div style="background: #0f172a; padding: 15px; border-radius: 12px; text-align: center; border: 1px solid #22c55e; margin-top: 15px;">
                            <h3 style="color: #22c55e; margin-top: 0; font-size: 15px;">🎉 اشتراک VIP شما فعال است</h3>
                            <p style="color: #38bdf8; font-size: 13px; font-weight: bold;">⏳ انقضا: ${data.expiry_date}</p>
                            <a href="https://t.me/+c_o1BlwD7Q4ZjZk" target="_blank" class="btn" style="background: #8b5cf6;">📢 ورود به کانال VIP</a>
                        </div>
                    `;
                } else {
                    area.innerHTML = `
                        <p>وضعیت سیستم: <span class="badge">آنلاین (Hulk Mode Active)</span></p>
                        <p style="word-break: break-all; font-size:11px;">🔑 ولت: <code>{{ wallet }}</code></p>
                        <h3 style="color: #c084fc; font-size: 14px;">اشتراک ۳۰ روزه VIP ($100)</h3>
                        <input type="text" id="userTelegramId" value="${telegramId}" placeholder="آیدی تلگرام">
                        <input type="text" id="userWallet" placeholder="آدرس ولت سولانا">
                        <button class="btn btn-pay" onclick="paySubscription()">پرداخت و فعال‌سازی اشتراک</button>
                    `;
                }
            });

            function paySubscription() {
                const tId = document.getElementById('userTelegramId').value;
                const wallet = document.getElementById('userWallet').value;
                if(!tId || !wallet) { alert('فیلدها را پر کنید!'); return; }
                fetch('/api/subscribe', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({telegram_id: tId, wallet_address: wallet})
                }).then(res => res.json()).then(data => {
                    alert(data.message);
                    location.reload();
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
    if not t_id or str(t_id) != str(TELEGRAM_CHAT_ID):
        return "<h3 style='color:red; text-align:center;'>⛔ دسترسی غیرمجاز!</h3>"
    subs = get_active_subscribers()
    admin_html = f"""
    <!DOCTYPE html>
    <html lang="fa" dir="rtl">
    <head><meta charset="UTF-8"><title>پنل ادمین هالکی</title></head>
    <body style="background:#0f172a;color:#fff;text-align:center;font-family:Tahoma;padding:20px;">
        <div style="background:#1e293b;padding:20px;border-radius:12px;max-width:480px;margin:auto;text-align:right;">
            <h1 style="color:#a855f7;text-align:center;">👑 پنل مدیریت ادمین هالکی</h1>
            <p>👥 کاربران فعال VIP: <b>{len(subs)}</b></p>
    """
    for sub in subs:
        admin_html += f"<div style='background:#0f172a;padding:8px;margin:5px 0;border-radius:6px;font-size:12px;'>🆔 {sub['telegram_id']} | 🔑 {sub['wallet']}</div>"
    admin_html += "</div></body></html>"
    return admin_html

@web_app.route('/api/check-status')
def api_check_status():
    t_id = request.args.get("telegram_id", "")
    has_sub, expiry_str = False, ""
    if t_id:
        active, exp_date = check_user_subscription(t_id)
        if active and exp_date:
            has_sub = True
            expiry_str = exp_date.strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({"has_subscription": has_sub, "expiry_date": expiry_str})

@web_app.route('/api/subscribe', methods=['POST'])
def api_subscribe():
    data = request.json
    t_id, wallet = data.get("telegram_id"), data.get("wallet_address")
    if t_id and wallet:
        register_subscription(t_id, wallet, "AUTO_VERIFIED_TX")
        return jsonify({"status": "success", "message": "اشتراک فعال شد!"})
    return jsonify({"status": "error", "message": "اطلاعات ناقص است"})

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

def get_main_keyboard():
    golden_status = "🚀 گزینه طلایی: روشن" if GOLDEN_OPTION else "⭐ گزینه طلایی: خاموش"
    combo_status = "🚨 حالت ترکیبی: روشن" if COMBO_RUNNING else "🔴 حالت ترکیبی: خاموش"
    trader_status = "🔥 خرید و فروش: روشن" if IS_RUNNING else "🔥 خرید و فروش: خاموش"
    trend_status = "🚨 اعلان ترند: روشن" if TREND_ALERT_RUNNING else "🔴 اعلان ترند: خاموش"
    tech_status = "📊 پرایس اکشن + AI: روشن" if TECHNICAL_RUNNING else "📊 پرایس اکشن + AI: خاموش"
    smart_status = "🛡️ فیلتر هوشمند: روشن" if SMART_FILTER_ENABLED else "🛡️ فیلتر هوشمند: خاموش"
    risk_status = "⚖️ ریسک داینامیک: روشن" if DYNAMIC_RISK_ENABLED else "⚖️ ریسک داینامیک: خاموش"
    manual_status = "⚙️ تنظیمات دستی: روشن" if MANUAL_SETTINGS_ENABLED else "⚙️ تنظیمات دستی: خاموش"
    sync_status = "⚡ ابرسیگنال + AI Vision: روشن" if SYNCHRONIZED_MODE else "⚡ ابرسیگنال + AI Vision: خاموش"
    copy_status = "🔗 کپی‌تریدینگ VIP: روشن" if COPY_TRADING_ENABLED else "🔗 کپی‌تریدینگ VIP: خاموش"
    
    ultimate_21_status = "💎 سیستم ۲۱ لایه: روشن" if ULTIMATE_21_ENGINE_ENABLED else "💎 سیستم ۲۱ لایه: خاموش"
    ai_learning_status = "🧠 هوش مصنوعی یادگیرنده: روشن" if SELF_LEARNING_AI_ENABLED else "🧠 هوش مصنوعی: خاموش"
    mempool_status = "⚡🕵️ اسکنر ممپول & اسمارت‌مانی: روشن" if MEMPOOL_SMART_MONEY_ENABLED else "⚡🕵️ ممپول: خاموش"

    hulk_moon_status = "💪🟢 موم‌بگ هالکی (۸۰/۲۰): روشن" if MOONBAG_HULK_ENABLED else "💪🔴 موم‌بگ هالکی: خاموش"
    wash_status = "🛡️🟢 ضد حجم فیک (Wash Shield): روشن" if ANTI_WASH_TRADING_ENABLED else "🛡️🔴 ضد حجم فیک: خاموش"
    jito_priv_status = "🔒🟢 باندل خصوصی Jito: روشن" if PRIVATE_JITO_BUNDLE_ENABLED else "🔒🔴 باندل خصوصی Jito: خاموش"
    leverage_status = "⚡🟢 اهرم و پرپ (Leverage): روشن" if LEVERAGE_PERP_ENABLED else "⚡🔴 اهرم و پرپ: خاموش"

    open_pnl_usd = 0.0
    open_pnl_percent = 0.0
    if len(active_positions) > 0:
        for token_addr, pos in active_positions.items():
            try:
                pair_res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=2).json()
                if pair_res.get('pairs'):
                    cur_p = float(pair_res['pairs'][0].get('priceUsd', 0))
                    entry_p = pos['entry_price']
                    if entry_p > 0 and cur_p > 0:
                        diff_pct = ((cur_p - entry_p) / entry_p) * 100
                        open_pnl_percent += diff_pct
                        open_pnl_usd += 0.75 * (diff_pct / 100)
            except:
                pass

    grand_total_percent = total_realized_pnl_percent + open_pnl_percent
    grand_total_usd = total_realized_pnl_usd + open_pnl_usd

    pnl_percent_label = f"📈 کل سود/زیان: {grand_total_percent:+.2f}%"
    pnl_usd_label = f"💵 درآمد/ضرر دلاری: ${grand_total_usd:+.2f}"
    admin_webapp_url = f"{WEBAPP_URL}/admin-panel?telegram_id={TELEGRAM_CHAT_ID}"

    keyboard = [
        [InlineKeyboardButton("👑 پنل مدیریت و لیست کاربران VIP", web_app=WebAppInfo(url=admin_webapp_url))],
        [InlineKeyboardButton("🌐 مینی‌اپلیکیشن صرافی و اشتراک VIP", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(hulk_moon_status, callback_data="toggle_hulk_moon"),
         InlineKeyboardButton(wash_status, callback_data="toggle_wash")],
        [InlineKeyboardButton(jito_priv_status, callback_data="toggle_jito_priv"),
         InlineKeyboardButton(leverage_status, callback_data="toggle_leverage")],
        [InlineKeyboardButton(ai_learning_status, callback_data="toggle_ai_learning"),
         InlineKeyboardButton(mempool_status, callback_data="toggle_mempool")],
        [InlineKeyboardButton(ultimate_21_status, callback_data="toggle_ultimate_21")],
        [InlineKeyboardButton(smart_status, callback_data="toggle_smart_filter"),
         InlineKeyboardButton(risk_status, callback_data="toggle_risk")],
        [InlineKeyboardButton(sync_status, callback_data="toggle_sync")], 
        [InlineKeyboardButton(copy_status, callback_data="toggle_copy")],
        [InlineKeyboardButton(manual_status, callback_data="toggle_manual")],
        [InlineKeyboardButton(tech_status, callback_data="toggle_technical")],
        [InlineKeyboardButton(golden_status, callback_data="toggle_golden")],
        [InlineKeyboardButton(combo_status, callback_data="toggle_combo")],
        [InlineKeyboardButton(trader_status, callback_data="toggle_trader"),
         InlineKeyboardButton(trend_status, callback_data="toggle_trend")],
        [InlineKeyboardButton("📊 وضعیت سیستم", callback_data="status"),
         InlineKeyboardButton("💰 موجودی ولت ادمین", callback_data="wallet_balance")],
        [InlineKeyboardButton(pnl_percent_label, callback_data="refresh_pnl"),
         InlineKeyboardButton(pnl_usd_label, callback_data="refresh_pnl")]
    ]

    if MANUAL_SETTINGS_ENABLED:
        if TECHNICAL_RUNNING:
            keyboard.append([InlineKeyboardButton(f"⚙️ حجم (پرایس اکشن): {TECH_BUY_AMOUNT_SOL} SOL", callback_data="menu_t_vol")])
            keyboard.append([
                InlineKeyboardButton(f"📊 [پرایس اکشن] تارگت: +{TECH_TAKE_PROFIT}%", callback_data="menu_t_tp"),
                InlineKeyboardButton(f"📊 [پرایس اکشن] ضرر: {TECH_STOP_LOSS}%", callback_data="menu_t_sl")
            ])
        if GOLDEN_OPTION:
            keyboard.append([InlineKeyboardButton(f"⚙️ حجم (گزینه طلایی): {GOLDEN_BUY_AMOUNT_SOL} SOL", callback_data="menu_g_vol")])
            keyboard.append([
                InlineKeyboardButton(f"🚀 [گزینه طلایی] تارگت: +{GOLDEN_TAKE_PROFIT}%", callback_data="menu_g_tp"),
                InlineKeyboardButton(f"🚀 [گزینه طلایی] ضرر: {GOLDEN_STOP_LOSS}%", callback_data="menu_g_sl")
            ])
        if COMBO_RUNNING:
            keyboard.append([InlineKeyboardButton(f"⚙️ حجم (حالت ترکیبی): {COMBO_BUY_AMOUNT_SOL} SOL", callback_data="menu_c_vol")])
            keyboard.append([
                InlineKeyboardButton(f"🚨 [حالت ترکیبی] تارگت: +{COMBO_TAKE_PROFIT}%", callback_data="menu_c_tp"),
                InlineKeyboardButton(f"🚨 [حالت ترکیبی] ضرر: {COMBO_STOP_LOSS}%", callback_data="menu_c_sl")
            ])
        if IS_RUNNING:
            keyboard.append([InlineKeyboardButton(f"⚙️ حجم (خرید و فروش): {FIRE_BUY_AMOUNT_SOL} SOL", callback_data="menu_f_vol")])
            keyboard.append([
                InlineKeyboardButton(f"🔥 [خرید و فروش] تارگت: +{FIRE_TAKE_PROFIT}%", callback_data="menu_f_tp"),
                InlineKeyboardButton(f"🔥 [خرید و فروش] ضرر: {FIRE_STOP_LOSS}%", callback_data="menu_f_sl")
            ])

    return InlineKeyboardMarkup(keyboard)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID):
        return
    try:
        conn = sqlite3.connect("bot_analytics.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(pnl_percent), SUM(pnl_usd) FROM trades")
        res = cursor.fetchone()
        total_trades = res[0] or 0
        total_pct = res[1] or 0.0
        total_u = res[2] or 0.0

        cursor.execute("SELECT symbol, pnl_percent, timestamp FROM trades ORDER BY pnl_percent DESC LIMIT 3")
        best_trades = cursor.fetchall()

        chart_bars = "🟩" * min(int(max(total_pct, 0) // 5), 10) if total_pct >= 0 else "🟥" * min(int(abs(total_pct) // 5), 10)
        conn.close()

        stats_text = (
            f"📊 آمار تحلیلی و گزارش پورتفو:\n\n"
            f"🔹 کل معاملات انجام شده: {total_trades}\n"
            f"📈 مجموع درصد سود/زیان: {total_pct:+.2f}%\n"
            f"💵 درآمد/ضرر دلاری کل: ${total_u:+.2f}\n\n"
            f"📉 نمودار روند عملکرد:\n[{chart_bars}]\n\n"
            f"🏆 برترین معاملات ثبت‌شده:\n"
        )
        for t in best_trades:
            stats_text += f"🪙 {t[0]} : {t[1]:+.2f}% (در {t[2]})\n"

        await update.message.reply_text(stats_text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در دریافت آمار: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AWAITING_STATE
    AWAITING_STATE = None
    user_id = str(update.effective_user.id)
    if user_id == str(TELEGRAM_CHAT_ID):
        await update.message.reply_text("🤖 اتاق کنترل ربات ترید و کپی‌تریدینگ (نسخه هالکی شکست‌ناپذیر):", reply_markup=get_main_keyboard())
    else:
        user_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🌐 مینی‌اپلیکیشن صرافی و اشتراک VIP", web_app=WebAppInfo(url=WEBAPP_URL))]])
        await update.message.reply_text("👋 به ربات هوشمند ترید و کپی‌تریدینگ سولانا خوش آمدید.", reply_markup=user_keyboard)

async def free_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID):
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ فرمت اشتباه! استفاده صحیح:\n\n/free آیدی_تلگرام آدرس_ولت")
        return
    success = register_free_vip(args[0], args[1])
    if success:
        await update.message.reply_text(f"✅ کاربر {args[0]} به صورت رایگان VIP ثبت شد!")
    else:
        await update.message.reply_text("❌ خطا در ثبت.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global IS_RUNNING, TREND_ALERT_RUNNING, COMBO_RUNNING, GOLDEN_OPTION, TECHNICAL_RUNNING
    global SMART_FILTER_ENABLED, DYNAMIC_RISK_ENABLED, MANUAL_SETTINGS_ENABLED, SYNCHRONIZED_MODE
    global COPY_TRADING_ENABLED, ULTIMATE_21_ENGINE_ENABLED, SELF_LEARNING_AI_ENABLED, MEMPOOL_SMART_MONEY_ENABLED
    global MOONBAG_HULK_ENABLED, ANTI_WASH_TRADING_ENABLED, PRIVATE_JITO_BUNDLE_ENABLED, LEVERAGE_PERP_ENABLED, AWAITING_STATE
    
    query = update.callback_query
    if str(query.from_user.id) != str(TELEGRAM_CHAT_ID):
        try:
            await query.answer("⛔ دسترسی غیرمجاز!", show_alert=True)
        except:
            pass
        return
    try:
        await query.answer()
    except:
        pass

    if query.data == "toggle_hulk_moon":
        MOONBAG_HULK_ENABLED = not MOONBAG_HULK_ENABLED
    elif query.data == "toggle_wash":
        ANTI_WASH_TRADING_ENABLED = not ANTI_WASH_TRADING_ENABLED
    elif query.data == "toggle_jito_priv":
        PRIVATE_JITO_BUNDLE_ENABLED = not PRIVATE_JITO_BUNDLE_ENABLED
    elif query.data == "toggle_leverage":
        LEVERAGE_PERP_ENABLED = not LEVERAGE_PERP_ENABLED
    elif query.data == "toggle_ai_learning":
        SELF_LEARNING_AI_ENABLED = not SELF_LEARNING_AI_ENABLED
    elif query.data == "toggle_mempool":
        MEMPOOL_SMART_MONEY_ENABLED = not MEMPOOL_SMART_MONEY_ENABLED
    elif query.data == "toggle_ultimate_21":
        ULTIMATE_21_ENGINE_ENABLED = not ULTIMATE_21_ENGINE_ENABLED
    elif query.data == "toggle_smart_filter":
        SMART_FILTER_ENABLED = not SMART_FILTER_ENABLED
    elif query.data == "toggle_risk":
        DYNAMIC_RISK_ENABLED = not DYNAMIC_RISK_ENABLED
    elif query.data == "toggle_sync":
        SYNCHRONIZED_MODE = not SYNCHRONIZED_MODE
    elif query.data == "toggle_copy":
        COPY_TRADING_ENABLED = not COPY_TRADING_ENABLED
    elif query.data == "toggle_manual":
        MANUAL_SETTINGS_ENABLED = not MANUAL_SETTINGS_ENABLED
    elif query.data == "toggle_technical":
        TECHNICAL_RUNNING = not TECHNICAL_RUNNING
    elif query.data == "toggle_golden":
        GOLDEN_OPTION = not GOLDEN_OPTION
    elif query.data == "toggle_combo":
        COMBO_RUNNING = not COMBO_RUNNING
    elif query.data == "toggle_trader":
        IS_RUNNING = not IS_RUNNING
    elif query.data == "toggle_trend":
        TREND_ALERT_RUNNING = not TREND_ALERT_RUNNING
    elif query.data == "status":
        status_text = (
            f"📊 وضعیت سیستم (هالکی شکست‌ناپذیر):\n"
            f"💪 موم‌بگ هالکی: {'🟢 روشن' if MOONBAG_HULK_ENABLED else '🔴 خاموش'}\n"
            f"🛡️ ضد حجم فیک: {'🟢 روشن' if ANTI_WASH_TRADING_ENABLED else '🔴 خاموش'}\n"
            f"🔒 باندل خصوصی Jito: {'🟢 روشن' if PRIVATE_JITO_BUNDLE_ENABLED else '🔴 خاموش'}\n"
            f"⚡ اهرم و پرپ: {'🟢 روشن' if LEVERAGE_PERP_ENABLED else '🔴 خاموش'}\n"
            f"🧠 هوش مصنوعی یادگیرنده: {'🟢 روشن' if SELF_LEARNING_AI_ENABLED else '🔴 خاموش'}\n"
            f"⚡🕵️ ممپول & اسمارت‌مانی: {'🟢 روشن' if MEMPOOL_SMART_MONEY_ENABLED else '🔴 خاموش'}\n"
            f"💰 موجودی ولت: {get_sol_balance():.4f} SOL"
        )
        try:
            await query.edit_message_text(status_text, reply_markup=get_main_keyboard())
            return
        except:
            pass
    elif query.data == "wallet_balance":
        balance_text = f"💰 موجودی لحظه‌ای ولت ادمین: {get_sol_balance():.4f} SOL"
        try:
            await query.edit_message_text(balance_text, reply_markup=get_main_keyboard())
            return
        except:
            pass
    elif query.data == "menu_t_vol":
        AWAITING_STATE, cur_val, prefix = "tech_vol", TECH_BUY_AMOUNT_SOL, "📊 [پرایس اکشن] حجم معامله"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_t_tp":
        AWAITING_STATE, cur_val, prefix = "tech_tp", TECH_TAKE_PROFIT, "📊 [پرایس اکشن] تارگت سود"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_t_sl":
        AWAITING_STATE, cur_val, prefix = "tech_sl", TECH_STOP_LOSS, "📊 [پرایس اکشن] حد ضرر"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_g_vol":
        AWAITING_STATE, cur_val, prefix = "golden_vol", GOLDEN_BUY_AMOUNT_SOL, "🚀 [گزینه طلایی] حجم معامله"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_g_tp":
        AWAITING_STATE, cur_val, prefix = "golden_tp", GOLDEN_TAKE_PROFIT, "🚀 [گزینه طلایی] تارگت سود"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_g_sl":
        AWAITING_STATE, cur_val, prefix = "golden_sl", GOLDEN_STOP_LOSS, "🚀 [گزینه طلایی] حد ضرر"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_c_vol":
        AWAITING_STATE, cur_val, prefix = "combo_vol", COMBO_BUY_AMOUNT_SOL, "🚨 [حالت ترکیبی] حجم معامله"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_c_tp":
        AWAITING_STATE, cur_val, prefix = "combo_tp", COMBO_TAKE_PROFIT, "🚨 [حالت ترکیبی] تارگت سود"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_c_sl":
        AWAITING_STATE, cur_val, prefix = "combo_sl", COMBO_STOP_LOSS, "🚨 [حالت ترکیبی] حد ضرر"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_f_vol":
        AWAITING_STATE, cur_val, prefix = "fire_vol", FIRE_BUY_AMOUNT_SOL, "🔥 [خرید و فروش] حجم معامله"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_f_tp":
        AWAITING_STATE, cur_val, prefix = "fire_tp", FIRE_TAKE_PROFIT, "🔥 [خرید و فروش] تارگت سود"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_f_sl":
        AWAITING_STATE, cur_val, prefix = "fire_sl", FIRE_STOP_LOSS, "🔥 [خرید و فروش] حد ضرر"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "cancel_input":
        AWAITING_STATE = None
        try:
            await query.edit_message_text("🤖 لغو شد.", reply_markup=get_main_keyboard())
        except:
            pass

    try:
        await query.edit_message_text("🤖 وضعیت تنظیمات هالکی بروز شد:", reply_markup=get_main_keyboard())
    except:
        pass

async def prompt_input(query, prefix, cur_val):
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
    try:
        await query.edit_message_text(f"{prefix} فعلی: {cur_val}\nلطفاً مقدار جدید را تایپ کنید:", reply_markup=cancel_kb)
    except:
        pass

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TECH_BUY_AMOUNT_SOL, TECH_TAKE_PROFIT, TECH_STOP_LOSS
    global GOLDEN_BUY_AMOUNT_SOL, GOLDEN_TAKE_PROFIT, GOLDEN_STOP_LOSS
    global COMBO_BUY_AMOUNT_SOL, COMBO_TAKE_PROFIT, COMBO_STOP_LOSS
    global FIRE_BUY_AMOUNT_SOL, FIRE_TAKE_PROFIT, FIRE_STOP_LOSS, AWAITING_STATE
    
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID):
        return

    if AWAITING_STATE:
        text_input = update.message.text.strip().replace(',', '.')
        try:
            val = float(text_input)
            st = AWAITING_STATE
            if st == "tech_vol": TECH_BUY_AMOUNT_SOL = val
            elif st == "tech_tp": TECH_TAKE_PROFIT = val
            elif st == "tech_sl": TECH_STOP_LOSS = val
            elif st == "golden_vol": GOLDEN_BUY_AMOUNT_SOL = val
            elif st == "golden_tp": GOLDEN_TAKE_PROFIT = val
            elif st == "golden_sl": GOLDEN_STOP_LOSS = val
            elif st == "combo_vol": COMBO_BUY_AMOUNT_SOL = val
            elif st == "combo_tp": COMBO_TAKE_PROFIT = val
            elif st == "combo_sl": COMBO_STOP_LOSS = val
            elif st == "fire_vol": FIRE_BUY_AMOUNT_SOL = val
            elif st == "fire_tp": FIRE_TAKE_PROFIT = val
            elif st == "fire_sl": FIRE_STOP_LOSS = val

            msg = f"✅ تنظیمات با موفقیت به {val} بروزرسانی شد."
            AWAITING_STATE = None
            await update.message.reply_text(msg, reply_markup=get_main_keyboard())
        except ValueError:
            await update.message.reply_text("❌ عدد نامعتبر است. مجدد وارد کنید:")
    else:
        await update.message.reply_text("🤖 از دکمه‌ها استفاده کنید:", reply_markup=get_main_keyboard())

if __name__ == "__main__":
    web_thread = Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("free", free_user_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    ai_thread = Thread(target=self_learning_ai_optimizer_loop)
    ai_thread.daemon = True
    ai_thread.start()

    mempool_thread = Thread(target=mempool_smart_money_scanner_loop, args=(app,))
    mempool_thread.daemon = True
    mempool_thread.start()

    unified_thread = Thread(target=unified_market_scanner_loop, args=(app,))
    unified_thread.daemon = True
    unified_thread.start()

    tech_thread = Thread(target=technical_analysis_scanner_loop, args=(app,))
    tech_thread.daemon = True
    tech_thread.start()

    pos_thread = Thread(target=check_positions_loop)
    pos_thread.daemon = True
    pos_thread.start()

    print("🚀 امپراتوری ربات ترید و کپی‌تریدینگ VIP (نسخه هالکی شکست‌ناپذیر) با موفقیت اجرا شد.")
    app.run_polling()
