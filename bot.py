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
from solders.transaction import VersionedTransaction

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "TOKEN_YOW")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "CHAT_ID_YOW")
PRIVATE_KEY_BASE58 = os.environ.get("PRIVATE_KEY_BASE58", "YOUR_PRIVATE_KEY")

RPC_URL = "https://mainnet.helius-rpc.com/?api-key=ef769dc4-03dc-4f1d-ba4a-a651d75f6b80"
SOL_MINT = "So11111111111111111111111111111111111111112"

IS_RUNNING = False
BUY_AMOUNT_SOL = 0.005
TAKE_PROFIT = 30.0
STOP_LOSS = -12.0
MIN_LIQUIDITY = 3000
MIN_VOLUME_5M = 1000

AWAITING_VOLUME = False
processed_tokens = set()
active_positions = {}

def send_telegram_msg(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": True
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

def get_token_balance(token_mint):
    """گرفتن موجودی دقیق توکن در ولت شخصی برای فروش کامل"""
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
        res = requests.post(RPC_URL, json=payload, timeout=10).json()
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

def execute_real_buy(token_mint, amount_sol):
    if not WALLET_PUBKEY:
        return False, "کلید عمومی ولت نامعتبر است"

    lamports = int(amount_sol * 1_000_000_000)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://jup.ag",
        "Referer": "https://jup.ag/"
    }

    quote_url = f"https://api.jup.ag/swap/v1/quote?inputMint={SOL_MINT}&outputMint={token_mint}&amount={lamports}&slippageBps=300"
    
    quote_res = None
    for attempt in range(3):
        try:
            res = requests.get(quote_url, headers=headers, timeout=10)
            if res.status_code == 200:
                quote_res = res.json()
                break
        except Exception:
            pass
        time.sleep(1)

    if not quote_res or "error" in quote_res:
        return False, "خطای دریافت قیمت از صرافی"

    swap_payload = {
        "quoteResponse": quote_res,
        "userPublicKey": WALLET_PUBKEY,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True
    }
    
    swap_res = None
    for attempt in range(3):
        try:
            res = requests.post("https://api.jup.ag/swap/v1/swap", json=swap_payload, headers=headers, timeout=10)
            if res.status_code == 200:
                swap_res = res.json()
                break
        except Exception:
            pass
        time.sleep(1)

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
        
        tx_res = requests.post(RPC_URL, json=rpc_payload, timeout=15).json()
        
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Origin": "https://jup.ag",
        "Referer": "https://jup.ag/"
    }

    quote_url = f"https://api.jup.ag/swap/v1/quote?inputMint={token_mint}&outputMint={SOL_MINT}&amount={token_amount}&slippageBps=300"
    
    quote_res = None
    for attempt in range(3):
        try:
            res = requests.get(quote_url, headers=headers, timeout=10)
            if res.status_code == 200:
                quote_res = res.json()
                break
        except Exception:
            pass
        time.sleep(1)

    if not quote_res or "error" in quote_res:
        return False, "خطای دریافت قیمت فروش از صرافی"

    swap_payload = {
        "quoteResponse": quote_res,
        "userPublicKey": WALLET_PUBKEY,
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True
    }
    
    swap_res = None
    for attempt in range(3):
        try:
            res = requests.post("https://api.jup.ag/swap/v1/swap", json=swap_payload, headers=headers, timeout=10)
            if res.status_code == 200:
                swap_res = res.json()
                break
        except Exception:
            pass
        time.sleep(1)

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
        
        tx_res = requests.post(RPC_URL, json=rpc_payload, timeout=15).json()
        
        if "result" in tx_res:
            return True, tx_res["result"]
        else:
            err_details = tx_res.get('error', {}).get('message', 'ریجکت توسط شبکه')
            return False, f"{err_details}"
    except Exception as e:
        return False, f"خطای امضا در فروش: {str(e)}"

