import time
import requests
import json
import base64
import base58
import os
from threading import Thread
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.hash import Hash
from solders.instruction import Instruction, AccountMeta
from solders.message import MessageV0
from solders.transaction import VersionedTransaction
from solders.system_program import create_account, CreateAccountParams

# تنظیمات کلیدی محیطی
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "TOKEN_YOW")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "CHAT_ID_YOW")
PRIVATE_KEY_BASE58 = os.environ.get("PRIVATE_KEY_BASE58", "YOUR_PRIVATE_KEY")

RPC_URL = "https://mainnet.helius-rpc.com/?api-key=ef769dc4-03dc-4f1d-ba4a-a651d75f6b80"
SOL_MINT = "So11111111111111111111111111111111111111112"
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ATA_PROGRAM_ID = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
SYS_PROG_ID = Pubkey.from_string("11111111111111111111111111111111")
RENT_SYSVAR = Pubkey.from_string("SysvarRent11111111111111111111111111111111")

IS_RUNNING = False          # خرید و فروش خودکار مستقل
TREND_ALERT_RUNNING = False # اعلان ترند مستقل (فقط هشدار)
COMBO_RUNNING = False       # حالت ترکیبی (ترندهای انفجاری + خرید واقعی + هشدار)

BUY_AMOUNT_SOL = 0.005

# تنظیمات سیگنال معمولی
TAKE_PROFIT = 30.0
STOP_LOSS = -12.0
MIN_LIQUIDITY = 35000       
MIN_VOLUME_5M = 5000       
MIN_PRICE_CHANGE_5M = 5.0  

# تنظیمات ترند / حالت ترکیبی
TREND_TAKE_PROFIT = 60.0
TREND_STOP_LOSS = -15.0
TREND_MIN_VOLUME_5M = 40000  
TREND_MIN_CHANGE_5M = 15.0   
MIN_BUYS_5M = 50             

AWAITING_STATE = None 
processed_tokens = set()
trend_alerted_tokens = set()
active_positions = {}

def send_telegram_msg(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": True,
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"❌ خطای ارسال پیام به تلگرام: {e}")

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
        return 0.0

def get_token_balance(token_mint):
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
    except Exception as e:
        print(f"⚠️ خطا در استعلام موجودی توکن: {e}")
    return 0

def is_token_safe(token_mint):
    try:
        url = f"https://api.rugcheck.xyz/v1/tokens/{token_mint}/summary"
        res = requests.get(url, timeout=4)
        if res.status_code == 200:
            data = res.json()
            risk_score = data.get("score", 0)
            if risk_score > 5000:
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

def execute_real_buy(token_mint, amount_sol):
    if not WALLET_PUBKEY:
        return False, "کلید عمومی ولت نامعتبر است"

    lamports = int(amount_sol * 1_000_000_000)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Origin": "https://jup.ag",
        "Referer": "https://jup.ag/"
    }

    quote_url = f"https://api.jup.ag/swap/v1/quote?inputMint={SOL_MINT}&outputMint={token_mint}&amount={lamports}&slippageBps=300"
    
    quote_res = None
    for attempt in range(2):
        try:
            res = requests.get(quote_url, headers=headers, timeout=5)
            if res.status_code == 200:
                quote_res = res.json()
                break
        except Exception:
            pass
        time.sleep(0.3)

    if not quote_res or "error" in quote_res:
        return False, "خطای دریافت قیمت از صرافی"

    swap_payload = {
        "quoteResponse": quote_res,
        "userPublicKey": WALLET_PUBKEY,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True
    }
    
    swap_res = None
    for attempt in range(2):
        try:
            res = requests.post("https://api.jup.ag/swap/v1/swap", json=swap_payload, headers=headers, timeout=5)
            if res.status_code == 200:
                swap_res = res.json()
                break
        except Exception:
            pass
        time.sleep(0.3)

    if not swap_res or "swapTransaction" not in swap_res:
        return False, "تراکنش سواپ توسط صرافی رد شد"

    try:
        swap_tx_b64 = swap_res["swapTransaction"]
        raw_tx = base64.b64decode(swap_tx_b64)
        txn = VersionedTransaction.from_bytes(raw_tx)
        signature = sender_keypair.sign_message(bytes(txn.message))
        signed_txn = VersionedTransaction.populate(txn.message, [signature])
        serialized_tx = base58.b58encode(bytes(signed_txn)).decode('utf-8')

        rpc_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendTransaction",
            "params": [serialized_tx, {"encoding": "base58", "skipPreflight": True}]
        }
        
        tx_res = requests.post(RPC_URL, json=rpc_payload, timeout=10).json()
        if "result" in tx_res:
            return True, tx_res["result"]
        else:
            err_details = tx_res.get('error', {}).get('message', 'ریجکت توسط شبکه')
            return False, f"{err_details}"
    except Exception as e:
        return False, f"خطای امضا: {str(e)}"

