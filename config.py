import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# پیش‌فرض‌ها
DEFAULT_CARD_NUMBER = "6037998800118522"
DEFAULT_PAYMENT_LINK = "https://mehryazdan.ir/pay/"
DEFAULT_REMINDER_TIME = "19:00"

# مبالغ پیشنهادی (تومان)
SUGGESTED_AMOUNTS = [10000, 50000, 100000, 200000]

WELCOME_MESSAGE = """🌷 *به ربات صدقه‌رس خوش آمدید*

این ربات شما را برای پرداخت صدقه ماهانه یاری می‌کند.

برای شروع، روی دکمه «ثبت‌نام» بزنید."""
