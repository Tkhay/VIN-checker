import os
import logging
import requests
import google.generativeai as genai
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# Load environment variables
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure Gemini AI
model = None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash-lite-preview-06-17')

logging.basicConfig(
    filename='bot.log',
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

# Check VIN command sets bot to expect VIN next
def checkvin(update: Update, context: CallbackContext):
    update.message.reply_text("Hi! Send me a VIN and I'll provide vehicle info including fuel tank capacity.")
    context.user_data["expecting_vin"] = True

# VIN Handler
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
        model = result.get("Model", "N/A")
        year = result.get("ModelYear", "N/A")

        logger.info(f"NHTSA decoded - Make: {make}, Model: {model}, Year: {year}")

        # Check if VIN decoding was successful
        if make == "N/A" or model == "N/A" or year == "N/A":
            logger.warning(f"VIN decoding failed. Raw result: {result}")
            update.message.reply_text(" Invalid VIN or unable to decode. Please check the VIN and try again.")
            return

        # Get fuel capacity from Gemini API
        fuel_capacity = get_fuel_capacity_from_gemini(make, model, year)

        # Format and send the response
        response_text = (
            f"🚗 **Vehicle Information**\n\n"
            f"**VIN:** {vin}\n"
            f"**Make:** {make}\n"
            f"**Model:** {model}\n"
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

def main():
    if not TOKEN:
        print(" BOT_TOKEN not found. Make sure your .env file is configured properly.")
        return
    
    if not GEMINI_API_KEY:
        print(" GEMINI_API_KEY not found. Fuel capacity lookup will not work.")
        

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("checkvin", checkvin))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    print("Bot is starting...")
    updater.start_polling()
    print("Bot is running! Press Ctrl+C to stop.")
    updater.idle()

if __name__ == "__main__":
    main()