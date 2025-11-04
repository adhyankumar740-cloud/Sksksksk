import telegram
from telegram import Update, constants, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
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
LOCK_KEY = 'quiz_in_progress' # Naya lock key

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
    """Open Trivia DB के English text को Hindi/Bengali mein translate karta hai।"""
    if dest_lang == 'en':
        return text
    
    TRANSLATE_URL = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl={dest_lang}&dt=t&q={requests.utils.quote(text)}"
    
    try:
        # Translation ke liye chhota timeout
        response = requests.get(TRANSLATE_URL, timeout=3) 
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
        await update.message.reply_text(
            f"Quiz shuru hai! Har **{QUIZ_TRIGGER_COUNT}** messages ke baad naya quiz automatic aayega. Apni baat-cheet jaari rakhein! 🥳"
        )
        return

    keyboard = [[lang for lang in LANG_MAP.keys()]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Namaskar! Please select your preferred language for the Quiz (Note: Quiz group mein automatic aayega):",
        reply_markup=reply_markup
    )

# --- 📣 QUIZ POST KARNE KA MAIN FUNCTION (Modified for Rate Limit) ---
async def send_periodic_quiz(context: ContextTypes.DEFAULT_TYPE):
    """
    Message counter se trigger hone par Open Trivia DB se sawal fetch karke teeno bhashaon mein bhejta hai.
    API Rate Limit se bachne ke liye har bhasha ke beech delay hai.
    """
    
    chat_id = CHAT_ID
    if not chat_id and context._chat_id:
        chat_id = context._chat_id 
        
    if not chat_id:
        logger.error("CHAT_ID not available to send the quiz.")
        return
        
    languages_to_send = ['en', 'hi', 'bn'] 

    for i, lang_code in enumerate(languages_to_send):
        await fetch_and_send_quiz(context, chat_id, lang_code)
        
        # 💡 API Rate Limit (429) se bachne ke liye delay (2.5 seconds)
        if i < len(languages_to_send) - 1:
            logger.info(f"Waiting 2.5 seconds to respect OpenTDB API limit before sending {languages_to_send[i+1]} quiz...")
            await asyncio.sleep(2.5) 

async def fetch_and_send_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id, lang_code):
    """API se sawal fetch karta hai aur di gayi bhasha mein translate karke bhejta hai।"""
    
    TRIVIA_API_URL = "https://opentdb.com/api.php?amount=1&type=multiple&encode=url_legacy"
    
    try:
        response = requests.get(TRIVIA_API_URL, timeout=5)
        response.raise_for_status() 
        data = response.json()
        
        if data['response_code'] != 0 or not data['results']:
            logger.warning(f"API se sawal fetch nahi ho paya for {lang_code}.")
            return

        question_data = data['results'][0]
        
        # Decode and unescape
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
        
    except requests.exceptions.HTTPError as e:
        logger.error(f"API Request Error: {e}")
        # Agar 429 aaye to aage badho (delay ki wajah se chances kam honge)
    except Exception as e:
        logger.error(f"General Error during quiz send: {e}")

# --- 🎯 Message Counter Logic (Modified for Lock) ---
async def send_quiz_after_n_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Har incoming message ko ginta hai. Lock system ka upyog karta hai taki ek baar mein ek hi quiz send ho.
    """
    
    chat_data = context.chat_data
    
    # 1. Lock check karein
    if chat_data.get(LOCK_KEY, False):
        logger.info("Quiz already in progress. Ignoring message count until process finishes.")
        return 
        
    # 2. Counter fetch aur update karein
    count = chat_data.get(MESSAGE_COUNTER_KEY, 0)
    chat_data[MESSAGE_COUNTER_KEY] = count + 1
    logger.info(f"Message Count in chat {update.effective_chat.id}: {chat_data[MESSAGE_COUNTER_KEY]}")

    # 3. Condition check karein
    if chat_data[MESSAGE_COUNTER_KEY] >= QUIZ_TRIGGER_COUNT:
        logger.info(f"Quiz trigger limit reached ({QUIZ_TRIGGER_COUNT}). Starting quiz process.")
        
        # 4. Lock set karein
        chat_data[LOCK_KEY] = True 
        
        try:
            # Quiz bhejein - ismein ab delay shamil hai
            await send_periodic_quiz(context) 
        except Exception as e:
            logger.error(f"Error during overall quiz send process: {e}")
        finally:
            # 5. Lock hatayein aur counter reset karein, chahe quiz fail ho ya pass
            chat_data[MESSAGE_COUNTER_KEY] = 0
            chat_data[LOCK_KEY] = False 
            logger.info("Quiz process finished and counter reset to 0.")
        
# --- 🚀 MAIN EXECUTION FUNCTION (Webhook/Render ke liye) ---
def main(): 
    if not TOKEN or not CHAT_ID or not WEBHOOK_URL:
        logger.critical("FATAL ERROR: Environment variables set nahi hain. Check TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, aur RENDER_EXTERNAL_URL.")
        return

    application = Application.builder().token(TOKEN).concurrent_updates(True).build()
    
    # Handlers add karein
    application.add_handler(CommandHandler("start", start_command))
    
    # Message Handler: filters.TEXT & ~filters.COMMAND ka matlab hai, sirf plain text messages ko gino
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            send_quiz_after_n_messages
        )
    )
    
    # Render Webhook Logic
    PORT = int(os.environ.get("PORT", "8000")) 
    
    logger.info("Bot starting with Webhook (Render mode)...")
    
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
