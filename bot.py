import os
import logging
import requests
from dotenv import load_dotenv
from flask import Flask, request
import csv
import io
import asyncio
from pathlib import Path

# Load environment variables
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

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

def send_message(chat_id, text, parse_mode=None):
    """Send a text message to a chat"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text
    }
    if parse_mode:
        data["parse_mode"] = parse_mode

    try:
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        return False

def send_document(chat_id, document_content, filename, caption=None):
    """Send a document to a chat"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"

    files = {
        'document': (filename, document_content, 'text/csv')
    }
    data = {
        'chat_id': chat_id
    }
    if caption:
        data['caption'] = caption

    try:
        response = requests.post(url, files=files, data=data, timeout=30)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send document: {e}")
        return False

def get_vin_info(vin: str):
    """Decode VIN using NHTSA API"""
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

def handle_start_command(chat_id):
    """Handle /start command"""
    message = (
        "👋 Welcome to the **Multi-VIN Bot**!\n\n"
        "Send me one or more VINs separated by commas (e.g., `VIN1,VIN2,VIN3`).\n"
        "I'll decode them and send back a CSV file with the **VIN, Year, Make, and Model** for each!\n\n"
        "Use /help for more information."
    )
    send_message(chat_id, message, parse_mode='Markdown')

def handle_help_command(chat_id):
    """Handle /help command"""
    message = (
        "📚 **Multi-VIN Bot Help**\n\n"
        "To get vehicle information:\n"
        "Just type or paste your VINs, separated by commas.\n"
        "Example: `1GNAF13R6CN123456`,`5UXWX7C5XBA000001`\n\n"
        "The bot will respond with a CSV file containing the decoded VIN data.\n\n"
        "**Note:** Fuel capacity lookup is not included in this version to simplify CSV output."
    )
    send_message(chat_id, message, parse_mode='Markdown')

def handle_vins(chat_id, user_input):
    """Handle VIN processing"""
    vins = [vin.strip().upper() for vin in user_input.split(',') if vin.strip()]

    if not vins:
        send_message(chat_id, "Please provide at least one VIN.")
        return

    send_message(chat_id, f"Processing {len(vins)} VIN(s)...")

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

    # Create CSV content
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=['VIN', 'Year', 'Make', 'Model'])
    writer.writeheader()
    writer.writerows(decoded_data)
    csv_content = output.getvalue().encode('utf-8')

    # Send the CSV file
    send_document(chat_id, csv_content, 'vin_data.csv', "Here's your VIN data CSV! 📊")

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming webhook updates"""
    try:
        update = request.get_json()
        logger.info(f"Received update: {update}")

        if not update or 'message' not in update:
            return 'OK', 200

        message = update['message']
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()

        if text == '/start':
            handle_start_command(chat_id)
        elif text == '/help':
            handle_help_command(chat_id)
        elif text and not text.startswith('/'):
            handle_vins(chat_id, text)
        else:
            send_message(chat_id, "Unknown command. Use /help for available commands.")

        return 'OK', 200

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return 'OK', 200

@app.route('/')
def index():
    """Health check endpoint"""
    return 'Bot is running!', 200

# Function to set webhook (run this once manually)
def set_webhook():
    """Set the webhook URL"""
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    data = {"url": WEBHOOK_URL}

    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        result = response.json()
        logger.info(f"Webhook set successfully: {result}")
        print(f"Webhook set successfully: {result}")
        return True
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")
        print(f"Failed to set webhook: {e}")
        return False

# Function to check webhook status
def check_webhook():
    """Check current webhook status"""
    url = f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo"

    try:
        response = requests.get(url)
        response.raise_for_status()
        result = response.json()
        logger.info(f"Webhook info: {result}")
        print(f"Webhook info: {result}")
        return result
    except Exception as e:
        logger.error(f"Failed to get webhook info: {e}")
        print(f"Failed to get webhook info: {e}")
        return None

if __name__ == "__main__":
    # This will only run when you execute the script directly
    # Use this to set up the webhook initially
    print("Setting up webhook...")
    set_webhook()
    print("Checking webhook status...")
    check_webhook()