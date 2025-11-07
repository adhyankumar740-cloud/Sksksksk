# leaderboard_manager.py (MODIFIED to remove Group Name from image)

import os
import psycopg2
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants, InputMediaPhoto
from telegram.ext import ContextTypes, CallbackContext
from telegram.helpers import escape_markdown
import logging
import asyncio
import telegram.error

import io
from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

# --- ⚙️ Image Generation Constants (MODIFIED) ---
# ⚠️ YOU MUST DOWNLOAD 'NotoSans-Regular.ttf' AND 'NotoSans-Bold.ttf'
# ⚠️ AND PUT THEM IN THE SAME DIRECTORY AS THIS SCRIPT.
FONT_FILE_BOLD = "NotoSans-Bold.ttf"
FONT_FILE_REGULAR = "NotoSans-Regular.ttf"
BACKGROUND_IMAGE_PATH = "25552 (1).jpg"
IMG_WIDTH = 1200
TITLE_COLOR = (255, 255, 255)
TEXT_COLOR = (200, 200, 200)
RANK_COLOR = (255, 215, 0)
# --- End Constants ---


# --- 👑 Bot Owner ---
OWNER_ID = os.environ.get('OWNER_ID')
if not OWNER_ID:
    logger.warning("OWNER_ID environment variable is not set. Broadcast command will be disabled.")
# --- End Owner ---

# --- Database Connection and Setup (Unchanged) ---
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

# --- Chat Registration (Unchanged) ---
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