def execute_real_sell(token_mint, token_amount):
    if not WALLET_PUBKEY:
        return False, "کلید عمومی ولت نامعتبر است"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Origin": "https://jup.ag",
        "Referer": "https://jup.ag/"
    }

    quote_url = f"https://api.jup.ag/swap/v1/quote?inputMint={token_mint}&outputMint={SOL_MINT}&amount={token_amount}&slippageBps=300"
    quote_res = None
    for attempt in range(2):
        try:
            res = requests.get(quote_url, headers=headers, timeout=5)
            if res.status_code == 200:
                quote_res = res.json()
                break
        except Exception:
            pass
        time.sleep(0.3)

    if not quote_res or "error" in quote_res:
        return False, "خطای دریافت قیمت فروش از صرافی"

    swap_payload = {
        "quoteResponse": quote_res,
        "userPublicKey": WALLET_PUBKEY,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True
    }
    
    swap_res = None
    for attempt in range(2):
        try:
            res = requests.post("https://api.jup.ag/swap/v1/swap", json=swap_payload, headers=headers, timeout=5)
            if res.status_code == 200:
                swap_res = res.json()
                break
        except Exception:
            pass
        time.sleep(0.3)

    if not swap_res or "swapTransaction" not in swap_res:
        return False, "تراکنش فروش توسط صرافی رد شد"

    try:
        swap_tx_b64 = swap_res["swapTransaction"]
        raw_tx = base64.b64decode(swap_tx_b64)
        txn = VersionedTransaction.from_bytes(raw_tx)
        signature = sender_keypair.sign_message(bytes(txn.message))
        signed_txn = VersionedTransaction.populate(txn.message, [signature])
        serialized_tx = base58.b58encode(bytes(signed_txn)).decode('utf-8')

        rpc_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendTransaction",
            "params": [serialized_tx, {"encoding": "base58", "skipPreflight": True}]
        }
        
        tx_res = requests.post(RPC_URL, json=rpc_payload, timeout=10).json()
        if "result" in tx_res:
            return True, tx_res["result"]
        else:
            err_details = tx_res.get('error', {}).get('message', 'ریجکت توسط شبکه')
            return False, f"{err_details}"
    except Exception as e:
        return False, f"خطای امضا در فروش: {str(e)}"

