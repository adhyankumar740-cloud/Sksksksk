# main.py (FINAL VERSION 18: Fix /chats Markdown V2 Escape)

import telegram
from telegram import Update, constants, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from telegram.helpers import escape_markdown
import requests
import random
import os
import asyncio
import html 
from datetime import datetime
import logging 
import traceback
import json
import time 
import tempfile 
import psutil
# --- Import Leaderboard Manager ---
import leaderboard_manager 

# --- ⚙️ Constants and Setup ---
# 10 MINUTE COOLDOWN (10 min * 60 sec)
GLOBAL_QUIZ_COOLDOWN = 600 

LOCK_KEY = 'global_quiz_lock' 
LAST_GLOBAL_QUIZ_KEY = 'last_global_quiz_time'
LAST_QUIZ_MESSAGE_KEY = 'last_quiz_message_ids' 

# --- 💡 VIDEO SOLUTION YAHAN HAI ---
WELCOME_VIDEO_URLS = [
    # 💡 IMPORTANT: Yahan apne video File_IDs daalein.
    "BAACAgUAAxkBAAIBxWkOFRIw0g1B_7xuSA4cyUE3ShSlAAJKGwAC_MFxVIx6wUDn1qKBNgQ",
    "BAACAgUAAxkBAAIByGkOFV746X7wbcPRCZTVy4iqtaC7AAKmIQACGV5QVJYHM5LZKdVANgQ",
    "BAACAgUAAyEFAATDIfMWAAICe2kNq_8rhMxyunaubyvrjovOEAz_AAIEJQACnClpVEIdwOhLrWhYNgQ",
    "BAACAgUAAyEFAATDIfMWAAIB3mkNk-cqNbscJhwvxOOBcK7PXkUcAAILJQACnClpVFEZkkwlNiBCNgQ",
]

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL') 
OWNER_ID = os.environ.get('OWNER_ID')
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')
STABLE_HORDE_API_KEY = os.environ.get('STABLE_HORDE_API_KEY', '0000000000')

# --- 💡 NEW: Photo IDs for Start/About ---
START_PHOTO_ID = os.environ.get('START_PHOTO_ID') 
ABOUT_PHOTO_ID = os.environ.get('ABOUT_PHOTO_ID') # Now unused in about_command, but kept for reference
DONATION_PHOTO_ID = os.environ.get('DONATION_PHOTO_ID') # QR Code Photo ID
DONATION_DETAILS = os.environ.get('DONATION_DETAILS', "UPI: example@upi / Wallet: 1234567890")
# --- 💡 NEW SPAM CONSTANTS ---
SPAM_MESSAGE_LIMIT = 5 
SPAM_TIME_WINDOW = 2
SPAM_BLOCK_DURATION = 600 

# --- 💡 Naya: Initialize Bot Start Time ---
BOT_START_TIME = datetime.now()
try:
    import psutil
    logger.info("psutil imported successfully.")
except ImportError:
    psutil = None
    logger.warning("psutil not installed. System metrics will be limited.")

# --- 💡 Naya: Uptime Helper Function ---
def get_uptime_string():
    """Calculates and formats the bot's uptime."""
    delta = datetime.now() - BOT_START_TIME
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    uptime_str = []
    if days > 0:
        uptime_str.append(f"{days}d")
    if hours > 0:
        uptime_str.append(f"{hours}h")
    if minutes > 0:
        uptime_str.append(f"{minutes}m")
    uptime_str.append(f"{seconds}s")
    
    return ' '.join(uptime_str)
    
# --- Error Handler ---
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


