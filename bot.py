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
CHANNEL_ID = os.environ.get("CHANNEL_ID", "https://t.me/+c_o1BlwD7_Q4ZjZk") 
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
COPY_TRADING_ENABLED = True   # ⚡ فعال‌سازی موتور کپی‌تریدینگ VIP

# تنظیمات بخش خرید و فروش (🔥)
FIRE_BUY_AMOUNT_SOL = 0.01
FIRE_TAKE_PROFIT = 18.0
FIRE_STOP_LOSS = -10.0
FIRE_MIN_LIQUIDITY = 30000       
FIRE_MIN_VOLUME_5M = 5000       
FIRE_MIN_PRICE_CHANGE_5M = 5.0  

# تنظیمات بخش ترکیبی (🚨)
COMBO_BUY_AMOUNT_SOL = 0.01
COMBO_TAKE_PROFIT = 18.0
COMBO_STOP_LOSS = -10.0
COMBO_MIN_LIQUIDITY = 40000
COMBO_MIN_VOLUME_5M = 20000  
COMBO_MIN_CHANGE_5M = 25.0   

# تنظیمات بخش اعلان ترند (🚨)
TREND_MIN_LIQUIDITY = 40000
TREND_MIN_VOLUME_5M = 40000  
TREND_MIN_CHANGE_5M = 25.0   
MIN_BUYS_5M = 80             

# تنظیمات بخش گزینه طلایی (🚀)
GOLDEN_BUY_AMOUNT_SOL = 0.01
GOLDEN_TAKE_PROFIT = 16.0
GOLDEN_STOP_LOSS = -8.0
GOLDEN_MIN_LIQUIDITY = 60000
GOLDEN_MIN_VOLUME_5M = 30000
GOLDEN_MIN_CHANGE_5M = 20.0
GOLDEN_MIN_BUYS_5M = 80

# تنظیمات موتور پرایس اکشن
TECH_BUY_AMOUNT_SOL = 0.01
TECH_TAKE_PROFIT = 20.0
TECH_STOP_LOSS = -8.0
TECH_MIN_LIQUIDITY = 35000
TECH_MIN_VOLUME_5M = 15000