def check_positions_loop():
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
                    tp = pos['tp']
                    sl = pos['sl']
                    
                    if entry_price > 0:
                        pnl_percent = ((current_price - entry_price) / entry_price) * 100

                        if pnl_percent >= tp or pnl_percent <= sl:
                            reason = "حد سود (TP) فعال شد 🎯" if pnl_percent >= 0 else "حد ضرر (SL) فعال شد 🛑"

                            token_balance = get_token_balance(token_addr)
                            if token_balance > 0:
                                success, sell_res_info = execute_real_sell(token_addr, token_balance)
                            else:
                                success, sell_res_info = False, "موجودی توکن در ولت یافت نشد"

                            sell_status_str = "انجام شد (موفق ✅)" if success else f"خطا ({sell_res_info} ❌)"
                            solscan_link = f"https://solscan.io/tx/{sell_res_info}" if success else "https://solscan.io"
                            
                            exit_msg = (
                                f"🔴 فروش خودکار ({reason})\n\n"
                                f"🪙 توکن: {symbol}\n"
                                f"📌 وضعیت فروش: {sell_status_str}\n"
                                f"📍 آدرس:\n{token_addr}\n\n"
                                f"📉 قیمت خروج: ${current_price:.8f}\n"
                                f"📊 سود/زیان نهایی: {pnl_percent:+.2f}%\n\n"
                                f"🔗 لینک‌های اختصاصی توکن:\n"
                                f"🔍 تراکنش در Solscan\n{solscan_link}\n"
                                f"📈 DexScreener\nhttps://dexscreener.com/solana/{token_addr}"
                            )
                            send_telegram_msg(exit_msg)
                            tokens_to_close.append(token_addr)
                except Exception as inner_e:
                    print(f"⚠️ خطا در بررسی پوزیشن {token_addr}: {inner_e}")

            for t_addr in tokens_to_close:
                active_positions.pop(t_addr, None)
        except Exception as e:
            print(f"⚠️ خطای حلقه بررسی پوزیشن‌ها: {e}")
        time.sleep(2)

def trend_alert_scanner_loop(app):
    global TREND_ALERT_RUNNING, COMBO_RUNNING, TREND_TAKE_PROFIT, TREND_STOP_LOSS, TREND_MIN_VOLUME_5M, MIN_BUYS_5M
    while True:
        if not TREND_ALERT_RUNNING and not COMBO_RUNNING:
            time.sleep(2)
            continue
        try:
            tokens = get_real_market_trending_tokens()
            for token_addr in tokens[:30]:
                if not TREND_ALERT_RUNNING and not COMBO_RUNNING:
                    break
                if not token_addr or token_addr in trend_alerted_tokens:
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

                if (price_change_5m >= TREND_MIN_CHANGE_5M and 
                    buys_5m >= MIN_BUYS_5M and 
                    volume_5m >= TREND_MIN_VOLUME_5M and 
                    price > 0 and 
                    is_token_safe(token_addr)):
                    
                    trend_alerted_tokens.add(token_addr)
                    
                    if TREND_ALERT_RUNNING:
                        alert_msg = (
                            f"🔥 اعلان ترند بازار (هشدار سریع) 🚀\n\n"
                            f"🪙 نام توکن: {symbol}\n"
                            f"📍 آدرس قرارداد (کپی با یک کلیک):\n{token_addr}\n\n"
                            f"💵 قیمت لحظه‌ای: ${price:.8f}\n"
                            f"📈 پامپ رشد ۵ دقیقه: +{price_change_5m:.2f}%\n"
                            f"📊 حجم معاملاتی ۵ دقیقه: ${volume_5m:,.0f}\n"
                            f"💧 نقدینگی: ${liquidity:,.0f}\n\n"
                            f"🔗 https://dexscreener.com/solana/{token_addr}"
                        )
                        send_telegram_msg(alert_msg)

                    if COMBO_RUNNING and token_addr not in active_positions:
                        print(f"⏳ [حالت ترکیبی] خرید توکن ترند {symbol}...")
                        success, result_info = execute_real_buy(token_addr, BUY_AMOUNT_SOL)
                        
                        buy_status_str = "انجام شد (موفق روی بلاکچین ✅)" if success else f"خطا ({result_info} ❌)"
                        solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

                        target_tp = price * (1 + (TREND_TAKE_PROFIT / 100))
                        target_sl = price * (1 + (TREND_STOP_LOSS / 100))

                        combo_msg = (
                            f"⚡🔥 خرید ترکیبی ترند (سود {TREND_TAKE_PROFIT}% / ضرر {TREND_STOP_LOSS}%)\n"
                            f"📌 وضعیت خرید: {buy_status_str}\n\n"
                            f"🪙 توکن: {symbol}\n"
                            f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                            f"💵 نقطه ورود دقیق: ${price:.8f}\n"
                            f"💰 مقدار خرید: SOL {BUY_AMOUNT_SOL}\n"
                            f"🎯 تارگت سود (+{TREND_TAKE_PROFIT}%): ${target_tp:.8f}\n"
                            f"🛑 حد ضرر ({TREND_STOP_LOSS}%): ${target_sl:.8f}\n\n"
                            f"📊 آمار لحظه‌ای بازار:\n"
                            f"🔹 روند ۵ دقیقه: +{price_change_5m:.2f}%\n"
                            f"🔹 حجم معاملاتی: ${volume_5m:,.0f}\n"
                            f"🔹 نقدینگی: ${liquidity:,.0f}\n\n"
                            f"🔗 لینک‌های توکن:\n"
                            f"🔍 Solscan\n{solscan_link}\n"
                            f"📈 DexScreener\nhttps://dexscreener.com/solana/{token_addr}"
                        )
                        if success:
                            active_positions[token_addr] = {
                                "entry_price": price,
                                "symbol": symbol,
                                "tp": TREND_TAKE_PROFIT,
                                "sl": TREND_STOP_LOSS
                            }
                        send_telegram_msg(combo_msg)
        except Exception as e:
            print(f"⚠️ خطای اسکنر ترند: {e}")
        time.sleep(5)