# --- Message Count Update (Unchanged) ---
async def update_message_count_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    if not conn: return
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    
    display_name = user.first_name
    if user.last_name:
        display_name = f"{user.first_name} {user.last_name}"

    register_chat(update)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO messages (chat_id, user_id, username)
                VALUES (%s, %s, %s);
            """, (chat_id, user_id, display_name))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to update message count in DB: {e}")
    finally:
        if conn: conn.close()


# --- Leaderboard Image Generator (MODIFIED: Removed Group Name) ---
def generate_leaderboard_image(title: str, leaderboard_data: list, chat_name: str):
    try:
        font_title = ImageFont.truetype(FONT_FILE_BOLD, 48)
        font_chat = ImageFont.truetype(FONT_FILE_REGULAR, 30) # Font still needed for calculations if we add it back
        font_rank = ImageFont.truetype(FONT_FILE_BOLD, 34)
        font_user = ImageFont.truetype(FONT_FILE_REGULAR, 34)
    except IOError as e:
        logger.error(f"Error: Font file '{FONT_FILE_BOLD}' or '{FONT_FILE_REGULAR}' not found: {e}.")
        img = Image.new('RGB', (IMG_WIDTH, 200), color=(50, 0, 0))
        d = ImageDraw.Draw(img)
        d.text((10, 10), "Error: Font file not found.\nDownload 'NotoSans' fonts and put them in the bot directory.", fill=(255,255,255))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

    try:
        bg_img = Image.open(BACKGROUND_IMAGE_PATH).convert("RGB")
    except FileNotFoundError:
        logger.error(f"Error: Background image '{BACKGROUND_IMAGE_PATH}' not found.")
        img = Image.new('RGB', (IMG_WIDTH, 200), color=(50, 0, 0))
        d = ImageDraw.Draw(img)
        d.text((10, 10), f"Error: Background image '{BACKGROUND_IMAGE_PATH}' not found.\nFalling back to solid color.", fill=(255,255,255))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes
    except Exception as e:
        logger.error(f"Error loading background image '{BACKGROUND_IMAGE_PATH}': {e}")
        img = Image.new('RGB', (IMG_WIDTH, 200), color=(50, 0, 0))
        d = ImageDraw.Draw(img)
        d.text((10, 10), f"Error loading background image: {e}\nFalling back to solid color.", fill=(255,255,255))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes

    item_height = 60
    header_height = 180
    footer_height = 60
    min_content_height = 300
    
    actual_content_height = max(min_content_height, len(leaderboard_data) * item_height)
    total_height = header_height + actual_content_height + footer_height

    bg_width, bg_height = bg_img.size
    if bg_width < IMG_WIDTH:
        bg_img = bg_img.resize((IMG_WIDTH, int(bg_height * (IMG_WIDTH / bg_width))), Image.LANCZOS)

    img = bg_img.resize((IMG_WIDTH, total_height), Image.LANCZOS)
    
    d = ImageDraw.Draw(img)

    # --- Draw Header (MODIFIED: Title centered, Group name removed) ---
    title_bbox = d.textbbox((0, 0), title, font=font_title)
    title_w = title_bbox[2] - title_bbox[0]
    # Moved title down (from 50 to 85) to center it in the header
    d.text(((IMG_WIDTH - title_w) / 2, 85), title, font=font_title, fill=TITLE_COLOR) 

    # --- Group Name REMOVED ---
    # chat_name_text = f"Group: {chat_name[:35]}" + ('...' if len(chat_name) > 35 else '')
    # chat_bbox = d.textbbox((0, 0), chat_name_text, font=font_chat)
    # chat_w = chat_bbox[2] - chat_bbox[0]
    # d.text(((IMG_WIDTH - chat_w) / 2, 120), chat_name_text, font=font_chat, fill=TEXT_COLOR)
    # ---

    # --- Draw Leaderboard Entries (Unchanged) ---
    if not leaderboard_data:
        no_data_text = "No data found."
        no_data_bbox = d.textbbox((0, 0), no_data_text, font=font_user)
        no_data_w = no_data_bbox[2] - no_data_bbox[0]
        d.text(((IMG_WIDTH - no_data_w) / 2, header_height + (actual_content_height - (no_data_bbox[3] - no_data_bbox[1])) / 2), no_data_text, font=font_user, fill=TEXT_COLOR)
    else:
        y_pos = header_height + 10
        for i, (display_name, count) in enumerate(leaderboard_data):
            rank = f"{i+1}."
            username_display = f"{display_name[:25]}" + ('...' if len(display_name) > 25 else '')
            count_str = f"{count} msgs"

            d.text((60, y_pos), rank, font=font_rank, fill=RANK_COLOR)
            d.text((150, y_pos), username_display, font=font_user, fill=TEXT_COLOR)

            count_bbox = d.textbbox((0, 0), count_str, font=font_user)
            count_w = count_bbox[2] - count_bbox[0]

            d.text( (IMG_WIDTH - count_w - 60, y_pos), count_str, font=font_user, fill=TEXT_COLOR)

            y_pos += item_height

    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes


# --- Leaderboard Core Logic (Unchanged) ---
async def get_leaderboard_data(chat_id: int, scope: str):
    conn = get_db_connection()
    if not conn:
        return ("Database Error", "Unknown", [])

    time_filter = ""
    chat_filter = ""
    title = ""

    if scope == 'daily':
        time_filter = "message_time >= NOW() - INTERVAL '1 day'"
        title = "Today's Leaderboard "
        chat_filter = f"chat_id = {chat_id}"
    elif scope == 'weekly':
        time_filter = "message_time >= NOW() - INTERVAL '7 days'"
        title = "Weekly Leaderboard "
        chat_filter = f"chat_id = {chat_id}"
    elif scope == 'alltime':
        title = "All-Time Leaderboard"
        chat_filter = f"chat_id = {chat_id}"
    else:
        logger.warning(f"Invalid leaderboard scope received: {scope}")
        return ("Invalid Scope", "Error", [])

    filters = []
    if chat_filter: filters.append(chat_filter)
    if time_filter: filters.append(time_filter)
    where_clause = " WHERE " + " AND ".join(filters) if filters else ""

    query = f"""
        WITH RankedMessages AS (
            SELECT
                user_id,
                username,
                message_time,
                ROW_NUMBER() OVER(PARTITION BY user_id ORDER BY message_time DESC) as rn
            FROM messages
            WHERE user_id IN (SELECT DISTINCT user_id FROM messages {where_clause})
        ),
        LatestUsernames AS (
            SELECT user_id, username
            FROM RankedMessages
            WHERE rn = 1
        ),
        UserCounts AS (
            SELECT
                user_id,
                COUNT(*) AS total_messages
            FROM messages
            {where_clause}
            GROUP BY user_id
        )
        SELECT
            lu.username,
            uc.total_messages
        FROM UserCounts uc
        JOIN LatestUsernames lu ON uc.user_id = lu.user_id
        ORDER BY uc.total_messages DESC
        LIMIT 10;
    """

    chat_name_query = "SELECT chat_name FROM chats WHERE chat_id = %s;"

    try:
        with conn.cursor() as cur:
            cur.execute(query)
            results = cur.fetchall()

            cur.execute(chat_name_query, (chat_id,))
            chat_name_result = cur.fetchone()
            if chat_name_result:
                chat_name = chat_name_result[0]
            else:
                chat_name = "This Chat"

        return (title, chat_name, results)

    except Exception as e:
        logger.error(f"Failed to fetch leaderboard: {e}. Query: {query}")
        return ("Database Query Error", "Error", [])
    finally:
        if conn: conn.close()

# --- Format Leaderboard Text (MODIFIED: Removed Chat Name) ---
def format_leaderboard_text(title: str, chat_name: str, data: list):
    escaped_title = escape_markdown(title, version=2)
    # escaped_chat_name = escape_markdown(chat_name, version=2) # No longer needed

    if not data:
        return f"*{escaped_title}*\n\nNo data found\."

    # Removed chat name from here
    leaderboard_text = f"*{escaped_title}* 🏆\n\n"
    for rank, (username, count) in enumerate(data, 1):
        escaped_username = escape_markdown(username, version=2)
        leaderboard_text += f"*{rank}.* {escaped_username}: {count} messages\n"

    return leaderboard_text

# --- Helper function for ticked buttons (Unchanged) ---
def create_leaderboard_keyboard(scope: str, chat_id: int):
    daily_text = "Today"
    weekly_text = "Weekly"
    alltime_text = "All-Time"

    if scope == 'daily':
        daily_text = f"✅ {daily_text}"
    elif scope == 'weekly':
        weekly_text = f"✅ {weekly_text}"
    elif scope == 'alltime':
        alltime_text = f"✅ {alltime_text}"

    keyboard = [
        [InlineKeyboardButton(daily_text, callback_data=f"lb_daily:{chat_id}"),
         InlineKeyboardButton(weekly_text, callback_data=f"lb_weekly:{chat_id}"),
         InlineKeyboardButton(alltime_text, callback_data=f"lb_alltime:{chat_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Ranking Command (Unchanged from last time) ---
async def ranking_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    try:
        sent_message = await update.message.reply_text("🏆 Generating ranking, please wait...")
    except Exception as e:
        logger.error(f"Failed to send loading message: {e}")
        return

    title, chat_name, data = await get_leaderboard_data(chat_id, 'daily')

    if title == "Database Error":
        await sent_message.edit_text("Could not connect to the database.")
        return

    image_bytes = generate_leaderboard_image(title, data, chat_name)
    caption_text = format_leaderboard_text(title, chat_name, data)
    reply_markup = create_leaderboard_keyboard('daily', chat_id)

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
        logger.error(f"Failed to send ranking photo: {e}. Sending text fallback.")
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption_text,
            reply_markup=reply_markup,
            parse_mode=constants.ParseMode.MARKDOWN
        )

# --- Leaderboard Callback (Unchanged) ---
async def leaderboard_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer("Updating...")

    try:
        data_payload = query.data.split('_', 1)[1]
        parts = data_payload.split(':')
        
        scope = parts[0]
        chat_id_str = parts[1]

        chat_id = int(chat_id_str)
    except (IndexError, ValueError) as e:
        logger.error(f"Invalid callback data: {query.data} | Error: {e}")
        return

    title, chat_name, data = await get_leaderboard_data(chat_id, scope)

    if title == "Database Error":
        await query.edit_message_caption(caption="Could not connect to the database.")
        return

    image_bytes = generate_leaderboard_image(title, data, chat_name)
    caption_text = format_leaderboard_text(title, chat_name, data)
    reply_markup = create_leaderboard_keyboard(scope, chat_id)

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


# --- Profile Command (Unchanged) ---
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("*Database is offline\.* Profile unavailable\.")
        return

    user = update.effective_user
    user_id = user.id
    
    raw_username = user.first_name
    if user.last_name:
        raw_username = f"{user.first_name} {user.last_name}"
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
                profile_text += "No group data found\."
            else:
                for chat_id, chat_name, count in group_stats:
                    escaped_chat_name = escape_markdown(chat_name[:25], version=2)
                    suffix = escape_markdown("...", version=2) if len(chat_name) > 25 else ""
                    profile_text += f"• {escaped_chat_name}{suffix}: {count}\n"

            await update.message.reply_text(profile_text, parse_mode=constants.ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Failed to fetch user profile: {e}")
        await update.message.reply_text("Database query error while fetching profile\.")
    finally:
        if conn: conn.close()

# --- Broadcast Feature (Unchanged) ---
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
    if not OWNER_ID:
        await update.message.reply_text("Bot owner ID is not configured. Broadcast disabled.")
        logger.error("Broadcast command used but OWNER_ID is not set.")
        return
    if str(update.effective_user.id) != str(OWNER_ID):
        await update.message.reply_text("This is an owner-only command.")
        return
    if update.effective_chat.type not in [constants.ChatType.PRIVATE]:
        await update.message.reply_text("This command must be used in a private chat.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to the message you want to broadcast.")
        return

    broadcast_message = update.message.reply_to_message
    chat_ids = get_all_active_chat_ids()
    if not chat_ids:
        await update.message.reply_text("No active chats found to broadcast to.")
        return

    await update.message.reply_text(f"Starting broadcast... Sending to {len(chat_ids)} chats.")
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
    await update.message.reply_text(f"✅ Broadcast complete! Successfully sent to {success_count} / {len(tasks)} chats.")

# --- Utility Functions (Unchanged) ---
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
