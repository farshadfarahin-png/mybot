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
from solders.pubkey import Pubkey

# ==========================================
# تنظیمات اصلی شما
# ==========================================
TELEGRAM_BOT_TOKEN = "8604836306:AAGxFStZhLvYzUOJ_StFwt0yQ14DZEn1Ly4" # توکن ربات خود را اینجا بگذارید یا از متغیر محیطی بخوانید
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

# ساخت کلید عمومی و کلید اصلی از Private Key
try:
    decoded_key = base58.b58decode(PRIVATE_KEY_BASE58)
    sender_keypair = Keypair.from_bytes(decoded_key)
    WALLET_PUBKEY = str(sender_keypair.pubkey())
except Exception as e:
    print(f"❌ خطا در پردازش کلید خصوصی: {e}")
    WALLET_PUBKEY = None

# تابع اجرای خرید واقعی (Swap) از طریق Jupiter API و ارسال تراکنش به Helius RPC
def execute_real_buy(token_mint, amount_sol):
    try:
        if not WALLET_PUBKEY:
            print("❌ کلید عمومی ولت نامعتبر است.")
            return False, "Invalid Wallet"

        lamports = int(amount_sol * 1_000_000_000)
        sol_mint = "So11111111111111111111111111111111111111112"

        # ۱. دریافت کوت (Quote) از Jupiter
        quote_url = f"https://quote-api.jup.ag/v6/quote?inputMint={sol_mint}&outputMint={token_mint}&amount={lamports}&slippageBps=100"
        quote_res = requests.get(quote_url, timeout=10).json()
        
        if "error" in quote_res:
            print(f"❌ خطای Jupiter Quote: {quote_res['error']}")
            return False, quote_res['error']

        # ۲. دریافت تراکنش Swap
        swap_payload = {
            "quoteResponse": quote_res,
            "userPublicKey": WALLET_PUBKEY,
            "wrapAndUnwrapSol": True
        }
        swap_res = requests.post("https://quote-api.jup.ag/v6/swap", json=swap_payload, timeout=10).json()
        
        if "swapTransaction" not in swap_res:
            print(f"❌ خطای دریافت تراکنش سواپ: {swap_res}")
            return False, "Swap transaction failed"

        # ۳. امضا و ارسال تراکنش روی شبکه با استفاده از RPC شما
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
            tx_signature = tx_res["result"]
            print(f"✅ خرید موفق! هش تراکنش: {tx_signature}")
            return True, tx_signature
        else:
            print(f"❌ خطای شبکه در ارسال تراکنش: {tx_res}")
            return False, str(tx_res)

    except Exception as e:
        print(f"❌ خطای سیستمی در اجرای خرید واقعی: {e}")
        return False, str(e)

# موتور پردازش، تحلیل و خرید واقعی
def auto_trader_loop(app):
    global IS_RUNNING, BUY_AMOUNT_SOL, TAKE_PROFIT, STOP_LOSS, MIN_LIQUIDITY, MIN_VOLUME_5M
    
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
                            f"⚠️ سود/زیان نهایی: {pnl_percent:.2f}%\n\n"
                            f"🔗 [مشاهده نمودار](https://dexscreener.com/solana/{token_addr})"
                        )
                        app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=exit_msg, parse_mode="Markdown")
                        tokens_to_close.append(token_addr)

            for t_addr in tokens_to_close:
                active_positions.pop(t_addr, None)

            # ۲. اسکن توکن‌های ترند بازار سولانا
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
                    
                    # اجرای واقعی خرید روی بلاکچین
                    print(f"⏳ در حال ارسال تراکنش خرید واقعی برای توکن {symbol} ({token_addr})...")
                    success, result_info = execute_real_buy(token_addr, BUY_AMOUNT_SOL)
                    
                    if not success:
                        print(f"❌ خرید ناموفق برای {symbol}: {result_info}")
                        continue

                    active_positions[token_addr] = {
                        "entry_price": price,
                        "symbol": symbol
                    }

                    target_tp = price * (1 + (TAKE_PROFIT / 100))
                    target_sl = price * (1 + (STOP_LOSS / 100))

                    solscan_link = f"https://solscan.io/tx/{result_info}"
                    dex_link = f"https://dexscreener.com/solana/{token_addr}"

                    msg = (
                        f"🚨 سیگنال جدید شناسایی شد\n"
                        f"✅ وضعیت خرید واقعی: انجام شد (موفق روی بلاکچین)\n\n"
                        f"🪙 توکن: {symbol}\n"
                        f"📍 آدرس: {token_addr}\n\n"
                        f"💵 قیمت ورود: ${price:.8f}\n"
                        f"💰 مقدار خرید: {BUY_AMOUNT_SOL} SOL\n"
                        f"🎯 تارگت حد سود (TP): ${target_tp:.8f} (+{TAKE_PROFIT}%)\n"
                        f"🛑 حد ضرر (SL): ${target_sl:.8f} ({STOP_LOSS}%)\n\n"
                        f"🔗 [مشاهده تراکنش در Solscan]({solscan_link})\n"
                        f"📈 [مشاهده در DexScreener]({dex_link})"
                    )
                    app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")
        except Exception as e:
            print(f"⚠️ خطا در حلقه اصلی اسکنر: {e}")

        time.sleep(10)

# وب‌سرور فلاسگ برای روشن ماندن ۲۴ ساعته روی رندر
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
    await update.message.reply_text("🤖 اتاق کنترل ربات تریدر واقعی سولانا", reply_markup=get_main_keyboard(), parse_mode="Markdown")

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
            await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🟢 اسکن خودکار و خرید واقعی فعال شد.", reply_markup=get_main_keyboard())
            
    elif query.data == "stop_bot":
        IS_RUNNING = False
        try:
            await query.edit_message_text("🔴 ربات متوقف شد.", reply_markup=get_main_keyboard())
        except Exception:
            await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🔴 ربات متوقف شد.", reply_markup=get_main_keyboard())
            
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
            await query.edit_message_text(status_text, parse_mode="Markdown", reply_markup=get_main_keyboard())
        except Exception:
            await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=status_text, parse_mode="Markdown", reply_markup=get_main_keyboard())
            
    elif query.data == "menu_volume":
        AWAITING_VOLUME = True
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text("⚙️ لطفاً مقدار حجم خرید جدید را به صورت عدد (مثلاً `0.02`) تایپ کنید و بفرستید:", reply_markup=cancel_kb, parse_mode="Markdown")
        except Exception:
            await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="⚙️ لطفاً مقدار حجم خرید جدید را به صورت عدد (مثلاً `0.02`) تایپ کنید و بفرستید:", reply_markup=cancel_kb, parse_mode="Markdown")
            
    elif query.data == "cancel_input":
        AWAITING_VOLUME = False
        try:
            await query.edit_message_text("🤖 عملیات لغو شد. اتاق کنترل ربات:", reply_markup=get_main_keyboard())
        except Exception:
            await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🤖 عملیات لغو شد. اتاق کنترل ربات:", reply_markup=get_main_keyboard())

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
            await update.message.reply_text(f"✅ حجم خرید با موفقیت به **{BUY_AMOUNT_SOL} SOL** تغییر کرد.", parse_mode="Markdown", reply_markup=get_main_keyboard())
        except ValueError:
            await update.message.reply_text("❌ خطا! لطفاً فقط یک عدد معتبر انگلیسی وارد کنید (مثلاً `0.01`). مجدداً تایپ کنید:", parse_mode="Markdown")

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
