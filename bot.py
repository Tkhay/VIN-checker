import os
import logging
import requests
from dotenv import load_dotenv
from flask import Flask, request
from telegram import Update, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import csv
import io

# Load environment variables
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") 

# Logging
logging.basicConfig(
    filename='bot.log',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
application = Application.builder().token(TOKEN).build()

# --- HANDLER FUNCTIONS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to the **Multi-VIN Bot**!\n\n"
        "Send me one or more VINs separated by commas (e.g., `VIN1,VIN2,VIN3`).\n"
        "I'll decode them and send back a CSV file with the **VIN, Year, Make, and Model** for each!\n\n"
        "Use /help for more information.",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 **Multi-VIN Bot Help**\n\n"
        "To get vehicle information:\n"
        "Just type or paste your VINs, separated by commas.\n"
        "Example: `1GNAF13R6CN123456,5UXWX7C5XBA000001`\n\n"
        "The bot will respond with a CSV file containing the decoded VIN data.\n\n"
        "**Note:** Fuel capacity lookup is not included in this version to simplify CSV output.",
        parse_mode='Markdown'
    )

def get_vin_info(vin: str):
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{vin}?format=json"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        result = data["Results"][0]

        make = result.get("Make", "N/A")
        model = result.get("Model", "N/A")
        year = result.get("ModelYear", "N/A")

        if make == "N/A" or model == "N/A" or year == "N/A":
            logger.warning(f"VIN decoding failed for {vin}: Incomplete data.")
            return None

        return {
            'vin': vin,
            'make': make,
            'model': model,
            'year': year
        }

    except Exception as e:
        logger.error(f"Error decoding VIN {vin}: {e}")
        return None

async def handle_vins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    vins = [vin.strip().upper() for vin in user_input.split(',') if vin.strip()]

    if not vins:
        await update.message.reply_text("Please provide at least one VIN.")
        return

    await update.message.reply_text(f"Processing {len(vins)} VIN(s)...")

    decoded_data = []
    for vin in vins:
        if len(vin) != 17 or not vin.isalnum():
            decoded_data.append({'VIN': vin, 'Year': 'Invalid VIN', 'Make': '', 'Model': ''})
            continue

        vin_info = get_vin_info(vin)
        if vin_info:
            decoded_data.append({
                'VIN': vin_info['vin'],
                'Year': vin_info['year'],
                'Make': vin_info['make'],
                'Model': vin_info['model']
            })
        else:
            decoded_data.append({'VIN': vin, 'Year': 'N/A', 'Make': 'N/A', 'Model': 'N/A'})

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=['VIN', 'Year', 'Make', 'Model'])
    writer.writeheader()
    writer.writerows(decoded_data)
    output.seek(0)

    await update.message.reply_document(
        document=InputFile(output.getvalue().encode('utf-8'), filename='vin_data.csv'),
        caption="Here's your VIN data CSV! 📊"
    )

# --- FLASK ROUTE FOR WEBHOOK ---

@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "OK"

# --- STARTUP FUNCTION (run once manually to set the webhook) ---

async def set_webhook():
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook set to {WEBHOOK_URL}")

# --- INIT ---

def setup():
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_vins))

# Only run this manually ONCE to register webhook
if __name__ == "__main__":
    import asyncio
    setup()
    asyncio.run(set_webhook())
