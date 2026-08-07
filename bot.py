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

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "TOKEN_YOW")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "CHAT_ID_YOW")
PRIVATE_KEY_BASE58 = os.environ.get("PRIVATE_KEY_BASE58", "YOUR_PRIVATE_KEY")
TWITTER_BEARER_TOKEN = os.environ.get("TWITTER_BEARER_TOKEN", "YOUR_TWITTER_BEARER_TOKEN")

RPC_URL = "https://mainnet.helius-rpc.com/?api-key=ef769dc4-03dc-4f1d-ba4a-a651d75f6b80"
SOL_MINT = "So11111111111111111111111111111111111111112"
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ATA_PROGRAM_ID = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
SYS_PROG_ID = Pubkey.from_string("11111111111111111111111111111111")
RENT_SYSVAR = Pubkey.from_string("SysvarRent11111111111111111111111111111111")

IS_RUNNING = False
BUY_AMOUNT_SOL = 0.005
TAKE_PROFIT = 30.0
STOP_LOSS = -12.0

MIN_LIQUIDITY = 5000       
MIN_VOLUME_5M = 1000       
MIN_PRICE_CHANGE_5M = 2.0  

AWAITING_STATE = None 

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

def is_token_safe(token_mint):
    try:
        url = f"https://api.rugcheck.xyz/v1/tokens/{token_mint}/summary"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            risk_score = data.get("score", 0)
            if risk_score > 4500:
                return False
        return True
    except Exception:
        return True

def get_real_twitter_trending_tokens():
    tokens = []
    try:
        url = "https://api.dexscreener.com/token-boosts/top/v1"
        res = requests.get(url, timeout=8).json()
        if isinstance(res, list):
            solana_tokens = [item for item in res if item.get('chainId') == 'solana']
            for t in solana_tokens:
                addr = t.get('tokenAddress')
                if addr and addr not in tokens:
                    tokens.append(addr)
    except Exception as e:
        print(f"⚠️ خطا در دریافت داده‌های دکس: {e}")

    try:
        latest_url = "https://api.dexscreener.com/latest/dex/search?q=solana"
        res_latest = requests.get(latest_url, timeout=8).json()
        pairs = res_latest.get("pairs", [])
        for p in pairs:
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
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    quote_url = f"https://api.jup.ag/swap/v1/quote?inputMint={SOL_MINT}&outputMint={token_mint}&amount={lamports}&slippageBps=300"
    
    try:
        quote_res = requests.get(quote_url, headers=headers, timeout=10).json()
        if "error" in quote_res:
            return False, "خطای دریافت قیمت از صرافی"

        swap_res = requests.post("https://api.jup.ag/swap/v1/swap", json={
            "quoteResponse": quote_res,
            "userPublicKey": WALLET_PUBKEY,
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True
        }, headers=headers, timeout=10).json()

        if "swapTransaction" not in swap_res:
            return False, "تراکنش سواپ رد شد"

        raw_tx = base64.b64decode(swap_res["swapTransaction"])
        txn = VersionedTransaction.from_bytes(raw_tx)
        signature = sender_keypair.sign_message(bytes(txn.message))
        signed_txn = VersionedTransaction.populate(txn.message, [signature])
        serialized_tx = base58.b58encode(bytes(signed_txn)).decode('utf-8')

        tx_res = requests.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "sendTransaction",
            "params": [serialized_tx, {"encoding": "base58", "skipPreflight": True}]
        }, timeout=15).json()

        if "result" in tx_res:
            return True, tx_res["result"]
        else:
            return False, tx_res.get('error', {}).get('message', 'خطای شبکه')
    except Exception as e:
        return False, str(e)