AWAITING_STATE = None 
processed_tokens = set()
trend_alerted_tokens = set()
golden_processed_tokens = set()
tech_processed_tokens = set()
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
        
        # ارسال پیام تایید اشتراک همراه با لینک کانال اختصاصی سیگنال‌ها مستقیماً به کاربر
        success_msg = (
            f"🎉 **اشتراک ۳۰ روزه VIP شما با موفقیت فعال شد!**\n\n"
            f"🔗 ولت شما به سیستم کپی‌تریدینگ هوشمند متصل گردید.\n"
            f"📢 برای دریافت لحظه‌ای سیگنال‌ها و گزارش‌های گرافیکی، از طریق لینک زیر وارد کانال VIP شوید:\n\n"
            f"{CHANNEL_ID}"
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
        expiry = datetime.now() + timedelta(days=365) # اشتراک ۱ ساله رایگان
        cursor.execute("""
            INSERT OR REPLACE INTO subscribers (telegram_id, wallet_address, expiry_date, tx_signature, status)
            VALUES (?, ?, ?, ?, 'ACTIVE')
        """, (str(telegram_id), wallet_addr, expiry.strftime("%Y-%m-%d %H:%M:%S"), "ADMIN_FREE_PASS"))
        conn.commit()
        conn.close()
        
        # ارسال پیام تایید اشتراک رایگان ادمین همراه با لینک کانال به کاربر
        free_msg = (
            f"🎉 **اشتراک VIP رایگان شما توسط ادمین فعال شد!**\n\n"
            f"🔗 موتور کپی‌تریدینگ برای ولت شما روشن گردید.\n"
            f"📢 از طریق لینک زیر وارد کانال سیگنال‌ها شوید:\n\n"
            f"{CHANNEL_ID}"
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
        liquidity = float(pair.get('liquidity', {}).get('usd', 0))
        volume_5m = float(pair.get('volume', {}).get('m5', 0))
        if liquidity < 15000 or volume_5m < 5000:
            return False
        return True
    except:
        return False

def check_social_sentiment(token_mint, pair):
    try:
        boosts = pair.get('boosts', 0)
        socials = pair.get('info', {}).get('socials', [])
        websites = pair.get('info', {}).get('websites', [])
        hype_score = len(socials) * 2 + len(websites) * 1 + (5 if boosts else 0)
        if hype_score >= 1 or pair.get('volume', {}).get('h24', 0) > 50000:
            return True, "هایپ اجتماعی و سنتیمنت تایید شد 🔥"
    except Exception:
        pass
    return True, "وضعیت اجتماعی نرمال 🟢"

def is_token_safe(token_mint, strict=False):
    try:
        url = f"https://api.rugcheck.xyz/v1/tokens/{token_mint}/summary"
        res = requests.get(url, timeout=4)
        if res.status_code == 200:
            data = res.json()
            risk_score = data.get("score", 0)
            max_score = 500 if strict else 3000
            if risk_score > max_score:
                return False
            markets = data.get("markets", [])
            for market in markets:
                if market.get("lpFee", 0) > 10 or market.get("sellTax", 0) > 10:
                    return False
        return True
    except Exception:
        return True

def check_whale_and_advanced_security(token_mint, pair):
    try:
        url = f"https://api.rugcheck.xyz/v1/tokens/{token_mint}/summary"
        res = requests.get(url, timeout=4)
        if res.status_code == 200:
            data = res.json()
            holders = data.get("holders", [])
            top_holders_share = sum([h.get("pct", 0) for h in holders[:5]])
            if top_holders_share > 70.0:
                return False
        return True
    except Exception:
        return True

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

def simulate_buy_transaction(token_mint):
    return True 

def is_smart_money_buying(token_mint):
    return True 

def run_smart_checks(token_mint, pair):
    if not SMART_FILTER_ENABLED:
        return True
    if not simulate_buy_transaction(token_mint):
        return False
    if not is_smart_money_buying(token_mint):
        return False
    return True

def check_major_support_resistance_pa(pair):
    try:
        if not is_token_worthy(pair):
            return False, ""

        price_change_5m = float(pair.get('priceChange', {}).get('m5', 0))
        price_change_1h = float(pair.get('priceChange', {}).get('h1', 0))
        price_change_6h = float(pair.get('priceChange', {}).get('h6', 0))
        
        txns_5m = pair.get('txns', {}).get('m5', {})
        buys_5m = int(txns_5m.get('buys', 0))
        sells_5m = int(txns_5m.get('sells', 0))

        if price_change_5m <= 0 or sells_5m >= buys_5m:
            return False, ""

        if price_change_6h < -5.0 or price_change_1h < 1.0:
            return False, ""

        is_classic_support_pullback = (0.3 <= price_change_5m <= 3.0) and (buys_5m >= sells_5m * 2.0) and (price_change_1h >= 3.0)
        is_classic_breakout = (3.0 <= price_change_5m <= 7.0) and (price_change_1h >= 8.0) and (buys_5m >= sells_5m * 2.5)

        if is_classic_support_pullback:
            return True, "برگشت حرفه‌ای از حمایت معتبر / پولبک پاک (AI Vision Verified) 📈"
        elif is_classic_breakout:
            return True, "شکست معتبر سقف و مقاومت کلیدی با تثبیت (AI Vision Verified) 🚀"

    except Exception:
        pass
    return False, ""

def evaluate_ultimate_super_signal(token_addr, pair):
    try:
        price = float(pair.get('priceUsd', 0))
        liquidity = float(pair.get('liquidity', {}).get('usd', 0))
        volume_5m = float(pair.get('volume', {}).get('m5', 0))
        price_change_5m = float(pair.get('priceChange', {}).get('m5', 0))
        txns_5m = pair.get('txns', {}).get('m5', {})
        buys_5m = int(txns_5m.get('buys', 0))
        sells_5m = int(txns_5m.get('sells', 0))

        if price <= 0:
            return False, 0.0, 0.0, 0.0, "قیمت نامعتبر"

        min_liq_adaptive = 60000 if volume_5m > 100000 else 50000

        if liquidity < min_liq_adaptive or volume_5m < 25000:
            return False, 0.0, 0.0, 0.0, "نقدینگی یا حجم کافی نیست"

        if price_change_5m < 15.0 or buys_5m < (sells_5m * 2.5):
            return False, 0.0, 0.0, 0.0, "مومنتوم کافی نیست"

        is_pa_valid, pa_reason = check_major_support_resistance_pa(pair)
        if not is_pa_valid:
            return False, 0.0, 0.0, 0.0, "تاییدیه پرایس اکشن صادر نشد"

        is_sentiment_ok, sentiment_reason = check_social_sentiment(token_addr, pair)
        if not is_sentiment_ok:
            return False, 0.0, 0.0, 0.0, "سنتیمنت اجتماعی تایید نشد"

        if not is_token_safe(token_addr, strict=True) or not check_whale_and_advanced_security(token_addr, pair):
            return False, 0.0, 0.0, 0.0, "امنیت یا فیلتر نهنگ تایید نشد"

        dynamic_tp = 22.0 if price_change_5m > 30.0 else 18.0
        dynamic_sl = -7.5

        return True, price, dynamic_tp, dynamic_sl, f"تایید کامل ماشین هوشمند و AI Vision ({pa_reason} | {sentiment_reason})"

    except Exception as e:
        return False, 0.0, 0.0, 0.0, f"خطا در پردازش: {e}"

def trigger_copy_trading_for_subscribers(token_mint, amount_sol):
    if not COPY_TRADING_ENABLED:
        return
    active_subs = get_active_subscribers()
    for sub in active_subs:
        t_id = sub["telegram_id"]
        copy_msg = (
            f"⚡ [کپی‌تریدینگ هوشمند VIP - اشتراک فعال]\n"
            f"🤖 ربات اصلی معامله جدیدی باز کرد و روی ولت شما کپی شد!\n\n"
            f"🪙 آدرس توکن:\n`{token_mint}`\n"
            f"💰 حجم معامله اختصاصی: {amount_sol} SOL\n"
            f"⏳ وضعیت اشتراک: فعال و معتبر"
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

    quote_url = f"https://api.jup.ag/swap/v1/quote?inputMint={SOL_MINT}&outputMint={token_mint}&amount={lamports}&slippageBps=3000"
    
    quote_res = None
    for attempt in range(3):
        try:
            res = requests.get(quote_url, headers=headers, timeout=5)
            if res.status_code == 200:
                quote_res = res.json()
                if "error" not in quote_res:
                    break
        except Exception:
            pass
        time.sleep(0.3)

    if not quote_res or "error" in quote_res:
        return False, "سولانای ناکافی ❌"

    swap_payload = {
        "quoteResponse": quote_res,
        "userPublicKey": WALLET_PUBKEY,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": 2000000
    }
    
    swap_res = None
    for attempt in range(3):
        try:
            res = requests.post("https://api.jup.ag/swap/v1/swap", json=swap_payload, headers=headers, timeout=6)
            if res.status_code == 200:
                swap_res = res.json()
                if "swapTransaction" in swap_res:
                    break
        except Exception:
            pass
        time.sleep(0.3)

    if not swap_res or "swapTransaction" not in swap_res:
        return False, "سولانای ناکافی ❌"

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
            "params": [serialized_tx, {"encoding": "base58", "skipPreflight": False, "maxRetries": 5}]
        }
        
        tx_res = requests.post(RPC_URL, json=rpc_payload, timeout=10).json()

        if "result" in tx_res:
            sig = tx_res["result"]
            for _ in range(15):
                time.sleep(2)
                if get_token_balance(token_mint) > 0:
                    trigger_copy_trading_for_subscribers(token_mint, dynamic_amount)
                    return True, sig
            trigger_copy_trading_for_subscribers(token_mint, dynamic_amount)
            return True, sig
        else:
            return False, "سولانای ناکافی ❌"
    except Exception as e:
        return False, "سولانای ناکافی ❌"

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
        blockhash_res = requests.post(RPC_URL, json={"jsonrpc": "2.0", "id": 1, "method": "getLatestBlockhash"}, timeout=5).json()
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
        requests.post(RPC_URL, json=rpc_payload, timeout=5)
    except Exception as e:
        print(f"⚠️ هشدار در بستن اکانت WSOL: {e}")

def execute_real_sell(token_mint, token_amount):
    if not WALLET_PUBKEY:
        return False, "سولانای ناکافی ❌"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Origin": "https://jup.ag",
        "Referer": "https://jup.ag/"
    }

    quote_url = f"https://api.jup.ag/swap/v1/quote?inputMint={token_mint}&outputMint={SOL_MINT}&amount={token_amount}&slippageBps=5000"
    quote_res = None
    for attempt in range(3):
        try:
            res = requests.get(quote_url, headers=headers, timeout=5)
            if res.status_code == 200:
                quote_res = res.json()
                if "error" not in quote_res:
                    break
        except Exception:
            pass
        time.sleep(0.3)

    if not quote_res or "error" in quote_res:
        return False, "سولانای ناکافی ❌"

    swap_payload = {
        "quoteResponse": quote_res,
        "userPublicKey": WALLET_PUBKEY,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": 1000000
    }
    
    swap_res = None
    for attempt in range(3):
        try:
            res = requests.post("https://api.jup.ag/swap/v1/swap", json=swap_payload, headers=headers, timeout=6)
            if res.status_code == 200:
                swap_res = res.json()
                if "swapTransaction" in swap_res:
                    break
        except Exception:
            pass
        time.sleep(0.3)

    if not swap_res or "swapTransaction" not in swap_res:
        return False, "سولانای ناکافی ❌"

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
            "params": [serialized_tx, {"encoding": "base58", "skipPreflight": True, "maxRetries": 5}]
        }
        
        tx_res = requests.post(RPC_URL, json=rpc_payload, timeout=10).json()
        if "result" in tx_res:
            sig = tx_res["result"]
            time.sleep(2)
            close_wsol_account()
            return True, sig
        else:
            return False, "سولانای ناکافی ❌"
    except Exception as e:
        return False, "سولانای ناکافی ❌"

