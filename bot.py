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
RENT_SYSVAR = Pubkey.from_string("SysvarRent111111111111111111111111111111111")

IS_RUNNING = False          
TREND_ALERT_RUNNING = False 
COMBO_RUNNING = False       
GOLDEN_OPTION = False       

# تنظیمات اختصاصی بخش خرید و فروش (آتیش 🔥)
FIRE_BUY_AMOUNT_SOL = 0.005
FIRE_TAKE_PROFIT = 30.0
FIRE_STOP_LOSS = -12.0
FIRE_MIN_LIQUIDITY = 35000       
FIRE_MIN_VOLUME_5M = 5000       
FIRE_MIN_PRICE_CHANGE_5M = 5.0  

# تنظیمات اختصاصی بخش ترند و ترکیبی (آژیر 🚨)
ALERT_BUY_AMOUNT_SOL = 0.005
TREND_TAKE_PROFIT = 20.0
TREND_STOP_LOSS = -5.0
TREND_MIN_LIQUIDITY = 40000
TREND_MIN_VOLUME_5M = 60000  
TREND_MIN_CHANGE_5M = 25.0   
MIN_BUYS_5M = 80             

# تنظیمات اختصاصی بخش گزینه طلایی (موشک 🚀)
GOLDEN_BUY_AMOUNT_SOL = 0.005
GOLDEN_TAKE_PROFIT = 25.0
GOLDEN_STOP_LOSS = -5.0
GOLDEN_MIN_LIQUIDITY = 80000
GOLDEN_MIN_VOLUME_5M = 70000
GOLDEN_MIN_CHANGE_5M = 20.0
GOLDEN_MIN_BUYS_5M = 80

