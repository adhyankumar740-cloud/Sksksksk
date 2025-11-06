# main.py (Updated with /img, /gen, /about and full English)

import telegram
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from telegram.helpers import escape_markdown # <-- 💡 NEW
import requests
import random
import os
import asyncio
import html 
from datetime import datetime
import logging 
import traceback
import json
import time # <-- 💡 NEW: For polling

# --- Import Leaderboard Manager ---
import leaderboard_manager 

# --- ⚙️ Constants and Setup ---
QUIZ_TRIGGER_COUNT = 5
MESSAGE_COUNTER_KEY = 'message_count'
LOCK_KEY = 'quiz_in_progress' 
LAST_GLOBAL_QUIZ_KEY = 'last_global_quiz_time'
GLOBAL_INTERVAL_MIN = 10 

WELCOME_VIDEO_URLS = [
    "https://files.catbox.moe/4mjz8l.mp4", 
    "https://files.catbox.moe/hxkkvt.mp4", 
    "https://files.catbox.moe/li9zgh.mp4", 
    "https://files.catbox.moe/vq58fh.mp4",
]

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL') 
OWNER_ID = os.environ.get('OWNER_ID') # <-- 💡 NEW: For /about
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY') # <-- 💡 NEW
STABLE_HORDE_API_KEY = os.environ.get('STABLE_HORDE_API_KEY', '0000000000') # <-- 💡 NEW


# --- 💡 Error Handler (TRANSLATED) ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Logs the error and sends a message to the user."""
    logger.error("Exception while handling an update:", exc_info=context.error)

    # Prepare traceback
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Format the message
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    logger.error(message) # Log the full error
    
    # Send a simplified message to the user or group
    if update and isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="😕 Oops! Something went wrong. I've reported this to the developer.", # <-- TRANSLATED
                parse_mode=constants.ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to send error message to chat: {e}")


# --- 🎯 COMMANDS (TRANSLATED) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    leaderboard_manager.register_chat(update) 
    
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        chat_id = update.effective_chat.id
        chat_name = update.effective_chat.title
        user_mention = member.mention_html()
        user_id = member.id
        chat_name_escaped = telegram.helpers.escape_markdown(chat_name, version=2) if chat_name else "this chat"
        
        welcome_message = (
            f"👋 *Welcome to {chat_name_escaped}*\\!\n\n"
            f"User: {user_mention}\n"
            f"Telegram ID: `{user_id}`\n\n"
            f"Chat and earn your spot on the leaderboard\\! 🏆" # <-- TRANSLATED
        )
        
        if not WELCOME_VIDEO_URLS:
            video_url = None
        else:
            video_index = context.bot_data.get('video_counter', 0)
            video_url = WELCOME_VIDEO_URLS[video_index % len(WELCOME_VIDEO_URLS)]
            context.bot_data['video_counter'] = video_index + 1
        
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
            await context.bot.send_message(
                chat_id=chat_id,
                text=welcome_message,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )

# --- 💡 NEW: /about Command ---
async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot = await context.bot.get_me()
    bot_name = escape_markdown(bot.first_name, version=2)
    
    about_text = (
        f"👋 *About Me*\n\n"
        f"Hi, I'm {bot_name}\\!\n\n"
        f"I was created to help manage leaderboards, run quizzes, and have fun\\.\n\n"
        f"**Features:**\n"
        f"• Automatic quizzes\n"
        f"• Message leaderboards \\(/leaderboard\\)\n"
        f"• User profiles \\(/profile\\)\n"
        f"• Image search \\(/img\\)\n"
        f"• AI Image generation \\(/gen\\)\n\n"
        f"•Owner: Gopu\n"
    )
    
    if OWNER_ID:
        # MarkdownV2 link syntax
        about_text += f"You can contact my owner for support: [Owner](tg://user?id={OWNER_ID})\n"
    else:
        about_text += "This bot is running without a configured owner\\.\n"
        
    await update.message.reply_text(about_text, parse_mode=constants.ParseMode.MARKDOWN_V2)

# --- 💡 NEW: /img Command (Pexels) ---
async def img_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not PEXELS_API_KEY:
        await update.message.reply_text("Image search is disabled. `PEXELS_API_KEY` is not configured.")
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
        photographer = photo['photographer']
        photographer_url = photo['photographer_url']
        
        caption = f"Photo by [{escape_markdown(photographer, version=2)}]({photographer_url}) on Pexels"

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

