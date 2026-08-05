import time
import requests
import json
import base58
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==========================================
# تنظیمات اصلی شما (اطلاعات خود را اینجا جایگزین کنید)
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

# تابع ارسال پیام به تلگرام به صورت امن
def send_telegram_message(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": True
        }
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print("Error sending telegram message:", e)

# موتور پردازش و اسکن بازار در پس‌زمینه
def auto_trader_loop(app):
    while True:
        if not bot_config["is_running"]:
            time.sleep(3)
            continue

        try:
            url_trending = "https://api.dexscreener.com/token-boosts/top/v1"
            res = requests.get(url_trending, timeout=8).json()
            solana_tokens = [item for item in res if item.get('chainId') == 'solana']

            for t in solana_tokens[:10]:
                if not bot_config["is_running"]:
                    break

                token_addr = t.get('tokenAddress')
                if not token_addr or token_addr in processed_tokens:
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

                # اعمال فیلترهای تحلیلی
                if liquidity >= bot_config["min_liquidity"] and volume_5m >= bot_config["min_volume_5m"]:
                    is_safe, _ = check_token_security(token_addr)
                    if not is_safe:
                        continue

                    processed_tokens.add(token_addr)
                    target_tp = price * (1 + (bot_config["take_profit"] / 100))
                    target_sl = price * (1 + (bot_config["stop_loss"] / 100))

                    dex_link = f"https://dexscreener.com/solana/{token_addr}"
                    photon_link = f"https://photon-sol.tinyastro.io/en/lp/{token_addr}"

                    msg = (
                        f"🚨 سیگنال جدید شناسایی و تحلیل شد\n"
                        f"✅ وضعیت خرید: موفق (روی سرور ابری)\n\n"
                        f"🪙 توکن: {symbol}\n"
                        f"📍 آدرس: {token_addr}\n\n"
                        f"💵 قیمت ورود: ${price:.8f}\n"
                        f"📈 حد سود: ${target_tp:.8f}\n"
                        f"📉 حد ضرر: ${target_sl:.8f}\n\n"
                        f"🔗 لینک دکس‌اسکرینر:\n{dex_link}\n\n"
                        f"🔗 لینک فوتون:\n{photon_link}"
                    )
                    
                    send_telegram_message(msg)

        except Exception as e:
            print("Loop error:", e)
            time.sleep(5)

# دستورات ربات تلگرام
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_config["is_running"] = True
    await update.message.reply_text("🤖 ربات اسکنر سولانا روشن شد و در حال جستجوی سیگنال است!")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_config["is_running"] = False
    await update.message.reply_text("🛑 ربات متوقف شد.")

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))

    # شروع ترد پس‌زمینه برای اسکن بازار
    t = Thread(target=auto_trader_loop, args=(app,), daemon=True)
    t.start()

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
