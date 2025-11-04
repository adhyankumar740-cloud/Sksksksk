import telegram
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import requests
import random
import os
import asyncio
import html 
from datetime import datetime, timedelta
import logging 

# --- ⚙️ Constants and Setup ---
QUIZ_TRIGGER_COUNT = 10 # Quiz har 10 message ke baad check hoga
MESSAGE_COUNTER_KEY = 'message_count'
LOCK_KEY = 'quiz_in_progress' 
LAST_GLOBAL_QUIZ_KEY = 'last_global_quiz_time' # Global time key (Timestamp)
GLOBAL_INTERVAL_MIN = 10 # Quiz har 10 minute mein ek baar
# CATCHUP_INTERVAL_MIN = 60 # Filhaal ise nahi use kar rahe hain
ACTIVE_CHATS_KEY = 'active_chats' # Sabhi groups ki list store karne ke liye

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Zaroori Variables (Environment variables se fetch karein)
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL') 
# CHAT_ID ki ab koi zaroorat nahi hai.

# --- 🎯 COMMANDS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot start hone par welcome message deta hai aur chat ko register karta hai।"""
    
    chat_id = update.effective_chat.id
    
    # Chat registration
    if 'active_chats' not in context.bot_data:
        context.bot_data[ACTIVE_CHATS_KEY] = set()
    context.bot_data[ACTIVE_CHATS_KEY].add(chat_id)
    
    if update.effective_chat.type in [telegram.constants.ChatType.GROUP, telegram.constants.ChatType.SUPERGROUP]:
        await update.message.reply_text(
            f"Welcome! This is an **English Quiz Bot**. Har **{QUIZ_TRIGGER_COUNT}** messages ke baad check hoga ki kya **10 minute** ho gaye hain. Agar ho gaye hain, to sabhi groups ko naya quiz bheja jayega! 🥳"
        )
        return

    await update.message.reply_text(
        "Welcome! This is an English Quiz Bot. The quiz scheduling works based on message activity across all registered groups."
    )

# --- 📣 QUIZ FETCH and SEND HELPERS ---

async def fetch_quiz_data_from_api():
    """Open Trivia DB se single quiz data fetch karta hai."""
    TRIVIA_API_URL = "https://opentdb.com/api.php?amount=1&type=multiple"
    
    try:
        response = requests.get(TRIVIA_API_URL, timeout=5)
        response.raise_for_status() 
        data = response.json()
        
        if data['response_code'] != 0 or not data['results']:
            logger.warning(f"API se sawal fetch nahi ho paya. Response Code: {data.get('response_code')}")
            return None

        question_data = data['results'][0]
        
        # Decode and unescape
        question_text = html.unescape(requests.utils.unquote(question_data['question']))
        correct_answer = html.unescape(requests.utils.unquote(question_data['correct_answer']))
        incorrect_answers = [html.unescape(requests.utils.unquote(ans)) for ans in question_data['incorrect_answers']]
        
        # Options
        all_options = incorrect_answers + [correct_answer]
        random.shuffle(all_options)
        correct_option_id = all_options.index(correct_answer)
        explanation = f"Correct Answer: {correct_answer}" 
        
        return {
            'question': question_text,
            'options': all_options,
            'correct_option_id': correct_option_id,
            'explanation': explanation
        }
        
    except Exception as e:
        logger.error(f"Error fetching quiz data from API: {e}")
        return None

async def send_poll_to_chat(context: ContextTypes.DEFAULT_TYPE, chat_id, quiz_data):
    """Diye gaye chat_id par poll bhejta hai."""
    
    await context.bot.send_poll(
        chat_id=chat_id,
        question=quiz_data['question'],
        options=quiz_data['options'],
        type=constants.PollType.QUIZ,
        correct_option_id=quiz_data['correct_option_id'],
        explanation=quiz_data['explanation'],
        is_anonymous=True, 
        open_period=600 # 10 minutes
    )
    logger.info(f"English Quiz sent successfully to chat: {chat_id}.")