def auto_trader_loop(app):
    global IS_RUNNING, BUY_AMOUNT_SOL, TAKE_PROFIT, STOP_LOSS, MIN_LIQUIDITY, MIN_VOLUME_5M
    
    send_telegram_msg("🤖 ربات تریدر واقعی و مانیتورینگ بازار روشن شد و آماده به کار است.")

    while True:
        if not IS_RUNNING:
            time.sleep(3)
            continue

        try:
            tokens_to_close = []
            for token_addr, pos in list(active_positions.items()):
                try:
                    pair_res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=6).json()
                    if not pair_res.get('pairs'):
                        continue
                    pair = pair_res['pairs'][0]
                    current_price = float(pair.get('priceUsd', 0))
                    entry_price = pos['entry_price']
                    symbol = pos['symbol']
                    
                    if entry_price > 0:
                        pnl_percent = ((current_price - entry_price) / entry_price) * 100

                        if pnl_percent >= TAKE_PROFIT or pnl_percent <= STOP_LOSS:
                            reason = "حد سود (TP) فعال شد 🎯" if pnl_percent >= 0 else "حد ضرر (SL) فعال شد 🛑"
                            
                            token_balance = get_token_balance(token_addr)
                            if token_balance > 0:
                                success, sell_res_info = execute_real_sell(token_addr, token_balance)
                            else:
                                success, sell_res_info = False, "موجودی توکن در ولت یافت نشد"

                            sell_status_str = f"انجام شد (موفق ✅ - {sell_res_info})" if success else f"خطا ({sell_res_info} ❌)"
                            
                            exit_msg = (
                                f"🔴 فروش خودکار ({reason})\n\n"
                                f"🪙 توکن: {symbol}\n"
                                f"📌 وضعیت فروش: {sell_status_str}\n"
                                f"📍 آدرس:\n{token_addr}\n\n"
                                f"📉 قیمت خروج: ${current_price:.8f}\n"
                                f"📊 سود/زیان نهایی: {pnl_percent:+.2f}%\n\n"
                                f"🔗 لینک‌های اختصاصی توکن:\n"
                                f"🔍 تراکنش در Solscan\nhttps://solscan.io/tx/{sell_res_info if success else 'failed'}\n"
                                f"📈 DexScreener\nhttps://dexscreener.com/solana/{token_addr}\n"
                                f"⚡ Photon\nhttps://photon-sol.today/token/{token_addr}"
                            )
                            send_telegram_msg(exit_msg)
                            tokens_to_close.append(token_addr)
                except Exception as inner_e:
                    print(f"⚠️ خطا در بررسی پوزیشن {token_addr}: {inner_e}")

            for t_addr in tokens_to_close:
                active_positions.pop(t_addr, None)

            url_trending = "https://api.dexscreener.com/token-boosts/top/v1"
            res = requests.get(url_trending, timeout=8).json()
            
            solana_tokens = []
            if isinstance(res, list):
                solana_tokens = [item for item in res if item.get('chainId') == 'solana']

            for t in solana_tokens[:6]:
                if not IS_RUNNING:
                    break

                token_addr = t.get('tokenAddress')
                if not token_addr or token_addr in processed_tokens or token_addr in active_positions:
                    continue

                pair_res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=6).json()
                if not pair_res.get('pairs'):
                    continue

                pair = pair_res['pairs'][0]
                price = float(pair.get('priceUsd', 0))
                liquidity = float(pair.get('liquidity', {}).get('usd', 0))
                volume_5m = float(pair.get('volume', {}).get('m5', 0))
                price_change_5m = float(pair.get('priceChange', {}).get('m5', 0))
                symbol = pair.get('baseToken', {}).get('symbol', 'TOKEN')

                if liquidity >= MIN_LIQUIDITY and volume_5m >= MIN_VOLUME_5M and price > 0:
                    processed_tokens.add(token_addr)
                    
                    print(f"⏳ اقدام برای خرید واقعی توکن {symbol} با حجم {BUY_AMOUNT_SOL} SOL...")
                    success, result_info = execute_real_buy(token_addr, BUY_AMOUNT_SOL)
                    
                    buy_status_str = "انجام شد (موفق روی بلاکچین ✅)" if success else f"خطا ({result_info} ❌)"

                    target_tp = price * (1 + (TAKE_PROFIT / 100))
                    target_sl = price * (1 + (STOP_LOSS / 100))

                    msg = (
                        f"🚨 سیگنال جدید شناسایی و پردازش شد\n"
                        f"📌 وضعیت خرید: {buy_status_str}\n\n"
                        f"🪙 توکن: {symbol}\n"
                        f"📍 آدرس قرارداد:\n{token_addr}\n\n"
                        f"💵 نقطه ورود دقیق: ${price:.8f}\n"
                        f"💰 مقدار خرید: {BUY_AMOUNT_SOL} SOL\n"
                        f"🎯 تارگت سود (+{TAKE_PROFIT}%): ${target_tp:.8f}\n"
                        f"🛑 حد ضرر (-{STOP_LOSS}%): ${target_sl:.8f}\n\n"
                        f"📊 تحلیل و آمار لحظه‌ای بازار:\n"
                        f"🔹 روند ۵ دقیقه: {price_change_5m:+.2f}%\n"
                        f"🔹 حجم معاملاتی ۵ دقیقه: ${volume_5m:,.0f}\n"
                        f"💧 نقدینگی استخر: ${liquidity:,.0f}\n\n"
                        f"🔗 لینک‌های اختصاصی این توکن:\n"
                        f"🔍 تراکنش در Solscan\nhttps://solscan.io/tx/{result_info if success else 'failed'}\n"
                        f"📈 تحلیل در DexScreener\nhttps://dexscreener.com/solana/{token_addr}\n"
                        f"⚡ رصد حرفه‌ای در Photon\nhttps://photon-sol.today/token/{token_addr}"
                    )
                    
                    if success:
                        active_positions[token_addr] = {
                            "entry_price": price,
                            "symbol": symbol
                        }

                    send_telegram_msg(msg)
        except Exception as e:
            print(f"⚠️ خطای حلقه اصلی تریدر: {e}")

        time.sleep(8)

