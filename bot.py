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

IS_RUNNING = False          # خرید و فروش خودکار مستقل
TREND_ALERT_RUNNING = False # اعلان ترند مستقل (فقط هشدار)
COMBO_RUNNING = False       # حالت ترکیبی (ترندهای انفجاری + خرید واقعی + هشدار)

BUY_AMOUNT_SOL = 0.005
TAKE_PROFIT = 30.0
STOP_LOSS = -12.0

# فیلترهای خرید و فروش معمولی (سیگنال)
MIN_LIQUIDITY = 35000       
MIN_VOLUME_5M = 5000       
MIN_PRICE_CHANGE_5M = 5.0  

# فیلترهای سنگین موتور ترند (پامپ خفن + خریداران زیاد + پول سنگین)
TREND_MIN_VOLUME_5M = 40000  # حداقل ۴۰ هزار دلار حجم ورودی در ۵ دقیقه
TREND_MIN_CHANGE_5M = 15.0   # حداقل ۱۵ درصد رشد قیمت (پامپ خفن)
MIN_BUYS_5M = 50             # حداقل ۵۰ نفر خریدار فعال در ۵ دقیقه

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