# --- 💡 NEW: /gen Command (Stable Horde) ---
async def gen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide a prompt. Example: `/gen a cat in space`")
        return

    prompt = " ".join(context.args)
    sent_msg = await update.message.reply_text(f"🎨 Generating '{prompt}'... This may take a minute.")

    try:
        # Step 1: Request Generation
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

        # Step 2: Poll for Result
        while True:
            await asyncio.sleep(5) # Wait 5 seconds between checks

            # Check for timeout (2 minutes)
            if time.time() - start_time > 120:
                await sent_msg.edit_text("Generation timed out. Please try again later.")
                return

            # Check status
            check_url = f"https://stablehorde.net/api/v2/generate/check/{generation_id}"
            check_response = requests.get(check_url, timeout=5)
            check_data = check_response.json()

            if check_data.get('faulted', False):
                await sent_msg.edit_text("Generation failed. The prompt might be invalid or the service is busy.")
                return

            if check_data.get('done', False):
                # Step 3: Get the Image
                status_url = f"https://stablehorde.net/api/v2/generate/status/{generation_id}"
                status_response = requests.get(status_url, timeout=5)
                status_data = status_response.json()
                
                img_url = status_data['generations'][0]['img']
                
                escaped_prompt = escape_markdown(prompt, version=2)

                await sent_msg.delete() # Delete "Generating..." message
                await update.message.reply_photo(
                    img_url,
                    caption=f"*Prompt:* {escaped_prompt}\n_Generated by Stable Horde_",
                    parse_mode=constants.ParseMode.MARKDOWN_V2
                )
                return # Exit loop

    except requests.Timeout:
        await sent_msg.edit_text("The generation service timed out. Please try again.")
    except Exception as e:
        logger.error(f"Stable Horde error: {e}")
        await sent_msg.edit_text(f"Sorry, an error occurred during image generation: {e}")


# --- 📣 QUIZ LOGIC (Same) ---

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

async def send_poll_to_chat(context: ContextTypes.DEFAULT_TYPE, chat_id, quiz_data):
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

async def send_quiz_and_handle_errors(context: ContextTypes.DEFAULT_TYPE, chat_id, quiz_data):
    try:
        await send_poll_to_chat(context, chat_id, quiz_data)
        logger.info(f"Quiz sent successfully to {chat_id}.")
        return (chat_id, "Success")
    
    except (telegram.error.Forbidden, telegram.error.BadRequest) as e:
        logger.warning(f"Failed to send to {chat_id} (Forbidden/Bad Request): {e}. Deactivating chat.")
        leaderboard_manager.deactivate_chat_in_db(chat_id) 
        return (chat_id, f"Failed_Deactivated: {e}")
        
    except Exception as e:
        logger.error(f"Failed to send quiz to {chat_id} (Timeout/Other): {e}")
        return (chat_id, f"Failed_Error: {e}")

async def broadcast_quiz(context: ContextTypes.DEFAULT_TYPE):
    bot_data = context.bot_data
    chat_ids = leaderboard_manager.get_all_active_chat_ids()
    
    if not chat_ids:
        logger.warning("No active chats registered for broadcast.")
        return

    quiz_data = await fetch_quiz_data_from_api()
    if not quiz_data:
        logger.error("Failed to fetch quiz data globally, cancelling broadcast.")
        return

    tasks = [
        send_quiz_and_handle_errors(context, chat_id, quiz_data) 
        for chat_id in chat_ids
    ]
    
    logger.info(f"Starting broadcast to {len(tasks)} chats...")
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successful_sends = 0
    for res in results:
        if isinstance(res, tuple) and res[1] == "Success":
            successful_sends += 1
        elif isinstance(res, Exception):
            logger.error(f"An unexpected error occurred during gather: {res}")

    bot_data[LAST_GLOBAL_QUIZ_KEY] = datetime.now().timestamp()
    logger.info(f"Broadcast attempt finished. Successful to {successful_sends} / {len(tasks)} chats. Global timer reset.")


# --- 🎯 CORE MESSAGE COUNTER LOGIC (Same) ---
async def send_quiz_after_n_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    chat_id = update.effective_chat.id
    if update.effective_chat.type not in [constants.ChatType.GROUP, constants.ChatType.SUPERGROUP, constants.ChatType.PRIVATE]:
        return
    
    chat_data = context.chat_data
    bot_data = context.bot_data

    await leaderboard_manager.update_message_count_db(update, context)

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
            
# --- 🚀 MAIN EXECUTION FUNCTION (Updated) ---
def main(): 
    if not TOKEN or not WEBHOOK_URL:
        logger.critical("FATAL ERROR: Environment variables missing (TOKEN or WEBHOOK_URL).")
        return
        
    leaderboard_manager.setup_database()

    application = (
        Application.builder()
        .token(TOKEN)
        .concurrent_updates(True)
        .connect_timeout(10)   
        .read_timeout(15)      
        .write_timeout(15)     
        .http_version('1.1')
        .build()
    )
    
    # Register the error handler
    application.add_error_handler(error_handler)
    
    # --- Add all handlers ---
    
    # Standard Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("about", about_command)) # <-- NEW
    application.add_handler(CommandHandler("broadcast", leaderboard_manager.broadcast_command))

    # Leaderboard Commands
    application.add_handler(CommandHandler("leaderboard", leaderboard_manager.leaderboard_command))
    application.add_handler(CommandHandler("profile", leaderboard_manager.profile_command))
    application.add_handler(CallbackQueryHandler(leaderboard_manager.leaderboard_callback, pattern='^lb_')) 
    
    # New Image Commands
    application.add_handler(CommandHandler("img", img_command)) # <-- NEW
    application.add_handler(CommandHandler("gen", gen_command)) # <-- NEW

    # Message Handlers
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            send_quiz_after_n_messages
        )
    )
    
    PORT = int(os.environ.get("PORT", "8000")) 
    
    logger.info("Starting bot webhook...")
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
