import telegram
from telegram import Update, constants, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import requests
import random
import os
import asyncio
import html 
import logging 

# --- ⚙️ Constants and Setup ---
QUIZ_TRIGGER_COUNT = 10 # Har 10 message ke baad quiz bheja jaayega
MESSAGE_COUNTER_KEY = 'message_count'
LOCK_KEY = 'quiz_in_progress' 

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

# --- ❌ Translation Function Removed ---

# --- 🎯 COMMANDS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot start hone par welcome message deta hai."""
    
    if update.effective_chat.type in [telegram.constants.ChatType.GROUP, telegram.constants.ChatType.SUPERGROUP]:
        await update.message.reply_text(
            f"Welcome! This is an English-only Quiz Bot. A new quiz will automatically appear every **{QUIZ_TRIGGER_COUNT}** messages. Keep the conversation going! 🥳"
        )
        return

    await update.message.reply_text(
        "Welcome! This is an English-only Quiz Bot. The quiz will appear automatically in the group chat."
    )


# --- 📣 QUIZ POST KARNE KA MAIN FUNCTION (Simplified) ---
async def send_periodic_quiz(context: ContextTypes.DEFAULT_TYPE):
    """
    Message counter se trigger hone par Open Trivia DB se sawal fetch karke sirf English mein bhejta hai.
    """
    
    chat_id = CHAT_ID
    if not chat_id and context._chat_id:
        chat_id = context._chat_id 
        
    if not chat_id:
        logger.error("CHAT_ID not available to send the quiz.")
        return
        
    # Sirf English mein bhej rahe hain, koi loop nahi
    await fetch_and_send_quiz(context, chat_id)
    

async def fetch_and_send_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id):
    """API se English sawal fetch karta hai aur bhejta hai।"""
    
    # 💡 CHANGED: '&encode=url_legacy' parameter hata diya gaya hai. 
    # Yeh Invalid Parameter (Code 2) error ko rokta hai aur API ko stable rakhta hai.
    TRIVIA_API_URL = "https://opentdb.com/api.php?amount=1&type=multiple"
    
    try:
        # Single API call, so no 429 error expected now
        response = requests.get(TRIVIA_API_URL, timeout=5)
        response.raise_for_status() 
        data = response.json()
        
        # ⚠️ NOTE: Response Code 1 (No Results) bhi aa sakta hai.
        # Simple error handling for Code 1 and Code 2:
        if data['response_code'] != 0 or not data['results']:
            logger.warning(f"API se sawal fetch nahi ho paya. Response Code: {data.get('response_code')}. Please try again later.")
            return

        question_data = data['results'][0]
        
        # Decode and unescape (original logic still works for basic encoding)
        question_text = html.unescape(requests.utils.unquote(question_data['question']))
        correct_answer = html.unescape(requests.utils.unquote(question_data['correct_answer']))
        incorrect_answers = [html.unescape(requests.utils.unquote(ans)) for ans in question_data['incorrect_answers']]
        
        # Options
        all_options = incorrect_answers + [correct_answer]
        random.shuffle(all_options)
        correct_option_id = all_options.index(correct_answer)
        explanation = f"Correct Answer: {correct_answer}" 

        # Quiz Poll bhejte hain
        await context.bot.send_poll(
            chat_id=chat_id,
            question=question_text,
            options=all_options,
            type=constants.PollType.QUIZ,
            correct_option_id=correct_option_id,
            explanation=explanation,
            is_anonymous=True, 
            open_period=600 # 10 minutes
        )
        logger.info(f"English Quiz sent to {chat_id}: '{question_text[:30]}...'")
        
    except requests.exceptions.HTTPError as e:
        logger.error(f"API Request Error: {e}")
    except Exception as e:
        logger.error(f"General Error during quiz send: {e}")
# --- 🎯 Message Counter Logic (No change in logic, only in function call) ---
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
            # Quiz bhejein - Ab yeh bahut tez hoga!
            await send_periodic_quiz(context) 
        except Exception as e:
            logger.error(f"Error during overall quiz send process: {e}")
        finally:
            # 5. Lock hatayein aur counter reset karein
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
