import os
import json
import requests
import asyncio
import platform
import logging
from flask import Flask
from threading import Thread
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes
from dotenv import load_dotenv

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

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
RAILWAY_PROJECT_ID = os.getenv("RAILWAY_PROJECT_ID")
RAILWAY_API_TOKEN = os.getenv("RAILWAY_API_TOKEN")
PORT = int(os.getenv("PORT", 8080))

if not TELEGRAM_BOT_TOKEN or not URL or not GITHUB_REPO or not GITHUB_TOKEN:
    raise ValueError("Missing required environment variables!")

STORAGE_FILE = "latest_number.json"
app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

# Detect deployment platform
def detect_platform():
    if os.getenv("REPL_ID"):
        return "REPLIT"
    elif os.getenv("FLY_ALLOC_ID"):
        return "FLY.IO"
    elif os.getenv("RAILWAY_SERVICE_ID"):
        return "RAILWAY"
    return "UNKNOWN"

DEPLOYMENT_PLATFORM = detect_platform()

def keep_alive():
    server = Flask(__name__)

    @server.route('/')
    def home():
        return f"Bot is running on {DEPLOYMENT_PLATFORM}"

    def run():
        server.run(host='0.0.0.0', port=PORT)

    Thread(target=run, daemon=True).start()

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args if context.args else []
    
    if args and args[0].isdigit():
        wait_time = int(args[0])  # Convert argument to integer
        hours, remainder = divmod(wait_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        formatted_time = f"{hours} hours {minutes} minutes {seconds} seconds"

        message = await update.message.reply_text(f"\U000023F3 Monitoring will stop for {formatted_time} for saving free hours 🎯. Countdown begins...")

        # Countdown loop
        for remaining in range(wait_time, 0, -1):
            hours, remainder = divmod(remaining, 3600)
            minutes, seconds = divmod(remainder, 60)
            countdown_text = f"\U000023F3 Monitoring will stop for {hours} hours {minutes} minutes {seconds} seconds."
            
            try:
                await message.edit_text(countdown_text)
                await asyncio.sleep(1)
            except Exception:
                break  # Stop updating if message was deleted/edited by user

        # Remove deployment from Railway if applicable
        if DEPLOYMENT_PLATFORM == "RAILWAY" and RAILWAY_PROJECT_ID and RAILWAY_API_TOKEN:
            railway_url = f"https://backboard.railway.app/graphql"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {RAILWAY_API_TOKEN}"
            }
            mutation = {
                "query": "mutation StopDeployment($projectId: String!) { deleteProject(id: $projectId) { id } }",
                "variables": {"projectId": RAILWAY_PROJECT_ID}
            }
            response = requests.post(railway_url, json=mutation, headers=headers)
            if response.status_code == 200:
                await update.message.reply_text("\U0000274C Railway deployment removed successfully.")
            else:
                await update.message.reply_text(f"⚠️ Failed to remove Railway deployment: {response.text}")

        # Kill the bot after countdown
        os.system("pkill -f bot.py")  
        os._exit(0)
    else:
        await update.message.reply_text("⚠️ Please specify the number of seconds, e.g., `/stop 5000`")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received /ping command")
    await update.message.reply_text("I am now online 🌐")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received /start command")
    await update.message.reply_text("Hello! I am your bot, ready to assist you.")

async def main():
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop_bot))
    app.add_handler(CommandHandler("ping", ping))
    
    if DEPLOYMENT_PLATFORM in ["REPLIT", "FLY.IO"]:
        keep_alive()
    
    print(f"✅ Bot is live on {DEPLOYMENT_PLATFORM}! I am now online 🌐")
    
    await app.initialize()
    await app.start()
    await app.run_polling()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    if loop.is_running():
        loop.create_task(main())
    else:
        loop.run_until_complete(main())