async def broadcast_quiz(context: ContextTypes.DEFAULT_TYPE):
    """सभी सक्रिय ग्रुप्स को क्विज़ भेजता है और Global Timer रीसेट करता है।"""
    
    bot_data = context.bot_data
    chat_ids = bot_data.get(ACTIVE_CHATS_KEY, set())
    
    if not chat_ids:
        logger.warning("No active chats registered for broadcast.")
        return

    # 1. Sabse pehle quiz data fetch karein
    quiz_data = await fetch_quiz_data_from_api()
    if not quiz_data:
        logger.error("Failed to fetch quiz data globally, cancelling broadcast.")
        return

    # 2. Sabhi chats ko quiz bhejein
    successful_sends = 0
    # Copy of set to safely modify if needed (e.g., discard inactive chat)
    chats_to_send = list(chat_ids) 
    
    for chat_id in chats_to_send:
        try:
            await send_poll_to_chat(context, chat_id, quiz_data) 
            successful_sends += 1
            await asyncio.sleep(0.5) # Telegram Rate Limit se bachne ke liye
        except telegram.error.BadRequest as e:
            if "chat not found" in str(e).lower() and chat_id in bot_data.get(ACTIVE_CHATS_KEY, set()):
                 logger.warning(f"Removing inactive chat: {chat_id}")
                 bot_data[ACTIVE_CHATS_KEY].discard(chat_id)
        except Exception as e:
            logger.error(f"Failed to send quiz to {chat_id}: {e}")

    # 3. Global timer ko reset karein
    bot_data[LAST_GLOBAL_QUIZ_KEY] = datetime.now().timestamp()
    logger.info(f"Broadcast successful to {successful_sends} chats. Global timer reset.")


# --- 🎯 CORE MESSAGE COUNTER LOGIC (Global Check) ---
async def send_quiz_after_n_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    # Initial checks
    chat_id = update.effective_chat.id
    if update.effective_chat.type not in [telegram.constants.ChatType.GROUP, telegram.constants.ChatType.SUPERGROUP]:
        return

    chat_data = context.chat_data
    bot_data = context.bot_data

    # 0. Register Chat (For broadcast list)
    if 'active_chats' not in bot_data:
        bot_data[ACTIVE_CHATS_KEY] = set()
    bot_data[ACTIVE_CHATS_KEY].add(chat_id)

    # 1. Lock check and Counter update
    if chat_data.get(LOCK_KEY, False):
        return

    count = chat_data.get(MESSAGE_COUNTER_KEY, 0)
    chat_data[MESSAGE_COUNTER_KEY] = count + 1
    logger.info(f"Message Count in chat {chat_id}: {chat_data[MESSAGE_COUNTER_KEY]}")

    # 2. Check for Quiz Trigger (10 messages)
    if chat_data[MESSAGE_COUNTER_KEY] >= QUIZ_TRIGGER_COUNT:
        logger.info(f"Trigger reached in chat {chat_id}. Checking global time lock.")
        
        last_global_time_ts = bot_data.get(LAST_GLOBAL_QUIZ_KEY, 0)
        last_global_time = datetime.fromtimestamp(last_global_time_ts)
        
        # 3. GLOBAL CHECK: Kya 10 minute ho gaye hain?
        time_diff = datetime.now() - last_global_time
        
        if time_diff.total_seconds() >= GLOBAL_INTERVAL_MIN * 60:
            logger.info("Global interval passed (>= 10 minutes). Starting global broadcast.")
            
            # Lock set
            chat_data[LOCK_KEY] = True 
            
            try:
                # Sabhi chats ko quiz bhejo
                await broadcast_quiz(context) 
            except Exception as e:
                logger.error(f"Global Quiz failed: {e}")
            finally:
                # Quiz chala gaya, to counter reset karo aur lock hatao
                # Yeh reset sabhi groups ke liye agle trigger ka wait karega
                chat_data[MESSAGE_COUNTER_KEY] = 0 
                chat_data[LOCK_KEY] = False 
                logger.info("Global quiz process finished and counters reset.")
            return

        else:
            # 4. Global time nahi hua hai: Bas message count ko reset karo taki
            # agle 10 message ke baad phir se check kiya ja sake.
            
            # Agar aap chahte hain ki yeh 10 se upar jaaye, to yeh line hata sakte hain.
            # Lekin "spam" se bachne ke liye, 10 par rokna behtar hai:
            chat_data[MESSAGE_COUNTER_KEY] = QUIZ_TRIGGER_COUNT - 1 # 10 par hi rok do
            logger.info(f"Global time is only {round(time_diff.total_seconds()/60, 2)} min. Waiting...")
            
# --- 🚀 MAIN EXECUTION FUNCTION (Webhook/Render ke liye) ---
def main(): 
    if not TOKEN or not WEBHOOK_URL:
        logger.critical("FATAL ERROR: TELEGRAM_BOT_TOKEN ya RENDER_EXTERNAL_URL environment variable set nahi hai.")
        return

    application = Application.builder().token(TOKEN).concurrent_updates(True).build()
    
    # Handlers add karein
    application.add_handler(CommandHandler("start", start_command))
    
    # Message Handler: filters.TEXT & ~filters.COMMAND
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            send_quiz_after_n_messages
        )
    )
    
    # Render Webhook Logic
    PORT = int(os.environ.get("PORT", "8000")) 
    
    logger.info("Bot starting with Global Scheduler Logic (Render mode)...")
    
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