def execute_real_sell(token_mint, token_amount):
    if not WALLET_PUBKEY:
        return False, "ولت نامعتبر است"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    quote_url = f"https://api.jup.ag/swap/v1/quote?inputMint={token_mint}&outputMint={SOL_MINT}&amount={token_amount}&slippageBps=400"
    
    try:
        quote_res = requests.get(quote_url, headers=headers, timeout=10).json()
        if "error" in quote_res:
            return False, "خطای قیمت فروش"

        swap_res = requests.post("https://api.jup.ag/swap/v1/swap", json={
            "quoteResponse": quote_res,
            "userPublicKey": WALLET_PUBKEY,
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True
        }, headers=headers, timeout=10).json()

        if "swapTransaction" not in swap_res:
            return False, "تراکنش فروش رد شد"

        raw_tx = base64.b64decode(swap_res["swapTransaction"])
        txn = VersionedTransaction.from_bytes(raw_tx)
        signature = sender_keypair.sign_message(bytes(txn.message))
        signed_txn = VersionedTransaction.populate(txn.message, [signature])
        serialized_tx = base58.b58encode(bytes(signed_txn)).decode('utf-8')

        tx_res = requests.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "sendTransaction",
            "params": [serialized_tx, {"encoding": "base58", "skipPreflight": True}]
        }, timeout=15).json()

        if "result" in tx_res:
            return True, tx_res["result"]
        else:
            return False, tx_res.get('error', {}).get('message', 'خطای شبکه')
    except Exception as e:
        return False, str(e)

def create_real_solana_token(name, symbol, supply_amount):
    if not WALLET_PUBKEY or not sender_keypair:
        return False, "ولت تنظیم نشده است"
    try:
        mint_keypair = Keypair()
        mint_pubkey = mint_keypair.pubkey()
        
        rent_resp = requests.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getMinimumBalanceForRentExemption",
            "params": [82]
        }, timeout=10).json()
        lamports = rent_resp.get("result", 1461600)
        
        bh_resp = requests.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getLatestBlockhash",
            "params": [{"commitment": "confirmed"}]
        }, timeout=10).json()
        blockhash_str = bh_resp.get("result", {}).get("value", {}).get("blockhash")
        if not blockhash_str:
            return False, "خطا در دریافت بلاک‌هاش"
        recent_blockhash = Hash.from_string(blockhash_str)
        
        create_acc_ix = create_account(
            CreateAccountParams(
                from_pubkey=sender_keypair.pubkey(),
                to_pubkey=mint_pubkey,
                lamports=lamports,
                space=82,
                owner=TOKEN_PROGRAM_ID
            )
        )
        
        init_data = bytes([0, 9]) + bytes(sender_keypair.pubkey()) + bytes([0])
        init_mint_ix = Instruction(
            program_id=TOKEN_PROGRAM_ID,
            accounts=[
                AccountMeta(mint_pubkey, is_signer=False, is_writable=True),
                AccountMeta(RENT_SYSVAR, is_signer=False, is_writable=False)
            ],
            data=init_data
        )
        
        def get_associated_token_address(wallet: Pubkey, mint: Pubkey) -> Pubkey:
            assoc, _ = Pubkey.find_program_address(
                bytes(wallet) + bytes(TOKEN_PROGRAM_ID) + bytes(mint),
                ATA_PROGRAM_ID
            )
            return assoc
            
        sender_ata = get_associated_token_address(sender_keypair.pubkey(), mint_pubkey)
        
        create_ata_ix = Instruction(
            program_id=ATA_PROGRAM_ID,
            accounts=[
                AccountMeta(sender_keypair.pubkey(), is_signer=True, is_writable=True),
                AccountMeta(sender_ata, is_signer=False, is_writable=True),
                AccountMeta(sender_keypair.pubkey(), is_signer=False, is_writable=False),
                AccountMeta(mint_pubkey, is_signer=False, is_writable=False),
                AccountMeta(SYS_PROG_ID, is_signer=False, is_writable=False),
                AccountMeta(TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
                AccountMeta(RENT_SYSVAR, is_signer=False, is_writable=False),
            ],
            data=bytes()
        )
        
        supply_raw = int(float(supply_amount) * 10**9)
        mint_to_data = bytes([7]) + supply_raw.to_bytes(8, "little")
        mint_to_ix = Instruction(
            program_id=TOKEN_PROGRAM_ID,
            accounts=[
                AccountMeta(mint_pubkey, is_signer=False, is_writable=True),
                AccountMeta(sender_ata, is_signer=False, is_writable=True),
                AccountMeta(sender_keypair.pubkey(), is_signer=True, is_writable=False)
            ],
            data=mint_to_data
        )
        
        message = MessageV0.try_compile(
            payer=sender_keypair.pubkey(),
            instructions=[create_acc_ix, init_mint_ix, create_ata_ix, mint_to_ix],
            address_lookup_table_accounts=[],
            recent_blockhash=recent_blockhash
        )
        
        txn = VersionedTransaction(message, [sender_keypair, mint_keypair])
        serialized_tx = base58.b58encode(bytes(txn)).decode('utf-8')
        
        tx_res = requests.post(RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "sendTransaction",
            "params": [serialized_tx, {"encoding": "base58", "skipPreflight": False}]
        }, timeout=20).json()
        
        if "result" in tx_res:
            return True, f"آدرس توکن: {str(mint_pubkey)}\nتراکنش: https://solscan.io/tx/{tx_res['result']}"
        else:
            return False, tx_res.get("error", {}).get("message", "خطای شبکه")
    except Exception as e:
        return False, str(e)