# --- 🎯 COMMANDS ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    bot_username = bot.username 
    
    add_button = InlineKeyboardButton(
        "➕ Add Me to Your Group", 
        url=f"https://t.me/{bot_username}?startgroup=true"
    )
    
    support_channel_button = InlineKeyboardButton(
        "📢 Support Channel", 
        url="https://t.me/Orbit_Studio" 
    )
    support_group_button = InlineKeyboardButton(
        "💬 Support Group", 
        url="https://t.me/OrbitStudioOfficial" 
    )
    
    keyboard = InlineKeyboardMarkup([
        [add_button],                                
        [support_channel_button, support_group_button] 
    ])
    
    if START_PHOTO_ID:
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=START_PHOTO_ID,
                caption=start_text,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboard 
            )
        except Exception as e:
            logger.error(f"Failed to send start photo: {e}. Sending text instead.")
            await update.message.reply_text(
                start_text, 
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboard 
            )
    else:
        await update.message.reply_text(
            start_text, 
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard 
        )

# --- Welcome Function ---
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.new_chat_members:
        return

    leaderboard_manager.register_chat(update)
    chat_id = update.effective_chat.id
    chat_name = html.escape(update.effective_chat.title or "this chat")

    video_id = None
    if WELCOME_VIDEO_URLS:
        video_index = context.bot_data.get('video_counter', 0)
        video_id = WELCOME_VIDEO_URLS[video_index % len(WELCOME_VIDEO_URLS)]
        context.bot_data['video_counter'] = video_index + 1

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
        
    # FIX: Use START_PHOTO_ID for the photo as requested
    photo_to_use = START_PHOTO_ID 
    
    if photo_to_use:
        try:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo_to_use,
                caption=about_text,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            logger.error(f"Failed to send about photo: {e}. Sending text instead.")
            await update.message.reply_text(about_text, parse_mode=constants.ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(about_text, parse_mode=constants.ParseMode.MARKDOWN_V2)

async def get_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        file_id = replied_msg.photo[-1].file_id 
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

async def donation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /donation command to display donation information."""
    
    donation_photo_id = DONATION_PHOTO_ID
    donation_details = DONATION_DETAILS
    bot_name = escape_markdown((await context.bot.get_me()).first_name, version=2)
    
    donation_text = (
        f"🙏 *Support {bot_name}*\\!\n\n"
        f"If you enjoy using this bot and wish to support its continued development, you can help us here\\.\n\n"
        f"**Donation Details:**\n"
        f"{escape_markdown(donation_details, version=2)}\n\n"
        f"Thank you for your generosity\\!"
    )
    
    if donation_photo_id:
        try:
            # Send photo with caption (Assuming DONATION_PHOTO_ID holds the QR code image ID)
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=donation_photo_id,
                caption=donation_text,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            logger.error(f"Failed to send donation photo: {e}. Sending text instead.")
            await update.message.reply_text(donation_text, parse_mode=constants.ParseMode.MARKDOWN_V2)
    else:
        # Send text only if DONATION_PHOTO_ID is not set
        await update.message.reply_text(
            f"⚠️ **Donation Photo Missing**\\!\n\n{donation_text}",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows detailed bot status: latency, uptime, resource usage, and database info."""
    
    start_time = time.time()
    
    # 1. Latency (Start)
    initial_message = await update.message.reply_text("Checking status... 🚀")
    
    # 2. Uptime Calculation
    uptime_str = get_uptime_string()

    # 3. Resource Usage (RAM/ROM)
    ram_usage = "N/A"
    try:
        if psutil:
            process = psutil.Process(os.getpid())
            mem = process.memory_info()
            # Convert bytes to megabytes (RSS: Resident Set Size)
            ram_usage = f"{mem.rss / (1024 * 1024):.2f} MB" 
        else:
            # Fallback for environments without psutil
            ram_usage = "Limited (Need psutil)"
    except Exception:
        ram_usage = "Error fetching RAM"
    
    # 4. Database Status (Assuming connection through leaderboard_manager)
    db_status = "SQLite / PostgreSQL (via Leaderboard Manager)"

    # 5. Latency (End)
    end_time = time.time()
    latency_ms = (end_time - start_time) * 1000
    
    # 6. Format Final Message
    bot_info = await context.bot.get_me()
    bot_name = escape_markdown(bot_info.first_name, version=2)
    
    status_text = (
        f"✨ *Bot Status for {bot_name}* ✨\n\n"
        f"**⚡️ Responsiveness**\n"
        f"  • Latency: `{latency_ms:.2f} ms`\n\n"
        f"**⏱️ Uptime**\n"
        f"  • Running For: `{uptime_str}`\n\n"
        f"**💾 Resources**\n"
        f"  • RAM Usage: `{ram_usage}`\n"
        f"  • Storage/ROM: `External (Render/DB)`\n\n" # Ye general info hai
        f"**📊 System Details**\n"
        f"  • Database: `{db_status}`"
    )

    # 7. Edit the initial message
    await initial_message.edit_text(
        status_text,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )

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

# --- NEW: Owner Only Chats Command ---
async def chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only command to display bot chat statistics."""
    if not OWNER_ID or str(update.effective_user.id) != str(OWNER_ID):
        await update.message.reply_text("This is an owner-only command\.")
        return
        
    stats = leaderboard_manager.get_chat_stats()
    
    if stats is None:
        await update.message.reply_text("❌ Database connection error or failed to fetch chat statistics\.")
        return
        
    group_count = stats.get('groups', 0)
    dm_count = stats.get('dms', 0)
    total_messages = stats.get('total_messages', 0)
    
    total_chats = group_count + dm_count
    
    # FIX: Escaping all reserved Markdown V2 characters (\( \. \- \) )
    response_text = (
        f"📊 *Bot Chat Statistics* 📊\n\n"
        f"**Total Active Chats:** `{total_chats}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"• *Groups/Supergroups:* `{group_count}`\n"
        f"• *Private Chats \\(DMs\\):* `{dm_count}`\n" # \(\) are now correctly escaped as \\( \\)
        f"━━━━━━━━━━━━━━━━━━\n"
        f"**Database Activity:**\n"
        f"• *Total Messages Tracked:* `{total_messages}`\n\n"
        f"\\(Note: Total member count cannot be accurately fetched without excessive API calls\\.\\)" # Entire note is escaped, including the outer parentheses and period
    )
    
    await update.message.reply_text(
        response_text,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )

# --- 📣 QUIZ LOGIC ---

# 💡 MODIFIED: New function to fetch multiple unique quizzes.
async def fetch_multiple_quiz_data_from_api(amount: int = 10):
    TRIVIA_API_URL = f"https://opentdb.com/api.php?amount={amount}&type=multiple"
    try:
        response = requests.get(TRIVIA_API_URL, timeout=8) # Increased timeout slightly
        response.raise_for_status() 
        data = response.json()
        if data['response_code'] != 0 or not data['results']:
            logger.error(f"API returned error code or no results: {data.get('response_code')}")
            return []
            
        quiz_list = []
        for question_data in data['results']:
            # Decode question and answers
            question_text = html.unescape(requests.utils.unquote(question_data['question']))
            correct_answer = html.unescape(requests.utils.unquote(question_data['correct_answer']))
            incorrect_answers = [html.unescape(requests.utils.unquote(ans)) for ans in question_data['incorrect_answers']]
            
            all_options = incorrect_answers + [correct_answer]
            random.shuffle(all_options)
            
            # Find the new index of the correct answer
            try:
                correct_option_id = all_options.index(correct_answer)
            except ValueError:
                correct_option_id = 0 
                
            explanation = f"Correct Answer: {correct_answer}" 
            
            quiz_list.append({
                'question': question_text,
                'options': all_options,
                'correct_option_id': correct_option_id,
                'explanation': explanation
            })
            
        return quiz_list

    except Exception as e:
        logger.error(f"Error fetching multiple quiz data from API: {e}")
        return []

# --- 💡 MODIFIED: Global Broadcast Logic with Unique Quiz and Delay ---
async def broadcast_quiz(context: ContextTypes.DEFAULT_TYPE):
    bot_data = context.bot_data
    chat_ids = leaderboard_manager.get_all_active_chat_ids()
    
    if not chat_ids:
        logger.warning("No active chats registered for broadcast.")
        return
        
    # --- New: Fetch a pool of 10 quizzes ---
    quiz_pool = await fetch_multiple_quiz_data_from_api(amount=10)
    if not quiz_pool:
        logger.error("Failed to fetch quiz data globally, cancelling broadcast.")
        return
        
    # --- 💡 STEP 1: DELETE OLD QUIZZES ---
    old_quiz_messages = bot_data.pop(LAST_QUIZ_MESSAGE_KEY, {}) 
    
    delete_tasks = []
    for chat_id_str, message_id in old_quiz_messages.items():
        try:
            chat_id = int(chat_id_str)
            delete_tasks.append(
                context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            )
        except ValueError:
            logger.warning(f"Invalid chat_id found in old quiz messages: {chat_id_str}")
        
    if delete_tasks:
        logger.info(f"Attempting to delete {len(delete_tasks)} old quiz messages.")
        await asyncio.gather(*delete_tasks, return_exceptions=True) 
    
    # --- 💡 STEP 2: SEND NEW QUIZ WITH UNIQUE CONTENT AND DELAY ---
    new_quiz_messages = {}
    successful_sends = 0
    quiz_index = 0
    num_quizzes = len(quiz_pool)
    
    logger.info(f"Starting broadcast to {len(chat_ids)} chats using {num_quizzes} unique quizzes.")

    for chat_id in chat_ids:
        # Cycle through the available 10 quizzes to give each group a unique one (if possible)
        # अगर 10 से ज़्यादा ग्रुप हैं, तो क्विज़ 11वें ग्रुप को पहला वाला मिलेगा।
        quiz_data = quiz_pool[quiz_index % num_quizzes] 
        
        # Send quiz and track (function returns a tuple or Exception)
        res = await send_quiz_and_track_id(context, chat_id, quiz_data)
        
        if isinstance(res, tuple) and res[1] == "Success":
            successful_sends += 1
            # res is (chat_id, "Success", message_id)
            new_quiz_messages[str(chat_id)] = res[2] 
            
        elif isinstance(res, tuple) and res[1].startswith("Failed_Deactivated"):
            pass
        elif isinstance(res, Exception):
            logger.error(f"An unexpected error occurred during single send for {chat_id}: {res}")
        
        quiz_index += 1 # Move to the next quiz index (will wrap around due to modulo)
        
        # --- New: Implement 5-second delay between chat broadcasts ---
        await asyncio.sleep(5)
            
    bot_data[LAST_QUIZ_MESSAGE_KEY] = new_quiz_messages
    bot_data[LAST_GLOBAL_QUIZ_KEY] = datetime.now().timestamp()
    logger.info(f"Broadcast attempt finished. Successful to {successful_sends} / {len(chat_ids)} chats. Global timer reset. {len(new_quiz_messages)} new quiz IDs stored.")


# --- 💡 IMPORTANT MODIFICATION: is_anonymous=False (Unchanged) ---
async def send_quiz_and_track_id(context: ContextTypes.DEFAULT_TYPE, chat_id, quiz_data):
    try:
        sent_message = await context.bot.send_poll( 
            chat_id=chat_id,
            question=quiz_data['question'],
            options=quiz_data['options'],
            type=constants.PollType.QUIZ, # Still a QUIZ (Green/Red check)
            correct_option_id=quiz_data['correct_option_id'],
            explanation=quiz_data['explanation'],
            is_anonymous=False, # 💡 Now Public (Shows who voted what)
            open_period=600 
        )
        logger.info(f"Quiz sent successfully to {chat_id}.")
        return (chat_id, "Success", sent_message.message_id) 
    except (telegram.error.Forbidden, telegram.error.BadRequest) as e:
        logger.warning(f"Failed to send to {chat_id} (Forbidden/Bad Request): {e}. Deactivating chat.")
        leaderboard_manager.deactivate_chat_in_db(chat_id)
        return (chat_id, f"Failed_Deactivated: {e}", None)
    except Exception as e:
        logger.error(f"Failed to send quiz to {chat_id} (Timeout/Other): {e}")
        return (chat_id, f"Failed_Error: {e}", None)


# --- 🎯 CORE MESSAGE HANDLER LOGIC ---
async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    if update.effective_chat.type not in [constants.ChatType.GROUP, constants.ChatType.SUPERGROUP] or not update.effective_user or update.effective_user.is_bot:
        return
    
    if not update.message:
        return
    
    if update.message.text and update.message.text.startswith('/'):
        return

    chat_id = update.effective_chat.id
    user_data = context.user_data
    bot_data = context.bot_data

    # --- 1. Spam Protection Logic ---
    current_time = time.time()
    blocked_until = user_data.get('leaderboard_blocked_until', 0)
    
    if current_time < blocked_until:
        logger.info(f"User {update.effective_user.id} message ignored (still blocked).")
        return 
        
    if 'leaderboard_blocked_until' in user_data:
         del user_data['leaderboard_blocked_until']
         
    message_timestamps = user_data.get('msg_timestamps', [])
    if not isinstance(message_timestamps, list):
         message_timestamps = []
         
    time_window_start = current_time - SPAM_TIME_WINDOW
    recent_timestamps = [t for t in message_timestamps if t > time_window_start]
    recent_timestamps.append(current_time)
    user_data['msg_timestamps'] = recent_timestamps
    
    if len(recent_timestamps) >= SPAM_MESSAGE_LIMIT:
        user_data['leaderboard_blocked_until'] = current_time + SPAM_BLOCK_DURATION
        user_data['msg_timestamps'] = [] 
        logger.warning(f"!!! SPAM IGNORE TRIGGERED !!! User {update.effective_user.id} ignored for 10 minutes.")
        
        try:
            username = update.effective_user.username
            mention = f"@{username}" if username else update.effective_user.mention_html()
            
            await update.message.reply_text(
                f"{mention} <b>You are being ignored for 10 minutes for spamming!</b>\n"
                f"Your rapid messages will not count towards the leaderboard or trigger quizzes during this time.",
                parse_mode=constants.ParseMode.HTML
            )
            return 
            
        except Exception as e:
            logger.warning(f"Failed to send spam warning: {e}")
            return
            
    # --- 2. Update DB (Leaderboard) ---
    await leaderboard_manager.update_message_count_db(update, context)

    # --- 3. Check for Quiz (Global Logic) ---
    last_quiz_time = bot_data.get(LAST_GLOBAL_QUIZ_KEY, 0)
    
    if current_time - last_quiz_time > GLOBAL_QUIZ_COOLDOWN:
        
        if bot_data.get(LOCK_KEY, False):
            return
        
        try:
            bot_data[LOCK_KEY] = True
            logger.info(f"Global quiz cooldown over. Triggered by user {update.effective_user.id} in chat {chat_id}. Broadcasting to all.")
            await broadcast_quiz(context) 
            
        except Exception as e:
            logger.error(f"Error during global quiz broadcast trigger: {e}")
        finally:
            bot_data[LOCK_KEY] = False
    else:
        pass
            
# --- 🚀 MAIN EXECUTION FUNCTION ---
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
    
    application.add_error_handler(error_handler)
    
    # Standard Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("broadcast", leaderboard_manager.broadcast_command))

    # NEW OWNER COMMAND
    application.add_handler(CommandHandler("chats", chats_command))

    # Leaderboard Commands
    application.add_handler(CommandHandler("ranking", leaderboard_manager.ranking_command))
    application.add_handler(CommandHandler("profile", leaderboard_manager.profile_command))
    application.add_handler(CommandHandler("prof", leaderboard_manager.profile_command))
    application.add_handler(CallbackQueryHandler(leaderboard_manager.leaderboard_callback, pattern='^lb_'))
    
    # Image Commands
    application.add_handler(CommandHandler("img", img_command))
    application.add_handler(CommandHandler("gen", gen_command))
    application.add_handler(CommandHandler("donation", donation_command))
    application.add_handler(CommandHandler("ping", ping_command))
    # ID Finder
    application.add_handler(CommandHandler("get_id", get_id_command))

    # Message Handlers
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    
    # Main Message Handler
    application.add_handler(
        MessageHandler(
            ~filters.COMMAND & filters.ChatType.GROUPS, 
            handle_all_messages 
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
