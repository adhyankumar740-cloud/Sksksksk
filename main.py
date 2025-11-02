import telegram
from telegram import Update, constants, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests
import random
import os
import asyncio
from datetime import datetime
import html # HTML entities ko decode karne ke liye

# --- ⚙️ Zaroori Variables ---
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Bhashaon ki mapping
LANG_MAP = {
    "English 🇬🇧": 'en',
    "Hindi 🇮🇳": 'hi',
    "বাংলা 🇧🇩": 'bn'
}

# Simple translation function using Google's free unofficial endpoint
# NOTE: Yeh official API nahi hai, Render par high load se yeh fail ho sakta hai.
def translate_text(text, dest_lang):
    if dest_lang == 'en':
        return text
    
    # Google Translate API ka free unofficial endpoint
    TRANSLATE_URL = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl={dest_lang}&dt=t&q={requests.utils.quote(text)}"
    
    try:
        response = requests.get(TRANSLATE_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        # Translation result nikalna
        translated_text = "".join(item[0] for item in data[0])
        return translated_text
        
    except Exception as e:
        print(f"Simple Translation Error to {dest_lang}: {e}")
        return text # Translation fail hone par original text wapas kar do

# --- 🎯 COMMANDS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot start hone par bhasha chune ka option deta hai (group chat ke liye nahi)."""
    # Group me start command ko ignore karna behtar hai
    if update.effective_chat.type in [telegram.constants.ChatType.GROUP, telegram.constants.ChatType.SUPERGROUP]:
        await update.message.reply_text("Quiz har 15 minute mein yahan automatic aayega.")
        return

    keyboard = [[lang for lang in LANG_MAP.keys()]]
    reply_markup = telegram.ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Namaskar! Please select your preferred language for the Quiz:\nनमस्ते! क्विज़ के लिए अपनी पसंदीदा भाषा चुनें:\nনমস্কার! কুইজের জন্য আপনার পছন্দের ভাষা নির্বাচন করুন:",
        reply_markup=reply_markup
    )
    
# --- 📣 QUIZ POST KARNE KA MAIN FUNCTION ---
async def send_periodic_quiz(context: ContextTypes.DEFAULT_TYPE):
    """Har 15 minute mein Open Trivia DB se naya sawal fetch karke teeno bhashaon mein bhejta hai."""
    
    if not CHAT_ID:
        print("Error: CHAT_ID is not set.")
        return
        
    # Sirf un languages mein bhejo jo hamare pass hain
    languages_to_send = ['en', 'hi', 'bn'] 

    for lang_code in languages_to_send:
        await fetch_and_send_quiz(context, CHAT_ID, lang_code)
        await asyncio.sleep(5) # API rate limit se bachne ke liye delay

async def fetch_and_send_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id, lang_code):
    """API se sawal fetch karta hai aur di gayi bhasha mein translate karke bhejta hai."""
    
    # URL encoded data fetch karne ke liye
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
            type=telegram.constants.PollType.QUIZ,
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


# --- 🚀 MAIN FUNCTION ---
def main():
    if not TOKEN or not CHAT_ID:
        print("FATAL ERROR: TELEGRAM_BOT_TOKEN ya TELEGRAM_CHAT_ID environment variable set nahi hai.")
        return

    # PTB v20.x Application
    application = Application.builder().token(TOKEN).build()
    
    # Commands aur Messages
    application.add_handler(CommandHandler("start", start_command))
    
    # Scheduler set karna
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_periodic_quiz, 
        'interval', 
        seconds=900,  # Har 15 minute (900 seconds)
        kwargs={'context': application}, 
        id='periodic_quiz_job'
    )
    scheduler.start()
    
    print("Bot started and scheduler active.")
    
    # application.run_polling() ki jagah hum run_non_blocking use karenge Render Worker ke liye
    application.run_polling(poll_interval=3.0) 

if __name__ == '__main__':
    main()
