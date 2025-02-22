import os
import json
import requests
import asyncio
import sys
import gunicorn
from flask import Flask
from threading import Thread
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# Load environment variables if config file exists
CONFIG_FILE = "config_file.env"
if os.path.exists(CONFIG_FILE):
    load_dotenv(CONFIG_FILE)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
URL = os.getenv("URL")
CHAT_ID = os.getenv("CHAT_ID")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 5))  # Default: 5 seconds
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
PORT = int(os.getenv("PORT", 8080))


# Detect deployment platform
def detect_platform():
    platform_mapping = {
        "AWS_EXECUTION_ENV": "AWS",
        "DYNO": "HEROKU",
        "FLY_ALLOC_ID": "FLY.IO",
        "GOOGLE_CLOUD_PROJECT": "GOOGLE_CLOUD",
        "ORACLE_CLOUD": "ORACLE_CLOUD",
        "PYTHONANYWHERE_DOMAIN": "PYTHONANYWHERE",
        "RAILWAY_SERVICE_ID": "RAILWAY",
        "REPL_ID": "REPLIT"
    }

    for env_var, platform in platform_mapping.items():
        if env_var in os.environ or os.getenv(env_var):
            return platform

    return "UNKNOWN"


DEPLOYMENT_PLATFORM = detect_platform()

if not TELEGRAM_BOT_TOKEN or not URL:
    raise ValueError("Missing required environment variables!")

if DEPLOYMENT_PLATFORM == "RAILWAY" and (not GITHUB_REPO or not GITHUB_TOKEN):
    raise ValueError("GITHUB_REPO and GITHUB_TOKEN are required on Railway!")

bot = Bot(token=TELEGRAM_BOT_TOKEN,
          default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

STORAGE_FILE = "latest_number.json"


def keep_alive():

    server = Flask(__name__)

    @server.route('/')
    def home():
        return f"Bot is running on {DEPLOYMENT_PLATFORM}"

    def run():
        try:
            from waitress import serve
            serve(server, host='0.0.0.0', port=PORT)
        except Exception as e:
            print(f"Flask server error: {e}")

    Thread(target=run, daemon=True).start()


async def load_last_number():
    if os.path.exists(STORAGE_FILE):
        with open(STORAGE_FILE, "r") as f:
            data = json.load(f)
            return data.get("storedNum", None)
    return None


async def save_last_number(number):
    with open(STORAGE_FILE, "w") as f:
        json.dump({"storedNum": number}, f)


def fetch_url_content():
    headers = {
        "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    try:
        response = requests.get(URL, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Request failed: {e}")
        return None


async def check_for_new_number():
    page_content = fetch_url_content()
    if not page_content:
        return None, None

    soup = BeautifulSoup(page_content, "html.parser")
    latest_title = soup.select_one('.latest-added__title a')
    new_number = int(latest_title.text.strip()) if latest_title else None
    flag_image = soup.select_one(".latest-added .container img")
    flag_url = flag_image.get("data-lazy-src").strip(
    ) if flag_image and flag_image.get("data-lazy-src") else None

    if flag_url and flag_url.startswith('//'):
        flag_url = f"https:{flag_url}"

    return new_number, flag_url


# Function to generate buttons
def get_buttons(number):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="📋 Copy Number",
                                 callback_data=f"copy_{number}"),
            InlineKeyboardButton(text="🔄 Update Number",
                                 callback_data=f"update_{number}")
        ],
                         [
                             InlineKeyboardButton(text="🌐 Visit Webpage",
                                                  url=f"{URL}/number/{number}")
                         ]])
    return keyboard


# Callback for copying the number
@dp.callback_query(lambda c: c.data.startswith("copy_"))
async def copy_number(callback_query: CallbackQuery):
    number = callback_query.data.split("_")[1]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Copied", callback_data="none")
    ]])
    await callback_query.message.edit_reply_markup(reply_markup=keyboard)
    await asyncio.sleep(3)
    await callback_query.message.edit_reply_markup(
        reply_markup=get_buttons(number))


