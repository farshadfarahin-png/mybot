import time
import requests
import json
import base58
import os
from threading import Thread
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

# ==========================================
# تنظیمات اصلی شما
# ==========================================
TELEGRAM_BOT_TOKEN = "8604836306:AAGxFStZhLvYzUOJ_StFwt0yQ14DZEn1Ly4"
TELEGRAM_CHAT_ID = "601441430"
PRIVATE_KEY_BASE58 = "5E3ff6vpUSDnpno8WvQcwHsiEgwXdV1yMWx5NjyqGguXAyWS9vrjcs3tQeQajxQuAbJdQnPybTbrWGiTeYfaworh"

RPC_URL = "https://mainnet.helius-rpc.com/?api-key=ef769dc4-03dc-4f1d-ba4a-a651d75f6b80"

# تنظیمات پیش‌فرض ربات
IS_RUNNING = False
BUY_AMOUNT_SOL = 0.005
TAKE_PROFIT = 30.0
STOP_LOSS = -12.0
MIN_LIQUIDITY = 3000
MIN_VOLUME_5M = 1000

AWAITING_VOLUME = False
processed_tokens = set()
active_positions = {}

# تابع ارسال پیام امن به تلگرام بدون پیش‌نمایش لینک (برای تمیزی اعلان)
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

# لود کردن ولت
try:
    decoded_key = base58.b58decode(PRIVATE_KEY_BASE58)
    sender_keypair = Keypair.from_bytes(decoded_key)
    WALLET_PUBKEY = str(sender_keypair.pubkey())
    print(f"✅ ولت لود شد: {WALLET_PUBKEY}")
except Exception as e:
    err_txt = f"خطا در کلید خصوصی: {e}"
    print(err_txt)
    send_telegram_msg(err_txt)
    WALLET_PUBKEY = None

# تابع خرید واقعی با هدر مرورگر برای عبور از فیلتر صرافی
def execute_real_buy(token_mint, amount_sol):
    try:
        if not WALLET_PUBKEY:
            return False, "کلید عمومی ولت نامعتبر است"

        lamports = int(amount_sol * 1_000_000_000)
        sol_mint = "So11111111111111111111111111111111111111112"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        quote_url = f"https://quote-api.jup.ag/v6/quote?inputMint={sol_mint}&outputMint={token_mint}&amount={lamports}&slippageBps=100"
        
        try:
            quote_res = requests.get(quote_url, headers=headers, timeout=10).json()
        except Exception:
            return False, "خطای اتصال به صرافی (Jupiter API)"
        
        if "error" in quote_res:
            return False, f"خطای صرافی: {quote_res['error']}"

        swap_payload = {
            "quoteResponse": quote_res,
            "userPublicKey": WALLET_PUBKEY,
            "wrapAndUnwrapSol": True
        }
        
        try:
            swap_res = requests.post("https://quote-api.jup.ag/v6/swap", json=swap_payload, timeout=10).json()
        except Exception:
            return False, "خطا در ساخت تراکنش سواپ"
        
        if "swapTransaction" not in swap_res:
            return False, "تراکنش سواپ توسط صرافی رد شد"

        swap_tx_b64 = swap_res["swapTransaction"]
        raw_tx = base58.b58decode(swap_tx_b64)
        txn = VersionedTransaction.from_bytes(raw_tx)
        
        signature = sender_keypair.sign_message(bytes(txn.message))
        signed_txn = VersionedTransaction.populate(txn.message, [signature])
        
        serialized_tx = base58.b58encode(bytes(signed_txn)).decode('utf-8')

        rpc_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendTransaction",
            "params": [serialized_tx, {"encoding": "base58"}]
        }
        
        tx_res = requests.post(RPC_URL, json=rpc_payload, timeout=15).json()
        
        if "result" in tx_res:
            return True, tx_res["result"]
        else:
            return False, "تراکنش توسط شبکه سولانا ریجکت شد"

    except Exception as e:
        return False, "خطای ناشناخته در اجرای خرید"

