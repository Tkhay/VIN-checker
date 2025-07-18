import os
import logging
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# Load environment variables
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    filename='bot.log',           # Log file saved in your project folder
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Commands
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "How may I help you?\n\nAvailable commands:\n"
        "/checkvin - Decode a Vehicle VIN\n"
        "/help - Show help info"
    )

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "I'm a Vehicle VIN decoder bot.\n\n"
        "Use /checkvin to begin."
    )

# Check VIN command sets bot to expect VIN next
def checkvin(update: Update, context: CallbackContext):
    update.message.reply_text("Hi! Send me a VIN and I’ll read it.")
    context.user_data["expecting_vin"] = True

# VIN Handler
def handle_message(update: Update, context: CallbackContext):
    if context.user_data.get("expecting_vin"):
        vin = update.message.text.strip()
        context.user_data["expecting_vin"] = False
        send_vin_info(update, vin)
    else:
        update.message.reply_text("How may I help you?\nUse /checkvin to decode a VIN.")

def send_vin_info(update: Update, vin: str):
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{vin}?format=json"
    try:
        response = requests.get(url)
        data = response.json()
        result = data["Results"][0]

        make = result.get("Make", "N/A")
        model = result.get("Model", "N/A")
        year = result.get("ModelYear", "N/A")

        update.message.reply_text(
            f"VIN Info:\nMake: {make}\nModel: {model}\nYear: {year}"
        )
    except Exception as e:
        logger.error(f"Error decoding VIN: {e}")
        update.message.reply_text("Sorry, something went wrong while decoding the VIN.")

def main():
    if not TOKEN:
        print("❌ BOT_TOKEN not found. Make sure your .env file is configured properly.")
        return

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("checkvin", checkvin))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
