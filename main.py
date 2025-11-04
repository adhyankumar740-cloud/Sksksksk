# main.py

import telegram
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import requests
import random
import os
import asyncio
import html 
from datetime import datetime, timedelta
import logging 

# --- 💡 NEW: Import Leaderboard Manager ---
import leaderboard_manager 

# --- ⚙️ Constants and Setup ---
QUIZ_TRIGGER_COUNT = 10 
MESSAGE_COUNTER_KEY = 'message_count'
LOCK_KEY = 'quiz_in_progress' 
LAST_GLOBAL_QUIZ_KEY = 'last_global_quiz_time'
GLOBAL_INTERVAL_MIN = 10 

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Zaroori Variables
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL') 


# --- 🎯 COMMANDS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot start hone par welcome message deta hai aur database setup karta hai।"""
    
    # 💡 NEW: Database setup on start (should ideally run only once on deployment)
    leaderboard_manager.setup_database() 
    
    if update.effective_chat.type in [telegram.constants.ChatType.GROUP, telegram.constants.ChatType.SUPERGROUP]:
        await update.message.reply_text(
            f"Welcome! Quiz schedule is active. Check /leaderboard and /profile!"
        )
        return

    await update.message.reply_text(
        "Welcome! Use /leaderboard in a group to see who talks the most."
    )


# --- 📣 QUIZ FETCH and SEND HELPERS (Quiz logic kept simple) ---

async def fetch_quiz_data_from_api():
    """Open Trivia DB se single quiz data fetch karta hai।"""
    TRIVIA_API_URL = "https://opentdb.com/api.php?amount=1&type=multiple"
    # ... (Rest of the fetch logic, same as previous version) ...
    try:
        response = requests.get(TRIVIA_API_URL, timeout=5)
        response.raise_for_status() 
        data = response.json()
        
        if data['response_code'] != 0 or not data['results']:
            return None

        question_data = data['results'][0]
        question_text = html.unescape(requests.utils.unquote(question_data['question']))
        correct_answer = html.unescape(requests.utils.unquote(question_data['correct_answer']))
        incorrect_answers = [html.unescape(requests.utils.unquote(ans)) for ans in question_data['incorrect_answers']]
        
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
    """Diye gaye chat_id par poll bhejta hai।"""
    # ... (Same as previous version) ...
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
    """सभी सक्रिय ग्रुप्स को क्विज़ भेजता है।"""
    
    bot_data = context.bot_data
    # 💡 NEW: Chats database se fetch ho rahi hain
    chat_ids = leaderboard_manager.get_all_active_chat_ids()
    
    if not chat_ids:
        logger.warning("No active chats registered for broadcast.")
        return

    quiz_data = await fetch_quiz_data_from_api()
    if not quiz_data:
        logger.error("Failed to fetch quiz data globally, cancelling broadcast.")
        return

    successful_sends = 0
    for chat_id in list(chat_ids):
        try:
            await send_poll_to_chat(context, chat_id, quiz_data) 
            successful_sends += 1
            await asyncio.sleep(0.5) 
        except Exception as e:
            logger.error(f"Failed to send quiz to {chat_id}: {e}")

    bot_data[LAST_GLOBAL_QUIZ_KEY] = datetime.now().timestamp()
    logger.info(f"Broadcast successful to {successful_sends} chats. Global timer reset.")


# --- 🎯 CORE MESSAGE COUNTER LOGIC (Global Check) ---
async def send_quiz_after_n_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    chat_id = update.effective_chat.id
    if update.effective_chat.type not in [telegram.constants.ChatType.GROUP, telegram.constants.ChatType.SUPERGROUP]:
        return

    chat_data = context.chat_data
    bot_data = context.bot_data

    # 💡 NEW: Leaderboard update (DB update)
    await leaderboard_manager.update_message_count_db(update, context)

    # 1. Lock check
    if chat_data.get(LOCK_KEY, False):
        return

    # 2. Counter update (still needed for quiz timing logic)
    count = chat_data.get(MESSAGE_COUNTER_KEY, 0)
    chat_data[MESSAGE_COUNTER_KEY] = count + 1
    logger.info(f"Message Count in chat {chat_id}: {chat_data[MESSAGE_COUNTER_KEY]}")

    # 3. Check for Quiz Trigger (10 messages)
    if chat_data[MESSAGE_COUNTER_KEY] >= QUIZ_TRIGGER_COUNT:
        logger.info(f"Trigger reached in chat {chat_id}. Checking global time lock.")
        
        last_global_time_ts = bot_data.get(LAST_GLOBAL_QUIZ_KEY, 0)
        last_global_time = datetime.fromtimestamp(last_global_time_ts)
        time_diff = datetime.now() - last_global_time
        
        if time_diff.total_seconds() >= GLOBAL_INTERVAL_MIN * 60:
            logger.info("Global interval passed (>= 10 minutes). Starting global broadcast.")
            
            chat_data[LOCK_KEY] = True 
            
            try:
                await broadcast_quiz(context) 
            except Exception as e:
                logger.error(f"Global Quiz failed: {e}")
            finally:
                chat_data[MESSAGE_COUNTER_KEY] = 0 
                chat_data[LOCK_KEY] = False 
                logger.info("Global quiz process finished and counters reset.")
            return
        else:
            chat_data[MESSAGE_COUNTER_KEY] = QUIZ_TRIGGER_COUNT - 1 
            logger.info(f"Global time is only {round(time_diff.total_seconds()/60, 2)} min. Waiting...")
            
# --- 🚀 MAIN EXECUTION FUNCTION ---
def main(): 
    if not TOKEN or not WEBHOOK_URL:
        logger.critical("FATAL ERROR: Environment variables missing.")
        return
        
    # Database setup should run before bot starts handling updates
    leaderboard_manager.setup_database()

    application = Application.builder().token(TOKEN).concurrent_updates(True).build()
    
    # Handlers add karein
    application.add_handler(CommandHandler("start", start_command))
    
    # 💡 NEW: Leaderboard and Profile commands from manager file
    application.add_handler(CommandHandler("leaderboard", leaderboard_manager.leaderboard_command))
    application.add_handler(CommandHandler("profile", leaderboard_manager.profile_command))
    application.add_handler(CallbackQueryHandler(leaderboard_manager.leaderboard_callback, pattern='^lb_')) # Inline button handler
    
    # Message Handler (Updates counter and checks quiz trigger)
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            send_quiz_after_n_messages
        )
    )
    
    PORT = int(os.environ.get("PORT", "8000")) 
    
    logger.info("Bot starting with Database and Global Scheduler Logic...")
    
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