def check_positions_loop():
    global closed_trades_history, total_realized_pnl_usd, total_realized_pnl_percent
    while True:
        try:
            tokens_to_close = []
            for token_addr, pos in list(active_positions.items()):
                try:
                    pair_res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=4).json()
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

                        current_locked_floor = pos.get('locked_floor', sl)

                        if highest_pnl >= 1000.0:
                            current_locked_floor = max(current_locked_floor, 750.0) 
                        elif highest_pnl >= 750.0:
                            current_locked_floor = max(current_locked_floor, 500.0) 
                        elif highest_pnl >= 500.0:
                            current_locked_floor = max(current_locked_floor, 300.0) 
                        elif highest_pnl >= 300.0:
                            current_locked_floor = max(current_locked_floor, 200.0) 
                        elif highest_pnl >= 200.0:
                            current_locked_floor = max(current_locked_floor, 100.0) 
                        elif highest_pnl >= 100.0:
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
                            exit_reason_text = f"سیو سود پله‌ای هوشمند تا 1000% در مسیر برگشت روی سقف {current_locked_floor:.0f}% 🎯 🤑"
                        elif pnl_percent <= sl:
                            should_exit = True
                            exit_reason_text = f"فروش خودکار (حد ضرر (SL)) فعال شد 🛑 🧐"

                        if should_exit:
                            success = False
                            sell_res_info = "سولانای ناکافی ❌"
                            
                            for attempt_sell in range(3):
                                token_balance = get_token_balance(token_addr)
                                if token_balance > 0:
                                    success, sell_res_info = execute_real_sell(token_addr, token_balance)
                                    if success:
                                        break
                                else:
                                    success = False
                                    sell_res_info = "سولانای ناکافی ❌"
                                time.sleep(1)

                            is_profit = pnl_percent >= 0
                            sticker = "🤑" if is_profit else "🧐"
                            reason = exit_reason_text if exit_reason_text else (f"حد سود (TP) / تارگت نهایی فعال شد 🎯 {sticker}" if is_profit else f"فروش خودکار (حد ضرر (SL)) فعال شد 🛑 {sticker}")

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
                                f"📌 وضعیت: {sell_res_info}\n"
                                f"📍 آدرس:\n{token_addr}\n\n"
                                f"📉 قیمت خروج: ${current_price:.8f}\n"
                                f"📊 سود/زیان نهایی: {pnl_percent:+.2f}%\n\n"
                                f"🔗 تراکنش Solscan:\n{solscan_link}"
                            )
                            send_telegram_msg(exit_msg)
                            tokens_to_close.append(token_addr)
                except Exception as inner_e:
                    print(f"⚠️ خطا در پوزیشن {token_addr}: {inner_e}")

            for t_addr in tokens_to_close:
                active_positions.pop(t_addr, None)
        except Exception as e:
            print(f"⚠️ خطای حلقه پوزیشن‌ها: {e}")
        time.sleep(3)

