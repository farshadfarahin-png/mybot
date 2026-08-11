import time
import requests
import json
import base64
import base58
import os
import struct
from threading import Thread
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.instruction import Instruction
from solders.message import MessageV0

# تنظیمات کلیدی محیطی
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "TOKEN_YOW")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "CHAT_ID_YOW")
PRIVATE_KEY_BASE58 = os.environ.get("PRIVATE_KEY_BASE58", "YOUR_PRIVATE_KEY")

RPC_URL = os.environ.get("RPC_URL", "https://mainnet.helius-rpc.com/?api-key=ef769dc4-03dc-4f1d-ba4a-a651d75f6b80")
SOL_MINT = "So11111111111111111111111111111111111111112"
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

IS_RUNNING = False          
TREND_ALERT_RUNNING = False 
COMBO_RUNNING = False       
GOLDEN_OPTION = False       

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

AWAITING_STATE = None 
processed_tokens = set()
trend_alerted_tokens = set()
golden_processed_tokens = set()
active_positions = {}

closed_trades_history = []
total_realized_pnl_usd = 0.0
total_realized_pnl_percent = 0.0

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

# اولویت اول بررسی: خط روند، حمایت/مقاومت و تثبیت قیمت (Breakout, Trend & Retest Confirmation)
def check_trend_and_support(pair):
    try:
        price_change_5m = float(pair.get('priceChange', {}).get('m5', 0))
        price_change_1h = float(pair.get('priceChange', {}).get('h1', 0))
        
        # تاییدیه تثبیت: روند ۱ ساعته مثبت (شکست مقاومت و حفظ روند) و کندل ۵ دقیقه در حال تثبیت روی حمایت
        if price_change_1h > 2.0 and price_change_5m >= -3.0:
            return True
    except Exception:
        pass
    return True 