AWAITING_STATE = None 
processed_tokens = set()
trend_alerted_tokens = set()
golden_processed_tokens = set()
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

    current_sol = get_sol_balance()
    if current_sol < (amount_sol + 0.002):
        return False, f"موجودی سولانا ناکافی ({current_sol:.4f} SOL). حداقل {amount_sol + 0.002} نیاز است."

    lamports = int(amount_sol * 1_000_000_000)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Origin": "https://jup.ag",
        "Referer": "https://jup.ag/"
    }

    quote_url = f"https://api.jup.ag/swap/v1/quote?inputMint={SOL_MINT}&outputMint={token_mint}&amount={lamports}&slippageBps=500"
    
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
        err_msg = quote_res.get("error", "خطای نامشخص") if quote_res else "خطای ارتباط با صرافی"
        return False, f"خطای کوت: {err_msg}"

    swap_payload = {
        "quoteResponse": quote_res,
        "userPublicKey": WALLET_PUBKEY,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": "auto"
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
            "params": [serialized_tx, {"encoding": "base58", "skipPreflight": True, "maxRetries": 3}]
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

    quote_url = f"https://api.jup.ag/swap/v1/quote?inputMint={token_mint}&outputMint={SOL_MINT}&amount={token_amount}&slippageBps=500"
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
        return False, "خطای دریافت قیمت فروش از صرافی"

    swap_payload = {
        "quoteResponse": quote_res,
        "userPublicKey": WALLET_PUBKEY,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": "auto"
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
            "params": [serialized_tx, {"encoding": "base58", "skipPreflight": True, "maxRetries": 3}]
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

def golden_engine_loop(app):
    global GOLDEN_OPTION, GOLDEN_BUY_AMOUNT_SOL, GOLDEN_TAKE_PROFIT, GOLDEN_STOP_LOSS, GOLDEN_MIN_LIQUIDITY, GOLDEN_MIN_VOLUME_5M, GOLDEN_MIN_CHANGE_5M, GOLDEN_MIN_BUYS_5M
    while True:
        if not GOLDEN_OPTION:
            time.sleep(3)
            continue
        try:
            tokens = get_real_market_trending_tokens()
            for token_addr in tokens[:30]:
                if not GOLDEN_OPTION:
                    break
                if not token_addr or token_addr in golden_processed_tokens or token_addr in active_positions:
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
                symbol = pair.get('baseToken', {}).get('symbol', 'GOLD')

                if (price_change_5m >= GOLDEN_MIN_CHANGE_5M and 
                    buys_5m >= GOLDEN_MIN_BUYS_5M and 
                    volume_5m >= GOLDEN_MIN_VOLUME_5M and 
                    liquidity >= GOLDEN_MIN_LIQUIDITY and 
                    price > 0 and 
                    is_token_safe(token_addr, strict=True)):
                    
                    golden_processed_tokens.add(token_addr)
                    print(f"🚀 [گزینه طلایی] خرید واقعی توکن {symbol}...")
                    
                    success, result_info = execute_real_buy(token_addr, GOLDEN_BUY_AMOUNT_SOL)
                    buy_status_str = "انجام شد (موفق روی بلاکچین ✅)" if success else f"خطا ({result_info} ❌)"
                    solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

                    target_tp = price * (1 + (GOLDEN_TAKE_PROFIT / 100))
                    target_sl = price * (1 + (GOLDEN_STOP_LOSS / 100))

                    golden_msg = (
                        f"🚀🔥 خرید گزینه طلایی (موتور موشکی / دقت بالا)\n"
                        f"📌 وضعیت خرید: {buy_status_str}\n\n"
                        f"🪙 توکن: {symbol}\n"
                        f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                        f"💵 نقطه ورود: ${price:.8f}\n"
                        f"💰 مقدار: SOL {GOLDEN_BUY_AMOUNT_SOL}\n"
                        f"🎯 تارگت سود (+{GOLDEN_TAKE_PROFIT}%): ${target_tp:.8f}\n"
                        f"🛑 حد ضرر ({GOLDEN_STOP_LOSS}%): ${target_sl:.8f}\n\n"
                        f"📊 آمار بازار:\n"
                        f"🔹 رشد ۵ دقیقه: +{price_change_5m:.2f}%\n"
                        f"🔹 حجم: ${volume_5m:,.0f} | نقدینگی: ${liquidity:,.0f}\n\n"
                        f"🔗 لینک‌ها:\n"
                        f"🔍 Solscan\n{solscan_link}\n"
                        f"📈 DexScreener\nhttps://dexscreener.com/solana/{token_addr}"
                    )
                    if success:
                        active_positions[token_addr] = {
                            "entry_price": price,
                            "symbol": symbol,
                            "tp": GOLDEN_TAKE_PROFIT,
                            "sl": GOLDEN_STOP_LOSS
                        }
                    send_telegram_msg(golden_msg)
        except Exception as e:
            print(f"⚠️ خطای موتور گزینه طلایی: {e}")
        time.sleep(5)

def trend_alert_scanner_loop(app):
    global TREND_ALERT_RUNNING, COMBO_RUNNING, TREND_TAKE_PROFIT, TREND_STOP_LOSS, TREND_MIN_VOLUME_5M, MIN_BUYS_5M, GOLDEN_OPTION, ALERT_BUY_AMOUNT_SOL, TREND_MIN_LIQUIDITY
    while True:
        if GOLDEN_OPTION:
            time.sleep(2)
            continue

        if not TREND_ALERT_RUNNING and not COMBO_RUNNING:
            time.sleep(2)
            continue
        try:
            tokens = get_real_market_trending_tokens()
            for token_addr in tokens[:30]:
                if GOLDEN_OPTION or (not TREND_ALERT_RUNNING and not COMBO_RUNNING):
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
                    liquidity >= TREND_MIN_LIQUIDITY and
                    price > 0 and 
                    is_token_safe(token_addr)):
                    
                    trend_alerted_tokens.add(token_addr)
                    
                    if TREND_ALERT_RUNNING:
                        alert_msg = (
                            f"🚨 اعلان ترند بازار (هشدار آژیر) 🚀\n\n"
                            f"🪙 نام توکن: {symbol}\n"
                            f"📍 آدرس قرارداد (کپی با یک کلیک):\n{token_addr}\n\n"
                            f"💵 قیمت لحظه‌ای: ${price:.8f}\n"
                            f"📈 پامپ رشد ۵ دقیقه: +{price_change_5m:.2f}%\n"
                            f"📊 حجم معاملاتی ۵ دقیقه: ${volume_5m:,.0f}\n"
                            f"💧 نقدینگی: ${liquidity:,.0f}\n\n"
                            f"🔗 https://dexscreener.com/solana/{token_addr}"
                        )
                        send_telegram_msg(alert_msg)

                    if COMBO_RUNNING and not GOLDEN_OPTION and token_addr not in active_positions:
                        print(f"⏳ [حالت ترکیبی] خرید توکن ترند {symbol}...")
                        success, result_info = execute_real_buy(token_addr, ALERT_BUY_AMOUNT_SOL)
                        
                        buy_status_str = "انجام شد (موفق روی بلاکچین ✅)" if success else f"خطا ({result_info} ❌)"
                        solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

                        target_tp = price * (1 + (TREND_TAKE_PROFIT / 100))
                        target_sl = price * (1 + (TREND_STOP_LOSS / 100))

                        combo_msg = (
                            f"🚨 خرید ترکیبی ترند (سود {TREND_TAKE_PROFIT}% / ضرر {TREND_STOP_LOSS}%)\n"
                            f"📌 وضعیت خرید: {buy_status_str}\n\n"
                            f"🪙 توکن: {symbol}\n"
                            f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                            f"💵 نقطه ورود دقیق: ${price:.8f}\n"
                            f"💰 مقدار خرید: SOL {ALERT_BUY_AMOUNT_SOL}\n"
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
    global IS_RUNNING, FIRE_BUY_AMOUNT_SOL, FIRE_TAKE_PROFIT, FIRE_STOP_LOSS, FIRE_MIN_LIQUIDITY, FIRE_MIN_VOLUME_5M, FIRE_MIN_PRICE_CHANGE_5M, GOLDEN_OPTION
    send_telegram_msg("🔥 خرید و فروش خودکار مستقل فعال شد.")

    while True:
        if GOLDEN_OPTION:
            time.sleep(1)
            continue

        if not IS_RUNNING:
            time.sleep(1)
            continue

        try:
            solana_tokens = get_real_market_trending_tokens()

            for token_addr in solana_tokens[:30]:
                if GOLDEN_OPTION or not IS_RUNNING:
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

                if (liquidity >= FIRE_MIN_LIQUIDITY and 
                    volume_5m >= FIRE_MIN_VOLUME_5M and 
                    price_change_5m >= FIRE_MIN_PRICE_CHANGE_5M and 
                    price > 0 and
                    is_token_safe(token_addr)):
                    
                    processed_tokens.add(token_addr)
                    
                    print(f"⏳ خرید سیگنال معمولی {symbol}...")
                    success, result_info = execute_real_buy(token_addr, FIRE_BUY_AMOUNT_SOL)
                    
                    buy_status_str = "انجام شد (موفق روی بلاکچین ✅)" if success else f"خطا ({result_info} ❌)"
                    solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

                    target_tp = price * (1 + (FIRE_TAKE_PROFIT / 100))
                    target_sl = price * (1 + (FIRE_STOP_LOSS / 100))

                    msg = (
                        f"🔥 سیگنال خرید خودکار (سود {FIRE_TAKE_PROFIT}% / ضرر {FIRE_STOP_LOSS}%)\n"
                        f"📌 وضعیت خرید: {buy_status_str}\n\n"
                        f"🪙 توکن: {symbol}\n"
                        f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                        f"💵 نقطه ورود دقیق: ${price:.8f}\n"
                        f"💰 مقدار خرید: SOL {FIRE_BUY_AMOUNT_SOL}\n"
                        f"🎯 تارگت سود (+{FIRE_TAKE_PROFIT}%): ${target_tp:.8f}\n"
                        f"🛑 حد ضرر ({FIRE_STOP_LOSS}%): ${target_sl:.8f}\n\n"
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
                            "tp": FIRE_TAKE_PROFIT,
                            "sl": FIRE_STOP_LOSS
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
    golden_status = "🚀 گزینه طلایی: روشن" if GOLDEN_OPTION else "⭐ گزینه طلایی: خاموش"
    combo_status = "🚨 حالت ترکیبی: روشن" if COMBO_RUNNING else "🔴 حالت ترکیبی: خاموش"
    trader_status = "🔥 خرید و فروش: روشن" if IS_RUNNING else "🔴 خرید و فروش: خاموش"
    trend_status = "🚨 اعلان ترند: روشن" if TREND_ALERT_RUNNING else "🔴 اعلان ترند: خاموش"
    
    # تفکیک دقیق مقادیر هر بخش برای نمایش روی دکمه‌های مجزای خودشون
    vol_display = (
        GOLDEN_BUY_AMOUNT_SOL if GOLDEN_OPTION else 
        (ALERT_BUY_AMOUNT_SOL if (COMBO_RUNNING or TREND_ALERT_RUNNING) else FIRE_BUY_AMOUNT_SOL)
    )

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(golden_status, callback_data="toggle_golden")],
        [InlineKeyboardButton(combo_status, callback_data="toggle_combo")],
        [InlineKeyboardButton(trader_status, callback_data="toggle_trader"),
         InlineKeyboardButton(trend_status, callback_data="toggle_trend")],
        [InlineKeyboardButton("📊 وضعیت سیستم", callback_data="status"),
         InlineKeyboardButton("💰 موجودی ولت", callback_data="wallet_balance")],
        
        # حجم کلی معامله فعال
        [InlineKeyboardButton(f"⚙️ حجم معامله: {vol_display} SOL", callback_data="menu_volume")],
        
        # دکمه‌های بالایی مختص خرید و فروش (🔥)
        [InlineKeyboardButton(f"🔥 [سیگنال] تارگت: +{FIRE_TAKE_PROFIT}%", callback_data="menu_tp"),
         InlineKeyboardButton(f"🔥 [سیگنال] ضرر: {FIRE_STOP_LOSS}%", callback_data="menu_sl")],
        [InlineKeyboardButton(f"🔥 نقدینگی: ${FIRE_MIN_LIQUIDITY}", callback_data="menu_liq"),
         InlineKeyboardButton(f"🔥 حجم ۵دقیقه: ${FIRE_MIN_VOLUME_5M}", callback_data="menu_vol5m")],
        [InlineKeyboardButton(f"🔥 رشد ۵دقیقه: +{FIRE_MIN_PRICE_CHANGE_5M}%", callback_data="menu_chg5m")],
        
        # دکمه‌های پایینی مختص ترند و ترکیبی (🚨)
        [InlineKeyboardButton(f"🚨 [ترند] سود: +{TREND_TAKE_PROFIT}%", callback_data="menu_trend_tp"),
         InlineKeyboardButton(f"🚨 [ترند] ضرر: {TREND_STOP_LOSS}%", callback_data="menu_trend_sl")]
    ])

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID):
        return
    global AWAITING_STATE
    AWAITING_STATE = None
    await update.message.reply_text("🤖 اتاق کنترل ربات هوشمند سولانا:", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global IS_RUNNING, TREND_ALERT_RUNNING, COMBO_RUNNING, GOLDEN_OPTION, AWAITING_STATE
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    if query.data == "toggle_golden":
        GOLDEN_OPTION = not GOLDEN_OPTION
        state_txt = "🚀 گزینه طلایی (موتور موشکی پر سرعت) روشن شد." if GOLDEN_OPTION else "⭐ گزینه طلایی خاموش شد."
        try:
            await query.edit_message_text(state_txt, reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg(state_txt)

    elif query.data == "toggle_combo":
        COMBO_RUNNING = not COMBO_RUNNING
        state_txt = "🚨 حالت ترکیبی (آژیر ترند) روشن شد." if COMBO_RUNNING else "🔴 حالت ترکیبی خاموش شد."
        try:
            await query.edit_message_text(state_txt, reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg(state_txt)

    elif query.data == "toggle_trader":
        IS_RUNNING = not IS_RUNNING
        state_txt = "🔥 خرید و فروش خودکار (حالت آتشین) روشن شد." if IS_RUNNING else "🔴 خرید و فروش خودکار خاموش شد."
        try:
            await query.edit_message_text(state_txt, reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg(state_txt)
            
    elif query.data == "toggle_trend":
        TREND_ALERT_RUNNING = not TREND_ALERT_RUNNING
        state_txt = "🚨 اعلان ترند (سیستم آژیر) روشن شد." if TREND_ALERT_RUNNING else "🔴 اعلان ترند خاموش شد."
        try:
            await query.edit_message_text(state_txt, reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg(state_txt)
            
    elif query.data == "status":
        pub_display = f"{WALLET_PUBKEY[:6]}...{WALLET_PUBKEY[-4:]}" if WALLET_PUBKEY else "تنظیم نشده"
        current_sol_bal = get_sol_balance()
        status_text = (
            f"📊 وضعیت کامل سیستم:\n\n"
            f"🚀 گزینه طلایی: {'🟢 روشن' if GOLDEN_OPTION else '🔴 خاموش'} (حجم: {GOLDEN_BUY_AMOUNT_SOL} SOL | سود: +{GOLDEN_TAKE_PROFIT}%)\n"
            f"🚨 حالت ترکیبی / ترند: {'🟢 روشن' if (COMBO_RUNNING or TREND_ALERT_RUNNING) else '🔴 خاموش'} (حجم: {ALERT_BUY_AMOUNT_SOL} SOL | سود: +{TREND_TAKE_PROFIT}%)\n"
            f"🔥 خرید و فروش: {'🟢 روشن' if IS_RUNNING else '🔴 خاموش'} (حجم: {FIRE_BUY_AMOUNT_SOL} SOL | سود: +{FIRE_TAKE_PROFIT}%)\n"
            f"💰 موجودی ولت: {current_sol_bal:.4f} SOL\n"
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
        if GOLDEN_OPTION:
            AWAITING_STATE = "golden_volume"
            cur_val = GOLDEN_BUY_AMOUNT_SOL
            prefix = "🚀 [گزینه طلایی]"
        elif COMBO_RUNNING or TREND_ALERT_RUNNING:
            AWAITING_STATE = "trend_volume"
            cur_val = ALERT_BUY_AMOUNT_SOL
            prefix = "🚨 [ترند/ترکیبی]"
        else:
            AWAITING_STATE = "fire_volume"
            cur_val = FIRE_BUY_AMOUNT_SOL
            prefix = "🔥 [خرید و فروش]"
            
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"{prefix} حجم فعلی: {cur_val} SOL\nلطفاً حجم جدید را تایپ کنید:", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("لطفاً حجم جدید را تایپ کنید:")

    elif query.data == "menu_tp":
        AWAITING_STATE = "fire_tp"
        cur_val = FIRE_TAKE_PROFIT
        prefix = "🔥 [خرید و فروش]"

        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"{prefix} تارگت سود فعلی: +{cur_val}%\nلطفاً مقدار جدید را تایپ کنید:", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("لطفاً مقدار جدید را تایپ کنید:")

    elif query.data == "menu_sl":
        AWAITING_STATE = "fire_sl"
        cur_val = FIRE_STOP_LOSS
        prefix = "🔥 [خرید و فروش]"

        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"{prefix} حد ضرر فعلی: {cur_val}%\nلطفاً مقدار جدید را تایپ کنید (مثلاً 12-):", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("لطفاً مقدار جدید را تایپ کنید:")

    elif query.data == "menu_liq":
        AWAITING_STATE = "fire_liq"
        cur_val = FIRE_MIN_LIQUIDITY
        prefix = "🔥 [خرید و فروش]"

        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"{prefix} نقدینگی فعلی: ${cur_val}\nلطفاً مقدار جدید را تایپ کنید:", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("لطفاً مقدار جدید را تایپ کنید:")

    elif query.data == "menu_vol5m":
        AWAITING_STATE = "fire_vol5m"
        cur_val = FIRE_MIN_VOLUME_5M
        prefix = "🔥 [خرید و فروش]"

        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"{prefix} حجم ۵ دقیقه فعلی: ${cur_val}\nلطفاً مقدار جدید را تایپ کنید:", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("لطفاً مقدار جدید را تایپ کنید:")

    elif query.data == "menu_chg5m":
        AWAITING_STATE = "fire_chg5m"
        cur_val = FIRE_MIN_PRICE_CHANGE_5M
        prefix = "🔥 [خرید و فروش]"

        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"{prefix} رشد ۵ دقیقه فعلی: +{cur_val}%\nلطفاً مقدار جدید را تایپ کنید:", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("لطفاً مقدار جدید را تایپ کنید:")

    elif query.data == "menu_trend_tp":
        AWAITING_STATE = "trend_tp_val"
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"🚨 [ترند] سود فعلی: +{TREND_TAKE_PROFIT}%\nلطفاً مقدار جدید را تایپ کنید:", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("لطفاً مقدار جدید را تایپ کنید:")

    elif query.data == "menu_trend_sl":
        AWAITING_STATE = "trend_sl_val"
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"🚨 [ترند] ضرر فعلی: {TREND_STOP_LOSS}%\nلطفاً مقدار جدید را تایپ کنید (مثلاً 5-):", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("لطفاً مقدار جدید را تایپ کنید:")
            
    elif query.data == "cancel_input":
        AWAITING_STATE = None
        try:
            await query.edit_message_text("🤖 لغو شد.", reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg("لغو شد.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global FIRE_BUY_AMOUNT_SOL, FIRE_TAKE_PROFIT, FIRE_STOP_LOSS, FIRE_MIN_LIQUIDITY, FIRE_MIN_VOLUME_5M, FIRE_MIN_PRICE_CHANGE_5M
    global ALERT_BUY_AMOUNT_SOL, TREND_TAKE_PROFIT, TREND_STOP_LOSS, TREND_MIN_LIQUIDITY, TREND_MIN_VOLUME_5M, TREND_MIN_CHANGE_5M
    global GOLDEN_BUY_AMOUNT_SOL, GOLDEN_TAKE_PROFIT, GOLDEN_STOP_LOSS, GOLDEN_MIN_LIQUIDITY, GOLDEN_MIN_VOLUME_5M, GOLDEN_MIN_CHANGE_5M
    global AWAITING_STATE
    
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID):
        return

    if AWAITING_STATE:
        text_input = update.message.text.strip().replace(',', '.')
        try:
            val = float(text_input)
            
            if AWAITING_STATE == "fire_volume":
                if val <= 0: raise ValueError()
                FIRE_BUY_AMOUNT_SOL = val
                msg = f"🔥 حجم بخش خرید و فروش به {FIRE_BUY_AMOUNT_SOL} SOL تغییر یافت."
            elif AWAITING_STATE == "fire_tp":
                if val <= 0: raise ValueError()
                FIRE_TAKE_PROFIT = val
                msg = f"🔥 تارگت سود بخش خرید و فروش به +{FIRE_TAKE_PROFIT}% تغییر یافت."
            elif AWAITING_STATE == "fire_sl":
                FIRE_STOP_LOSS = val
                msg = f"🔥 حد ضرر بخش خرید و فروش به {FIRE_STOP_LOSS}% تغییر یافت."
            elif AWAITING_STATE == "fire_liq":
                if val < 0: raise ValueError()
                FIRE_MIN_LIQUIDITY = val
                msg = f"🔥 نقدینگی بخش خرید و فروش به ${FIRE_MIN_LIQUIDITY} تغییر یافت."
            elif AWAITING_STATE == "fire_vol5m":
                if val < 0: raise ValueError()
                FIRE_MIN_VOLUME_5M = val
                msg = f"🔥 حجم ۵ دقیقه بخش خرید و فروش به ${FIRE_MIN_VOLUME_5M} تغییر یافت."
            elif AWAITING_STATE == "fire_chg5m":
                FIRE_MIN_PRICE_CHANGE_5M = val
                msg = f"🔥 رشد ۵ دقیقه بخش خرید و فروش به +{FIRE_MIN_PRICE_CHANGE_5M}% تغییر یافت."

            elif AWAITING_STATE == "trend_volume":
                if val <= 0: raise ValueError()
                ALERT_BUY_AMOUNT_SOL = val
                msg = f"🚨 حجم بخش ترند/ترکیبی به {ALERT_BUY_AMOUNT_SOL} SOL تغییر یافت."
            elif AWAITING_STATE == "trend_tp_val":
                if val <= 0: raise ValueError()
                TREND_TAKE_PROFIT = val
                msg = f"🚨 سود ترند/ترکیبی به +{TREND_TAKE_PROFIT}% تغییر یافت."
            elif AWAITING_STATE == "trend_sl_val":
                TREND_STOP_LOSS = val
                msg = f"🚨 ضرر ترند/ترکیبی به {TREND_STOP_LOSS}% تغییر یافت."
            elif AWAITING_STATE == "trend_liq":
                if val < 0: raise ValueError()
                TREND_MIN_LIQUIDITY = val
                msg = f"🚨 نقدینگی ترند/ترکیبی به ${TREND_MIN_LIQUIDITY} تغییر یافت."
            elif AWAITING_STATE == "trend_vol5m":
                if val < 0: raise ValueError()
                TREND_MIN_VOLUME_5M = val
                msg = f"🚨 حجم ۵ دقیقه ترند/ترکیبی به ${TREND_MIN_VOLUME_5M} تغییر یافت."
            elif AWAITING_STATE == "trend_chg5m":
                TREND_MIN_CHANGE_5M = val
                msg = f"🚨 رشد ۵ دقیقه ترند/ترکیبی به +{TREND_MIN_CHANGE_5M}% تغییر یافت."

            elif AWAITING_STATE == "golden_volume":
                if val <= 0: raise ValueError()
                GOLDEN_BUY_AMOUNT_SOL = val
                msg = f"🚀 حجم گزینه طلایی به {GOLDEN_BUY_AMOUNT_SOL} SOL تغییر یافت."
            elif AWAITING_STATE == "golden_tp":
                if val <= 0: raise ValueError()
                GOLDEN_TAKE_PROFIT = val
                msg = f"🚀 تارگت گزینه طلایی به +{GOLDEN_TAKE_PROFIT}% تغییر یافت."
            elif AWAITING_STATE == "golden_sl":
                GOLDEN_STOP_LOSS = val
                msg = f"🚀 حد ضرر گزینه طلایی به {GOLDEN_STOP_LOSS}% تغییر یافت."
            elif AWAITING_STATE == "golden_liq":
                if val < 0: raise ValueError()
                GOLDEN_MIN_LIQUIDITY = val
                msg = f"🚀 نقدینگی گزینه طلایی به ${GOLDEN_MIN_LIQUIDITY} تغییر یافت."
            elif AWAITING_STATE == "golden_vol5m":
                if val < 0: raise ValueError()
                GOLDEN_MIN_VOLUME_5M = val
                msg = f"🚀 حجم ۵ دقیقه گزینه طلایی به ${GOLDEN_MIN_VOLUME_5M} تغییر یافت."
            elif AWAITING_STATE == "golden_chg5m":
                GOLDEN_MIN_CHANGE_5M = val
                msg = f"🚀 رشد ۵ دقیقه گزینه طلایی به +{GOLDEN_MIN_CHANGE_5M}% تغییر یافت."
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

    golden_thread = Thread(target=golden_engine_loop, args=(app,))
    golden_thread.daemon = True
    golden_thread.start()

    pos_thread = Thread(target=check_positions_loop)
    pos_thread.daemon = True
    pos_thread.start()

    print("🚀 ربات هوشمند سولانا استارت شد.")
    app.run_polling()