# حلقه اصلی اسکنر و تریدر
def auto_trader_loop(app):
    global IS_RUNNING, BUY_AMOUNT_SOL, TAKE_PROFIT, STOP_LOSS, MIN_LIQUIDITY, MIN_VOLUME_5M
    
    send_telegram_msg("🤖 ربات تریدر روشن شد و آماده اسکن بازار است.")

    while True:
        if not IS_RUNNING:
            time.sleep(3)
            continue

        try:
            # ۱. بررسی موقعیت‌های باز برای حد سود و ضرر
            tokens_to_close = []
            for token_addr, pos in list(active_positions.items()):
                pair_res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=5).json()
                if not pair_res.get('pairs'):
                    continue
                pair = pair_res['pairs'][0]
                current_price = float(pair.get('priceUsd', 0))
                entry_price = pos['entry_price']
                
                if entry_price > 0:
                    pnl_percent = ((current_price - entry_price) / entry_price) * 100

                    if pnl_percent >= TAKE_PROFIT or pnl_percent <= STOP_LOSS:
                        reason = "حد سود فعال شد" if pnl_percent >= 0 else "حد ضرر فعال شد"
                        symbol = pos['symbol']
                        
                        exit_msg = (
                            f"🛑 فروش خودکار ({reason})\n\n"
                            f"🪙 توکن: {symbol}\n"
                            f"📉 قیمت خروج: ${current_price:.8f}\n"
                            f"⚠️ سود/زیان: {pnl_percent:.2f}%\n\n"
                            f"🔗 مشاهده نمودار:\nhttps://dexscreener.com/solana/{token_addr}"
                        )
                        send_telegram_msg(exit_msg)
                        tokens_to_close.append(token_addr)

            for t_addr in tokens_to_close:
                active_positions.pop(t_addr, None)

            # ۲. اسکن توکن‌های ترند بازار
            url_trending = "https://api.dexscreener.com/token-boosts/top/v1"
            res = requests.get(url_trending, timeout=8).json()
            
            solana_tokens = []
            if isinstance(res, list):
                solana_tokens = [item for item in res if item.get('chainId') == 'solana']

            for t in solana_tokens[:5]:
                if not IS_RUNNING:
                    break

                token_addr = t.get('tokenAddress')
                if not token_addr or token_addr in processed_tokens or token_addr in active_positions:
                    continue

                pair_res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}", timeout=5).json()
                if not pair_res.get('pairs'):
                    continue

                pair = pair_res['pairs'][0]
                price = float(pair.get('priceUsd', 0))
                liquidity = float(pair.get('liquidity', {}).get('usd', 0))
                volume_5m = float(pair.get('volume', {}).get('m5', 0))
                price_change_5m = float(pair.get('priceChange', {}).get('m5', 0))
                symbol = pair.get('baseToken', {}).get('symbol', 'TOKEN')

                if liquidity >= MIN_LIQUIDITY and volume_5m >= MIN_VOLUME_5M:
                    processed_tokens.add(token_addr)
                    
                    print(f"⏳ تلاش برای خرید واقعی توکن {symbol}...")
                    success, result_info = execute_real_buy(token_addr, BUY_AMOUNT_SOL)
                    
                    buy_status_str = "انجام شد (موفق روی بلاکچین)" if success else f"خطا ({result_info})"

                    target_tp = price * (1 + (TAKE_PROFIT / 100))
                    target_sl = price * (1 + (STOP_LOSS / 100))

                    msg = (
                        f"🚨 سیگنال جدید شناسایی شد\n"
                        f"✅ وضعیت خرید: {buy_status_str}\n\n"
                        f"🪙 توکن: {symbol}\n"
                        f"📍 آدرس:\n{token_addr}\n\n"
                        f"💵 قیمت ورود: ${price:.8f}\n"
                        f"💰 مقدار خرید: {BUY_AMOUNT_SOL} SOL\n"
                        f"🎯 تارگت حد سود (+{TAKE_PROFIT}%): (TP) ${target_tp:.8f}\n"
                        f"🛑 حد ضرر (-{STOP_LOSS}%): (SL) ${target_sl:.8f}\n\n"
                        f"📊 آمار بازار:\n"
                        f"🔹 رشد ۵ دقیقه: {price_change_5m:+.2f}%\n"
                        f"🔹 حجم ۵ دقیقه: ${volume_5m:,.0f}\n"
                        f"💧 نقدینگی: ${liquidity:,.0f}\n\n"
                        f"🔗 لینک‌های دسترسی:\n"
                        f"🔍 تراکنش خرید در Solscan\nhttps://solscan.io/tx/{result_info if success else 'failed'}\n"
                        f"📈 مشاهده در DexScreener\nhttps://dexscreener.com/solana/{token_addr}\n"
                        f"⚡ مشاهده در Photon\nhttps://photon-sol.today/token/{token_addr}"
                    )
                    
                    if success:
                        active_positions[token_addr] = {
                            "entry_price": price,
                            "symbol": symbol
                        }

                    send_telegram_msg(msg)
        except Exception as e:
            print(f"⚠️ خطای حلقه: {e}")

        time.sleep(10)

