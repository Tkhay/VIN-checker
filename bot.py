import os
import logging
import requests
import google.generativeai as genai
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time


load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
VIN_WEBSITE_URL = os.getenv("VIN_WEBSITE_URL")  


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


def get_chrome_options():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_argument("--disable-javascript")
    return chrome_options

def scrape_vin_from_website():
    """
    Scrape VIN from website using headless Chrome
    """
    driver = None
    try:
        logger.info("Starting Chrome driver for VIN scraping")
        chrome_options = get_chrome_options()
        driver = webdriver.Chrome(options=chrome_options)
        
        
        driver.get(VIN_WEBSITE_URL)
        logger.info(f"Navigated to {VIN_WEBSITE_URL}")
        
        
        wait = WebDriverWait(driver, 10)
        
        
        button_selectors = [
            'input.random:nth-child(2)',
            "//button[contains(text(), 'Random Real VIN')]",
            "//button[contains(text(), 'Real VIN')]",
            "//input[@type='button' and contains(@value, 'Real')]",

        ]
        
        button = None
        for selector in button_selectors:
            try:
                button = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
                logger.info(f"Found button with selector: {selector}")
                break
            except:
                continue
        
        if not button:
            logger.error("Could not find Generate VIN button")
            return None
        
        
        driver.execute_script("arguments[0].click();", button)
        logger.info("Clicked Generate VIN button")
        
        
        time.sleep(2)
        
        
        vin_selectors = [
            '//*[@id="Result"]'
            "//span[@id='Result']",
            "//div[@id='Result']",
            "//p[contains(@class, 'Result')]",
            "//div[contains(@class, 'Result')]",
            "//span[contains(@class, 'Result')]",
            "//div[contains(text(), 'Result:')]",
            "//*[contains(text(), 'Result:')]/following-sibling::*",
            "//*[string-length(text()) = 17 and matches(text(), '^[A-HJ-NPR-Z0-9]{17}$')]"
        ]
        
        vin = None
        for selector in vin_selectors:
            try:
                vin_element = driver.find_element(By.XPATH, selector)
                vin_text = vin_element.text.strip()
                # Basic VIN validation (17 characters, alphanumeric excluding I, O, Q)
                if len(vin_text) == 17 and vin_text.replace(' ', '').isalnum():
                    vin = vin_text.replace(' ', '')
                    logger.info(f"Found VIN: {vin}")
                    break
            except:
                continue
        
        if not vin:
            # Try to find any 17-character alphanumeric string on the page
            page_text = driver.page_source
            import re
            vin_pattern = r'[A-HJ-NPR-Z0-9]{17}'
            matches = re.findall(vin_pattern, page_text)
            if matches:
                vin = matches[0]
                logger.info(f"Found VIN via regex: {vin}")
        
        return vin
        
    except Exception as e:
        logger.error(f"Error scraping VIN: {e}")
        return None
    finally:
        if driver:
            driver.quit()


def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        " Welcome to VIN Bot!\n\n"
        "Available commands:\n"
        "• /checkvin - Decode a Vehicle VIN manually\n"
        "• Send a number (1-2) - Auto-scrape that many VINs\n"
        "• /help - Show help info"
    )

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        " VIN Bot Help\n\n"
        "**Manual VIN Check:**\n"
        "Use /checkvin then enter a VIN\n\n"
        "**Auto VIN Scraping:**\n"
        "Send a number (1 or 2) to automatically scrape and process that many VINs\n\n"
        "The bot will get VINs from the configured website and provide complete vehicle information including fuel capacity."
    )


def checkvin(update: Update, context: CallbackContext):
    update.message.reply_text("📝 Send me a VIN and I'll provide vehicle info including fuel tank capacity.")
    context.user_data["expecting_vin"] = True

def process_vin_count(update: Update, count: int):
    """
    Process the specified number of VINs by scraping from website
    """
    if count > 2:
        update.message.reply_text(" Maximum 2 VINs per request. Please enter 1 or 2.")
        return
    
    update.message.reply_text(f" Starting to scrape and process {count} VIN(s)...\nThis may take a moment.")
    
    results = []
    
    for i in range(count):
        update.message.reply_text(f" Processing VIN {i+1}/{count}...")
        
        vin = scrape_vin_from_website()
        
        if not vin:
            results.append({
                'index': i+1,
                'error': 'Failed to scrape VIN from website'
            })
            continue
        
        
        vin_info = get_vin_info(vin)
        
        if vin_info:
            results.append({
                'index': i+1,
                'vin': vin,
                'info': vin_info
            })
        else:
            results.append({
                'index': i+1,
                'vin': vin,
                'error': 'Failed to decode VIN'
            })
    
    send_batch_results(update, results)