def auto_trader_loop(app):
    global IS_RUNNING, BUY_AMOUNT_SOL, TAKE_PROFIT, STOP_LOSS, MIN_LIQUIDITY, MIN_VOLUME_5M
    send_telegram_msg("🤖 اسکنر بازار و رصد توکن‌ها فعال شد.")

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
                            reason = "تارگت سود 🎯" if pnl_percent >= 0 else "حد ضرر 🛑"
                            token_balance = get_token_balance(token_addr)
                            if token_balance > 0:
                                success, sell_res_info = execute_real_sell(token_addr, token_balance)
                            else:
                                success, sell_res_info = False, "موجودی صفر بود"

                            exit_msg = (
                                f"🔴 فروش خودکار ({reason})\n"
                                f"🪙 توکن: {symbol}\n"
                                f"📊 سود/زیان: {pnl_percent:+.2f}%\n"
                                f"🔗 تراکنش: https://solscan.io/tx/{sell_res_info if success else 'failed'}"
                            )
                            send_telegram_msg(exit_msg)
                            tokens_to_close.append(token_addr)
                except Exception:
                    pass

            for t_addr in tokens_to_close:
                active_positions.pop(t_addr, None)

            solana_tokens = get_real_twitter_trending_tokens()

            for token_addr in solana_tokens[:10]:
                if not IS_RUNNING:
                    break
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

                if (liquidity >= MIN_LIQUIDITY and 
                    volume_5m >= MIN_VOLUME_5M and 
                    price_change_5m >= MIN_PRICE_CHANGE_5M and 
                    price > 0 and
                    is_token_safe(token_addr)):
                    
                    processed_tokens.add(token_addr)
                    success, result_info = execute_real_buy(token_addr, BUY_AMOUNT_SOL)
                    
                    msg = (
                        f"🔥 سیگنال جدید خرید\n"
                        f"🪙 توکن: {symbol}\n"
                        f"📍 آدرس:\n{token_addr}\n"
                        f"💵 ورود: ${price:.8f}\n"
                        f"💰 حجم: {BUY_AMOUNT_SOL} SOL\n"
                        f"📊 نقدینگی: ${liquidity:,.0f} | حجم ۵م: ${volume_5m:,.0f}\n"
                        f"🔗 تراکنش: https://solscan.io/tx/{result_info if success else 'failed'}"
                    )
                    
                    if success:
                        active_positions[token_addr] = {"entry_price": price, "symbol": symbol}
                    send_telegram_msg(msg)
        except Exception:
            pass

        time.sleep(8)

web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running!"

