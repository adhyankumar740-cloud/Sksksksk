# leaderboard_manager.py (Updated for English, Owner-Only Broadcast, and Bugfixes)

import os
import psycopg2
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants, InputMediaPhoto
from telegram.ext import ContextTypes, CallbackContext
from telegram.helpers import escape_markdown # <-- IMPORTED FOR BUGFIX
import logging
import asyncio
import telegram.error

import io
from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

# --- ⚙️ Owner and Image Constants ---
FONT_FILE_BOLD = "Roboto-Bold.ttf"
FONT_FILE_REGULAR = "Roboto-Regular.ttf"
BACKGROUND_IMAGE_PATH = "25552 (1).jpg"
IMG_WIDTH = 800
TITLE_COLOR = (255, 255, 255)
TEXT_COLOR = (200, 200, 200)
RANK_COLOR = (255, 215, 0)

# --- 👑 Bot Owner ---
# Load the Owner ID from environment variables
OWNER_ID = os.environ.get('OWNER_ID')
if not OWNER_ID:
    logger.warning("OWNER_ID environment variable is not set. Broadcast command will be disabled.")
# --- End Constants ---


# --- Database Connection and Setup ---
def get_db_connection():
    DB_URL = os.environ.get('DATABASE_URL')
    if not DB_URL:
        logger.error("DATABASE_URL environment variable is not set.")
        return None
    try:
        conn = psycopg2.connect(DB_URL, sslmode='require')
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None

def setup_database():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id BIGSERIAL PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        username VARCHAR(255),
                        message_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS chats (
                        chat_id BIGINT PRIMARY KEY,
                        chat_name VARCHAR(255),
                        chat_type VARCHAR(50),
                        last_activity TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE NOT NULL
                    );
                """)

                try:
                    cur.execute("SELECT chat_type FROM chats LIMIT 1;")
                except psycopg2.ProgrammingError:
                    conn.rollback()
                    logger.warning("Adding 'chat_type' column to existing 'chats' table.")
                    cur.execute("ALTER TABLE chats ADD COLUMN chat_type VARCHAR(50);")
                    conn.commit()

                try:
                    cur.execute("SELECT is_active FROM chats LIMIT 1;")
                except psycopg2.ProgrammingError:
                    conn.rollback()
                    logger.warning("Adding 'is_active' column to 'chats' table.")
                    cur.execute("ALTER TABLE chats ADD COLUMN is_active BOOLEAN DEFAULT TRUE NOT NULL;")
                    conn.commit()

            conn.commit()
            logger.info("Database setup complete.")
        except Exception as e:
            logger.error(f"Database setup failed: {e}")
            conn.rollback()
        finally:
            if conn:
                conn.close()

# --- Chat Registration ---
def register_chat(update: Update):
    conn = get_db_connection()
    if not conn: return
    chat = update.effective_chat
    chat_id = chat.id
    chat_name = chat.title or (chat.username or chat.first_name)
    chat_type = chat.type
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO chats (chat_id, chat_name, chat_type, last_activity, is_active)
                VALUES (%s, %s, %s, NOW(), TRUE)
                ON CONFLICT (chat_id) DO UPDATE
                SET last_activity = NOW(), chat_name = %s, chat_type = %s, is_active = TRUE;
            """, (chat_id, chat_name, chat_type, chat_name, chat_type))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to register chat: {e}")
    finally:
        if conn: conn.close()

