import os
import json
import requests
import asyncio
import platform
from flask import Flask
from threading import Thread
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
URL = os.getenv("URL")
CHAT_ID = os.getenv("CHAT_ID")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 5))  # Default: 5 seconds

if not TELEGRAM_BOT_TOKEN or not URL:
    raise ValueError("Missing required environment variables!")

STORAGE_FILE = "latest_number.json"
app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

# Detect deployment platform
DEPLOYMENT_PLATFORM = os.getenv("DEPLOYMENT_PLATFORM", "UNKNOWN")

# Flask keep-alive server
def keep_alive():
    server = Flask(__name__)

    @server.route('/')
    def home():
        return f"Bot is running on {DEPLOYMENT_PLATFORM}"

    def run():
        server.run(host='0.0.0.0', port=int(os.getenv("PORT", 8080)))

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


async def check_for_new_number():
    response = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(response.text, "html.parser")
    latest_title = soup.select_one('.latest-added__title a')
    new_number = int(latest_title.text.strip()) if latest_title else None
    flag_image = soup.select_one(".latest-added .container img")
    if not flag_image:
        flag_image = soup.select_one(".nav__logo img")

    flag_url = flag_image.get("data-lazy-src").strip(
    ) if flag_image and flag_image.get("data-lazy-src") else None

    if flag_url and flag_url.startswith('//'):
        flag_url = f"https:{flag_url}"

    return new_number, flag_url


async def send_telegram_notification(number, flag_url):
    message = f"🎁 *New Number Added* 🎁\n\n`+{number}` check it out! 💖"
    keyboard = [[
        InlineKeyboardButton("📋 Copy Number", callback_data=f"copy_{number}"),
        InlineKeyboardButton("🔄 Update Number", callback_data=f"update_{number}")
    ], [
        InlineKeyboardButton(
            "🌐 Visit Webpage",
            url=f"{URL}/number/{number}")
    ]]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if CHAT_ID:
        try:
            if flag_url:
                await app.bot.send_message(chat_id=CHAT_ID,
                                           text=message,
                                           parse_mode="Markdown",
                                           reply_markup=reply_markup)
            else:
                await app.bot.send_message(chat_id=CHAT_ID,
                                           text=message,
                                           parse_mode="Markdown",
                                           reply_markup=reply_markup)
                                           
        except Exception as e:
            print(f"Failed to send notification: {e}")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action, number = query.data.split("_")
    if action == "copy":
        await query.answer("Number copied!", show_alert=False)
        await query.edit_message_reply_markup(
            InlineKeyboardMarkup([[InlineKeyboardButton("✅ Copied", callback_data=f"copy_{number}")]])
        )
    elif action == "update":
        await save_last_number(int(number))
        await query.edit_message_text(f"🔄 *Updated to:* `{number}`", parse_mode="Markdown")


async def monitor_website():
    last_number = await load_last_number()
    while True:
        new_number, flag_url = await check_for_new_number()
        if new_number and new_number != last_number:
            await send_telegram_notification(new_number, flag_url)
            await save_last_number(new_number)
        await asyncio.sleep(CHECK_INTERVAL)


async def send_startup_message():
    print("✅ Bot is live! At Your Service 🍒🍄")
    if CHAT_ID:
        try:
            await app.bot.send_message(chat_id=CHAT_ID,
                                       text="At Your Service 🍒🍄")
            new_number, flag_url = await check_for_new_number()
            if new_number:
                await send_telegram_notification(new_number, flag_url)
                await save_last_number(new_number)
        except Exception as e:
            print(f"⚠️ Failed to send startup message: {e}")


async def main():
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    if DEPLOYMENT_PLATFORM in ["REPLIT", "FLY.IO"]:
        keep_alive()

    await app.initialize()
    await app.start()
    await asyncio.gather(monitor_website())
    await app.running()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped gracefully")
