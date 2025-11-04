import telegram
from telegram import Update, constants, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from apscheduler.schedulers.background import BackgroundScheduler 
import requests
import random
import os
import asyncio
import threading # <-- Threading ki zaroorat hai Web Service ke liye
from datetime import datetime
import html 
from flask import Flask 

# --- ⚙️ Zaroori Variables ---
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Flask web app object
web_app = Flask(__name__) 

# Bhashaon ki mapping
LANG_MAP = {
    "English 🇬🇧": 'en',
    "Hindi 🇮🇳": 'hi',
    "বাংলা 🇧🇩": 'bn'
}

# --- Translation and Quiz Functions (Same as before) ---
def translate_text(text, dest_lang):
    # ... (same translation logic)
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
        return text 

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (same command logic)
    if update.effective_chat.type in [telegram.constants.ChatType.GROUP, telegram.constants.ChatType.SUPERGROUP]:
        await update.message.reply_text("Quiz har 15 minute mein yahan automatic aayega.")
        return

    keyboard = [[lang for lang in LANG_MAP.keys()]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Namaskar! Please select your preferred language for the Quiz:\nनमस्ते! क्विज़ के लिए अपनी पसंदीदा भाषा चुनें:\nনমস্কার! কুইজের জন্য আপনার পছন্দের ভাষা নির্বাচন করুন:",
        reply_markup=reply_markup
    )

async def send_periodic_quiz(context: ContextTypes.DEFAULT_TYPE):
    # ... (same quiz scheduler logic)
    if not CHAT_ID:
        print("Error: TELEGRAM_CHAT_ID is not set.")
        return
        
    languages_to_send = ['en', 'hi', 'bn'] 

    for lang_code in languages_to_send:
        await fetch_and_send_quiz(context, CHAT_ID, lang_code)
        await asyncio.sleep(5) 

async def fetch_and_send_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id, lang_code):
    # ... (same fetch logic)
    TRIVIA_API_URL = "https://opentdb.com/api.php?amount=1&type=multiple&encode=url_legacy"
    
    try:
        response = requests.get(TRIVIA_API_URL)
        response.raise_for_status() 
        data = response.json()
        
        if data['response_code'] != 0 or not data['results']:
            print(f"API se sawal fetch nahi ho paya for {lang_code}.")
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

        await context.bot.send_poll(
            chat_id=chat_id,
            question=translated_question,
            options=all_options,
            type=constants.PollType.QUIZ,
            correct_option_id=correct_option_id,
            explanation=explanation,
            is_anonymous=True, 
            open_period=900 
        )
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Quiz sent in {lang_code}: '{translated_question[:30]}...'")
        
    except requests.exceptions.RequestException as e:
        print(f"API Request Error: {e}")
    except Exception as e:
        print(f"General Error: {e}")


# --- 🌐 FLASK HEALTH CHECK ROUTE ---
@web_app.route('/')
def health_check():
    """Render ko OK response dene ke liye."""
    # Yahan hum check karte hain ki Bot thread chal raha hai ya nahi
    if 'bot_thread' in web_app.config and web_app.config['bot_thread'].is_alive():
        return 'Telegram Bot Polling is Active.', 200
    else:
        # Agar bot thread crash ho gaya to 503 denge
        return 'Telegram Bot Polling is DOWN.', 503

# --- 🏃 BOT POLLING FUNCTION (Alag Thread mein chalega) ---
def run_bot_polling(application: Application):
    """PTB application ko synchronous polling mode mein chalata hai."""
    print("Starting bot polling in new thread...")
    try:
        # run_polling() ko ek naye thread mein chalane se Event Loop ki problem avoid ho jaati hai
        application.run_polling(poll_interval=3.0, allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        print(f"FATAL BOT POLLING ERROR: {e}")

# --- 🚀 FINAL MAIN FUNCTION (Web Service) ---
def main(): 
    if not TOKEN or not CHAT_ID:
        print("FATAL ERROR: Environment variables set nahi hain.")
        return

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    
    # BackgroundScheduler (Polling Loop ke saath chalega)
    scheduler = BackgroundScheduler() 
    scheduler.add_job(
        send_periodic_quiz, 
        'interval', 
        seconds=900,  
        kwargs={'context': application}, 
        id='periodic_quiz_job'
    )
    scheduler.start()
    print("Scheduler active.")

    # 1. Bot Polling ko alag Thread mein chalao
    bot_thread = threading.Thread(target=run_bot_polling, args=(application,))
    bot_thread.daemon = True # Main process exit hone par thread bhi exit ho jaayega
    bot_thread.start()
    
    # Bot thread ko Flask config mein store karo health check ke liye
    web_app.config['bot_thread'] = bot_thread
    print("Telegram Polling started in a separate thread.")

    # 2. Main thread ab Flask server chalaegi (Port open karne ke liye)
    port = int(os.environ.get('PORT', 8080))
    print(f"Flask running on port {port} for Render health check.")
    
    # use_reloader=False Render par zaruri hai
    web_app.run(host='0.0.0.0', port=port, use_reloader=False)


if __name__ == '__main__':
    try:
        main() 
    except (KeyboardInterrupt, SystemExit):
        print("Bot shutdown gracefully.")
