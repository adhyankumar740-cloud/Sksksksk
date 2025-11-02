import telegram
from telegram import Update, constants, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests
import random
import os
import asyncio
from datetime import datetime

# Translation Library
from googletrans import Translator, LANGUAGES

# --- ⚙️ Zaroori Variables ---
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# User ki language store karne ke liye (Simple Dict for single group)
# Production bot mein yeh Database mein store hota hai.
USER_LANGUAGES = {} # Format: {chat_id: 'hi', ...}

# Bhashaon ki mapping
LANG_MAP = {
    "English 🇬🇧": 'en',
    "Hindi 🇮🇳": 'hi',
    "বাংলা 🇧🇩": 'bn'
}

# --- Translation Function ---
def translate_text(text, dest_lang):
    if dest_lang == 'en':
        return text
    try:
        translator = Translator()
        # Source language ko English assume kiya hai (Open Trivia DB se aata hai)
        translation = translator.translate(text, dest=dest_lang, src='en')
        return translation.text
    except Exception as e:
        print(f"Translation Error to {dest_lang}: {e}")
        return text # Translation fail hone par original text wapas kar do

# --- 🎯 COMMANDS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot start hone par bhasha chune ka option deta hai."""
    keyboard = [[KeyboardButton(lang) for lang in LANG_MAP.keys()]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Namaskar! Please select your preferred language for the Quiz:\nनमस्ते! क्विज़ के लिए अपनी पसंदीदा भाषा चुनें:\nনমস্কার! কুইজের জন্য আপনার পছন্দের ভাষা নির্বাচন করুন:",
        reply_markup=reply_markup
    )

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User ki chuni hui bhasha ko save karta hai."""
    chat_id = str(update.effective_chat.id)
    selected_lang_name = update.message.text
    
    if selected_lang_name in LANG_MAP:
        lang_code = LANG_MAP[selected_lang_name]
        USER_LANGUAGES[chat_id] = lang_code
        
        if lang_code == 'hi':
            response_text = "धन्यवाद! आपको अब हिंदी में सवाल मिलेंगे।"
        elif lang_code == 'bn':
            response_text = "ধন্যবাদ! আপনি এখন বাংলাতে প্রশ্ন পাবেন।"
        else:
            response_text = "Thank you! You will now receive questions in English."
            
        await update.message.reply_text(response_text)
        print(f"Chat {chat_id} set to {lang_code}")
    else:
        # Agar koi random message aaya ho to ignore kar do
        pass


# --- 📣 QUIZ POST KARNE KA MAIN FUNCTION ---
async def send_periodic_quiz(context: ContextTypes.DEFAULT_TYPE):
    """Har 15 minute mein Open Trivia DB se naya sawal fetch karke bhejta hai."""
    
    # Simple logic: Har 15 minute mein teeno languages mein quiz bhej do
    
    # Agar aap sirf us bhasha mein bhejenge jo 'set' ki gayi hai to:
    # for chat_id, lang_code in USER_LANGUAGES.items():
    #     await fetch_and_send_quiz(context, chat_id, lang_code)
    
    # Lekin automatic bot ke liye, hum simple rakhenge aur har 15 min mein send karenge.
    
    # Hum yahan CHAT_ID ko use karke main group mein send karenge
    
    if not CHAT_ID:
        print("Error: CHAT_ID is not set.")
        return
        
    # Sirf un languages mein bhejo jo hamare pass hain
    languages_to_send = ['en', 'hi', 'bn'] 

    for lang_code in languages_to_send:
        await fetch_and_send_quiz(context, CHAT_ID, lang_code)
        # Ek quiz ke baad thoda delay do (API limit ke liye)
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
        
        # HTML entities decode karna (Open Trivia DB data ko saaf karta hai)
        question_text = requests.utils.unquote(question_data['question'])
        correct_answer = requests.utils.unquote(question_data['correct_answer'])
        incorrect_answers = [requests.utils.unquote(ans) for ans in question_data['incorrect_answers']]
        
        # 2. Translation karna
        translated_question = translate_text(question_text, lang_code)
        translated_correct = translate_text(correct_answer, lang_code)
        translated_incorrect = [translate_text(ans, lang_code) for ans in incorrect_answers]
        
        # 3. Options set karna
        all_options = translated_incorrect + [translated_correct]
        random.shuffle(all_options)
        
        # Sahi jawab ka naya index dhundna
        correct_option_id = all_options.index(translated_correct)
        
        explanation = translate_text(f"Correct Answer: {correct_answer}", lang_code) # Explanation ko bhi translate karna

        # 4. Quiz Poll bhejte hain
        await context.bot.send_poll(
            chat_id=chat_id,
            question=translated_question,
            options=all_options,
            type=constants.PollType.QUIZ,
            correct_option_id=correct_option_id,
            explanation=explanation,
            is_anonymous=True, # Taki sab log free se jawab de sakein
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
        print("FATAL ERROR: Environment Variable set nahi hai.")
        return

    application = Application.builder().token(TOKEN).build()
    
    # Commands aur Messages
    application.add_handler(CommandHandler("start", start_command))
    # Language selection buttons ke liye
    application.add_handler(MessageHandler(filters.Text(list(LANG_MAP.keys())), set_language))
    
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
    
    # Bot ko chalu rakhega
    application.run_polling(poll_interval=3.0)

if __name__ == '__main__':
    main()
