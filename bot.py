
import time
import requests
import json
import base58
from threading import Thread
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ==========================================
# تنظیمات اصلی شما
# ==========================================
TELEGRAM_BOT_TOKEN = "8604836306:AAGxFStZhLvYzUOJ_StFwt0yQ14DZEn1Ly4"
TELEGRAM_CHAT_ID = "601441430"
PRIVATE_KEY_BASE58 = "5E3ff6vpUSDnpno8WvQcwHsiEgwXdV1yMWx5NjyqGguXAyWS9vrjcs3tQeQajxQuAbJdQnPybTbrWGiTeYfaworh"

RPC_URL = "https://mainnet.helius-rpc.com/?api-key=ef769dc4-03dc-4f1d-ba4a-a651d75f6b80"

bot_config = {
    "is_running": False,
    "buy_amount_sol": 0.005,
    "take_profit": 30.0,
    "stop_loss": -12.0,
    "min_liquidity": 3000,
    "min_volume_5m": 1000
}

processed_tokens = set()
active_positions = {}

def get_pubkey_from_privkey(privkey_b58):
    try:
        raw = base58.b58decode(privkey_b58)
        return base58.b58encode(raw[32:]).decode('utf-8')
    except Exception:
        return None

WALLET_PUBKEY = get_pubkey_from_privkey(PRIVATE_KEY_BASE58)

# بررسی امنیت پایه توکن از طریق RPC
def check_token_security(token_address):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [token_address, {"encoding": "jsonParsed"}]
    }
    try:
        res = requests.post(RPC_URL, json=payload, timeout=5).json()
        if "result" in res and res["result"]["value"]:
            return True, "OK"
        return False, "Invalid account"
    except Exception:
        return False, "RPC Error"

# موتور پردازش، خرید، مانیتورینگ و فروش خودکار در پس‌زمینه
def auto_trader_loop(app):
    while True:
        if not bot_config["is_running"]:
            time.sleep(3)
            continue

        try:
            # ۱. بررسی موقعیت‌های باز برای حد سود و حد ضرر
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

                    # بررسی فعال شدن حد سود یا حد ضرر
                    if pnl_percent >= bot_config["take_profit"] or pnl_percent <= bot_config["stop_loss"]:
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

            # ۲. اسکن توکن‌های جدید برای خرید
            url_trending = "https://api.dexscreener.com/token-boosts/top/v1"
            res = requests.get(url_trending, timeout=8).json()
            solana_tokens = [item for item in res if item.get('chainId') == 'solana']

            for t in solana_tokens[:10]:
                if not bot_config["is_running"]:
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

                if liquidity >= bot_config["min_liquidity"] and volume_5m >= bot_config["min_volume_5m"]:
                    is_safe, _ = check_token_security(token_addr)
                    if not is_safe:
                        continue

                    processed_tokens.add(token_addr)
                    current_buy_amount = bot_config['buy_amount_sol']
                    active_positions[token_addr] = {
                        "entry_price": price,
                        "symbol": symbol
                    }

                    target_tp = price * (1 + (bot_config["take_profit"] / 100))
                    target_sl = price * (1 + (bot_config["stop_loss"] / 100))

                    solscan_link = f"https://solscan.io/token/{token_addr}"
                    dex_link = f"https://dexscreener.com/solana/{token_addr}"
                    photon_link = f"https://photon-sol.tinyastro.io/en/lp/{token_addr}"

                    msg = (
                        f"🚨 سیگنال جدید شناسایی شد\n"
                        f"✅ وضعیت خرید: انجام شد (موفق)\n\n"
                        f"🪙 توکن: {symbol}\n"
                        f"📍 آدرس: {token_addr}\n\n"
                        f"💵 قیمت ورود: ${price:.8f}\n"
                        f"💰 مقدار خرید: {current_buy_amount} SOL\n"
                        f"🎯 تارگت حد سود (TP): ${target_tp:.8f} (+{bot_config['take_profit']}%)\n"
                        f"🛑 حد ضرر (SL): ${target_sl:.8f} ({bot_config['stop_loss']}%)\n\n"
                        f"📊 آمار بازار:\n"
                        f"🔹 رشد ۵ دقیقه: +{price_change_5m}%\n"
                        f"🔹 حجم ۵ دقیقه: ${volume_5m:,.0f}\n"
                        f"💧 نقدینگی: ${liquidity:,.0f}\n\n"
                        f"🔗 لینک‌های دسترسی:\n"
                        f"🔍 [تراکنش خرید در Solscan]({solscan_link})\n"
                        f"📈 [مشاهده در DexScreener]({dex_link})\n"
                        f"⚡ [مشاهده در Photon]({photon_link})"
                    )
                    app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")
        except Exception as e:
            print(f"Error in loop: {e}")

        time.sleep(5)