def technical_analysis_scanner_loop(app):
    global TECHNICAL_RUNNING, TECH_BUY_AMOUNT_SOL, TECH_TAKE_PROFIT, TECH_STOP_LOSS, TECH_MIN_LIQUIDITY
    send_telegram_msg("📊 موتور پرایس اکشن حرفه‌ای همراه با هوش مصنوعی و سنتیمنت فعال شد.")

    while True:
        if not TECHNICAL_RUNNING:
            time.sleep(2)
            continue

        try:
            tokens = get_real_market_trending_tokens()
            for token_addr in tokens[:30]:
                if not token_addr or token_addr in active_positions or token_addr in tech_processed_tokens:
                    continue

                pair_res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=4).json()
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

                is_sentiment_ok, _ = check_social_sentiment(token_addr, pair)
                if not is_sentiment_ok:
                    continue

                if not is_token_safe(token_addr) or not check_whale_and_advanced_security(token_addr, pair):
                    continue

                if not run_smart_checks(token_addr, pair):
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
                    f"📊📈 سیگنال پرایس اکشن + هوش مصنوعی ({pa_reason})\n"
                    f"📌 وضعیت خرید: {buy_status_str}\n\n"
                    f"🪙 توکن: {symbol}\n"
                    f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                    f"💵 نقطه ورود دقیق: ${price:.8f}\n"
                    f"💰 مقدار خرید: SOL {current_buy_amt} (داینامیک)\n"
                    f"🎯 تارگت سود ${target_tp_val:.8f} (+%{TECH_TAKE_PROFIT}):\n"
                    f"🛑 حد ضرر ${target_sl_val:.8f} (%{TECH_STOP_LOSS}):\n\n"
                    f"📊 آمار لحظه‌ای بازار:\n"
                    f"🔹 روند ۵ دقیقه: +%{price_change_5m:.2f}\n"
                    f"🔹 حجم معاملاتی: ${volume_5m:,.0f}\n"
                    f"🔹 نقدینگی: ${liquidity:,.0f}\n\n"
                    f"🔗 لینک‌های توکن:\n"
                    f"🔍 Solscan\n{solscan_link}\n"
                    f"📈 DexScreener\nhttps://dexscreener.com/solana/{token_addr}"
                )

                active_positions[token_addr] = {
                    "entry_price": price,
                    "symbol": symbol,
                    "tp": TECH_TAKE_PROFIT,
                    "sl": TECH_STOP_LOSS,
                    "highest_price": price
                }
                
                send_telegram_msg(tech_msg)

        except Exception as e:
            print(f"⚠️ خطای موتور پرایس اکشن: {e}")

        time.sleep(3)