def auto_trader_loop(app):
    global IS_RUNNING, BUY_AMOUNT_SOL, TAKE_PROFIT, STOP_LOSS, MIN_LIQUIDITY, MIN_VOLUME_5M
    send_telegram_msg("⚡ خرید و فروش خودکار مستقل فعال شد.")

    while True:
        if not IS_RUNNING:
            time.sleep(1)
            continue

        try:
            solana_tokens = get_real_market_trending_tokens()

            for token_addr in solana_tokens[:30]:
                if not IS_RUNNING:
                    break

                if not token_addr or token_addr in processed_tokens or token_addr in active_positions:
                    continue

                pair_res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=4).json()
                if not pair_res.get('pairs'):
                    continue

                pair = pair_res['pairs'][0]
                price = float(pair.get('priceUsd', 0))
                liquidity = float(pair.get('liquidity', {}).get('usd', 0))
                volume_5m = float(pair.get('volume', {}).get('m5', 0))
                price_change_5m = float(pair.get('priceChange', {}).get('m5', 0))
                symbol = pair.get('baseToken', {}).get('symbol', 'TOKEN')

                if (liquidity >= MIN_LIQUIDITY and 
                    volume_5m >= MIN_VOLUME_5M and 
                    price_change_5m >= MIN_PRICE_CHANGE_5M and 
                    price > 0 and
                    is_token_safe(token_addr)):
                    
                    processed_tokens.add(token_addr)
                    
                    print(f"⏳ خرید سیگنال معمولی {symbol}...")
                    success, result_info = execute_real_buy(token_addr, BUY_AMOUNT_SOL)
                    
                    buy_status_str = "انجام شد (موفق روی بلاکچین ✅)" if success else f"خطا ({result_info} ❌)"
                    solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

                    target_tp = price * (1 + (TAKE_PROFIT / 100))
                    target_sl = price * (1 + (STOP_LOSS / 100))

                    msg = (
                        f"⚡🔥 سیگنال خرید خودکار (سود {TAKE_PROFIT}% / ضرر {STOP_LOSS}%)\n"
                        f"📌 وضعیت خرید: {buy_status_str}\n\n"
                        f"🪙 توکن: {symbol}\n"
                        f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                        f"💵 نقطه ورود دقیق: ${price:.8f}\n"
                        f"💰 مقدار خرید: SOL {BUY_AMOUNT_SOL}\n"
                        f"🎯 تارگت سود (+{TAKE_PROFIT}%): ${target_tp:.8f}\n"
                        f"🛑 حد ضرر ({STOP_LOSS}%): ${target_sl:.8f}\n\n"
                        f"📊 آمار لحظه‌ای بازار:\n"
                        f"🔹 روند ۵ دقیقه: +{price_change_5m:.2f}%\n"
                        f"🔹 حجم معاملاتی: ${volume_5m:,.0f}\n"
                        f"🔹 نقدینگی: ${liquidity:,.0f}\n\n"
                        f"🔗 لینک‌های توکن:\n"
                        f"🔍 Solscan\n{solscan_link}\n"
                        f"📈 DexScreener\nhttps://dexscreener.com/solana/{token_addr}"
                    )
                    
                    if success:
                        active_positions[token_addr] = {
                            "entry_price": price,
                            "symbol": symbol,
                            "tp": TAKE_PROFIT,
                            "sl": STOP_LOSS
                        }

                    send_telegram_msg(msg)
        except Exception as e:
            print(f"⚠️ خطای حلقه تریدر معمولی: {e}")

        time.sleep(1)