# --- Message Count Update ---
async def update_message_count_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    if not conn: return
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    username = f"@{user.username}" if user.username else user.first_name
    register_chat(update)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO messages (chat_id, user_id, username)
                VALUES (%s, %s, %s);
            """, (chat_id, user_id, username))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to update message count in DB: {e}")
    finally:
        if conn: conn.close()


# --- Leaderboard Image Generator (MODIFIED) ---
def generate_leaderboard_image(title: str, leaderboard_data: list, chat_name: str):
    try:
        font_title = ImageFont.truetype(FONT_FILE_BOLD, 40)
        font_chat = ImageFont.truetype(FONT_FILE_REGULAR, 24)
        font_rank = ImageFont.truetype(FONT_FILE_BOLD, 28)
        font_user = ImageFont.truetype(FONT_FILE_REGULAR, 28)
    except IOError as e:
        logger.error(f"Error: Font file '{FONT_FILE_BOLD}' or '{FONT_FILE_REGULAR}' not found: {e}.")
        img = Image.new('RGB', (IMG_WIDTH, 200), color=(50, 0, 0)) # Reddish background for error
        d = ImageDraw.Draw(img)
        d.text((10, 10), "Error: Font file not found.\nPlease install fonts.", fill=(255,255,255))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

    try:
        # Load the background image
        bg_img = Image.open(BACKGROUND_IMAGE_PATH).convert("RGB")
    except FileNotFoundError:
        logger.error(f"Error: Background image '{BACKGROUND_IMAGE_PATH}' not found.")
        # Fallback to a solid color if background image is not found
        img = Image.new('RGB', (IMG_WIDTH, 200), color=(50, 0, 0))
        d = ImageDraw.Draw(img)
        d.text((10, 10), f"Error: Background image '{BACKGROUND_IMAGE_PATH}' not found.\nFalling back to solid color.", fill=(255,255,255))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes
    except Exception as e:
        logger.error(f"Error loading background image '{BACKGROUND_IMAGE_PATH}': {e}")
        # Fallback to a solid color for other image loading errors
        img = Image.new('RGB', (IMG_WIDTH, 200), color=(50, 0, 0))
        d = ImageDraw.Draw(img)
        d.text((10, 10), f"Error loading background image: {e}\nFalling back to solid color.", fill=(255,255,255))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

    # Calculate desired height for the generated image
    item_height = 50
    header_height = 150
    footer_height = 50
    # Minimum height to ensure header and footer are always visible
    min_content_height = 200 # For "no data" message
    actual_content_height = max(min_content_height, len(leaderboard_data) * item_height)
    total_height = header_height + actual_content_height + footer_height

    # Resize background image to fit the leaderboard dimensions
    bg_width, bg_height = bg_img.size
    
    if bg_width < IMG_WIDTH:
        bg_img = bg_img.resize((IMG_WIDTH, int(bg_height * (IMG_WIDTH / bg_width))), Image.LANCZOS)
        bg_width = IMG_WIDTH

    img = bg_img.resize((IMG_WIDTH, total_height), Image.LANCZOS)
    
    d = ImageDraw.Draw(img)

    # --- Draw Header ---
    title_bbox = d.textbbox((0, 0), title, font=font_title)
    title_w = title_bbox[2] - title_bbox[0]
    d.text(((IMG_WIDTH - title_w) / 2, 40), title, font=font_title, fill=TITLE_COLOR)

    chat_name_text = f"Group: {chat_name[:35]}" + ('...' if len(chat_name) > 35 else '')
    chat_bbox = d.textbbox((0, 0), chat_name_text, font=font_chat)
    chat_w = chat_bbox[2] - chat_bbox[0]
    d.text(((IMG_WIDTH - chat_w) / 2, 100), chat_name_text, font=font_chat, fill=TEXT_COLOR)

    # --- Draw Leaderboard Entries ---
    if not leaderboard_data:
        no_data_text = "No data found." # <-- TRANSLATED
        no_data_bbox = d.textbbox((0, 0), no_data_text, font=font_user)
        no_data_w = no_data_bbox[2] - no_data_bbox[0]
        d.text(((IMG_WIDTH - no_data_w) / 2, header_height + (actual_content_height - (no_data_bbox[3] - no_data_bbox[1])) / 2), no_data_text, font=font_user, fill=TEXT_COLOR)
    else:
        y_pos = header_height
        for i, (username, count) in enumerate(leaderboard_data):
            rank = f"{i+1}."
            username_display = f"{username[:20]}" + ('...' if len(username) > 20 else '')
            count_str = f"{count} msgs"

            d.text((50, y_pos), rank, font=font_rank, fill=RANK_COLOR)
            d.text((120, y_pos), username_display, font=font_user, fill=TEXT_COLOR)

            count_bbox = d.textbbox((0, 0), count_str, font=font_user)
            count_w = count_bbox[2] - count_bbox[0]

            d.text( (IMG_WIDTH - count_w - 50, y_pos), count_str, font=font_user, fill=TEXT_COLOR)

            y_pos += item_height

    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes


# --- Leaderboard Core Logic (TRANSLATED) ---
async def get_leaderboard_data(chat_id: int, scope: str):
    conn = get_db_connection()
    if not conn:
        return ("Database Error", "Unknown", [])

    time_filter = ""
    chat_filter = ""
    title = ""

    if scope == 'daily':
        time_filter = "message_time >= NOW() - INTERVAL '1 day'"
        title = "Today's Leaderboard (Local)" # <-- TRANSLATED
        chat_filter = f"chat_id = {chat_id}"
    elif scope == 'weekly':
        time_filter = "message_time >= NOW() - INTERVAL '7 days'"
        title = "Weekly Leaderboard (Local)" # <-- TRANSLATED
        chat_filter = f"chat_id = {chat_id}"
    elif scope == 'alltime':
        title = "All-Time Leaderboard (Local)" # <-- TRANSLATED
        chat_filter = f"chat_id = {chat_id}"
    elif scope == 'global_daily':
        time_filter = "message_time >= NOW() - INTERVAL '1 day'"
        title = "🌍 Global Leaderboard (24 Hrs)"
        chat_filter = ""
    elif scope == 'global_alltime':
        title = "🌍 Global Leaderboard (All Time)"
        chat_filter = ""

    filters = []
    if chat_filter: filters.append(chat_filter)
    if time_filter: filters.append(time_filter)
    where_clause = " WHERE " + " AND ".join(filters) if filters else ""

    query = f"""
        SELECT username, COUNT(*) AS total_messages
        FROM messages
        {where_clause}
        GROUP BY username
        ORDER BY total_messages DESC
        LIMIT 10;
    """

    chat_name_query = "SELECT chat_name FROM chats WHERE chat_id = %s;"

    try:
        with conn.cursor() as cur:
            cur.execute(query)
            results = cur.fetchall()

            chat_name = "Global"
            if "Local" in title:
                cur.execute(chat_name_query, (chat_id,))
                chat_name_result = cur.fetchone()
                if chat_name_result:
                    chat_name = chat_name_result[0]
                else:
                    chat_name = "This Chat" # <-- TRANSLATED

        return (title, chat_name, results)

    except Exception as e:
        logger.error(f"Failed to fetch leaderboard: {e}. Query: {query}")
        return ("Database Query Error", "Error", [])
    finally:
        if conn: conn.close()

# --- Format Leaderboard Text (TRANSLATED & FIXED) ---
def format_leaderboard_text(title: str, chat_name: str, data: list):
    # Escape all dynamic text for MARKDOWN_V2 parsing
    escaped_title = escape_markdown(title, version=2)
    escaped_chat_name = escape_markdown(chat_name, version=2)

    if not data:
        return f"*{escaped_title}*\n_{escaped_chat_name}_\n\nNo data found\." # <-- TRANSLATED & FIXED

    leaderboard_text = f"*{escaped_title}* 🏆\n_{escaped_chat_name}_\n\n"
    for rank, (username, count) in enumerate(data, 1):
        # This is the important fix: escape the username
        escaped_username = escape_markdown(username, version=2)
        leaderboard_text += f"*{rank}.* {escaped_username}: {count} messages\n"

    return leaderboard_text

# --- Leaderboard Command (TRANSLATED) ---
async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    try:
        sent_message = await update.message.reply_text("🏆 Generating leaderboard, please wait...") # <-- TRANSLATED
    except Exception as e:
        logger.error(f"Failed to send loading message: {e}")
        return

    title, chat_name, data = await get_leaderboard_data(chat_id, 'daily')

    if title == "Database Error":
        await sent_message.edit_text("Could not connect to the database.") # <-- TRANSLATED
        return

    image_bytes = generate_leaderboard_image(title, data, chat_name)
    caption_text = format_leaderboard_text(title, chat_name, data)

    keyboard = [
        [InlineKeyboardButton("Today (Local)", callback_data=f"lb_daily:{chat_id}"), # <-- TRANSLATED
         InlineKeyboardButton("Weekly (Local)", callback_data=f"lb_weekly:{chat_id}"), # <-- TRANSLATED
         InlineKeyboardButton("All-Time (Local)", callback_data=f"lb_alltime:{chat_id}")], # <-- TRANSLATED
        [InlineKeyboardButton("Global (24 Hrs)", callback_data=f"lb_global_daily:{chat_id}"),
         InlineKeyboardButton("Global (All Time)", callback_data=f"lb_global_alltime:{chat_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await sent_message.delete()
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=image_bytes,
            caption=caption_text,
            reply_markup=reply_markup,
            parse_mode=constants.ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to send leaderboard photo: {e}. Sending text fallback.")
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption_text,
            reply_markup=reply_markup,
            parse_mode=constants.ParseMode.MARKDOWN
        )

# --- Leaderboard Callback (TRANSLATED) ---
async def leaderboard_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer("Updating...") # <-- TRANSLATED

    try:
        parts = query.data.split('_', 1)[1].split(':')
        scope = parts[0]
        if len(parts) > 2:
            scope = f"{parts[0]}_{parts[1]}"
            chat_id_str = parts[2]
        else:
            chat_id_str = parts[1]

        chat_id = int(chat_id_str)
    except (IndexError, ValueError) as e:
        logger.error(f"Invalid callback data: {query.data} | Error: {e}")
        return

    title, chat_name, data = await get_leaderboard_data(chat_id, scope)

    if title == "Database Error":
        await query.edit_message_caption(caption="Could not connect to the database.") # <-- TRANSLATED
        return

    image_bytes = generate_leaderboard_image(title, data, chat_name)
    caption_text = format_leaderboard_text(title, chat_name, data)

    keyboard = [
        [InlineKeyboardButton("Today (Local)", callback_data=f"lb_daily:{chat_id}"), # <-- TRANSLATED
         InlineKeyboardButton("Weekly (Local)", callback_data=f"lb_weekly:{chat_id}"), # <-- TRANSLATED
         InlineKeyboardButton("All-Time (Local)", callback_data=f"lb_alltime:{chat_id}")], # <-- TRANSLATED
        [InlineKeyboardButton("Global (24 Hrs)", callback_data=f"lb_global_daily:{chat_id}"),
         InlineKeyboardButton("Global (All Time)", callback_data=f"lb_global_alltime:{chat_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_media(
            media=InputMediaPhoto(media=image_bytes, caption=caption_text, parse_mode=constants.ParseMode.MARKDOWN),
            reply_markup=reply_markup
        )
    except telegram.error.BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.warning(f"Failed to edit message media: {e}")
        pass
    except Exception as e:
        logger.error(f"Error during final leaderboard edit: {e}")


# --- Profile Command (TRANSLATED & FIXED) ---
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("*Database is offline\.* Profile unavailable\.") # <-- FIXED
        return

    user = update.effective_user
    user_id = user.id
    
    # Escape username for Markdown
    raw_username = f"@{user.username}" if user.username else user.first_name
    username = escape_markdown(raw_username, version=2)
    
    profile_text = f"👤 *{username}'s Profile Stats* 📈\n\n"

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM messages WHERE user_id = %s;", (user_id,))
            total_messages = cur.fetchone()[0]
            profile_text += f"**Total Messages (All Time):** {total_messages}\n\n"

            cur.execute("""
                SELECT m.chat_id, c.chat_name, COUNT(*) AS count
                FROM messages m
                JOIN chats c ON m.chat_id = c.chat_id
                WHERE m.user_id = %s
                GROUP BY m.chat_id, c.chat_name
                ORDER BY count DESC;
            """, (user_id,))
            group_stats = cur.fetchall()

            profile_text += "*Messages per Group:*\n"
            if not group_stats:
                profile_text += "No group data found\." # <-- TRANSLATED & FIXED
            else:
                for chat_id, chat_name, count in group_stats:
                    # Escape chat name
                    escaped_chat_name = escape_markdown(chat_name[:25], version=2)
                    suffix = escape_markdown("...", version=2) if len(chat_name) > 25 else ""
                    profile_text += f"• {escaped_chat_name}{suffix}: {count}\n"

            await update.message.reply_text(profile_text, parse_mode=constants.ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Failed to fetch user profile: {e}")
        await update.message.reply_text("Database query error while fetching profile\.") # <-- FIXED
    finally:
        if conn: conn.close()

# --- Broadcast Feature (OWNER-ONLY & TRANSLATED) ---
async def send_broadcast_and_handle_errors(context: ContextTypes.DEFAULT_TYPE, chat_id, from_chat_id, message_id):
    try:
        await context.bot.copy_message(
            chat_id=chat_id,
            from_chat_id=from_chat_id,
            message_id=message_id
        )
        return (chat_id, "Success")
    except (telegram.error.Forbidden, telegram.error.BadRequest) as e:
        logger.warning(f"Broadcast failed for {chat_id} (Forbidden/Bad Request). Deactivating: {e}")
        deactivate_chat_in_db(chat_id)
        return (chat_id, "Failed_Deactivated")
    except Exception as e:
        logger.error(f"Broadcast failed for {chat_id} (Other): {e}")
        return (chat_id, "Failed_Error")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Check if OWNER_ID is configured
    if not OWNER_ID:
        await update.message.reply_text("Bot owner ID is not configured. Broadcast disabled.")
        logger.error("Broadcast command used but OWNER_ID is not set.")
        return

    # 2. Check if the user is the owner
    if str(update.effective_user.id) != str(OWNER_ID):
        await update.message.reply_text("This is an owner-only command.")
        return

    # 3. Check if in private chat
    if update.effective_chat.type not in [constants.ChatType.PRIVATE]:
        await update.message.reply_text("This command must be used in a private chat.") # <-- TRANSLATED
        return
        
    # 4. Check if replying to a message
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to the message you want to broadcast.") # <-- TRANSLATED
        return

    broadcast_message = update.message.reply_to_message
    chat_ids = get_all_active_chat_ids()

    if not chat_ids:
        await update.message.reply_text("No active chats found to broadcast to.") # <-- TRANSLATED
        return

    await update.message.reply_text(f"Starting broadcast... Sending to {len(chat_ids)} chats.") # <-- TRANSLATED

    tasks = [
        send_broadcast_and_handle_errors(
            context,
            chat_id,
            update.effective_chat.id,
            broadcast_message.message_id
        )
        for chat_id in chat_ids
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    success_count = 0
    for res in results:
        if isinstance(res, tuple) and res[1] == "Success":
            success_count += 1
        elif isinstance(res, Exception):
            logger.error(f"An unexpected error occurred during broadcast gather: {res}")

    await update.message.reply_text(f"✅ Broadcast complete! Successfully sent to {success_count} / {len(tasks)} chats.") # <-- TRANSLATED

# --- Utility Functions (Same as before) ---
def get_all_active_chat_ids():
    conn = get_db_connection()
    if not conn: return set()

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT chat_id FROM chats WHERE is_active = TRUE;")
            chat_ids = {row[0] for row in cur.fetchall()}
            return chat_ids
    except Exception as e:
        logger.error(f"Failed to fetch active chat IDs for broadcast: {e}")
        return set()
    finally:
        if conn: conn.close()

def deactivate_chat_in_db(chat_id):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE chats SET is_active = FALSE WHERE chat_id = %s;", (chat_id,))
        conn.commit()
        logger.info(f"[DB] Deactivated chat: {chat_id}")
    except Exception as e:
        logger.error(f"[DB] Error deactivating chat {chat_id}: {e}")
    finally:
        if conn: conn.close()
