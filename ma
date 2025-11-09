# main.py (Updated to use DB Persistence instead of Pickle)

import telegram
from telegram import Update, constants
# 💡 FIX 1: PicklePersistence ko HATA diya
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from telegram.helpers import escape_markdown
import requests
import random
import os
import asyncio
import html 
from datetime import datetime, timezone # 💡 IMPORT TIMEZONE
import logging 
import traceback
import json
import time 
import tempfile 

# --- Import Leaderboard Manager ---
import leaderboard_manager 
# 💡 NEW: DB persistence functions import karo
from leaderboard_manager import get_spam_data, set_spam_data, get_bot_value, set_bot_value, check_and_set_bot_lock

# --- ⚙️ Constants and Setup ---
# 10 MINUTE COOLDOWN (10 min * 60 sec)
GLOBAL_QUIZ_COOLDOWN = 600 

# Yeh keys ab 'bot_data' (DB) mein use hongi
LOCK_KEY = 'global_quiz_lock' 
LAST_GLOBAL_QUIZ_KEY = 'last_global_quiz_time'
LAST_QUIZ_MESSAGE_KEY = 'last_quiz_message_ids' 

# ... (baaki constants waise hi) ...
WELCOME_VIDEO_URLS = [
    "BAACAgUAAxkBAAIBxWkOFRIw0g1B_7xuSA4cyUE3ShSlAAJKGwAC_MFxVIx6wUDn1qKBNgQ",
    "BAACAgUAAxkBAAIByGkOFV746X7wbcPRCZTVy4iqtaC7AAKmIQACGV5QVJYHM5LZKdVANgQ",
    "BAACAgUAAyEFAATDIfMWAAICe2kNq_8rhMxyunaubyvrjovOEAz_AAIEJQACnClpVEIdwOhLrWhYNgQ",
    "BAACAgUAAyEFAATDIfMWAAIB3mkNk-cqNbscJhwvxWOBcK7PXkUcAAILJQACnClpVFEZkkwlNiBCNgQ",
]

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL') 
OWNER_ID = os.environ.get('OWNER_ID')
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')
STABLE_HORDE_API_KEY = os.environ.get('STABLE_HORDE_API_KEY', '0000000000')

START_PHOTO_ID = os.environ.get('START_PHOTO_ID') 
ABOUT_PHOTO_ID = os.environ.get('ABOUT_PHOTO_ID') 

# --- 💡 NEW SPAM CONSTANTS ---
SPAM_MESSAGE_LIMIT = 5 # 5 messages
SPAM_TIME_WINDOW = 5 # in 5 seconds
SPAM_BLOCK_DURATION = 1200 # 1200 s = 20 मिनट


# --- Error Handler (Unchanged) ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )
    logger.error(message) 
    if update and isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="😕 Oops! Something went wrong. I've reported this to the developer.",
                parse_mode=constants.ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to send error message to chat: {e}")


