# main.py

import telegram
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import requests
import random
import os
import asyncio
import html 
from datetime import datetime
import logging 

# --- Import Leaderboard Manager ---
import leaderboard_manager 

# --- ⚙️ Constants and Setup ---
QUIZ_TRIGGER_COUNT = 10 
MESSAGE_COUNTER_KEY = 'message_count'
LOCK_KEY = 'quiz_in_progress' 
LAST_GLOBAL_QUIZ_KEY = 'last_global_quiz_time'
GLOBAL_INTERVAL_MIN = 10 

# --- Placeholder for Video URLs ---
# ⚠️ IMPORTANT: These must be Telegram File IDs or direct HTTPS URLs.
WELCOME_VIDEO_URLS = [
    "https://files.catbox.moe/4mjz8l.mp4", 
    "https://files.catbox.moe/hxkkvt.mp4", 
]

# Logging Setup (Same)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Zaroori Variables
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL') 


# --- 🎯 COMMANDS

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot start hone par welcome message deta hai aur DM/Group ko register karta hai।"""
    
    leaderboard_manager.setup_database() 
    leaderboard_manager.register_chat(update) 
    
    if update.effective_chat.type in [telegram.constants.ChatType.GROUP, telegram.constants.ChatType.SUPERGROUP]:
        await update.message.reply_text(
            f"Welcome! Quiz schedule is active. Check /leaderboard and /profile! 🥳"
        )
        return

    await update.message.reply_text(
        "Welcome! Your DM is registered for global quiz broadcasts. Use /profile to check your stats."
    )

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Naye member ke join hone par welcome message aur video bhejta hai।"""
    
    leaderboard_manager.register_chat(update) # Ensure chat is registered
    
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue # Bots ko welcome na karein

        chat_id = update.effective_chat.id
        chat_name = update.effective_chat.title
        
        # Use HTML mention for better compatibility
        user_mention = member.mention_html()
        user_id = member.id
        
        welcome_message = (
            f"👋 *Welcome to {chat_name}*!\n\n"
            f"User: {user_mention}\n"
            f"Telegram ID: `{user_id}`\n\n"
            f"Chat karo aur leaderboard mein jagah banao! 🏆"
        )
        
        # 2. Video Rotation Logic (using bot_data for temporary rotation state)
        if not WELCOME_VIDEO_URLS:
            logger.warning("WELCOME_VIDEO_URLS not set.")
            video_url = None
        else:
            video_index = context.bot_data.get('video_counter', 0)
            video_url = WELCOME_VIDEO_URLS[video_index % len(WELCOME_VIDEO_URLS)]
            context.bot_data['video_counter'] = video_index + 1
        
        # 3. Video aur Message bhejein
        try:
            if video_url:
                await context.bot.send_video(
                    chat_id=chat_id, 
                    video=video_url,
                    caption=welcome_message,
                    parse_mode=constants.ParseMode.MARKDOWN_V2
                )
            else:
                 raise Exception("No video URL found.")
        except Exception as e:
            logger.error(f"Failed to send welcome video to {chat_id}: {e}")
            # Agar video fail ho to sirf message bhej dein
            await context.bot.send_message(
                chat_id=chat_id,
                text=welcome_message,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )

# --- 📣 QUIZ LOGIC (Simplified) ---

async def fetch_quiz_data_from_api():
    """Open Trivia DB se single quiz data fetch karta hai।"""
    TRIVIA_API_URL = "https://opentdb.com/api.php?amount=1&type=multiple"
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
    """Diye गए chat_id पर poll bhejta hai।"""
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
    """सभी सक्रिय ग्रुप्स और DMs को क्विज़ भेजता है।"""
    
    bot_data = context.bot_data
    # Chats database se fetch ho rahi hain (includes DMs)
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
    # DM (Private) mein bhi counter chalega
    if update.effective_chat.type not in [constants.ChatType.GROUP, constants.ChatType.SUPERGROUP, constants.ChatType.PRIVATE]:
        return
    
    chat_data = context.chat_data
    bot_data = context.bot_data

    # Leaderboard update (DB update) + Chat Registration
    await leaderboard_manager.update_message_count_db(update, context)

    # Quiz timing logic starts here
    if chat_data.get(LOCK_KEY, False):
        return

    count = chat_data.get(MESSAGE_COUNTER_KEY, 0)
    chat_data[MESSAGE_COUNTER_KEY] = count + 1

    if chat_data[MESSAGE_COUNTER_KEY] >= QUIZ_TRIGGER_COUNT:
        
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
            return
        else:
            chat_data[MESSAGE_COUNTER_KEY] = QUIZ_TRIGGER_COUNT - 1 
            logger.info(f"Global time is only {round(time_diff.total_seconds()/60, 2)} min. Waiting...")
            
# --- 🚀 MAIN EXECUTION FUNCTION ---
def main(): 
    if not TOKEN or not WEBHOOK_URL:
        logger.critical("FATAL ERROR: Environment variables missing.")
        return
        
    # Database setup must run before the bot starts
    leaderboard_manager.setup_database()

    application = Application.builder().token(TOKEN).concurrent_updates(True).build()
    
    # Handlers add karein
    application.add_handler(CommandHandler("start", start_command))
    
    # 💡 NEW: Welcome Message Handler
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))

    # Leaderboard, Profile, and Broadcast commands
    application.add_handler(CommandHandler("broadcast", leaderboard_manager.broadcast_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_manager.leaderboard_command))
    application.add_handler(CommandHandler("profile", leaderboard_manager.profile_command))
    application.add_handler(CallbackQueryHandler(leaderboard_manager.leaderboard_callback, pattern='^lb_')) 
    
    # Message Handler (Updates counter and checks quiz trigger)
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            send_quiz_after_n_messages
        )
    )
    
    PORT = int(os.environ.get("PORT", "8000")) 
    
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutdown gracefully.")
