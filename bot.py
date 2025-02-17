import os
import json
import time
import requests
import asyncio
from flask import Flask
from threading import Thread
from bs4 import BeautifulSoup
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

# Load environment variables from GitHub Secrets
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
URL = os.getenv("URL")
CHAT_ID = os.getenv("CHAT_ID") # Optional, bot will still work 
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 5)) # Default: 5 seconds

if not TELEGRAM_BOT_TOKEN or not URL:
    raise ValueError("Missing required environment variables: TELEGRAM_BOT_TOKEN or URL")

STORAGE_FILE = "latest_number.json"
app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

# Flask keep-alive server
def keep_alive():
    server = Flask(__name__)
    @server.route('/')
    def home():
        return "I'm alive!"
    Thread(target=lambda: server.run(host='0.0.0.0', port=8080)).start()

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
    flag_image = soup.select_one("img:nth-of-type(19)")
    flag_url = flag_image["src"] if flag_image else "default_flag_url"
    return new_number, flag_url

async def send_telegram_notification(number, flag_url):
    message = f"🎁 *New Number Added* 🎁\n\n`+{number}` check it out! 💖"
    keyboard = [
      [
        InlineKeyboardButton("📋 Copy Number", callback_data=f"copy_{number}"),
        InlineKeyboardButton("🔄 Update Number", callback_data=f"update_{number}")
      ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if CHAT_ID:
        await app.bot.send_photo(chat_id=CHAT_ID, photo=flag_url, caption=message, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, number = query.data.split("_")
    if action == "copy":
        await query.message.reply_text(f"✅ *Copied:* `{number}`", parse_mode="Markdown")
    elif action == "update":
        await save_last_number(int(number))
        await query.message.reply_text(f"🔄 *Updated to:* `{number}`", parse_mode="Markdown")

async def monitor_website():
    last_number = await load_last_number()
    while True:
        new_number, flag_url = await check_for_new_number()
        if new_number and new_number != last_number:
            await send_telegram_notification(new_number, flag_url)
            await save_last_number(new_number)
        await asyncio.sleep(CHECK_INTERVAL)

async def send_startup_message():
    print("Attempting to send startup message...")  # Debugging log
    try:
        bot_info = await app.bot.get_me()  # Get bot's own ID
        target_chat_id = CHAT_ID if CHAT_ID else bot_info.id  # Use provided CHAT_ID or bot's ID

        await app.bot.send_message(chat_id=target_chat_id, text="At Your Service 🍒🍄")
        print(f"Startup message sent successfully to {target_chat_id}!")
    except Exception as e:
        print(f"Failed to send startup message: {e}")  # Log errors


async def main():
    app.add_handler(CallbackQueryHandler(handle_callback))
    await send_startup_message()
    asyncio.create_task(app.run_polling())
    asyncio.create_task(monitor_website())
    keep_alive()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
