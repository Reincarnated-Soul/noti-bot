import os
import json
import time
import requests
import asyncio
from bs4 import BeautifulSoup
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

# Load environment variables from a .env file (for local development)
if os.path.exists(".env"):
    load_dotenv()

# Telegram bot credentials and settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")  # Optional, bot will still work
URL = os.getenv("URL")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 5))  # Default: 5 seconds

# Ensure mandatory credentials are set
if not TELEGRAM_BOT_TOKEN or not URL:
    missing = [
        "TELEGRAM_BOT_TOKEN" if not TELEGRAM_BOT_TOKEN else "",
        "URL" if not URL else ""
    ]
    raise ValueError(f"Missing required environment variables: {', '.join(filter(None, missing))}")

# Storage file to keep track of last seen number
STORAGE_FILE = "latest_number.json"

# Initialize Telegram bot application
app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

async def load_last_number():
    """Load last stored number from file."""
    if os.path.exists(STORAGE_FILE):
        with open(STORAGE_FILE, "r") as f:
            data = json.load(f)
            return data.get("storedNum", None)
    return None

async def save_last_number(number):
    """Save the last detected number to a file."""
    with open(STORAGE_FILE, "w") as f:
        json.dump({"storedNum": number}, f)

async def check_for_new_number():
    """Check the website for a new number."""
    response = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(response.text, "html.parser")

    latest_title = soup.select_one('.latest-added__title a')
    new_number = int(latest_title.text.strip()) if latest_title else None

    flag_image = soup.select_one("img:nth-of-type(19)")  # Adjust the index if needed
    flag_url = flag_image["src"] if flag_image else "https://anonymsms.com/wp-content/uploads/2022/09/Anonym-SMS-500-×-200px.svg"

    return new_number, flag_url

async def send_telegram_notification(number, flag_url):
    """Send a notification via Telegram with action buttons."""
    message = f"🎁 *New Number Added* 🎁\n\n`+{number}` check it out! 💖"

    # Create inline keyboard buttons
    keyboard = [
        [
            InlineKeyboardButton("📋 Copy Number", callback_data=f"copy_{number}"),
            InlineKeyboardButton("🔄 Update Number", callback_data=f"update_{number}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if CHAT_ID:
        await app.bot.send_photo(chat_id=CHAT_ID, photo=flag_url, caption=message, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        print("CHAT_ID is not set. Notification will not be sent.")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks."""
    query = update.callback_query
    await query.answer()

    data = query.data.split("_")
    action, number = data[0], data[1]

    if action == "copy":
        await query.message.reply_text(f"✅ *Copied:* `{number}`", parse_mode="Markdown")

    elif action == "update":
        await save_last_number(int(number))
        await query.message.reply_text(f"🔄 *Updated to:* `{number}`", parse_mode="Markdown")

async def monitor_website():
    """Monitor the webpage in real-time."""
    last_number = await load_last_number()

    while True:
        new_number, flag_url = await check_for_new_number()

        if new_number and new_number != last_number:
            print(f"New number detected: {new_number}")
            await send_telegram_notification(new_number, flag_url)
            await save_last_number(new_number)
        else:
            print("No new number found.")

        await asyncio.sleep(CHECK_INTERVAL)  # Use configurable check interval
async def send_startup_message():
    """Send a startup confirmation message."""
    if CHAT_ID:
        await app.bot.send_message(chat_id=CHAT_ID, text="At Your Service 🍒🍄")

async def main():
    """Start the bot and monitor the website."""
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Start bot polling in the background
    async with app:
        await send_startup_message()
        await asyncio.gather(app.run_polling(), monitor_website())

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(main())  # Schedule the main coroutine
    loop.run_forever()  # Keep the script running