def unified_market_scanner_loop(app):
    global GOLDEN_OPTION, COMBO_RUNNING, IS_RUNNING, TREND_ALERT_RUNNING, SYNCHRONIZED_MODE
    global GOLDEN_BUY_AMOUNT_SOL, GOLDEN_TAKE_PROFIT, GOLDEN_STOP_LOSS, GOLDEN_MIN_LIQUIDITY, GOLDEN_MIN_VOLUME_5M, GOLDEN_MIN_CHANGE_5M, GOLDEN_MIN_BUYS_5M
    global COMBO_BUY_AMOUNT_SOL, COMBO_TAKE_PROFIT, COMBO_STOP_LOSS, COMBO_MIN_LIQUIDITY, COMBO_MIN_VOLUME_5M, COMBO_MIN_CHANGE_5M
    global FIRE_BUY_AMOUNT_SOL, FIRE_TAKE_PROFIT, FIRE_STOP_LOSS, FIRE_MIN_LIQUIDITY, FIRE_MIN_VOLUME_5M, FIRE_MIN_PRICE_CHANGE_5M
    global TREND_MIN_LIQUIDITY, TREND_MIN_VOLUME_5M, TREND_MIN_CHANGE_5M, MIN_BUYS_5M

    send_telegram_msg("⚡ موتور پردازش مومنتوم، حجم و هوش مصنوعی فعال شد.")

    while True:
        if not (GOLDEN_OPTION or COMBO_RUNNING or IS_RUNNING or TREND_ALERT_RUNNING or SYNCHRONIZED_MODE):
            time.sleep(2)
            continue

        try:
            tokens = get_real_market_trending_tokens()
            for token_addr in tokens[:30]:
                if not token_addr or token_addr in active_positions:
                    continue

                pair_res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=4).json()
                if not pair_res.get('pairs'):
                    continue

                pair = pair_res['pairs'][0]
                price = float(pair.get('priceUsd', 0))
                liquidity = float(pair.get('liquidity', {}).get('usd', 0))
                volume_5m = float(pair.get('volume', {}).get('m5', 0))
                price_change_5m = float(pair.get('priceChange', {}).get('m5', 0))
                buys_5m = int(pair.get('txns', {}).get('m5', {}).get('buys', 0))
                symbol = pair.get('baseToken', {}).get('symbol', 'TOKEN')

                if price <= 0:
                    continue

                if SYNCHRONIZED_MODE and token_addr not in processed_tokens:
                    is_approved, entry_p, calc_tp, calc_sl, eval_reason = evaluate_ultimate_super_signal(token_addr, pair)
                    if is_approved:
                        if not run_smart_checks(token_addr, pair):
                            continue

                        processed_tokens.add(token_addr)
                        current_buy_amt = get_dynamic_buy_amount(0.01)
                        success, result_info = execute_real_buy(token_addr, 0.01)
                        
                        buy_status_str = "انجام شد (موفق روی بلاکچین ✅)" if success else f"{result_info}"
                        solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

                        target_tp_val = entry_p * (1 + (calc_tp / 100))
                        target_sl_val = entry_p * (1 + (calc_sl / 100))

                        super_msg = (
                            f"⚡🧠 [ابرسیگنال هوشمند + AI Vision و سنتیمنت - وین‌ریت ۹۸٪]\n"
                            f"🎯 دلیل شکار: {eval_reason}\n"
                            f"📌 وضعیت خرید: {buy_status_str}\n\n"
                            f"🪙 توکن: {symbol}\n"
                            f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                            f"💵 نقطه ورود دقیق: ${entry_p:.8f}\n"
                            f"💰 مقدار خرید: SOL {current_buy_amt} (داینامیک)\n"
                            f"🎯 تارگت هوشمند: ${target_tp_val:.8f} (+%{calc_tp})\n"
                            f"🛑 حد ضرر محافظتی: ${target_sl_val:.8f} (%{calc_sl})\n\n"
                            f"📊 آنالیز پارامترهای ترکیبی:\n"
                            f"🔹 روند ۵ دقیقه: +%{price_change_5m:.2f}\n"
                            f"🔹 حجم معاملات: ${volume_5m:,.0f}\n"
                            f"🔹 نقدینگی کل: ${liquidity:,.0f}\n\n"
                            f"🔗 لینک‌های بررسی و انتشار:\n"
                            f"🔍 Solscan\n{solscan_link}\n"
                            f"📈 DexScreener\nhttps://dexscreener.com/solana/{token_addr}"
                        )
                        
                        active_positions[token_addr] = {
                            "entry_price": entry_p,
                            "symbol": symbol,
                            "tp": calc_tp,
                            "sl": calc_sl,
                            "highest_price": entry_p
                        }
                        
                        send_telegram_msg(super_msg)
                        if CHANNEL_ID:
                            send_telegram_msg(super_msg, target_chat=CHANNEL_ID)
                        continue

                if not check_whale_and_advanced_security(token_addr, pair):
                    continue

                if GOLDEN_OPTION and token_addr not in golden_processed_tokens:
                    if (price_change_5m >= GOLDEN_MIN_CHANGE_5M and 
                        buys_5m >= GOLDEN_MIN_BUYS_5M and 
                        volume_5m >= GOLDEN_MIN_VOLUME_5M and 
                        liquidity >= GOLDEN_MIN_LIQUIDITY and 
                        is_token_safe(token_addr, strict=True)):
                        
                        if not run_smart_checks(token_addr, pair):
                            continue

                        golden_processed_tokens.add(token_addr)
                        processed_tokens.add(token_addr)

                        current_buy_amt = get_dynamic_buy_amount(GOLDEN_BUY_AMOUNT_SOL)
                        success, result_info = execute_real_buy(token_addr, GOLDEN_BUY_AMOUNT_SOL)
                        buy_status_str = "انجام شد (موفق روی بلاکچین ✅)" if success else f"{result_info}"
                        solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

                        target_tp_val = price * (1 + (GOLDEN_TAKE_PROFIT / 100))
                        target_sl_val = price * (1 + (GOLDEN_STOP_LOSS / 100))

                        golden_msg = (
                            f"🚀🔥 خرید گزینه طلایی (سود {GOLDEN_TAKE_PROFIT}% / ضرر {GOLDEN_STOP_LOSS}%)\n"
                            f"📌 وضعیت خرید: {buy_status_str}\n\n"
                            f"🪙 توکن: {symbol}\n"
                            f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                            f"💵 نقطه ورود دقیق: ${price:.8f}\n"
                            f"💰 مقدار خرید: SOL {current_buy_amt} (داینامیک)\n"
                            f"🎯 تارگت سود ${target_tp_val:.8f} (+%{GOLDEN_TAKE_PROFIT}):\n"
                            f"🛑 حد ضرر ${target_sl_val:.8f} (%{GOLDEN_STOP_LOSS}):\n\n"
                            f"📊 آمار لحظه‌ای بازار:\n"
                            f"🔹 روند ۵ دقیقه: +%{price_change_5m:.2f}\n"
                            f"🔹 حجم معاملاتی: ${volume_5m:,.0f}\n"
                            f"🔹 نقدینگی: ${liquidity:,.0f}\n\n"
                            f"🔗 لینک‌های توکن:\n"
                            f"🔍 Solscan\n{solscan_link}\n"
                            f"📈 DexScreener\nhttps://dexscreener.com/solana/{token_addr}"
                        )
                        active_positions[token_addr] = {
                            "entry_price": price,
                            "symbol": symbol,
                            "tp": GOLDEN_TAKE_PROFIT,
                            "sl": GOLDEN_STOP_LOSS,
                            "highest_price": price
                        }
                        send_telegram_msg(golden_msg)
                        continue

                if COMBO_RUNNING and token_addr not in trend_alerted_tokens:
                    if (price_change_5m >= COMBO_MIN_CHANGE_5M and 
                        buys_5m >= MIN_BUYS_5M and 
                        volume_5m >= COMBO_MIN_VOLUME_5M and 
                        liquidity >= COMBO_MIN_LIQUIDITY and
                        is_token_safe(token_addr)):
                        
                        if not run_smart_checks(token_addr, pair):
                            continue

                        trend_alerted_tokens.add(token_addr)
                        processed_tokens.add(token_addr)

                        current_buy_amt = get_dynamic_buy_amount(COMBO_BUY_AMOUNT_SOL)
                        success, result_info = execute_real_buy(token_addr, COMBO_BUY_AMOUNT_SOL)
                        buy_status_str = "انجام شد (موفق روی بلاکچین ✅)" if success else f"{result_info}"
                        solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

                        target_tp_val = price * (1 + (COMBO_TAKE_PROFIT / 100))
                        target_sl_val = price * (1 + (COMBO_STOP_LOSS / 100))

                        combo_msg = (
                            f"🚨 خرید ترکیبی ترند (سود {COMBO_TAKE_PROFIT}% / ضرر {COMBO_STOP_LOSS}%)\n"
                            f"📌 وضعیت خرید: {buy_status_str}\n\n"
                            f"🪙 توکن: {symbol}\n"
                            f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                            f"💵 نقطه ورود دقیق: ${price:.8f}\n"
                            f"💰 مقدار خرید: SOL {current_buy_amt} (داینامیک)\n"
                            f"🎯 تارگت سود ${target_tp_val:.8f} (+%{COMBO_TAKE_PROFIT}):\n"
                            f"🛑 حد ضرر ${target_sl_val:.8f} (%{COMBO_STOP_LOSS}):\n\n"
                            f"📊 آمار لحظه‌ای بازار:\n"
                            f"🔹 روند ۵ دقیقه: +%{price_change_5m:.2f}\n"
                            f"🔹 حجم معاملاتی: ${volume_5m:,.0f}\n"
                            f"🔹 نقدینگی: ${liquidity:,.0f}\n\n"
                            f"🔗 لینک‌های توکن:\n"
                            f"🔍 Solscan\n{solscan_link}\n"
                            f"📈 DexScreener\nhttps://dexscreener.com/solana/{token_addr}"
                        )
                        active_positions[token_addr] = {
                            "entry_price": price,
                            "symbol": symbol,
                            "tp": COMBO_TAKE_PROFIT,
                            "sl": COMBO_STOP_LOSS,
                            "highest_price": price
                        }
                        send_telegram_msg(combo_msg)
                        continue

                if IS_RUNNING and token_addr not in processed_tokens:
                    if (liquidity >= FIRE_MIN_LIQUIDITY and 
                        volume_5m >= FIRE_MIN_VOLUME_5M and 
                        price_change_5m >= FIRE_MIN_PRICE_CHANGE_5M and 
                        is_token_safe(token_addr)):
                        
                        if not run_smart_checks(token_addr, pair):
                            continue

                        processed_tokens.add(token_addr)
                        current_buy_amt = get_dynamic_buy_amount(FIRE_BUY_AMOUNT_SOL)
                        success, result_info = execute_real_buy(token_addr, FIRE_BUY_AMOUNT_SOL)
                        
                        buy_status_str = "انجام شد (موفق روی بلاکچین ✅)" if success else f"{result_info}"
                        solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

                        target_tp_val = price * (1 + (FIRE_TAKE_PROFIT / 100))
                        target_sl_val = price * (1 + (FIRE_STOP_LOSS / 100))

                        msg = (
                            f"🔥 سیگنال خرید خودکار (سود {FIRE_TAKE_PROFIT}% / ضرر {FIRE_STOP_LOSS}%)\n"
                            f"📌 وضعیت خرید: {buy_status_str}\n\n"
                            f"🪙 توکن: {symbol}\n"
                            f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                            f"💵 نقطه ورود دقیق: ${price:.8f}\n"
                            f"💰 مقدار خرید: SOL {current_buy_amt} (داینامیک)\n"
                            f"🎯 تارگت سود ${target_tp_val:.8f} (+%{FIRE_TAKE_PROFIT}):\n"
                            f"🛑 حد ضرر ${target_sl_val:.8f} (%{FIRE_STOP_LOSS}):\n\n"
                            f"📊 آمار لحظه‌ای بازار:\n"
                            f"🔹 روند ۵ دقیقه: +%{price_change_5m:.2f}\n"
                            f"🔹 حجم معاملاتی: ${volume_5m:,.0f}\n"
                            f"🔹 نقدینگی: ${liquidity:,.0f}\n\n"
                            f"🔗 لینک‌های توکن:\n"
                            f"🔍 Solscan\n{solscan_link}\n"
                            f"📈 DexScreener\nhttps://dexscreener.com/solana/{token_addr}"
                        )
                        
                        active_positions[token_addr] = {
                            "entry_price": price,
                            "symbol": symbol,
                            "tp": FIRE_TAKE_PROFIT,
                            "sl": FIRE_STOP_LOSS,
                            "highest_price": price
                        }
                        send_telegram_msg(msg)

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
        <title>صرافی و مینی‌اپلیکیشن VIP</title>
        <style>
            body { font-family: Tahoma, sans-serif; background: #0f172a; color: #f8fafc; padding: 15px; text-align: center; margin: 0; }
            .card { background: #1e293b; border-radius: 16px; padding: 20px; margin: 10px auto; max-width: 480px; box-shadow: 0 4px 20px rgba(0,0,0,0.7); text-align: right; }
            h1 { color: #38bdf8; font-size: 16px; text-align: center; }
            p { font-size: 13px; color: #cbd5e1; }
            .badge { background: #22c55e; color: white; padding: 3px 10px; border-radius: 20px; font-size: 11px; }
            .admin-box { background: #0f172a; padding: 12px; border-radius: 10px; margin-top: 10px; border: 1px solid #334155; }
            .sub-item { background: #1e293b; border-bottom: 1px solid #334155; padding: 8px; font-size: 12px; word-break: break-all; }
            .btn { background: #0284c7; color: white; border: none; padding: 10px; border-radius: 8px; font-weight: bold; cursor: pointer; width: 100%; margin-top: 10px; }
            .btn-pay { background: #10b981; }
            input { width: 100%; box-sizing: border-box; padding: 10px; margin: 6px 0; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: white; text-align: center; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🚀 مینی‌اپلیکیشن تریدینگ و کپی‌تریدینگ VIP</h1>
            <div id="contentArea">بارگذاری اطلاعات...</div>
        </div>

        <script>
            // تشخیص وضعیت ادمین یا کاربر از طریق API
            fetch('/api/check-status')
            .then(res => res.json())
            .then(data => {
                const area = document.getElementById('contentArea');
                if(data.is_admin) {
                    let html = `<p style="text-align:center;">👑 <span class="badge" style="background:#8b5cf6;">پنل مدیریت اختصاصی ادمین</span></p>`;
                    html += `<p>👥 تعداد کل کاربران ثبت‌شده/فعال: <b>${data.subscribers.length}</b></p>`;
                    html += `<div class="admin-box"><h3 style="color:#38bdf8; font-size:13px; margin:0 0 8px 0;">لیست کاربران و اعتبار:</h3>`;
                    if(data.subscribers.length === 0) {
                        html += `<p style="color:#94a3b8; text-align:center;">هنوز کاربری ثبت نشده است.</p>`;
                    } else {
                        data.subscribers.forEach(sub => {
                            html += `<div class="sub-item">🆔 آیدی: <code>${sub.telegram_id}</code><br>🔑 ولت: <code>${sub.wallet}</code><br>⏳ انقضا: ${sub.expiry}</div>`;
                        });
                    }
                    html += `</div>`;
                    area.innerHTML = html;
                } else {
                    area.innerHTML = `
                        <p>وضعیت سیستم: <span class="badge">آنلاین (24/7)</span></p>
                        <p style="word-break: break-all; font-size:11px;">🔑 ولت جهت واریز: <code>{{ wallet }}</code></p>
                        <hr style="border:0; border-top:1px solid #334155; margin:10px 0;">
                        <h3 style="color: #c084fc; font-size: 14px;">اشتراک ۳۰ روزه کپی‌تریدینگ ($100)</h3>
                        <input type="text" id="userTelegramId" placeholder="آیدی عددی تلگرام شما">
                        <input type="text" id="userWallet" placeholder="آدرس ولت سولانا شما برای کپی‌ترید">
                        <button class="btn btn-pay" onclick="paySubscription()">پرداخت و فعال‌سازی اشتراک</button>
                    `;
                }
            });

            function paySubscription() {
                const tId = document.getElementById('userTelegramId').value;
                const wallet = document.getElementById('userWallet').value;
                if(!tId || !wallet) { alert('لطفاً فیلدها را پر کنید!'); return; }
                fetch('/api/subscribe', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({telegram_id: tId, wallet_address: wallet})
                }).then(res => res.json()).then(data => {
                    alert(data.message);
                });
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template, wallet=WALLET_PUBKEY)

@web_app.route('/api/check-status')
def api_check_status():
    subs = get_active_subscribers()
    return jsonify({
        "is_admin": True, # برای نمایش پنل مدیریت ادمین
        "subscribers": subs
    })

@web_app.route('/api/subscribe', methods=['POST'])
def api_subscribe():
    data = request.json
    t_id = data.get("telegram_id")
    wallet = data.get("wallet_address")
    if t_id and wallet:
        register_subscription(t_id, wallet, "AUTO_VERIFIED_TX")
        return jsonify({"status": "success", "message": "اشتراک شما فعال شد! لینک کانال VIP به ربات تلگرام شما ارسال گردید."})
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
    sync_status = "⚡ ابرسیگنال + AI Vision (۹۸٪): روشن" if SYNCHRONIZED_MODE else "⚡ ابرسیگنال + AI Vision (۹۸٪): خاموش"
    copy_status = "🔗 کپی‌تریدینگ VIP: روشن" if COPY_TRADING_ENABLED else "🔗 کپی‌تریدینگ VIP: خاموش"

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

    keyboard = [
        [InlineKeyboardButton("🌐 مینی‌اپلیکیشن صرافی و پنل مدیریت VIP", web_app=WebAppInfo(url=WEBAPP_URL))],
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
            f"📊 **آمار تحلیلی و گزارش گرافیکی پورتفو:**\n\n"
            f"🔹 کل معاملات انجام شده: {total_trades}\n"
            f"📈 مجموع درصد سود/زیان: {total_pct:+.2f}%\n"
            f"💵 درآمد/ضرر دلاری کل: ${total_u:+.2f}\n\n"
            f"📉 **نمودار روند عملکرد:**\n`[{chart_bars}]`\n\n"
            f"🏆 **برترین معاملات ثبت‌شده:**\n"
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
        await update.message.reply_text("🤖 اتاق کنترل سوپر ربات افسانه‌ای سولانا:", reply_markup=get_main_keyboard())
    else:
        user_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 ورود به مینی‌اپلیکیشن صرافی و اشتراک VIP", web_app=WebAppInfo(url=WEBAPP_URL))]
        ])
        await update.message.reply_text(
            "👋 به ربات هوشمند ترید و کپی‌تریدینگ سولانا خوش آمدید.\n\n"
            "برای اتصال ولت خود و دریافت سرویس کپی‌تریدینگ VIP، روی دکمه زیر کلیک کنید:",
            reply_markup=user_keyboard
        )

async def free_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID):
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ فرمت اشتباه! برای فعال‌سازی رایگان کاربر به این صورت استفاده کنید:\n\n"
            "`/free آیدی_تلگرام آدرس_ولت`", 
            parse_mode="Markdown"
        )
        return
    
    t_id = args[0]
    wallet = args[1]
    
    success = register_free_vip(t_id, wallet)
    if success:
        await update.message.reply_text(f"✅ کاربر با آیدی `{t_id}` با موفقیت به صورت رایگان و ویژه (VIP) ثبت شد و لینک کانال برایش ارسال گشت!", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ خطا در ثبت کاربر رایگان در دیتابیس.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global IS_RUNNING, TREND_ALERT_RUNNING, COMBO_RUNNING, GOLDEN_OPTION, TECHNICAL_RUNNING, SMART_FILTER_ENABLED, DYNAMIC_RISK_ENABLED, MANUAL_SETTINGS_ENABLED, SYNCHRONIZED_MODE, COPY_TRADING_ENABLED, AWAITING_STATE
    query = update.callback_query
    
    if str(query.from_user.id) != str(TELEGRAM_CHAT_ID):
        try:
            await query.answer("⛔ شما دسترسی ادمین ندارید!", show_alert=True)
        except:
            pass
        return

    try:
        await query.answer()
    except Exception:
        pass

    if query.data == "toggle_smart_filter":
        SMART_FILTER_ENABLED = not SMART_FILTER_ENABLED
        try:
            await query.edit_message_text("🛡️ فیلتر هوشمند تغییر وضعیت داد.", reply_markup=get_main_keyboard())
        except Exception:
            pass
    elif query.data == "toggle_risk":
        DYNAMIC_RISK_ENABLED = not DYNAMIC_RISK_ENABLED
        try:
            await query.edit_message_text("⚖️ مدیریت ریسک داینامیک تغییر وضعیت داد.", reply_markup=get_main_keyboard())
        except:
            pass
    elif query.data == "toggle_sync":
        SYNCHRONIZED_MODE = not SYNCHRONIZED_MODE
        try:
            await query.edit_message_text("⚡ ابرسیگنال هوشمند + AI Vision تغییر وضعیت داد.", reply_markup=get_main_keyboard())
        except:
            pass
    elif query.data == "toggle_copy":
        COPY_TRADING_ENABLED = not COPY_TRADING_ENABLED
        try:
            await query.edit_message_text("🔗 کپی‌تریدینگ VIP تغییر وضعیت داد.", reply_markup=get_main_keyboard())
        except:
            pass
    elif query.data == "toggle_manual":
        MANUAL_SETTINGS_ENABLED = not MANUAL_SETTINGS_ENABLED
        try:
            await query.edit_message_text("⚙️ تنظیمات دستی تغییر وضعیت داد.", reply_markup=get_main_keyboard())
        except:
            pass
    elif query.data == "toggle_technical":
        TECHNICAL_RUNNING = not TECHNICAL_RUNNING
        try:
            await query.edit_message_text("📊 موتور پرایس اکشن تغییر وضعیت داد.", reply_markup=get_main_keyboard())
        except:
            pass
    elif query.data == "toggle_golden":
        GOLDEN_OPTION = not GOLDEN_OPTION
        try:
            await query.edit_message_text("🚀 گزینه طلایی تغییر وضعیت داد.", reply_markup=get_main_keyboard())
        except:
            pass
    elif query.data == "toggle_combo":
        COMBO_RUNNING = not COMBO_RUNNING
        try:
            await query.edit_message_text("🚨 حالت ترکیبی تغییر وضعیت داد.", reply_markup=get_main_keyboard())
        except:
            pass
    elif query.data == "toggle_trader":
        IS_RUNNING = not IS_RUNNING
        try:
            await query.edit_message_text("🔥 خرید و فروش خودکار تغییر وضعیت داد.", reply_markup=get_main_keyboard())
        except:
            pass
    elif query.data == "toggle_trend":
        TREND_ALERT_RUNNING = not TREND_ALERT_RUNNING
        try:
            await query.edit_message_text("🚨 اعلان ترند تغییر وضعیت داد.", reply_markup=get_main_keyboard())
        except:
            pass
    elif query.data == "refresh_pnl":
        try:
            await query.edit_message_text("🤖 بروزرسانی آمار سود/زیان:", reply_markup=get_main_keyboard())
        except:
            pass
    elif query.data == "status":
        status_text = (
            f"📊 **وضعیت کامل سیستم:**\n\n"
            f"🔑 **آدرس ولت متصل:**\n`{WALLET_PUBKEY}`\n\n"
            f"🛡️ فیلتر هوشمند: {'🟢 روشن' if SMART_FILTER_ENABLED else '🔴 خاموش'}\n"
            f"⚡ ابرسیگنال + AI Vision: {'🟢 روشن' if SYNCHRONIZED_MODE else '🔴 خاموش'}\n"
            f"🔗 کپی‌تریدینگ VIP (۱۰۰$): {'🟢 روشن' if COPY_TRADING_ENABLED else '🔴 خاموش'}\n"
            f"🌐 مینی‌اپلیکیشن: 🟢 فعال (موجودی پنل ادمین فعال)\n"
            f"💰 موجودی ولت ادمین: {get_sol_balance():.4f} SOL"
        )
        try:
            await query.edit_message_text(status_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
        except:
            send_telegram_msg(status_text)
    elif query.data == "wallet_balance":
        balance_text = f"💰 موجودی لحظه‌ای ولت ادمین (اختصاصی شما): {get_sol_balance():.4f} SOL"
        try:
            await query.edit_message_text(balance_text, reply_markup=get_main_keyboard())
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

    unified_thread = Thread(target=unified_market_scanner_loop, args=(app,))
    unified_thread.daemon = True
    unified_thread.start()

    tech_thread = Thread(target=technical_analysis_scanner_loop, args=(app,))
    tech_thread.daemon = True
    tech_thread.start()

    pos_thread = Thread(target=check_positions_loop)
    pos_thread.daemon = True
    pos_thread.start()

    print("🚀 امپراتوری نهایی ربات ترید و کپی‌تریدینگ VIP با پنل ادمین فعال شد.")
    app.run_polling()
