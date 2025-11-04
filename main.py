import telegram
from telegram import Update, constants, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
# apscheduler ko hata diya gaya hai kyunki hum Webhook aur message counter use kar rahe hain
import requests
import random
import os
import asyncio
from datetime import datetime
import html 
import logging 

# --- ⚙️ Constants and Setup ---
QUIZ_TRIGGER_COUNT = 10 # Har 10 message ke baad quiz bheja jaayega
MESSAGE_COUNTER_KEY = 'message_count'

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Zaroori Variables (Environment variables se fetch karein)
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL') 

# Bhashaon ki mapping
LANG_MAP = {
    "English 🇬🇧": 'en',
    "Hindi 🇮🇳": 'hi',
    "বাংলা 🇧🇩": 'bn'
}

# --- Translation Function ---
def translate_text(text, dest_lang):
    """Open Trivia DB के English text को Hindi/Bengali में translate करता है।"""
    if dest_lang == 'en':
        return text
    
    TRANSLATE_URL = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl={dest_lang}&dt=t&q={requests.utils.quote(text)}"
    
    try:
        # Translation ke liye chhota timeout
        response = requests.get(TRANSLATE_URL, timeout=3) 
        response.raise_for_status()
        data = response.json()
        # Data structure ko sambhalte hue
        translated_text = "".join(item[0] for item in data[0])
        return translated_text
        
    except Exception as e:
        logger.error(f"Translation Error to {dest_lang}: {e}")
        return text 

# --- 🎯 COMMANDS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot start hone par bhasha chune ka option deta hai."""
    
    # Groups/Supergroups mein simple reply
    if update.effective_chat.type in [telegram.constants.ChatType.GROUP, telegram.constants.ChatType.SUPERGROUP]:
        await update.message.reply_text(
            f"Quiz shuru hai! Har {QUIZ_TRIGGER_COUNT} messages ke baad naya quiz automatic aayega. Apni baat-cheet jaari rakhein! 🥳"
        )
        return

    # Private chat mein language option
    keyboard = [[lang for lang in LANG_MAP.keys()]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Namaskar! Please select your preferred language for the Quiz (Note: Quiz group mein automatic aayega):",
        reply_markup=reply_markup
    )

# --- 📣 QUIZ POST KARNE KA MAIN FUNCTION ---
async def send_periodic_quiz(context: ContextTypes.DEFAULT_TYPE):
    """Message counter se trigger hone par Open Trivia DB se sawal fetch karke teeno bhashaon mein bhejta hai."""
    
    # Agar chat_id set hai to wahan bhejenge, warna context se lenge
    chat_id = CHAT_ID
    # Agar chat_id environment variable set nahi hai, to group chat se lein (agar group mein trigger hua hai)
    if not chat_id and context._chat_id:
        chat_id = context._chat_id 
        
    if not chat_id:
        logger.error("CHAT_ID not available to send the quiz.")
        return
        
    languages_to_send = ['en', 'hi', 'bn'] 

    for lang_code in languages_to_send:
        await fetch_and_send_quiz(context, chat_id, lang_code)
        # Webhook timeout se bachne ke liye chhota delay (ya hatayein)
        await asyncio.sleep(0.5) 

async def fetch_and_send_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id, lang_code):
    """API se sawal fetch karta hai aur di gayi bhasha mein translate karke bhejta hai."""
    
    TRIVIA_API_URL = "https://opentdb.com/api.php?amount=1&type=multiple&encode=url_legacy"
    
    try:
        response = requests.get(TRIVIA_API_URL, timeout=5)
        response.raise_for_status() 
        data = response.json()
        
        if data['response_code'] != 0 or not data['results']:
            logger.warning(f"API se sawal fetch nahi ho paya for {lang_code}.")
            return

        question_data = data['results'][0]
        
        # Decode URL-encoded text and unescape HTML entities
        question_text = html.unescape(requests.utils.unquote(question_data['question']))
        correct_answer = html.unescape(requests.utils.unquote(question_data['correct_answer']))
        incorrect_answers = [html.unescape(requests.utils.unquote(ans)) for ans in question_data['incorrect_answers']]
        
        # Translation
        translated_question = translate_text(question_text, lang_code)
        translated_correct = translate_text(correct_answer, lang_code)
        translated_incorrect = [translate_text(ans, lang_code) for ans in incorrect_answers]
        
        all_options = translated_incorrect + [translated_correct]
        random.shuffle(all_options)
        
        correct_option_id = all_options.index(translated_correct)
        
        explanation = translate_text(f"Correct Answer: {correct_answer}", lang_code) 

        # Quiz Poll bhejte hain
        await context.bot.send_poll(
            chat_id=chat_id,
            question=translated_question,
            options=all_options,
            type=constants.PollType.QUIZ,
            correct_option_id=correct_option_id,
            explanation=explanation,
            is_anonymous=True, 
            open_period=600 # 10 minutes
        )
        logger.info(f"Quiz sent in {lang_code} to {chat_id}: '{translated_question[:30]}...'")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"API Request Error: {e}")
    except Exception as e:
        logger.error(f"General Error during quiz send: {e}")

# --- 🎯 Message Counter Logic ---
async def send_quiz_after_n_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Har incoming message (jo command nahi hai) ko ginta hai aur QUIZ_TRIGGER_COUNT ke baad quiz bhejta hai.
    """
    
    chat_data = context.chat_data
    
    # Counter fetch karein, agar nahi hai to 0 se shuru karein
    count = chat_data.get(MESSAGE_COUNTER_KEY, 0)
    
    # Counter badhaayein
    chat_data[MESSAGE_COUNTER_KEY] = count + 1
    logger.info(f"Message Count in chat {update.effective_chat.id}: {chat_data[MESSAGE_COUNTER_KEY]}")

    # Condition check karein
    if chat_data[MESSAGE_COUNTER_KEY] >= QUIZ_TRIGGER_COUNT:
        logger.info(f"Quiz trigger limit reached ({QUIZ_TRIGGER_COUNT}). Sending quiz.")
        
        # Quiz bhejein
        # Hamara send_periodic_quiz function ContextTypes.DEFAULT_TYPE object expect karta hai.
        await send_periodic_quiz(context) 
        
        # Counter ko reset karein
        chat_data[MESSAGE_COUNTER_KEY] = 0
        logger.info("Message counter reset to 0.")
        
# --- 🚀 MAIN EXECUTION FUNCTION (Webhook/Render ke liye) ---
def main(): 
    if not TOKEN or not CHAT_ID or not WEBHOOK_URL:
        logger.critical("FATAL ERROR: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ya RENDER_EXTERNAL_URL environment variable set nahi hai.")
        # Agar koi variable missing hai, to bot ko band kar dein
        return

    # User data aur chat data ko enable karein
    application = Application.builder().token(TOKEN).concurrent_updates(True).build()
    
    # Handlers add karein
    application.add_handler(CommandHandler("start", start_command))
    
    # Message Handler: filters.TEXT & ~filters.COMMAND ka matlab hai, sirf plain text messages ko gino, commands ko nahi.
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            send_quiz_after_n_messages
        )
    )
    
    # Render Webhook Logic
    PORT = int(os.environ.get("PORT", "8000")) 
    
    logger.info("Bot starting with Webhook (Render mode)...")
    
    # Webhook set karein
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )
    logger.info(f"Bot successfully started and listening on port {PORT}")

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutdown gracefully.")