# --- 🎯 COMMANDS (Unchanged) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Setup DB on start
    leaderboard_manager.setup_database() 
    leaderboard_manager.register_chat(update) 
    
    bot = await context.bot.get_me()
    bot_name = escape_markdown(bot.first_name, version=2)
    user_name = escape_markdown(update.effective_user.first_name, version=2)

    start_text = (
        f"👋 *Hi {user_name}, I'm {bot_name}*\\!\n\n"
        f"I'm here to make this group fun with quizzes and rankings\\.\n\n"
        f"**What I can do:**\n"
        f"• 🏆 Track message rankings \\(/ranking\\)\n"
        f"• 🧠 Run automatic quizzes as you chat\n"
        f"• 👤 Check your stats with \\/profile\n"
        f"• 🖼️ Find images with \\/img `[query]`\n"
        f"• 🎨 Generate images with \\/gen `[prompt]`\n\n"
        f"Just start chatting to activate the next quiz and climb the ranks\\!"
    )

    if START_PHOTO_ID:
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=START_PHOTO_ID,
                caption=start_text,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            logger.error(f"Failed to send start photo: {e}. Sending text instead.")
            await update.message.reply_text(start_text, parse_mode=constants.ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(start_text, parse_mode=constants.ParseMode.MARKDOWN_V2)

# ---
# --- 💡 MODIFIED: Welcome message now uses DB for video counter ---
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.new_chat_members:
        return

    leaderboard_manager.register_chat(update)
    chat_id = update.effective_chat.id
    chat_name = html.escape(update.effective_chat.title or "this chat")

    video_id = None
    if WELCOME_VIDEO_URLS:
        # 💡 DB se counter laao
        video_index = leaderboard_manager.get_bot_value('video_counter', 0)
        
        video_id = WELCOME_VIDEO_URLS[video_index % len(WELCOME_VIDEO_URLS)]
        
        # 💡 DB mein naya counter save karo
        leaderboard_manager.set_bot_value('video_counter', video_index + 1)

    for member in update.message.new_chat_members:
        if member.is_bot:
            continue

        user_mention = member.mention_html()
        user_id = member.id
        welcome_message = (
            f"👋 <b>Welcome to {chat_name}</b>!\n\n"
            f"User: {user_mention}\n"
            f"Telegram ID: <code>{user_id}</code>\n\n"
            f"Chat and earn your spot on the leaderboard! 🏆"
        )

        if not video_id:
            await context.bot.send_message(chat_id=chat_id, text=welcome_message, parse_mode=constants.ParseMode.HTML)
            return

        try:
            await context.bot.send_video(
                chat_id=chat_id,
                video=video_id, 
                caption=welcome_message,
                parse_mode=constants.ParseMode.HTML,
            )
        except telegram.error.BadRequest as e:
            logger.error(f"FATAL: File ID ({video_id}) is still invalid. Error: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{welcome_message}\n\n⚠️ Video loading failed due to invalid File ID.",
                parse_mode=constants.ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Unexpected error during welcome video send: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=welcome_message,
                parse_mode=constants.ParseMode.HTML
            )
                
# --- About Command (Unchanged) ---
async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot = await context.bot.get_me()
    bot_name = escape_markdown(bot.first_name, version=2)
    
    about_text = (
        f"👋 *About Me*\n\n"
        f"Hi, I'm {bot_name}\\!\n\n"
        f"I was created to help manage leaderboards, run quizzes, and have fun\\.\n\n"
        f"**Features:**\n"
        f"• Automatic quizzes\n"
        f"• Message rankings \\(/ranking\\)\n"
        f"• User profiles \\(/profile\\)\n"
        f"• Image search \\(/img\\)\n"
        f"• AI Image generation \\(/gen\\)\n\n"
        f"•Owner: Gopu\n"
    )
    
    if OWNER_ID:
        about_text += f"You can contact my owner for support: [Owner](tg://user?id={OWNER_ID})\n"
    else:
        about_text += "This bot is running without a configured owner\\.\n"
        
    if ABOUT_PHOTO_ID:
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=ABOUT_PHOTO_ID,
                caption=about_text,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            logger.error(f"Failed to send about photo: {e}. Sending text instead.")
            await update.message.reply_text(about_text, parse_mode=constants.ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(about_text, parse_mode=constants.ParseMode.MARKDOWN_V2)


# --- get_id Command (Unchanged) ---
async def get_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Replies to a message (video, photo, sticker, audio) with its File_ID.
    """
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "Please reply to a video, photo, or any media file with this command."
        )
        return
    
    replied_msg = update.message.reply_to_message
    file_id = None
    file_type = None

    if replied_msg.video:
        file_id = replied_msg.video.file_id
        file_type = "Video"
    elif replied_msg.photo:
        file_id = replied_msg.photo[-1].file_id # Get largest photo
        file_type = "Photo"
    elif replied_msg.audio:
        file_id = replied_msg.audio.file_id
        file_type = "Audio"
    elif replied_msg.document:
        file_id = replied_msg.document.file_id
        file_type = "Document"
    elif replied_msg.sticker:
        file_id = replied_msg.sticker.file_id
        file_type = "Sticker"
    
    if file_id:
        response_text = (
            f"<b>{file_type} File ID Found:</b>\n\n"
            f"<code>{file_id}</code>\n\n"
            f"(Copy this ID and paste it into the WELCOME_VIDEO_URLS or PHOTO_ID variables in the code)"
        )
        await update.message.reply_text(response_text, parse_mode=constants.ParseMode.HTML)
    else:
        await update.message.reply_text("Could not find a File ID in the replied message.")


# --- Image Commands (Unchanged) ---
async def img_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not PEXELS_API_KEY:
        await update.message.reply_text("Image search is disabled. `API_KEY` is not configured.")
        return
    if not context.args:
        await update.message.reply_text("Please provide a search term. Example: `/img nature`")
        return
    query = " ".join(context.args)
    url = f"https://api.pexels.com/v1/search?query={query}&per_page=15"
    headers = {"Authorization": PEXELS_API_KEY}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        if not data.get('photos'):
            await update.message.reply_text(f"Sorry, I couldn't find any images for '{query}'.")
            return
        photo = random.choice(data['photos'])
        photo_url = photo['src']['large']
        caption="Your Image"
        await update.message.reply_photo(
            photo_url,
            caption=caption,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    except requests.Timeout:
        await update.message.reply_text("The image search timed out. Please try again.")
    except requests.RequestException as e:
        logger.error(f"Pexels API error: {e}")
        await update.message.reply_text("Sorry, there was an error with the image search.")

async def gen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide a prompt. Example: `/gen a cat in space`")
        return
    prompt = " ".join(context.args)
    sent_msg = await update.message.reply_text(f"🎨 Generating '{prompt}'... This may take a minute.")
    try:
        post_url = "https://stablehorde.net/api/v2/generate/async"
        headers = {"apikey": STABLE_HORDE_API_KEY, "Client-Agent": "TelegramBot/1.0"}
        payload = {
            "prompt": prompt,
            "params": { "n": 1, "width": 512, "height": 512 }
        }
        post_response = requests.post(post_url, json=payload, headers=headers, timeout=10)
        post_response.raise_for_status()
        if 'id' not in post_response.json():
             raise Exception(f"API Error: {post_response.json().get('message', 'Unknown')}")
        generation_id = post_response.json()['id']
        start_time = time.time()

        while True:
            await asyncio.sleep(5)
            if time.time() - start_time > 120:
                await sent_msg.edit_text("Generation timed out. Please try again later.")
                return
            check_url = f"https://stablehorde.net/api/v2/generate/check/{generation_id}"
            check_response = requests.get(check_url, timeout=5)
            check_data = check_response.json()
            if check_data.get('faulted', False):
                await sent_msg.edit_text("Generation failed. The prompt might be invalid or the service is busy.")
                return
            if check_data.get('done', False):
                status_url = f"https://stablehorde.net/api/v2/generate/status/{generation_id}"
                status_response = requests.get(status_url, timeout=5)
                status_data = status_response.json()
                img_url = status_data['generations'][0]['img']
                escaped_prompt = escape_markdown(prompt, version=2)
                await sent_msg.delete()
                await update.message.reply_photo(
                    img_url,
                    caption=f"*Prompt:* {escaped_prompt}\n",
                    parse_mode=constants.ParseMode.MARKDOWN_V2
                )
                return
    except requests.Timeout:
        await sent_msg.edit_text("The generation service timed out. Please try again.")
    except Exception as e:
        logger.error(f"Stable Horde error: {e}")
        await sent_msg.edit_text(f"Sorry, an error occurred during image generation: {e}")


# --- 📣 QUIZ LOGIC (Unchanged) ---
async def fetch_quiz_data_from_api():
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

# --- 💡 QUIZ BROADCAST (MODIFIED to use DB) ---

# Naye message ID wapas lene ke liye (Unchanged)
async def send_quiz_and_track_id(context: ContextTypes.DEFAULT_TYPE, chat_id, quiz_data):
    try:
        sent_message = await context.bot.send_poll(
            chat_id=chat_id,
            question=quiz_data['question'],
            options=quiz_data['options'],
            type=constants.PollType.QUIZ,
            correct_option_id=quiz_data['correct_option_id'],
            explanation=quiz_data['explanation'],
            is_anonymous=True,
            open_period=600 
        )
        logger.info(f"Quiz sent successfully to {chat_id}.")
        return (chat_id, "Success", sent_message.message_id) 
    except (telegram.error.Forbidden, telegram.error.BadRequest) as e:
        logger.warning(f"Failed to send to {chat_id} (Forbidden/Bad Request): {e}. Deactivating chat.")
        # 💡 Deactivate chat in DB
        leaderboard_manager.deactivate_chat_in_db(chat_id)
        return (chat_id, f"Failed_Deactivated: {e}", None)
    except Exception as e:
        logger.error(f"Failed to send quiz to {chat_id} (Timeout/Other): {e}")
        return (chat_id, f"Failed_Error: {e}", None)

# 💡 MODIFIED: Ab yeh DB se 'bot_data' lega
async def broadcast_quiz(context: ContextTypes.DEFAULT_TYPE):
    chat_ids = leaderboard_manager.get_all_active_chat_ids()
    
    if not chat_ids:
        logger.warning("No active chats registered for broadcast.")
        return
        
    quiz_data = await fetch_quiz_data_from_api()
    if not quiz_data:
        logger.error("Failed to fetch quiz data globally, cancelling broadcast.")
        return
        
    # --- 💡 STEP 1: PURANE QUIZZES KO DELETE KAREIN (DB se laakar) ---
    # DB se 'last_quiz_message_ids' (jo ek dict/json hai) nikaalo
    old_quiz_messages = leaderboard_manager.get_bot_value(LAST_QUIZ_MESSAGE_KEY, {})
    new_quiz_messages = {} # Naye IDs store karne ke liye
    
    delete_tasks = []
    if isinstance(old_quiz_messages, dict):
        for chat_id_str, message_id in old_quiz_messages.items():
            try:
                chat_id = int(chat_id_str)
                delete_tasks.append(
                    context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                )
            except ValueError:
                logger.warning(f"Invalid chat_id_str in old_quiz_messages: {chat_id_str}")
    
    if delete_tasks:
        logger.info(f"Attempting to delete {len(delete_tasks)} old quiz messages.")
        await asyncio.gather(*delete_tasks, return_exceptions=True) 
    # ----------------------------------------------------
    
    # --- 💡 STEP 2: NAYA QUIZ BHEJEIN AUR ID STORE KAREIN ---
    tasks = [
        send_quiz_and_track_id(context, chat_id, quiz_data) 
        for chat_id in chat_ids
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    successful_sends = 0
    
    for res in results:
        if isinstance(res, tuple) and res[1] == "Success":
            successful_sends += 1
            chat_id, message_id = res[0], res[2] 
            new_quiz_messages[str(chat_id)] = message_id # Naye ID ko store kar rahe hain
        elif isinstance(res, Exception):
            logger.error(f"An unexpected error occurred during gather: {res}")
            
    # Naye message IDs ko DB mein save karo
    leaderboard_manager.set_bot_value(LAST_QUIZ_MESSAGE_KEY, new_quiz_messages)
    
    # VERY IMPORTANT: Yahan global timer reset ho raha hai (DB mein)
    leaderboard_manager.set_bot_value(LAST_GLOBAL_QUIZ_KEY, datetime.now().timestamp())
    logger.info(f"Broadcast attempt finished. Successful to {successful_sends} / {len(tasks)} chats. Global timer reset. {len(new_quiz_messages)} new quiz IDs stored.")


# --- 🎯 CORE MESSAGE COUNTER LOGIC (💡 MODIFIED FOR DB PERSISTENCE) ---
async def send_quiz_after_n_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    if update.effective_chat.type not in [constants.ChatType.GROUP, constants.ChatType.SUPERGROUP, constants.ChatType.PRIVATE] or not update.effective_user:
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    # 💡 Ab user_data ka istemal nahi karenge

    # --- 1. Spam Protection Logic (DB se) ---
    current_time = time.time()
    
    # 💡 DB se spam data laao
    blocked_until, message_timestamps = leaderboard_manager.get_spam_data(user_id) 
    
    is_blocked = False

    if current_time < blocked_until:
        is_blocked = True
    else:
        # Agar user pehle block tha, toh 'is_blocked' ko explicitly False karein
        if blocked_until > (current_time - SPAM_BLOCK_DURATION):
             logger.info(f"User {user_id} is now unblocked.")
             # DB mein blocked_until ko update karne ki zaroorat nahi, 
             # bas timestamps ko process karo

        message_timestamps = message_timestamps or [] # Ensure it's a list
        time_window_start = current_time - SPAM_TIME_WINDOW
        recent_timestamps = [t for t in message_timestamps if t > time_window_start]
        recent_timestamps.append(current_time)
        
        if len(recent_timestamps) >= SPAM_MESSAGE_LIMIT:
            is_blocked = True
            new_blocked_until = current_time + SPAM_BLOCK_DURATION
            new_timestamps_list = [] # Timestamps clear karo
            
            # 💡 DB mein naya block time save karo
            leaderboard_manager.set_spam_data(user_id, new_blocked_until, new_timestamps_list)
            
            logger.info(f"User {user_id} blocked for spamming.")
            
            try:
                username = update.effective_user.username
                mention = f"@{username}" if username else update.effective_user.mention_html()
                
                await update.message.reply_text(
                    f"{mention} <b>You have been blocked for {int(SPAM_BLOCK_DURATION/60)} min for spamming!</b>\n"
                    f"Your messages will not be counted in the leaderboard.",
                    parse_mode=constants.ParseMode.HTML
                )
            except Exception as e:
                logger.warning(f"Failed to send spam warning: {e}")
        else:
            # 💡 DB mein naye timestamps save karo (block time wahi rahega)
            leaderboard_manager.set_spam_data(user_id, blocked_until, recent_timestamps)

    # --- 2. Update DB (Leaderboard) ---
    if not is_blocked:
        await leaderboard_manager.update_message_count_db(update, context)
    
    # --- 3. Check for Quiz (Global Logic using DB) ---
    
    # 💡 DB se last quiz time laao
    last_quiz_time = leaderboard_manager.get_bot_value(LAST_GLOBAL_QUIZ_KEY, 0)
    
    if current_time - last_quiz_time > GLOBAL_QUIZ_COOLDOWN:
        # Cooldown poora ho gaya hai.
        
        # 💡 DB mein ATOMIC lock lagane ki koshish karo
        if not leaderboard_manager.check_and_set_bot_lock(LOCK_KEY):
            # Lock nahi mila (koi aur process pehle se kar raha hai)
            return
        
        try:
            logger.info(f"Global quiz cooldown over. Triggered by user {user_id} in chat {chat_id}. Broadcasting to all.")
            
            # Global broadcast function ko call karo
            # Yeh function khud hi 'LAST_GLOBAL_QUIZ_KEY' ko DB mein reset kar dega
            await broadcast_quiz(context) 
            
        except Exception as e:
            logger.error(f"Error during global quiz broadcast trigger: {e}")
        finally:
            # 💡 Kaam hote hi lock DB se hata do
            leaderboard_manager.set_bot_value(LOCK_KEY, False)
    else:
        # Cooldown abhi chal raha hai. Kuch nahi karna.
        pass
    
            
            
# --- 🚀 MAIN EXECUTION FUNCTION (MODIFIED) ---
def main(): 
    if not TOKEN or not WEBHOOK_URL:
        logger.critical("FATAL ERROR: Environment variables missing (TOKEN or WEBHOOK_URL).")
        return
        
    # 💡 Bot start hote hi DB setup karega
    leaderboard_manager.setup_database()

    # --- 💡 FIX 1: PERSISTENCE HATA DI GAYI ---
    # persistence = PicklePersistence(...) # <-- ISKI ZAROORAT NAHI HAI

    application = (
        Application.builder()
        .token(TOKEN)
        # .persistence(persistence)  # <-- HATA DIYA GAYA
        .concurrent_updates(True)
        .connect_timeout(10)   
        .read_timeout(15)      
        .write_timeout(15)     
        .http_version('1.1')
        .build()
    )
    
    # Register the error handler
    application.add_error_handler(error_handler)
    
    # --- Add all handlers (Unchanged) ---
    
    # Standard Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("broadcast", leaderboard_manager.broadcast_command))

    # Leaderboard Commands
    application.add_handler(CommandHandler("ranking", leaderboard_manager.ranking_command))
    application.add_handler(CommandHandler("profile", leaderboard_manager.profile_command))
    application.add_handler(CommandHandler("prof", leaderboard_manager.profile_command))
    application.add_handler(CallbackQueryHandler(leaderboard_manager.leaderboard_callback, pattern='^lb_'))
    
    # New Image Commands
    application.add_handler(CommandHandler("img", img_command))
    application.add_handler(CommandHandler("gen", gen_command))

    # NAYA COMMAND
    application.add_handler(CommandHandler("get_id", get_id_command))

    # Message Handlers
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    
    # Message handler
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            send_quiz_after_n_messages
        )
    )
    
    PORT = int(os.environ.get("PORT", "8000")) 
    
    logger.info("Starting bot webhook (with DB persistence)...")
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