# Callback for updating the number
@dp.callback_query(lambda c: c.data.startswith("update_"))
async def update_number(callback_query: CallbackQuery):
    number = callback_query.data.split("_")[1]
    await save_last_number(int(number))
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"✅ Updated to: +{number}",
                             callback_data="none")
    ]])
    await callback_query.message.edit_reply_markup(reply_markup=keyboard)
    await asyncio.sleep(3)
    updated_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"{number}", callback_data="none")
    ]])
    await callback_query.message.edit_reply_markup(
        reply_markup=updated_keyboard)


async def send_telegram_notification(number, flag_url):
    message = f"🎁 *New Number Added* 🎁\n\n`+{number}` check it out! 💖"
    keyboard = get_buttons(number)

    if CHAT_ID:
        try:
            if flag_url:
                await bot.send_photo(CHAT_ID,
                                     photo=flag_url,
                                     caption=message,
                                     parse_mode="Markdown",
                                     reply_markup=keyboard)
            else:
                await bot.send_message(CHAT_ID,
                                       text=message,
                                       parse_mode="Markdown",
                                       reply_markup=keyboard)
        except Exception as e:
            print(f"Failed to send notification: {e}")


@dp.message(Command("ping"))
async def ping(message: types.Message):
    print("Received /ping command")
    await message.answer("I am now online 🌐")


# @dp.message(Commands("stop"))
# async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     args = context.args or []
#     wait_time = int(args[0]) if args and args[0].isdigit() else None

#     print("⛔ Stopping all tasks and will be restarted automatically...")
#     print(f"⏳ Scheduling restart in {wait_time} seconds...")

#     if args and args[0].isdigit():
#         hours, remainder = divmod(wait_time, 3600)
#         minutes, seconds = divmod(remainder, 60)
#         formatted_time = f"{hours:02}:{minutes:02}:{seconds:02}"

#         message = await update.message.reply_text(
#             f"⏳ Monitoring will stop for {formatted_time} for saving free hours 🎯. Countdown begins..."
#         )

#         # Countdown loop
#         for remaining in range(wait_time, 0, -1):
#             hours, remainder = divmod(remaining, 3600)
#             minutes, seconds = divmod(remainder, 60)
#             countdown_text = f"Monitoring will stop for {hours} hours {minutes} minutes {seconds} seconds."

#             try:
#                 await message.edit_text(countdown_text)
#                 await asyncio.sleep(1)
#             except Exception:
#                 break

#         if GITHUB_REPO and GITHUB_TOKEN:
#             url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/deploy.yml/dispatches"
#             headers = {
#                 "Authorization": f"token {GITHUB_TOKEN}",
#                 "Accept": "application/vnd.github.v3+json"
#             }
#             data = {"ref": "main"}

#             response = requests.post(url, json=data, headers=headers)
#             if response.status_code == 204:
#                 print("✅ GitHub Actions triggered successfully.")
#             else:
#                 print(f"⚠️ Failed to trigger redeployment: {response.text}")

#         sys.exit(0)
#     else:
#         await update.message.reply_text(
#             "⚠️ Please specify the number of seconds, e.g., `/stop 5000`")


async def monitor_website():
    last_number = await load_last_number()
    while True:
        new_number, flag_url = await check_for_new_number()
        if new_number and new_number != last_number:
            await send_telegram_notification(new_number, flag_url)
            await save_last_number(new_number)
            last_number = new_number
        await asyncio.sleep(CHECK_INTERVAL)


async def send_startup_message():
    if CHAT_ID:
        try:
            await bot.send_message(CHAT_ID, text="At Your Service 🍒🍄")
            new_number, flag_url = await check_for_new_number()
            if new_number:
                await send_telegram_notification(new_number, flag_url)
                await save_last_number(new_number)
        except Exception as e:
            print(f"⚠️ Failed to send startup message: {e}")


async def main():
    keep_alive()

    print(f"✅ Bot is live on {DEPLOYMENT_PLATFORM}! I am now online 🌐")

    await asyncio.sleep(2)
    await send_startup_message()
    await monitor_website()
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped gracefully")