web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Multi-Mode Solana Bot is running 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

def get_main_keyboard():
    trader_status = "🟢 خرید و فروش: روشن" if IS_RUNNING else "🔴 خرید و فروش: خاموش"
    trend_status = "🟢 اعلان ترند: روشن" if TREND_ALERT_RUNNING else "🔴 اعلان ترند: خاموش"
    combo_status = "🟢 حالت ترکیبی: روشن" if COMBO_RUNNING else "🔴 حالت ترکیبی: خاموش"
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(combo_status, callback_data="toggle_combo")],
        [InlineKeyboardButton(trader_status, callback_data="toggle_trader"),
         InlineKeyboardButton(trend_status, callback_data="toggle_trend")],
        [InlineKeyboardButton("📊 وضعیت سیستم", callback_data="status"),
         InlineKeyboardButton("💰 موجودی ولت", callback_data="wallet_balance")],
        [InlineKeyboardButton(f"⚙️ حجم معامله: {BUY_AMOUNT_SOL} SOL", callback_data="menu_volume")],
        
        # تنظیمات سیگنال معمولی
        [InlineKeyboardButton(f"🔵 [سیگنال] تارگت: +{TAKE_PROFIT}%", callback_data="menu_tp"),
         InlineKeyboardButton(f"🔵 [سیگنال] ضرر: {STOP_LOSS}%", callback_data="menu_sl")],
        [InlineKeyboardButton(f"🔵 نقدینگی: ${MIN_LIQUIDITY}", callback_data="menu_liq"),
         InlineKeyboardButton(f"🔵 حجم ۵دقیقه: ${MIN_VOLUME_5M}", callback_data="menu_vol5m")],
        [InlineKeyboardButton(f"🔵 رشد ۵دقیقه: +{MIN_PRICE_CHANGE_5M}%", callback_data="menu_chg5m")],
        
        # تنظیمات ترند و حالت ترکیبی
        [InlineKeyboardButton(f"🔥 [ترند] سود: +{TREND_TAKE_PROFIT}%", callback_data="menu_trend_tp"),
         InlineKeyboardButton(f"🔥 [ترند] ضرر: {TREND_STOP_LOSS}%", callback_data="menu_trend_sl")]
    ])

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID):
        return
    global AWAITING_STATE
    AWAITING_STATE = None
    await update.message.reply_text("🤖 اتاق کنترل ربات هوشمند سولانا:", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global IS_RUNNING, TREND_ALERT_RUNNING, COMBO_RUNNING, AWAITING_STATE
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    if query.data == "toggle_combo":
        COMBO_RUNNING = not COMBO_RUNNING
        state_txt = "🟢 حالت ترکیبی روشن شد." if COMBO_RUNNING else "🔴 حالت ترکیبی خاموش شد."
        try:
            await query.edit_message_text(state_txt, reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg(state_txt)

    elif query.data == "toggle_trader":
        IS_RUNNING = not IS_RUNNING
        state_txt = "🟢 خرید و فروش خودکار روشن شد." if IS_RUNNING else "🔴 خرید و فروش خودکار خاموش شد."
        try:
            await query.edit_message_text(state_txt, reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg(state_txt)
            
    elif query.data == "toggle_trend":
        TREND_ALERT_RUNNING = not TREND_ALERT_RUNNING
        state_txt = "🟢 اعلان ترند روشن شد." if TREND_ALERT_RUNNING else "🔴 اعلان ترند خاموش شد."
        try:
            await query.edit_message_text(state_txt, reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg(state_txt)
            
    elif query.data == "status":
        pub_display = f"{WALLET_PUBKEY[:6]}...{WALLET_PUBKEY[-4:]}" if WALLET_PUBKEY else "تنظیم نشده"
        current_sol_bal = get_sol_balance()
        status_text = (
            f"📊 وضعیت کامل سیستم:\n\n"
            f"🔹 حالت ترکیبی: {'🟢 روشن' if COMBO_RUNNING else '🔴 خاموش'} (سود: +{TREND_TAKE_PROFIT}% | ضرر: {TREND_STOP_LOSS}%)\n"
            f"🔹 خرید و فروش خودکار: {'🟢 روشن' if IS_RUNNING else '🔴 خاموش'} (سود: +{TAKE_PROFIT}% | ضرر: {STOP_LOSS}%)\n"
            f"🔹 اعلان ترند: {'🟢 روشن' if TREND_ALERT_RUNNING else '🔴 خاموش'}\n"
            f"💰 موجودی ولت: {current_sol_bal:.4f} SOL\n"
            f"⚙️ حجم معامله: {BUY_AMOUNT_SOL} SOL\n"
            f"🔑 ولت متصل: {pub_display}"
        )
        try:
            await query.edit_message_text(status_text, reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg(status_text)

    elif query.data == "wallet_balance":
        current_sol_bal = get_sol_balance()
        balance_text = f"💰 موجودی ولت: {current_sol_bal:.4f} SOL"
        try:
            await query.edit_message_text(balance_text, reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg(balance_text)

    elif query.data == "menu_volume":
        AWAITING_STATE = "volume"
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"⚙️ حجم فعلی: {BUY_AMOUNT_SOL} SOL\nلطفاً حجم جدید را تایپ کنید:", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("لطفاً حجم جدید را تایپ کنید:")

    elif query.data == "menu_tp":
        AWAITING_STATE = "tp"
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"🎯 تارگت سیگنال فعلی: +{TAKE_PROFIT}%\nلطفاً مقدار جدید را تایپ کنید:", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("لطفاً مقدار جدید را تایپ کنید:")

    elif query.data == "menu_sl":
        AWAITING_STATE = "sl"
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"🛑 حد ضرر سیگنال فعلی: {STOP_LOSS}%\nلطفاً مقدار جدید را تایپ کنید (مثلاً 12-):", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("لطفاً مقدار جدید را تایپ کنید:")

    elif query.data == "menu_liq":
        AWAITING_STATE = "liq"
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"🔒 نقدینگی فعلی: ${MIN_LIQUIDITY}\nلطفاً مقدار جدید را تایپ کنید:", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("لطفاً مقدار جدید را تایپ کنید:")

    elif query.data == "menu_vol5m":
        AWAITING_STATE = "vol5m"
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"📈 حجم ۵ دقیقه فعلی: ${MIN_VOLUME_5M}\nلطفاً مقدار جدید را تایپ کنید:", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("لطفاً مقدار جدید را تایپ کنید:")

    elif query.data == "menu_chg5m":
        AWAITING_STATE = "chg5m"
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"🚀 رشد ۵ دقیقه فعلی: +{MIN_PRICE_CHANGE_5M}%\nلطفاً مقدار جدید را تایپ کنید:", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("لطفاً مقدار جدید را تایپ کنید:")

    elif query.data == "menu_trend_tp":
        AWAITING_STATE = "trend_tp"
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"🔥 [ترند] سود فعلی: +{TREND_TAKE_PROFIT}%\nلطفاً مقدار جدید را تایپ کنید:", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("لطفاً مقدار جدید را تایپ کنید:")

    elif query.data == "menu_trend_sl":
        AWAITING_STATE = "trend_sl"
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"🔥 [ترند] ضرر فعلی: {TREND_STOP_LOSS}%\nلطفاً مقدار جدید را تایپ کنید (مثلاً 15-):", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("لطفاً مقدار جدید را تایپ کنید:")
            
    elif query.data == "cancel_input":
        AWAITING_STATE = None
        try:
            await query.edit_message_text("🤖 لغو شد.", reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg("لغو شد.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BUY_AMOUNT_SOL, TAKE_PROFIT, STOP_LOSS, MIN_LIQUIDITY, MIN_VOLUME_5M, MIN_PRICE_CHANGE_5M, TREND_TAKE_PROFIT, TREND_STOP_LOSS, AWAITING_STATE
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID):
        return

    if AWAITING_STATE:
        text_input = update.message.text.strip().replace(',', '.')
        try:
            val = float(text_input)
            
            if AWAITING_STATE == "volume":
                if val <= 0: raise ValueError()
                BUY_AMOUNT_SOL = val
                msg = f"✅ حجم خرید به {BUY_AMOUNT_SOL} SOL تغییر یافت."
            elif AWAITING_STATE == "tp":
                if val <= 0: raise ValueError()
                TAKE_PROFIT = val
                msg = f"✅ تارگت سیگنال به +{TAKE_PROFIT}% تغییر یافت."
            elif AWAITING_STATE == "sl":
                STOP_LOSS = val
                msg = f"✅ حد ضرر سیگنال به {STOP_LOSS}% تغییر یافت."
            elif AWAITING_STATE == "liq":
                if val < 0: raise ValueError()
                MIN_LIQUIDITY = val
                msg = f"✅ نقدینگی به ${MIN_LIQUIDITY} تغییر یافت."
            elif AWAITING_STATE == "vol5m":
                if val < 0: raise ValueError()
                MIN_VOLUME_5M = val
                msg = f"✅ حجم ۵ دقیقه به ${MIN_VOLUME_5M} تغییر یافت."
            elif AWAITING_STATE == "chg5m":
                MIN_PRICE_CHANGE_5M = val
                msg = f"✅ رشد ۵ دقیقه به +{MIN_PRICE_CHANGE_5M}% تغییر یافت."
            elif AWAITING_STATE == "trend_tp":
                if val <= 0: raise ValueError()
                TREND_TAKE_PROFIT = val
                msg = f"✅ سود ترند به +{TREND_TAKE_PROFIT}% تغییر یافت."
            elif AWAITING_STATE == "trend_sl":
                TREND_STOP_LOSS = val
                msg = f"✅ ضرر ترند به {TREND_STOP_LOSS}% تغییر یافت."
            else:
                msg = "خطا در تنظیمات."

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
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    trader_thread = Thread(target=auto_trader_loop, args=(app,))
    trader_thread.daemon = True
    trader_thread.start()

    trend_thread = Thread(target=trend_alert_scanner_loop, args=(app,))
    trend_thread.daemon = True
    trend_thread.start()

    pos_thread = Thread(target=check_positions_loop)
    pos_thread.daemon = True
    pos_thread.start()

    print("🚀 ربات هوشمند سولانا استارت شد.")
    app.run_polling()