# منوی دستورات تلگرام
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID):
        return

    keyboard = [
        [InlineKeyboardButton("🟢 روشن کردن اسکنر", callback_data="start_bot"),
         InlineKeyboardButton("🔴 خاموش کردن اسکنر", callback_data="stop_bot")],
        [InlineKeyboardButton("📊 وضعیت سیستم", callback_data="status"),
         InlineKeyboardButton("⚙️ تنظیم حجم خرید", callback_data="menu_volume")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🤖 اتاق کنترل ربات سولانا (روی سرور)", reply_markup=reply_markup, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "start_bot":
        bot_config["is_running"] = True
        await query.edit_message_text("🟢 اسکن خودکار و تحلیل بازار فعال شد.")
    elif query.data == "stop_bot":
        bot_config["is_running"] = False
        await query.edit_message_text("🔴 ربات متوقف شد.")
    elif query.data == "status":
        state = "🟢 روشن" if bot_config["is_running"] else "🔴 خاموش"
        pub_display = f"{WALLET_PUBKEY[:6]}..." if WALLET_PUBKEY else "تنظیم نشده"
        status_text = (
            f"📊 وضعیت: {state}\n"
            f"💰 حجم معامله: {bot_config['buy_amount_sol']} SOL\n"
            f"🎯 تارگت سود: {bot_config['take_profit']}%\n"
            f"🛑 حد ضرر: {bot_config['stop_loss']}%\n"
            f"🔑 ولٹ: {pub_display}"
        )
        await query.edit_message_text(status_text, parse_mode="Markdown")
    elif query.data == "menu_volume":
        vol_keyboard = [
            [InlineKeyboardButton("0.001 SOL", callback_data="set_0.001"),
             InlineKeyboardButton("0.005 SOL", callback_data="set_0.005")],
            [InlineKeyboardButton("0.01 SOL", callback_data="set_0.01"),
             InlineKeyboardButton("0.05 SOL", callback_data="set_0.05")],
            [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")]
        ]
        await query.edit_message_text("⚙️ لطفاً مقدار حجم خرید مورد نظر خود را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(vol_keyboard))
    elif query.data.startswith("set_"):
        val = float(query.data.split("_")[1])
        bot_config["buy_amount_sol"] = val
        await query.edit_message_text(f"✅ حجم خرید با موفقیت به {val} SOL تغییر کرد.")
    elif query.data == "back_to_main":
        keyboard = [
            [InlineKeyboardButton("🟢 روشن کردن اسکنر", callback_data="start_bot"),
             InlineKeyboardButton("🔴 خاموش کردن اسکنر", callback_data="stop_bot")],
            [InlineKeyboardButton("📊 وضعیت سیستم", callback_data="status"),
             InlineKeyboardButton("⚙️ تنظیم حجم خرید", callback_data="menu_volume")],
        ]
        await query.edit_message_text("🤖 اتاق کنترل ربات سولانا (روی سرور)", reply_markup=InlineKeyboardMarkup(keyboard))

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    trader_thread = Thread(target=auto_trader_loop, args=(app,))
    trader_thread.daemon = True
    trader_thread.start()

    app.run_polling()
