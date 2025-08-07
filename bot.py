import os
import logging
import requests
import google.generativeai as genai
from dotenv import load_dotenv
from telegram import Update, InputFile
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import csv
import io

# Load environment variables from .env file
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure logging
logging.basicConfig(
    filename='bot.log',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Gemini model if API key is provided
model = None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash-lite-preview-06-17')

def start(update: Update, context: CallbackContext):
    """Sends a welcome message and explains how to use the bot."""
    update.message.reply_text(
        "👋 Welcome to the **Multi-VIN Bot**!\n\n"
        "Send me one or more VINs separated by commas (e.g., `VIN1,VIN2,VIN3`).\n"
        "I'll decode them and send back a CSV file with the **VIN, Year, Make, and Model** for each!\n\n"
        "Use /help for more information.",
        parse_mode='Markdown'
    )

def help_command(update: Update, context: CallbackContext):
    """Sends help information about the bot's commands."""
    update.message.reply_text(
        "📚 **Multi-VIN Bot Help**\n\n"
        "To get vehicle information:\n"
        "Just type or paste your VINs, separated by commas.\n"
        "Example: `1GNAF13R6CN123456,5UXWX7C5XBA000001`\n\n"
        "The bot will respond with a CSV file containing the decoded VIN data.\n\n"
        "**Note:** Fuel capacity lookup is not included in this version to simplify CSV output.",
        parse_mode='Markdown'
    )

def get_vin_info(vin: str):
    """
    Fetches vehicle information from the NHTSA API for a single VIN.
    Returns a dictionary with 'make', 'model', and 'year' if successful, otherwise None.
    """
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{vin}?format=json"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        result = data["Results"][0]

        make = result.get("Make", "N/A")
        model = result.get("Model", "N/A")
        year = result.get("ModelYear", "N/A")

        if make == "N/A" or model == "N/A" or year == "N/A":
            logger.warning(f"VIN decoding failed for {vin}: Incomplete data from NHTSA.")
            return None

        logger.info(f"NHTSA decoded - VIN: {vin}, Make: {make}, Model: {model}, Year: {year}")
        return {
            'vin': vin,
            'make': make,
            'model': model,
            'year': year
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error while decoding VIN {vin}: {e}")
        return None
    except KeyError:
        logger.error(f"Unexpected JSON structure for VIN {vin} from NHTSA API.")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while decoding VIN {vin}: {e}")
        return None

def handle_vins(update: Update, context: CallbackContext):
    """
    Handles user messages containing VINs, processes them, and sends a CSV file.
    """
    user_input = update.message.text.strip()
    vins = [vin.strip().upper() for vin in user_input.split(',') if vin.strip()]

    if not vins:
        update.message.reply_text("Please provide at least one VIN.")
        return

    update.message.reply_text(f"Processing {len(vins)} VIN(s). This may take a moment...")

    decoded_data = []
    for vin in vins:
        if len(vin) != 17 or not vin.isalnum(): # Basic VIN validation
            logger.warning(f"Skipping invalid VIN format: {vin}")
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

    if not decoded_data:
        update.message.reply_text("No valid VINs were processed.")
        return

    # Create CSV in memory
    output = io.StringIO()
    fieldnames = ['VIN', 'Year', 'Make', 'Model']
    writer = csv.DictWriter(output, fieldnames=fieldnames)

    writer.writeheader()
    writer.writerows(decoded_data)
    output.seek(0) # Go to the beginning of the stream

    # Send the CSV file
    update.message.reply_document(
        document=InputFile(output.getvalue().encode('utf-8'), filename='vin_data.csv'),
        caption="Here's your VIN data CSV! 📊"
    )
    logger.info(f"Sent CSV for {len(vins)} VINs to user {update.effective_user.id}")


def main():
    """Starts the bot."""
    if not TOKEN:
        print("❌ BOT_TOKEN not found. Make sure your .env file is configured properly.")
        return
    
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY not found. Gemini model will not be initialized.")

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Register handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_vins))

    print("🤖 Bot is starting...")
    updater.start_polling()
    print("✅ Bot is running! Press Ctrl+C to stop.")
    updater.idle()

if __name__ == "__main__":
    main()