web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Solana Ultimate Trading Bot is running 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 روشن کردن اسکنر", callback_data="start_bot"),
         InlineKeyboardButton("🔴 خاموش کردن اسکنر", callback_data="stop_bot")],
        [InlineKeyboardButton("📊 وضعیت سیستم", callback_data="status"),
         InlineKeyboardButton(f"⚙️ حجم: {BUY_AMOUNT_SOL} SOL", callback_data="menu_volume")],
    ])

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID):
        return
    global AWAITING_VOLUME
    AWAITING_VOLUME = False
    await update.message.reply_text("🤖 اتاق کنترل مرکزی ربات تریدر سولانا\nاز دکمه‌های زیر استفاده کنید:", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global IS_RUNNING, AWAITING_VOLUME
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    if query.data == "start_bot":
        IS_RUNNING = True
        try:
            await query.edit_message_text("🟢 اسکن خودکار و خرید واقعی با موفقیت فعال شد.", reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg("🟢 اسکن خودکار و خرید واقعی با موفقیت فعال شد.")
            
    elif query.data == "stop_bot":
        IS_RUNNING = False
        try:
            await query.edit_message_text("🔴 ربات متوقف شد.", reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg("🔴 ربات متوقف شد.")
            
    elif query.data == "status":
        state = "🟢 روشن و فعال" if IS_RUNNING else "🔴 خاموش"
        pub_display = f"{WALLET_PUBKEY[:6]}...{WALLET_PUBKEY[-4:]}" if WALLET_PUBKEY else "تنظیم نشده"
        status_text = (
            f"📊 وضعیت فعلی سیستم:\n\n"
            f"🔹 وضعیت اسکنر: {state}\n"
            f"💰 حجم معامله: {BUY_AMOUNT_SOL} SOL\n"
            f"🎯 تارگت سود: {TAKE_PROFIT}%\n"
            f"🛑 حد ضرر: {STOP_LOSS}%\n"
            f"🔑 ولت متصل: {pub_display}"
        )
        try:
            await query.edit_message_text(status_text, reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg(status_text)
            
    elif query.data == "menu_volume":
        AWAITING_VOLUME = True
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text(f"⚙️ حجم فعلی: {BUY_AMOUNT_SOL} SOL\nلطفاً حجم خرید جدید (به سولانا) را تایپ کنید و بفرستید:", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("⚙️ لطفاً حجم خرید جدید (به سولانا) را تایپ کنید:")
            
    elif query.data == "cancel_input":
        AWAITING_VOLUME = False
        try:
            await query.edit_message_text("🤖 عملیات تنظیم حجم لغو شد.", reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg("🤖 عملیات تنظیم حجم لغو شد.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BUY_AMOUNT_SOL, AWAITING_VOLUME
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID):
        return

    if AWAITING_VOLUME:
        text_val = update.message.text.strip().replace(',', '.')
        try:
            new_volume = float(text_val)
            if new_volume <= 0:
                raise ValueError()
            BUY_AMOUNT_SOL = new_volume
            AWAITING_VOLUME = False
            await update.message.reply_text(f"✅ حجم خرید با موفقیت به {BUY_AMOUNT_SOL} SOL تغییر یافت و ثبت شد.", reply_markup=get_main_keyboard())
        except ValueError:
            await update.message.reply_text("❌ خطا! لطفاً فقط یک عدد معتبر (مثلاً 0.005) وارد کنید:")
    else:
        await update.message.reply_text("🤖 برای کنترل ربات از دکمه‌ها استفاده کنید:", reply_markup=get_main_keyboard())

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

    print("🚀 ربات نهایی با موفقیت استارت شد و آماده به‌کار است.")
    app.run_polling()
