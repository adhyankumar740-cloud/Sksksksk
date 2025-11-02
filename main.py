import telegram
from telegram import Update, constants, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests
import random
import os
import asyncio
from datetime import datetime
import html 

# --- ⚙️ Zaroori Variables (Aapke original code se) ---
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Bhashaon ki mapping
LANG_MAP = {
    "English 🇬🇧": 'en',
    "Hindi 🇮🇳": 'hi',
    "বাংলা 🇧🇩": 'bn'
}

# Simple translation function (Jaisa pichle answer mein tha)
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
        # print(f"Simple Translation Error to {dest_lang}: {e}") # Log hata diya
        return text 

# --- 🎯 COMMANDS (Same as before) ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (Function code same rahega)
    if update.effective_chat.type in [telegram.constants.ChatType.GROUP, telegram.constants.ChatType.SUPERGROUP]:
        await update.message.reply_text("Quiz har 15 minute mein yahan automatic aayega.")
        return

    keyboard = [[lang for lang in LANG_MAP.keys()]]
    reply_markup = telegram.ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Namaskar! Please select your preferred language for the Quiz:\nनमस्ते! क्विज़ के लिए अपनी पसंदीदा भाषा चुनें:\nনমস্কার! কুইজের জন্য আপনার পছন্দের ভাষা নির্বাচন করুন:",
        reply_markup=reply_markup
    )
    
# --- 📣 QUIZ POST KARNE KA MAIN FUNCTION (Same as before) ---
async def send_periodic_quiz(context: ContextTypes.DEFAULT_TYPE):
    """Har 15 minute mein Open Trivia DB se naya sawal fetch karke teeno bhashaon mein bhejta hai."""
    
    if not CHAT_ID:
        print("Error: CHAT_ID is not set.")
        return
        
    languages_to_send = ['en', 'hi', 'bn'] 

    for lang_code in languages_to_send:
        await fetch_and_send_quiz(context, CHAT_ID, lang_code)
        await asyncio.sleep(5) 

async def fetch_and_send_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id, lang_code):
    # ... (Function code same rahega)
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

# --- 🚀 FINAL MAIN ASYNC FUNCTION ---
# --- 🚀 FINAL MAIN ASYNC FUNCTION ---
async def main(): 
    if not TOKEN or not CHAT_ID:
        print("FATAL ERROR: TELEGRAM_BOT_TOKEN ya TELEGRAM_CHAT_ID environment variable set nahi hai.")
        return

    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    
    # Scheduler ko application ke saath attach karein
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_periodic_quiz, 
        'interval', 
        seconds=900,  
        kwargs={'context': application}, 
        id='periodic_quiz_job'
    )
    
    # Scheduler ko start karein. Ab yeh Application ke loop mein chalega.
    scheduler.start()
    
    print("Bot started and scheduler active (har 15 minute mein).")
    
    # FINAL FIX: run_polling ki jagah run_bufferless() ka use karein.
    # Yeh blocking call hai aur background worker ke liye sahi hai.
    await application.run_bufferless() 

if __name__ == '__main__':
    try:
        # asyncio.run() se main() ko chalao
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        # Graceful exit ke liye
        print("Bot shutdown gracefully.")
