import telegram
from telegram import Update, constants, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from apscheduler.schedulers.background import BackgroundScheduler 
import requests
import random
import os
import asyncio
from datetime import datetime
import html 
import logging # Logging ke liye

# --- ⚙️ Logging Setup ---
# Simple logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ⚙️ Zaroori Variables (Environment variables se fetch karein) ---
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL') # Render khud yeh URL deta hai

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
        response = requests.get(TRANSLATE_URL, timeout=5) 
        response.raise_for_status()
        data = response.json()
        translated_text = "".join(item[0] for item in data[0])
        return translated_text
        
    except Exception as e:
        logger.error(f"Translation Error to {dest_lang}: {e}")
        return text 

# --- 🎯 COMMANDS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot start hone par bhasha chune ka option deta hai."""
    if update.effective_chat.type in [telegram.constants.ChatType.GROUP, telegram.constants.ChatType.SUPERGROUP]:
        await update.message.reply_text("Quiz har 15 minute mein yahan automatic aayega.")
        return

    keyboard = [[lang for lang in LANG_MAP.keys()]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Namaskar! Please select your preferred language for the Quiz:",
        reply_markup=reply_markup
    )

# --- 📣 QUIZ POST KARNE KA MAIN FUNCTION ---
async def send_periodic_quiz(context: ContextTypes.DEFAULT_TYPE):
    """Har 15 minute mein Open Trivia DB se naya sawal fetch karke teeno bhashaon mein bhejta hai."""
    
    if not CHAT_ID:
        logger.error("TELEGRAM_CHAT_ID is not set.")
        return
        
    languages_to_send = ['en', 'hi', 'bn'] 

    for lang_code in languages_to_send:
        await fetch_and_send_quiz(context, CHAT_ID, lang_code)
        # API rate limit se bachne ke liye delay
        await asyncio.sleep(5) 

async def fetch_and_send_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id, lang_code):
    """API se sawal fetch karta hai aur di gayi bhasha mein translate karke bhejta hai."""
    
    TRIVIA_API_URL = "https://opentdb.com/api.php?amount=1&type=multiple&encode=url_legacy"
    
    try:
        response = requests.get(TRIVIA_API_URL)
        response.raise_for_status() 
        data = response.json()
        
        if data['response_code'] != 0 or not data['results']:
            logger.warning(f"API se sawal fetch nahi ho paya for {lang_code}.")
            return

        question_data = data['results'][0]
        
        question_text = html.unescape(requests.utils.unquote(question_data['question']))
        correct_answer = html.unescape(requests.utils.unquote(question_data['correct_answer']))
        incorrect_answers = [html.unescape(requests.utils.unquote(ans)) for ans in question_data['incorrect_answers']]
        
        translated_question = translate_text(question_text, lang_code)
        translated_correct = translate_text(correct_answer, lang_code)
        translated_incorrect = [translate_text(ans, lang_code) for ans in incorrect_answers]
        
        all_options = translated_incorrect + [translated_correct]
        random.shuffle(all_options)
        
        correct_option_id = all_options.index(translated_correct)
        
        explanation = translate_text(f"Correct Answer is: {correct_answer}", lang_code) 

        # Quiz Poll bhejte hain
        await context.bot.send_poll(
            chat_id=chat_id,
            question=translated_question,
            options=all_options,
            type=constants.PollType.QUIZ,
            correct_option_id=correct_option_id,
            explanation=explanation,
            is_anonymous=True, 
            open_period=900 # 15 minutes
        )
        logger.info(f"Quiz sent in {lang_code}: '{translated_question[:30]}...'")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"API Request Error: {e}")
    except Exception as e:
        logger.error(f"General Error during quiz send: {e}")


# --- 🚀 MAIN EXECUTION FUNCTION (Aapke logic ke anusaar) ---
def main(): 
    if not TOKEN or not CHAT_ID:
        logger.critical("FATAL ERROR: TOKEN ya CHAT_ID environment variable set nahi hai.")
        return

    application = Application.builder().token(TOKEN).build()
    
    # Handlers add karein
    application.add_handler(CommandHandler("start", start_command))
    
    # Scheduler Setup
    scheduler = BackgroundScheduler() 
    scheduler.add_job(
        send_periodic_quiz, 
        'interval', 
        seconds=900,  
        kwargs={'context': application}, 
        id='periodic_quiz_job'
    )
    scheduler.start()
    logger.info("Scheduler active.")
    
    # Aapke Webhook/Polling Logic ke anusaar
    if WEBHOOK_URL:
        # Render par Web Service ke liye zaroori
        PORT = int(os.environ.get("PORT", "8000")) 
        
        # Webhook URL mein token ka upyog karein
        application.run_webhook(
            listen="0.0.0.0", # Sabhi interfaces par suno
            port=PORT,
            url_path=TOKEN, # URL path mein TOKEN ka upyog
            webhook_url=f"{WEBHOOK_URL}/{TOKEN}" # Complete Webhook URL
        )
        logger.info(f"Bot started with Webhook on port {PORT}")
    else:
        # Local development ya Worker mode ke liye
        logger.info("Bot started with Polling")
        application.run_polling(poll_interval=3.0, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutdown gracefully.")