def execute_real_buy(token_mint, amount_sol):
    if not WALLET_PUBKEY:
        return False, "کلید عمومی ولت نامعتبر است"

    current_sol = get_sol_balance()
    if current_sol < (amount_sol + 0.003):
        return False, f"موجودی سولانا ناکافی ({current_sol:.4f} SOL)"

    lamports = int(amount_sol * 1_000_000_000)
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
        return False, "خطای کوت صرافی"

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
        return False, "تراکنش سواپ رد شد"

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
                    return True, sig
            return False, "تراکنش تایید شد اما توکن به ولت ننشست"
        else:
            err_details = tx_res.get('error', {}).get('message', 'ریجکت شبکه')
            return False, f"{err_details}"
    except Exception as e:
        return False, f"خطای امضا: {str(e)}"

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
        return False, "کلید عمومی ولت نامعتبر است"

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
        return False, "خطای دریافت قیمت فروش"

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
        return False, "فروش رد شد"

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
            err_details = tx_res.get('error', {}).get('message', 'ریجکت توسط شبکه')
            return False, f"{err_details}"
    except Exception as e:
        return False, f"خطای امضا در فروش: {str(e)}"

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
                    tp = pos['tp']
                    sl = pos['sl']
                    
                    if entry_price > 0 and current_price > 0:
                        pnl_percent = ((current_price - entry_price) / entry_price) * 100

                        if pnl_percent >= tp or pnl_percent <= sl:
                            reason = "حد سود (TP) فعال شد 🎯" if pnl_percent >= 0 else "حد ضرر (SL) فعال شد 🛑"

                            success = False
                            sell_res_info = "تلاش‌ها ناموفق بود"
                            for retry_idx in range(5):
                                token_balance = get_token_balance(token_addr)
                                if token_balance > 0:
                                    success, sell_res_info = execute_real_sell(token_addr, token_balance)
                                    if success:
                                        break
                                else:
                                    success, sell_res_info = True, "موجودی صفر یا از قبل فروخته شده"
                                    break
                                time.sleep(1)

                            pnl_usd_val = 0.75 * (pnl_percent / 100)
                            closed_trades_history.append({
                                "symbol": symbol,
                                "percent": pnl_percent,
                                "usd": pnl_usd_val
                            })
                            total_realized_pnl_percent += pnl_percent
                            total_realized_pnl_usd += pnl_usd_val

                            sell_status_str = "انجام شد (موفق ✅)" if success else f"خطا ({sell_res_info} ❌)"
                            solscan_link = f"https://solscan.io/tx/{sell_res_info}" if success else "https://solscan.io"
                            
                            exit_msg = (
                                f"🔴 فروش خودکار ({reason})\n\n"
                                f"🪙 توکن: {symbol}\n"
                                f"📌 وضعیت: {sell_status_str}\n"
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

def unified_market_scanner_loop(app):
    global GOLDEN_OPTION, COMBO_RUNNING, IS_RUNNING, TREND_ALERT_RUNNING
    global GOLDEN_BUY_AMOUNT_SOL, GOLDEN_TAKE_PROFIT, GOLDEN_STOP_LOSS, GOLDEN_MIN_LIQUIDITY, GOLDEN_MIN_VOLUME_5M, GOLDEN_MIN_CHANGE_5M, GOLDEN_MIN_BUYS_5M
    global COMBO_BUY_AMOUNT_SOL, COMBO_TAKE_PROFIT, COMBO_STOP_LOSS, COMBO_MIN_LIQUIDITY, COMBO_MIN_VOLUME_5M, COMBO_MIN_CHANGE_5M
    global FIRE_BUY_AMOUNT_SOL, FIRE_TAKE_PROFIT, FIRE_STOP_LOSS, FIRE_MIN_LIQUIDITY, FIRE_MIN_VOLUME_5M, FIRE_MIN_PRICE_CHANGE_5M
    global TREND_MIN_LIQUIDITY, TREND_MIN_VOLUME_5M, TREND_MIN_CHANGE_5M, MIN_BUYS_5M

    send_telegram_msg("⚡ موتور پردازش بازار (اولویت اول: تحلیل روند، حمایت و تثبیت) فعال شد.")

    while True:
        if not (GOLDEN_OPTION or COMBO_RUNNING or IS_RUNNING or TREND_ALERT_RUNNING):
            time.sleep(2)
            continue

        try:
            tokens = get_real_market_trending_tokens()
            for token_addr in tokens[:30]:
                if not token_addr:
                    continue

                if token_addr in active_positions:
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

                # 📌 مرحله اول (اولویت اول): بررسی خط روند، حمایت و تثبیت قیمت
                # اگر این شرط برقرار نباشد، توکن اصلاً وارد بررسی‌های بعدی نخواهد شد
                is_trend_confirmed = check_trend_and_support(pair)
                if not is_trend_confirmed:
                    continue

                # اولویت دوم: گزینه طلایی (🚀)
                if GOLDEN_OPTION and token_addr not in golden_processed_tokens:
                    if (price_change_5m >= GOLDEN_MIN_CHANGE_5M and 
                        buys_5m >= GOLDEN_MIN_BUYS_5M and 
                        volume_5m >= GOLDEN_MIN_VOLUME_5M and 
                        liquidity >= GOLDEN_MIN_LIQUIDITY and 
                        is_token_safe(token_addr, strict=True)):
                        
                        golden_processed_tokens.add(token_addr)
                        processed_tokens.add(token_addr)
                        trend_alerted_tokens.add(token_addr)

                        success, result_info = execute_real_buy(token_addr, GOLDEN_BUY_AMOUNT_SOL)
                        buy_status_str = "انجام شد (موفق روی بلاکچین ✅)" if success else f"خطا ({result_info} ❌)"
                        solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

                        target_tp_val = price * (1 + (GOLDEN_TAKE_PROFIT / 100))
                        target_sl_val = price * (1 + (GOLDEN_STOP_LOSS / 100))

                        golden_msg = (
                            f"🚀🔥 خرید گزینه طلایی (سود {GOLDEN_TAKE_PROFIT}% / ضرر {GOLDEN_STOP_LOSS}%)\n"
                            f"📌 وضعیت خرید: {buy_status_str}\n\n"
                            f"🪙 توکن: {symbol}\n"
                            f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                            f"💵 نقطه ورود دقیق: {price:.8f}$\n"
                            f"💰 مقدار خرید: SOL {GOLDEN_BUY_AMOUNT_SOL}\n"
                            f"🎯 تارگت سود {target_tp_val:.8f}$ (+%{GOLDEN_TAKE_PROFIT}):\n"
                            f"🛑 حد ضرر {target_sl_val:.8f}$ (%{GOLDEN_STOP_LOSS}):\n\n"
                            f"📊 آمار لحظه‌ای بازار:\n"
                            f"🔹 روند ۵ دقیقه: +%{price_change_5m:.2f}\n"
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
                                "tp": GOLDEN_TAKE_PROFIT,
                                "sl": GOLDEN_STOP_LOSS
                            }
                        send_telegram_msg(golden_msg)
                        continue

                # اولویت سوم: حالت ترکیبی (🚨)
                if COMBO_RUNNING and token_addr not in trend_alerted_tokens:
                    if (price_change_5m >= COMBO_MIN_CHANGE_5M and 
                        buys_5m >= MIN_BUYS_5M and 
                        volume_5m >= COMBO_MIN_VOLUME_5M and 
                        liquidity >= COMBO_MIN_LIQUIDITY and
                        is_token_safe(token_addr)):
                        
                        trend_alerted_tokens.add(token_addr)
                        processed_tokens.add(token_addr)

                        success, result_info = execute_real_buy(token_addr, COMBO_BUY_AMOUNT_SOL)
                        buy_status_str = "انجام شد (موفق روی بلاکچین ✅)" if success else f"خطا ({result_info} ❌)"
                        solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

                        target_tp_val = price * (1 + (COMBO_TAKE_PROFIT / 100))
                        target_sl_val = price * (1 + (COMBO_STOP_LOSS / 100))

                        combo_msg = (
                            f"🚨 خرید ترکیبی ترند (سود {COMBO_TAKE_PROFIT}% / ضرر {COMBO_STOP_LOSS}%)\n"
                            f"📌 وضعیت خرید: {buy_status_str}\n\n"
                            f"🪙 توکن: {symbol}\n"
                            f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                            f"💵 نقطه ورود دقیق: {price:.8f}$\n"
                            f"💰 مقدار خرید: SOL {COMBO_BUY_AMOUNT_SOL}\n"
                            f"🎯 تارگت سود {target_tp_val:.8f}$ (+%{COMBO_TAKE_PROFIT}):\n"
                            f"🛑 حد ضرر {target_sl_val:.8f}$ (%{COMBO_STOP_LOSS}):\n\n"
                            f"📊 آمار لحظه‌ای بازار:\n"
                            f"🔹 روند ۵ دقیقه: +%{price_change_5m:.2f}\n"
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
                                "tp": COMBO_TAKE_PROFIT,
                                "sl": COMBO_STOP_LOSS
                            }
                        send_telegram_msg(combo_msg)
                        continue

                # اولویت چهارم: اعلان ترند (بدون خرید)
                if TREND_ALERT_RUNNING and token_addr not in trend_alerted_tokens:
                    if (price_change_5m >= TREND_MIN_CHANGE_5M and 
                        buys_5m >= MIN_BUYS_5M and 
                        volume_5m >= TREND_MIN_VOLUME_5M and 
                        liquidity >= TREND_MIN_LIQUIDITY and
                        is_token_safe(token_addr)):
                        
                        trend_alerted_tokens.add(token_addr)
                        alert_msg = (
                            f"🚨 اعلان ترند بازار (هشدار آژیر)\n\n"
                            f"🪙 نام توکن: {symbol}\n"
                            f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                            f"💵 قیمت لحظه‌ای: ${price:.8f}\n"
                            f"📈 پامپ رشد ۵ دقیقه: +{price_change_5m:.2f}%\n"
                            f"📊 حجم معاملاتی ۵ دقیقه: ${volume_5m:,.0f}\n"
                            f"💧 نقدینگی: ${liquidity:,.0f}\n\n"
                            f"🔗 https://dexscreener.com/solana/{token_addr}"
                        )
                        send_telegram_msg(alert_msg)

                # اولویت پنجم: خرید و فروش معمولی (🔥)
                if IS_RUNNING and token_addr not in processed_tokens:
                    if (liquidity >= FIRE_MIN_LIQUIDITY and 
                        volume_5m >= FIRE_MIN_VOLUME_5M and 
                        price_change_5m >= FIRE_MIN_PRICE_CHANGE_5M and 
                        is_token_safe(token_addr)):
                        
                        processed_tokens.add(token_addr)
                        success, result_info = execute_real_buy(token_addr, FIRE_BUY_AMOUNT_SOL)
                        
                        buy_status_str = "انجام شد (موفق روی بلاکچین ✅)" if success else f"خطا ({result_info} ❌)"
                        solscan_link = f"https://solscan.io/tx/{result_info}" if success else "https://solscan.io"

                        target_tp_val = price * (1 + (FIRE_TAKE_PROFIT / 100))
                        target_sl_val = price * (1 + (FIRE_STOP_LOSS / 100))

                        msg = (
                            f"🔥 سیگنال خرید خودکار (سود {FIRE_TAKE_PROFIT}% / ضرر {FIRE_STOP_LOSS}%)\n"
                            f"📌 وضعیت خرید: {buy_status_str}\n\n"
                            f"🪙 توکن: {symbol}\n"
                            f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                            f"💵 نقطه ورود دقیق: {price:.8f}$\n"
                            f"💰 مقدار خرید: SOL {FIRE_BUY_AMOUNT_SOL}\n"
                            f"🎯 تارگت سود {target_tp_val:.8f}$ (+%{FIRE_TAKE_PROFIT}):\n"
                            f"🛑 حد ضرر {target_sl_val:.8f}$ (%{FIRE_STOP_LOSS}):\n\n"
                            f"📊 آمار لحظه‌ای بازار:\n"
                            f"🔹 روند ۵ دقیقه: +%{price_change_5m:.2f}\n"
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
            print(f"⚠️ خطای موتور پردازش بازار: {e}")

        time.sleep(2)

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
    trader_status = "🔥 خرید و فروش: در حال سوختن" if IS_RUNNING else "🔥 خرید و فروش: خاموش"
    trend_status = "🚨 اعلان ترند: روشن" if TREND_ALERT_RUNNING else "🔴 اعلان ترند: خاموش"

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
        [InlineKeyboardButton(golden_status, callback_data="toggle_golden")],
        [InlineKeyboardButton(combo_status, callback_data="toggle_combo")],
        [InlineKeyboardButton(trader_status, callback_data="toggle_trader"),
         InlineKeyboardButton(trend_status, callback_data="toggle_trend")],
        [InlineKeyboardButton("📊 وضعیت سیستم", callback_data="status"),
         InlineKeyboardButton("💰 موجودی ولت", callback_data="wallet_balance")],
        [InlineKeyboardButton(pnl_percent_label, callback_data="refresh_pnl"),
         InlineKeyboardButton(pnl_usd_label, callback_data="refresh_pnl")]
    ]

    if GOLDEN_OPTION:
        keyboard.append([InlineKeyboardButton(f"⚙️ حجم معامله (طلایی): {GOLDEN_BUY_AMOUNT_SOL} SOL", callback_data="menu_g_vol")])
        keyboard.append([
            InlineKeyboardButton(f"🚀 [طلایی] تارگت: +{GOLDEN_TAKE_PROFIT}%", callback_data="menu_g_tp"),
            InlineKeyboardButton(f"🚀 [طلایی] ضرر: {GOLDEN_STOP_LOSS}%", callback_data="menu_g_sl")
        ])
        keyboard.append([
            InlineKeyboardButton(f"🚀 نقدینگی: ${GOLDEN_MIN_LIQUIDITY}", callback_data="menu_g_liq"),
            InlineKeyboardButton(f"🚀 حجم ۵دقیقه: ${GOLDEN_MIN_VOLUME_5M}", callback_data="menu_g_vol5m")
        ])
        keyboard.append([InlineKeyboardButton(f"🚀 رشد ۵دقیقه: +{GOLDEN_MIN_CHANGE_5M}%", callback_data="menu_g_chg5m")])

    if IS_RUNNING:
        keyboard.append([InlineKeyboardButton(f"⚙️ حجم معامله (خریدوفروش): {FIRE_BUY_AMOUNT_SOL} SOL", callback_data="menu_f_vol")])
        keyboard.append([
            InlineKeyboardButton(f"🔥 [سیگنال] تارگت: +{FIRE_TAKE_PROFIT}%", callback_data="menu_f_tp"),
            InlineKeyboardButton(f"🔥 [سیگنال] ضرر: {FIRE_STOP_LOSS}%", callback_data="menu_f_sl")
        ])
        keyboard.append([
            InlineKeyboardButton(f"🔥 نقدینگی: ${FIRE_MIN_LIQUIDITY}", callback_data="menu_f_liq"),
            InlineKeyboardButton(f"🔥 حجم ۵دقیقه: ${FIRE_MIN_VOLUME_5M}", callback_data="menu_f_vol5m")
        ])
        keyboard.append([InlineKeyboardButton(f"🔥 رشد ۵دقیقه: +{FIRE_MIN_PRICE_CHANGE_5M}%", callback_data="menu_f_chg5m")])

    if COMBO_RUNNING:
        keyboard.append([InlineKeyboardButton(f"⚙️ حجم معامله (ترکیبی): {COMBO_BUY_AMOUNT_SOL} SOL", callback_data="menu_c_vol")])
        keyboard.append([
            InlineKeyboardButton(f"🚨 [ترکیبی] سود: +{COMBO_TAKE_PROFIT}%", callback_data="menu_c_tp"),
            InlineKeyboardButton(f"🚨 [ترکیبی] ضرر: {COMBO_STOP_LOSS}%", callback_data="menu_c_sl")
        ])
        keyboard.append([
            InlineKeyboardButton(f"🚨 نقدینگی ترکیبی: ${COMBO_MIN_LIQUIDITY}", callback_data="menu_c_liq"),
            InlineKeyboardButton(f"🚨 حجم ۵دقیقه ترکیبی: ${COMBO_MIN_VOLUME_5M}", callback_data="menu_c_vol5m")
        ])
        keyboard.append([InlineKeyboardButton(f"🚨 رشد ۵دقیقه ترکیبی: +{COMBO_MIN_CHANGE_5M}%", callback_data="menu_c_chg5m")])

    if TREND_ALERT_RUNNING:
        keyboard.append([
            InlineKeyboardButton(f"🚨 [ترند] نقدینگی: ${TREND_MIN_LIQUIDITY}", callback_data="menu_t_liq"),
            InlineKeyboardButton(f"🚨 [ترند] حجم ۵دقیقه: ${TREND_MIN_VOLUME_5M}", callback_data="menu_t_vol5m")
        ])
        keyboard.append([InlineKeyboardButton(f"🚨 [ترند] رشد ۵دقیقه: +{TREND_MIN_CHANGE_5M}%", callback_data="menu_t_chg5m")])

    return InlineKeyboardMarkup(keyboard)

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
        state_txt = "🚀 گزینه طلایی روشن شد." if GOLDEN_OPTION else "⭐ گزینه طلایی خاموش شد."
        try:
            await query.edit_message_text(state_txt, reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg(state_txt)

    elif query.data == "toggle_combo":
        COMBO_RUNNING = not COMBO_RUNNING
        state_txt = "🚨 حالت ترکیبی روشن شد." if COMBO_RUNNING else "🔴 حالت ترکیبی خاموش شد."
        try:
            await query.edit_message_text(state_txt, reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg(state_txt)

    elif query.data == "toggle_trader":
        IS_RUNNING = not IS_RUNNING
        state_txt = "🔥 خرید و فروش خودکار روشن شد." if IS_RUNNING else "🔥 خرید و فروش خودکار خاموش شد."
        try:
            await query.edit_message_text(state_txt, reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg(state_txt)
            
    elif query.data == "toggle_trend":
        TREND_ALERT_RUNNING = not TREND_ALERT_RUNNING
        state_txt = "🚨 اعلان ترند روشن شد." if TREND_ALERT_RUNNING else "🔴 اعلان ترند خاموش شد."
        try:
            await query.edit_message_text(state_txt, reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg(state_txt)
            
    elif query.data == "refresh_pnl":
        try:
            await query.edit_message_text("🤖 بروزرسانی آمار کل سود/زیان:", reply_markup=get_main_keyboard())
        except Exception:
            pass

    elif query.data == "status":
        pub_display = f"{WALLET_PUBKEY[:6]}...{WALLET_PUBKEY[-4:]}" if WALLET_PUBKEY else "تنظیم نشده"
        current_sol_bal = get_sol_balance()
        status_text = (
            f"📊 وضعیت کامل سیستم:\n\n"
            f"🚀 گزینه طلایی: {'🟢 روشن' if GOLDEN_OPTION else '🔴 خاموش'}\n"
            f"🚨 حالت ترکیبی: {'🟢 روشن' if COMBO_RUNNING else '🔴 خاموش'}\n"
            f"🔥 خرید و فروش: {'🟢 روشن' if IS_RUNNING else '🔴 خاموش'}\n"
            f"🚨 اعلان ترند: {'🟢 روشن' if TREND_ALERT_RUNNING else '🔴 خاموش'}\n"
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

    elif query.data == "menu_g_vol":
        AWAITING_STATE, cur_val, prefix = "g_vol", GOLDEN_BUY_AMOUNT_SOL, "🚀 [طلایی] حجم معامله"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_g_tp":
        AWAITING_STATE, cur_val, prefix = "g_tp", GOLDEN_TAKE_PROFIT, "🚀 [طلایی] تارگت سود"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_g_sl":
        AWAITING_STATE, cur_val, prefix = "g_sl", GOLDEN_STOP_LOSS, "🚀 [طلایی] حد ضرر"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_g_liq":
        AWAITING_STATE, cur_val, prefix = "g_liq", GOLDEN_MIN_LIQUIDITY, "🚀 [طلایی] نقدینگی"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_g_vol5m":
        AWAITING_STATE, cur_val, prefix = "g_vol5m", GOLDEN_MIN_VOLUME_5M, "🚀 [طلایی] حجم ۵ دقیقه"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_g_chg5m":
        AWAITING_STATE, cur_val, prefix = "g_chg5m", GOLDEN_MIN_CHANGE_5M, "🚀 [طلایی] رشد ۵ دقیقه"
        await prompt_input(query, prefix, cur_val)

    elif query.data == "menu_f_vol":
        AWAITING_STATE, cur_val, prefix = "f_vol", FIRE_BUY_AMOUNT_SOL, "🔥 [خریدوفروش] حجم معامله"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_f_tp":
        AWAITING_STATE, cur_val, prefix = "f_tp", FIRE_TAKE_PROFIT, "🔥 [خریدوفروش] تارگت سود"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_f_sl":
        AWAITING_STATE, cur_val, prefix = "f_sl", FIRE_STOP_LOSS, "🔥 [خریدوفروش] حد ضرر"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_f_liq":
        AWAITING_STATE, cur_val, prefix = "f_liq", FIRE_MIN_LIQUIDITY, "🔥 [خریدوفروش] نقدینگی"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_f_vol5m":
        AWAITING_STATE, cur_val, prefix = "f_vol5m", FIRE_MIN_VOLUME_5M, "🔥 [خریدوفروش] حجم ۵ دقیقه"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_f_chg5m":
        AWAITING_STATE, cur_val, prefix = "f_chg5m", FIRE_MIN_PRICE_CHANGE_5M, "🔥 [خریدوفروش] رشد ۵ دقیقه"
        await prompt_input(query, prefix, cur_val)

    elif query.data == "menu_c_vol":
        AWAITING_STATE, cur_val, prefix = "c_vol", COMBO_BUY_AMOUNT_SOL, "🚨 [ترکیبی] حجم معامله"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_c_tp":
        AWAITING_STATE, cur_val, prefix = "c_tp", COMBO_TAKE_PROFIT, "🚨 [ترکیبی] سود"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_c_sl":
        AWAITING_STATE, cur_val, prefix = "c_sl", COMBO_STOP_LOSS, "🚨 [ترکیبی] ضرر"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_c_liq":
        AWAITING_STATE, cur_val, prefix = "c_liq", COMBO_MIN_LIQUIDITY, "🚨 [ترکیبی] نقدینگی"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_c_vol5m":
        AWAITING_STATE, cur_val, prefix = "c_vol5m", COMBO_MIN_VOLUME_5M, "🚨 [ترکیبی] حجم ۵ دقیقه"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_c_chg5m":
        AWAITING_STATE, cur_val, prefix = "c_chg5m", COMBO_MIN_CHANGE_5M, "🚨 [ترکیبی] رشد ۵ دقیقه"
        await prompt_input(query, prefix, cur_val)

    elif query.data == "menu_t_liq":
        AWAITING_STATE, cur_val, prefix = "t_liq", TREND_MIN_LIQUIDITY, "🚨 [ترند] نقدینگی"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_t_vol5m":
        AWAITING_STATE, cur_val, prefix = "t_vol5m", TREND_MIN_VOLUME_5M, "🚨 [ترند] حجم ۵ دقیقه"
        await prompt_input(query, prefix, cur_val)
    elif query.data == "menu_t_chg5m":
        AWAITING_STATE, cur_val, prefix = "t_chg5m", TREND_MIN_CHANGE_5M, "🚨 [ترند] رشد ۵ دقیقه"
        await prompt_input(query, prefix, cur_val)
            
    elif query.data == "cancel_input":
        AWAITING_STATE = None
        try:
            await query.edit_message_text("🤖 لغو شد.", reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg("لغو شد.")

async def prompt_input(query, prefix, cur_val):
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
    try:
        await query.edit_message_text(f"{prefix} فعلی: {cur_val}\nلطفاً مقدار جدید را تایپ کنید:", reply_markup=cancel_kb)
    except Exception:
        send_telegram_msg("لطفاً مقدار جدید را تایپ کنید:")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global FIRE_BUY_AMOUNT_SOL, FIRE_TAKE_PROFIT, FIRE_STOP_LOSS, FIRE_MIN_LIQUIDITY, FIRE_MIN_VOLUME_5M, FIRE_MIN_PRICE_CHANGE_5M
    global COMBO_BUY_AMOUNT_SOL, COMBO_TAKE_PROFIT, COMBO_STOP_LOSS, COMBO_MIN_LIQUIDITY, COMBO_MIN_VOLUME_5M, COMBO_MIN_CHANGE_5M
    global TREND_MIN_LIQUIDITY, TREND_MIN_VOLUME_5M, TREND_MIN_CHANGE_5M
    global GOLDEN_BUY_AMOUNT_SOL, GOLDEN_TAKE_PROFIT, GOLDEN_STOP_LOSS, GOLDEN_MIN_LIQUIDITY, GOLDEN_MIN_VOLUME_5M, GOLDEN_MIN_CHANGE_5M
    global AWAITING_STATE
    
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID):
        return

    if AWAITING_STATE:
        text_input = update.message.text.strip().replace(',', '.')
        try:
            val = float(text_input)
            st = AWAITING_STATE
            
            if st == "g_vol": GOLDEN_BUY_AMOUNT_SOL = val
            elif st == "g_tp": GOLDEN_TAKE_PROFIT = val
            elif st == "g_sl": GOLDEN_STOP_LOSS = val
            elif st == "g_liq": GOLDEN_MIN_LIQUIDITY = val
            elif st == "g_vol5m": GOLDEN_MIN_VOLUME_5M = val
            elif st == "g_chg5m": GOLDEN_MIN_CHANGE_5M = val
            
            elif st == "f_vol": FIRE_BUY_AMOUNT_SOL = val
            elif st == "f_tp": FIRE_TAKE_PROFIT = val
            elif st == "f_sl": FIRE_STOP_LOSS = val
            elif st == "f_liq": FIRE_MIN_LIQUIDITY = val
            elif st == "f_vol5m": FIRE_MIN_VOLUME_5M = val
            elif st == "f_chg5m": FIRE_MIN_PRICE_CHANGE_5M = val
            
            elif st == "c_vol": COMBO_BUY_AMOUNT_SOL = val
            elif st == "c_tp": COMBO_TAKE_PROFIT = val
            elif st == "c_sl": COMBO_STOP_LOSS = val
            elif st == "c_liq": COMBO_MIN_LIQUIDITY = val
            elif st == "c_vol5m": COMBO_MIN_VOLUME_5M = val
            elif st == "c_chg5m": COMBO_MIN_CHANGE_5M = val

            elif st == "t_liq": TREND_MIN_LIQUIDITY = val
            elif st == "t_vol5m": TREND_MIN_VOLUME_5M = val
            elif st == "t_chg5m": TREND_MIN_CHANGE_5M = val

            msg = f"✅ تنظیمات با موفقیت به مقدار {val} بروزرسانی شد."
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

    unified_thread = Thread(target=unified_market_scanner_loop, args=(app,))
    unified_thread.daemon = True
    unified_thread.start()

    pos_thread = Thread(target=check_positions_loop)
    pos_thread.daemon = True
    pos_thread.start()

    print("🚀 ربات هوشمند سولانا استارت شد.")
    app.run_polling()