def run_web():
    web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 روشن کردن اسکنر", callback_data="start_bot"),
         InlineKeyboardButton("🔴 خاموش کردن اسکنر", callback_data="stop_bot")],
        [InlineKeyboardButton("📊 وضعیت سیستم", callback_data="status"),
         InlineKeyboardButton("🪙 ساخت توکن جدید", callback_data="menu_create_token")],
        [InlineKeyboardButton(f"⚙️ حجم: {BUY_AMOUNT_SOL} SOL", callback_data="menu_volume"),
         InlineKeyboardButton(f"🎯 تارگت: {TAKE_PROFIT}%", callback_data="menu_tp")],
        [InlineKeyboardButton(f"🛑 حد ضرر: {STOP_LOSS}%", callback_data="menu_sl")],
        [InlineKeyboardButton(f"🔒 نقدینگی: ${MIN_LIQUIDITY}", callback_data="menu_liq"),
         InlineKeyboardButton(f"📈 حجم۵دقیقه: ${MIN_VOLUME_5M}", callback_data="menu_vol5m")]
    ])

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID):
        return
    global AWAITING_STATE
    AWAITING_STATE = None
    await update.message.reply_text("🤖 منوی کنترل ربات تریدر و سازنده توکن:", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global IS_RUNNING, AWAITING_STATE
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    if query.data == "start_bot":
        IS_RUNNING = True
        try:
            await query.edit_message_text("🟢 اسکنر روشن شد.", reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg("🟢 اسکنر روشن شد.")
    elif query.data == "stop_bot":
        IS_RUNNING = False
        try:
            await query.edit_message_text("🔴 اسکنر خاموش شد.", reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg("🔴 اسکنر خاموش شد.")
    elif query.data == "status":
        state = "🟢 روشن" if IS_RUNNING else "🔴 خاموش"
        status_text = f"📊 وضعیت:\nاسکنر: {state}\nحجم خرید: {BUY_AMOUNT_SOL} SOL\nتارگت: {TAKE_PROFIT}%\nحد ضرر: {STOP_LOSS}%"
        try:
            await query.edit_message_text(status_text, reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg(status_text)
    elif query.data == "menu_create_token":
        AWAITING_STATE = "create_token"
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ انصراف", callback_data="cancel_input")]])
        try:
            await query.edit_message_text("🪙 اطلاعات ساخت توکن را بفرستید:\nنام, نماد, تعداد\n(مثال: DogeToken, DOGE, 1000000000)", reply_markup=cancel_kb)
        except Exception:
            send_telegram_msg("🪙 اطلاعات ساخت توکن را بفرستید (نام, نماد, تعداد):")
    elif query.data == "cancel_input":
        AWAITING_STATE = None
        try:
            await query.edit_message_text("🤖 لغو شد.", reply_markup=get_main_keyboard())
        except Exception:
            send_telegram_msg("🤖 لغو شد.")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AWAITING_STATE
    if str(update.effective_user.id) != str(TELEGRAM_CHAT_ID):
        return

    if AWAITING_STATE == "create_token":
        text_input = update.message.text.strip()
        try:
            parts = [p.strip() for p in text_input.split(',')]
            if len(parts) < 3:
                await update.message.reply_text("❌ فرمت اشتباه است! مثال:\nDogeToken, DOGE, 1000000000")
                return
            t_name, t_symbol, t_supply = parts[0], parts[1], parts[2]
            
            await update.message.reply_text("⏳ در حال ساخت توکن روی بلاکچین...")
            success, res_msg = create_real_solana_token(t_name, t_symbol, t_supply)
            
            AWAITING_STATE = None
            if success:
                final_txt = f"✅ توکن ساخته شد!\n\n{res_msg}"
            else:
                final_txt = f"❌ خطا در ساخت توکن:\n{res_msg}"
                
            await update.message.reply_text(final_txt, reply_markup=get_main_keyboard())
        except Exception as e:
            await update.message.reply_text(f"❌ خطا: {e}")
            AWAITING_STATE = None
    else:
        await update.message.reply_text("🤖 از دکمه‌ها استفاده کنید:", reply_markup=get_main_keyboard())

if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    Thread(target=auto_trader_loop, args=(app,), daemon=True).start()
    app.run_polling()