def get_vin_info(vin: str):
    """
    Get vehicle information from VIN using NHTSA API
    """
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{vin}?format=json"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        result = data["Results"][0]

        make = result.get("Make", "N/A")
        model = result.get("Model", "N/A")
        year = result.get("ModelYear", "N/A")

        logger.info(f"NHTSA decoded - VIN: {vin}, Make: {make}, Model: {model}, Year: {year}")

        if make == "N/A" or model == "N/A" or year == "N/A":
            logger.warning(f"VIN decoding failed for {vin}")
            return None

        fuel_capacity = get_fuel_capacity_from_gemini(make, model, year)

        return {
            'make': make,
            'model': model,
            'year': year,
            'fuel_capacity': fuel_capacity
        }
        
    except Exception as e:
        logger.error(f"Error decoding VIN {vin}: {e}")
        return None

def send_batch_results(update: Update, results):
    """
    Send formatted results for batch VIN processing
    """
    if not results:
        update.message.reply_text("❌ No results to display.")
        return
    
    response_text = "🚗 **VIN Processing Results**\n\n"
    
    success_count = 0
    for result in results:
        response_text += f"**VIN #{result['index']}:**\n"
        
        if 'error' in result:
            response_text += f"❌ {result['error']}\n"
            if 'vin' in result:
                response_text += f"VIN: {result['vin']}\n"
        else:
            info = result['info']
            response_text += f"✅ **VIN:** {result['vin']}\n"
            response_text += f"**Make:** {info['make']}\n"
            response_text += f"**Model:** {info['model']}\n"
            response_text += f"**Year:** {info['year']}\n"
            response_text += f"**Fuel Capacity:** {info['fuel_capacity']}\n"
            success_count += 1
        
        response_text += "\n" + "─" * 30 + "\n\n"
    
    response_text += f"📊 **Summary:** {success_count}/{len(results)} VINs processed successfully"
    
    # Split long messages if needed 
    if len(response_text) > 4000:
        parts = response_text.split("─" * 30)
        for i, part in enumerate(parts):
            if part.strip():
                if i == 0:
                    update.message.reply_text(part + "─" * 30, parse_mode='Markdown')
                elif i == len(parts) - 1:
                    update.message.reply_text(part, parse_mode='Markdown')
                else:
                    update.message.reply_text(part + "─" * 30, parse_mode='Markdown')
    else:
        update.message.reply_text(response_text, parse_mode='Markdown')

def handle_message(update: Update, context: CallbackContext):
    message_text = update.message.text.strip()
    
    if context.user_data.get("expecting_vin"):
        context.user_data["expecting_vin"] = False
        send_vin_info(update, message_text)
        return
    
    if message_text.isdigit():
        count = int(message_text)
        if 1 <= count <= 2:
            process_vin_count(update, count)
        else:
            update.message.reply_text(" Please enter 1 or 2 for VIN count.\nUse /checkvin to decode a VIN manually.")
    else:
        update.message.reply_text(" Send a number (1-2) to scrape VINs, or use /checkvin to decode a VIN manually.")

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
    """
    Send VIN information for manual VIN input
    """
    update.message.reply_text("🔍 Decoding VIN and looking up fuel capacity...")
    
    vin_info = get_vin_info(vin)
    
    if not vin_info:
        update.message.reply_text("❌ Invalid VIN or unable to decode. Please check the VIN and try again.")
        return
    
    response_text = (
        f"🚗 **Vehicle Information**\n\n"
        f"**VIN:** {vin}\n"
        f"**Make:** {vin_info['make']}\n"
        f"**Model:** {vin_info['model']}\n"
        f"**Year:** {vin_info['year']}\n"
        f"**Fuel Tank Capacity:** {vin_info['fuel_capacity']}"
    )
    
    update.message.reply_text(response_text, parse_mode='Markdown')

def main():
    if not TOKEN:
        print("❌ BOT_TOKEN not found. Make sure your .env file is configured properly.")
        return
    
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY not found. Fuel capacity lookup will not work.")
    
    if not VIN_WEBSITE_URL or VIN_WEBSITE_URL == "https://example.com":
        print("⚠️ VIN_WEBSITE_URL not configured. Set it in your .env file.")

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Handlers
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("checkvin", checkvin))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    print("🤖 Bot is starting...")
    updater.start_polling()
    print("✅ Bot is running! Press Ctrl+C to stop.")
    updater.idle()

if __name__ == "__main__":
    main()