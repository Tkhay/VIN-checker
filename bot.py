import os
import logging
import requests
import google.generativeai as genai
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext

# Load environment variables
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  

# Configure Gemini AI
model = None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash-lite-preview-06-17')

# Flask app for webhook
app = Flask(__name__)

# Initialize bot and dispatcher
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, workers=0, use_context=True)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Commands
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "How may I help you?\n\n"
        "Available commands:\n"
        "/checkvin - Decode a Vehicle VIN and get fuel capacity\n"
        "/help - Show help info"
    )

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "I'm a Vehicle VIN decoder bot with fuel capacity lookup.\n\n"
        "Use /checkvin to begin."
    )

def checkvin(update: Update, context: CallbackContext):
    update.message.reply_text("Hi! Send me a VIN and I'll provide vehicle info including fuel tank capacity.")
    context.user_data["expecting_vin"] = True

def handle_message(update: Update, context: CallbackContext):
    if context.user_data.get("expecting_vin"):
        vin = update.message.text.strip()
        context.user_data["expecting_vin"] = False
        send_vin_info(update, vin)
    else:
        update.message.reply_text("How may I help you?\nUse /checkvin to decode a VIN.")

def get_fuel_capacity_from_gemini(make: str, model_name: str, year: str):
    """
    Query Gemini API for fuel tank capacity
    """
    if not GEMINI_API_KEY:
        return "API key not configured"
    
    if not model:
        return "Gemini model not initialized"
    
    try:
        prompt = f"What is the fuel tank capacity in gallons for a {year} {make} {model_name}? Please provide only the numerical value followed by 'gallons'. If there are multiple trim levels with different capacities, provide the most common capacity or a range."
        
        logger.info(f"Querying Gemini for: {year} {make} {model_name}")
        
        response = model.generate_content(prompt)
        
        logger.info(f"Gemini response object: {response}")
        
        if response and hasattr(response, 'text') and response.text:
            logger.info(f"Gemini response text: {response.text}")
            return response.text.strip()
        else:
            logger.warning(f"Empty or invalid response from Gemini: {response}")
            return "Unable to retrieve fuel capacity from AI"
            
    except Exception as e:
        logger.error(f"Error querying Gemini API: {e}")
        logger.error(f"Error type: {type(e)}")
        return f"Error retrieving fuel capacity: {str(e)}"

def send_vin_info(update: Update, vin: str):
    # Show "typing" indicator while processing
    update.message.reply_text("🔍 Decoding VIN and looking up fuel capacity...")
    
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{vin}?format=json"
    try:
        response = requests.get(url)
        data = response.json()
        result = data["Results"][0]

        make = result.get("Make", "N/A")
        model_car = result.get("Model", "N/A")
        year = result.get("ModelYear", "N/A")

        logger.info(f"NHTSA decoded - Make: {make}, Model: {model_car}, Year: {year}")

        # Check if VIN decoding was successful
        if make == "N/A" or model_car == "N/A" or year == "N/A":
            logger.warning(f"VIN decoding failed. Raw result: {result}")
            update.message.reply_text(" Invalid VIN or unable to decode. Please check the VIN and try again.")
            return

        # Get fuel capacity from Gemini API
        fuel_capacity = get_fuel_capacity_from_gemini(make, model_car, year)

        # Format and send the response
        response_text = (
            f" **Vehicle Information**\n\n"
            f"**VIN:** {vin}\n"
            f"**Make:** {make}\n"
            f"**Model:** {model_car}\n"
            f"**Year:** {year}\n"
            f"**Fuel Tank Capacity:** {fuel_capacity}"
        )
        
        update.message.reply_text(response_text, parse_mode='Markdown')
        
    except requests.RequestException as e:
        logger.error(f"Error contacting NHTSA API: {e}")
        update.message.reply_text(" Sorry, there was an error contacting the VIN database. Please try again later.")
    except Exception as e:
        logger.error(f"Error decoding VIN: {e}")
        update.message.reply_text(" Sorry, something went wrong while decoding the VIN.")

# Add handlers to dispatcher
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("help", help_command))
dispatcher.add_handler(CommandHandler("checkvin", checkvin))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

# Webhook routes
@app.route('/')
def home():
    return "Telegram VIN Bot is running!"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('UTF-8')
        update = Update.de_json(request.get_json(force=True), bot)
        dispatcher.process_update(update)
        return jsonify({'status': 'ok'})
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/set_webhook')
def set_webhook():
    """Call this endpoint once to set up the webhook"""
    if not WEBHOOK_URL:
        return "WEBHOOK_URL not configured in environment variables"
    
    webhook_url = f"{WEBHOOK_URL}/webhook"
    result = bot.set_webhook(url=webhook_url)
    
    if result:
        return f"Webhook set successfully to {webhook_url}"
    else:
        return "Failed to set webhook"

@app.route('/webhook_info')
def webhook_info():
    """Check current webhook status"""
    info = bot.get_webhook_info()
    return jsonify({
        'url': info.url,
        'has_custom_certificate': info.has_custom_certificate,
        'pending_update_count': info.pending_update_count,
        'last_error_date': info.last_error_date,
        'last_error_message': info.last_error_message,
        'max_connections': info.max_connections,
        'allowed_updates': info.allowed_updates
    })
# Enable this for local testing
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)