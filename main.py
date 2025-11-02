import telegram
from telegram import Update, constants, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
# FIX: BackgroundScheduler Event Loop की समस्या को हल करता है
from apscheduler.schedulers.background import BackgroundScheduler 
import requests
import random
import os
import asyncio
from datetime import datetime
import html 

# --- ⚙️ Zaroori Variables (Set these in Render Environment) ---
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Bhashaon ki mapping
LANG_MAP = {
    "English 🇬🇧": 'en',
    "Hindi 🇮🇳": 'hi',
    "বাংলা 🇧🇩": 'bn'
}

# --- Translation Function (Using Google's free unofficial endpoint) ---
def translate_text(text, dest_lang):
    """Open Trivia DB के English text को Hindi/Bengali में translate करता है।"""
    if dest_lang == 'en':
        return text
    
    # URL encoded data ko quote karte hain
    TRANSLATE_URL = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl={dest_lang}&dt=t&q={requests.utils.quote(text)}"
    
    try:
        # 5 second timeout set kiya gaya hai
        response = requests.get(TRANSLATE_URL, timeout=5) 
        response.raise_for_status()
        data = response.json()
        
        # Translation result nikalna
        translated_text = "".join(item[0] for item in data[0])
        return translated_text
        
    except Exception as e:
        # Translation fail hone par original text wapas kar do
        # print(f"Simple Translation Error to {dest_lang}: {e}") 
        return text 

# --- 🎯 COMMANDS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot start hone par bhasha chune ka option deta hai."""
    # Group me start command ko ignore karna behtar hai, ya sirf info de sakte hain
    if update.effective_chat.type in [telegram.constants.ChatType.GROUP, telegram.constants.ChatType.SUPERGROUP]:
        await update.message.reply_text("Quiz har 15 minute mein yahan automatic aayega.")
        return

    # User ko bhasha chune ka option do (sirf private chat mein)
    keyboard = [[lang for lang in LANG_MAP.keys()]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Namaskar! Please select your preferred language for the Quiz:\nनमस्ते! क्विज़ के लिए अपनी पसंदीदा भाषा चुनें:\nনমস্কার! কুইজের জন্য আপনার পছন্দের ভাষা নির্বাচন করুন:",
        reply_markup=reply_markup
    )

# Note: Humne set_language function yahan se hata diya hai, 
# kyunki hum har 15 min mein teeno bhashaon mein quiz bhej rahe hain.
# Agar aap sirf ek bhasha mein bhejna chahte hain, to isko database/dict me store karna hoga.

# --- 📣 QUIZ POST KARNE KA MAIN FUNCTION ---
async def send_periodic_quiz(context: ContextTypes.DEFAULT_TYPE):
    """Har 15 minute mein Open Trivia DB se naya sawal fetch karke teeno bhashaon mein bhejta hai."""
    
    if not CHAT_ID:
        # Agar CHAT_ID set nahi hai to log karo
        print("Error: TELEGRAM_CHAT_ID is not set.")
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
        # 1. API se English question fetch karna
        response = requests.get(TRIVIA_API_URL)
        response.raise_for_status() 
        data = response.json()
        
        if data['response_code'] != 0 or not data['results']:
            print(f"API se sawal fetch nahi ho paya for {lang_code}.")
            return

        question_data = data['results'][0]
        
        # HTML entities aur URL encoding decode karna
        question_text = html.unescape(requests.utils.unquote(question_data['question']))
        correct_answer = html.unescape(requests.utils.unquote(question_data['correct_answer']))
        incorrect_answers = [html.unescape(requests.utils.unquote(ans)) for ans in question_data['incorrect_answers']]
        
        # 2. Translation karna
        translated_question = translate_text(question_text, lang_code)
        translated_correct = translate_text(correct_answer, lang_code)
        translated_incorrect = [translate_text(ans, lang_code) for ans in incorrect_answers]
        
        # 3. Options set karna
        all_options = translated_incorrect + [translated_correct]
        random.shuffle(all_options)
        
        correct_option_id = all_options.index(translated_correct)
        
        explanation = translate_text(f"Correct Answer is: {correct_answer}", lang_code) 

        # 4. Quiz Poll bhejte hain
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
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Quiz sent in {lang_code}: '{translated_question[:30]}...'")
        
    except requests.exceptions.RequestException as e:
        print(f"API Request Error: {e}")
    except Exception as e:
        print(f"General Error: {e}")


# --- IMPORTS KE BAAD, AUR BAARI BAARI FUNCTIONS KE BAAD ---
# ... (Apka poora bot code yahan tak)
# ...

# Flask import karein
from flask import Flask

# Web app object banayein
web_app = Flask(__name__)

@web_app.route('/')
def hello_world():
    """Render health check ke liye simple OK response."""
    return 'Bot is running (Polling mode).', 200

# --- 🚀 FINAL MAIN SYNCHRONOUS FUNCTION (Ise chota karna hoga) ---
# Main function mein bada badlav nahi, bas run polling ko start karein
def main(): 
    if not TOKEN or not CHAT_ID:
        print("FATAL ERROR: TELEGRAM_BOT_TOKEN ya TELEGRAM_CHAT_ID environment variable set nahi hai.")
        return

    # PTB v20.x Application
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    
    # BackgroundScheduler (Same as before)
    scheduler = BackgroundScheduler() 
    scheduler.add_job(
        send_periodic_quiz, 
        'interval', 
        seconds=900,  
        kwargs={'context': application}, 
        id='periodic_quiz_job'
    )
    scheduler.start()
    
    print("Bot started and scheduler active (har 15 minute mein).")
    
    # run_polling() ko naye thread mein chalao taaki main thread web server ke liye free ho jaaye
    # Bot ko start karne ke liye ek alag thread shuru karein
    import threading
    bot_thread = threading.Thread(target=application.run_polling, kwargs={'poll_interval': 3.0, 'allowed_updates': Update.ALL_TYPES})
    bot_thread.start()
    
    # Main thread ab Flask server chalaegi
    # Render environment se port number lein, default 8080 agar nahi mila toh
    port = int(os.environ.get('PORT', 8080))
    print(f"Flask running on port {port} for Render health check.")
    # Flask ko ab chala dein (Yeh Render ke liye zaroori hai)
    web_app.run(host='0.0.0.0', port=port)


if __name__ == '__main__':
    try:
        main() 
    except (KeyboardInterrupt, SystemExit):
        print("Bot shutdown gracefully.")
