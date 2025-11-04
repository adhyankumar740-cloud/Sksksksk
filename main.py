import telegram
from telegram import Update, constants, ReplyKeyboardMarkup, KeyboardButton
# Webhooks ke liye Zaroori imports
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from apscheduler.schedulers.background import BackgroundScheduler 
import requests
import random
import os
import asyncio
from datetime import datetime
import html 
from flask import Flask, request # Request import kiya gaya

# --- ⚙️ Zaroori Variables ---
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL') # Render khud yeh URL deta hai
PORT = int(os.environ.get('PORT', 8080))

# Flask web app object
web_app = Flask(__name__) 

# Bhashaon ki mapping
LANG_MAP = {
    "English 🇬🇧": 'en',
    "Hindi 🇮🇳": 'hi',
    "বাংলা 🇧🇩": 'bn'
}

# --- Translation and Quiz Functions (Same as before) ---
# NOTE: Translation and Quiz Logic Functions yahan same rahenge. 
# Maine unhe chhota kar diya hai taaki code clear rahe.

def translate_text(text, dest_lang):
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
    if update.effective_chat.type in [telegram.constants.ChatType.GROUP, telegram.constants.ChatType.SUPERGROUP]:
        await update.message.reply_text("Quiz har 15 minute mein yahan automatic aayega.")
        return
    keyboard = [[lang for lang in LANG_MAP.keys()]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "Namaskar! Please select your preferred language for the Quiz:",
        reply_markup=reply_markup
    )

async def send_periodic_quiz(context: ContextTypes.DEFAULT_TYPE):
    if not CHAT_ID: return
    languages_to_send = ['en', 'hi', 'bn'] 
    for lang_code in languages_to_send:
        await fetch_and_send_quiz(context, CHAT_ID, lang_code)
        await asyncio.sleep(5) 

async def fetch_and_send_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id, lang_code):
    TRIVIA_API_URL = "https://opentdb.com/api.php?amount=1&type=multiple&encode=url_legacy"
    try:
        response = requests.get(TRIVIA_API_URL)
        response.raise_for_status() 
        data = response.json()
        if data['response_code'] != 0 or not data['results']: return
        
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
            chat_id=chat_id, question=translated_question, options=all_options,
            type=constants.PollType.QUIZ, correct_option_id=correct_option_id,
            explanation=explanation, is_anonymous=True, open_period=900 
        )
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Quiz sent in {lang_code}.")
    except Exception as e:
        print(f"General Error: {e}")

# --- 🌐 FLASK WEBHOOK SETUP ---

# Application object ko globally declare karna zaroori hai
application = Application.builder().token(TOKEN).build()

@web_app.route('/', methods=['GET'])
def set_webhook():
    """Render health check aur webhook set karne ke liye."""
    return 'Bot Webhook Ready!', 200

@web_app.route('/telegram', methods=['POST'])
async def telegram_webhook():
    """Telegram se incoming updates ko handle karta hai."""
    # PTB ko update process karne ke liye bolta hai
    await application.update_queue.put(Update.de_json(request.get_json(force=True), application.bot))
    return 'OK'

# --- 🚀 FINAL MAIN FUNCTION (Webhook Service) ---
def main(): 
    if not TOKEN or not CHAT_ID:
        print("FATAL ERROR: Environment variables set nahi hain.")
        return
    
    if not WEBHOOK_URL:
        print("FATAL ERROR: RENDER_EXTERNAL_URL is not set. Webhooks cannot be set.")
        return

    # Handlers add karein
    application.add_handler(CommandHandler("start", start_command))
    
    # 1. Scheduler ko start karein (BackgroundScheduler non-blocking hai)
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

    # 2. Webhook URL set karein
    webhook_path = '/telegram'
    full_webhook_url = f"{WEBHOOK_URL}{webhook_path}"
    
    print(f"Setting webhook to: {full_webhook_url}")
    
    # run_polling() ki jagah set_webhook() use karein
    # Isko chalaneke liye alag se asyncio loop ki zaroorat nahi, yeh background mein chalta hai.
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=webhook_path,
        webhook_url=full_webhook_url,
        # Flask server ko chalao
        external_host=WEBHOOK_URL,
    )
    
    # Flask app ko chalao (yeh blocking call hai aur port open rakhega)
    # Note: Humne application.run_webhook ka upyog kiya hai, to humein 
    # Flask ko alag se run nahi karna chahiye. PTB khud hi Flask ko chalaega.
    # Lekin Render par, humein gunicorn ki zaroorat ho sakti hai.
    
    # Testing ke liye, hum Flask ko manually chalate hain:
    print(f"Flask running on port {PORT} for Render.")
    web_app.run(host='0.0.0.0', port=PORT, use_reloader=False)


if __name__ == '__main__':
    try:
        main() 
    except (KeyboardInterrupt, SystemExit):
        print("Bot shutdown gracefully.")