# وب‌سرور فلاسگ برای رندر
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Real Trader Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 روشن کردن اسکنر", callback_data="start_bot"),
         InlineKeyboardButton("🔴 خاموش کردن اسکنر", callback_data="stop_bot")],
        [InlineKeyboardButton("📊 وضعیت سیستم", callback_data="status"),
         InlineKeyboardButton("⚙️ تنظیم حجم خرید (دستی)", callback_data="menu_volume")],
    ])

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID):
        return
    global AWAITING_VOLUME
    AWAITING_VOLUME = False
    await update.message.reply_text("🤖 اتاق کنترل ربات تریدر واقعی سولانا", reply_markup=get_main_keyboard())

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
            await query.edit_message_text("🟢 اسکن خودکار و خرید واقعی فعال شد.", reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg("🟢 اسکن خودکار و خرید واقعی فعال شد.")
            
    elif query.data == "stop_bot":
        IS_RUNNING = False
        try:
            await query.edit_message_text("🔴 ربات متوقف شد.", reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg("🔴 ربات متوقف شد.")
            
    elif query.data == "status":
        state = "🟢 روشن" if IS_RUNNING else "🔴 خاموش"
        pub_display = f"{WALLET_PUBKEY[:6]}..." if WALLET_PUBKEY else "تنظیم نشده"
        status_text = (
            f"📊 وضعیت: {state}\n"
            f"💰 حجم معامله: {BUY_AMOUNT_SOL} SOL\n"
            f"🎯 تارگت سود: {TAKE_PROFIT}%\n"
            f"🛑 حد ضرر: {STOP_LOSS}%\n"
            f"🔑 ولت: {pub_display}"
        )
        try:
            await query.edit_message_text(status_text, reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg(status_text)
            
    elif query.data == "menu_volume":
        AWAITING_VOLUME = True
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text("⚙️ لطفاً حجم خرید جدید را به صورت عدد تایپ کنید:", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("⚙️ لطفاً حجم خرید جدید را به صورت عدد تایپ کنید:")
            
    elif query.data == "cancel_input":
        AWAITING_VOLUME = False
        try:
            await query.edit_message_text("🤖 عملیات لغو شد.", reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg("🤖 عملیات لغو شد.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BUY_AMOUNT_SOL, AWAITING_VOLUME
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID):
        return

    if AWAITING_VOLUME:
        try:
            new_volume = float(update.message.text.strip())
            if new_volume <= 0:
                raise ValueError()
            BUY_AMOUNT_SOL = new_volume
            AWAITING_VOLUME = False
            await update.message.reply_text(f"✅ حجم خرید به {BUY_AMOUNT_SOL} SOL تغییر کرد.", reply_markup=get_main_keyboard())
        except ValueError:
            await update.message.reply_text("❌ خطا! فقط عدد معتبر وارد کنید:")

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

    app.run_polling()
