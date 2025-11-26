# leaderboard_manager.py (FINAL VERSION 4: Maximum Compactness + Verified Caption Fallback)

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
import re 

logger = logging.getLogger(__name__)

# --- ⚙️ Image & Font Configuration (Robust Configuration) ---
FONT_MAIN = "Roboto-Bold.ttf"
FONT_NAMES = "NotoSans-Regular.ttf" 
FONT_FALLBACK = "arial.ttf" 
BACKGROUND_IMAGE_PATH = "25552 (1).jpg" 

# Image Dimensions (MAXIMUM COMPACTNESS)
IMG_WIDTH = 1200
HEADER_HEIGHT = 160  # Reduced for compactness
ROW_HEIGHT = 55      # Reduced for compactness
FOOTER_HEIGHT = 40   # Reduced for compactness

# --- 🎨 Stylish Colors (Dark Theme - Unchanged) ---
COLOR_BG = (15, 23, 42)         
COLOR_TITLE = (255, 255, 255)   
COLOR_SUBTITLE = (56, 189, 248) 
COLOR_TEXT_NAME = (226, 232, 240) 
COLOR_TEXT_COUNT = (148, 163, 184) 
COLOR_RANK_1 = (255, 215, 0)    
COLOR_RANK_2 = (192, 192, 192)  
COLOR_RANK_3 = (205, 127, 50)   
COLOR_DIVIDER = (51, 65, 85)

# --- 👑 Bot Owner (Unchanged) ---
OWNER_ID = os.environ.get('OWNER_ID')
if not OWNER_ID:
    logger.warning("OWNER_ID environment variable is not set. Broadcast command will be disabled.")
# --- End Owner ---

# --- Database Connection (Unchanged) ---
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

# --- Database Setup (Unchanged) ---
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
                        is_active BOOLEAN DEFAULT TRUE NOT NULL,
                        quiz_message_count INT DEFAULT 0 NOT NULL
                    );
                """)
                
                def check_and_add_column(cur, table, column, definition):
                    try:
                        cur.execute(f"SELECT {column} FROM {table} LIMIT 1;")
                    except psycopg2.ProgrammingError:
                        conn.rollback()
                        logger.warning(f"Adding '{column}' column to existing '{table}' table.")
                        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition};")
                        conn.commit()

                check_and_add_column(cur, 'chats', 'chat_type', 'VARCHAR(50)')
                check_and_add_column(cur, 'chats', 'is_active', 'BOOLEAN DEFAULT TRUE NOT NULL')
                check_and_add_column(cur, 'chats', 'quiz_message_count', 'INT DEFAULT 0 NOT NULL')

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
    
    # Stores display name (first_name + last_name)
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


# --- 🖼️ Leaderboard Image Generator (MODIFIED: New Compact Heights) ---
def generate_leaderboard_image(title: str, leaderboard_data: list, chat_name: str, total_count: int):
    # Helper to load font safely
    def get_font(name, size):
        try:
            return ImageFont.truetype(name, size)
        except IOError:
            try:
                return ImageFont.truetype(FONT_FALLBACK, size)
            except:
                return ImageFont.load_default()

    # Load Fonts
    font_title = get_font(FONT_MAIN, 50)  
    font_sub = get_font(FONT_MAIN, 30)    
    font_text = get_font(FONT_NAMES, 36) 
    font_rank = get_font(FONT_MAIN, 36)
    
    # Dynamic Height Calculation (Uses new compact constants)
    content_height = max(200, len(leaderboard_data) * ROW_HEIGHT) 
    total_height = HEADER_HEIGHT + content_height + FOOTER_HEIGHT

    # --- Load Background Image (Unchanged logic for pasting/cropping) ---
    try:
        bg_img = Image.open(BACKGROUND_IMAGE_PATH).convert("RGB")
        
        bg_width, bg_height = bg_img.size
        ratio = IMG_WIDTH / bg_width
        bg_img = bg_img.resize((IMG_WIDTH, int(bg_height * ratio)), Image.LANCZOS)
        
        img = Image.new('RGB', (IMG_WIDTH, total_height), color=COLOR_BG)
        
        img.paste(bg_img, (0, 0)) # Paste the resized background image from the top
            
    except Exception as e:
        logger.error(f"Error loading background image: {e}. Using solid color fallback.")
        img = Image.new('RGB', (IMG_WIDTH, total_height), color=COLOR_BG)
        
    d = ImageDraw.Draw(img)
    # --- End Background Load ---


    # --- Draw Header (Position Adjusted for 160 height) ---
    title_bbox = d.textbbox((0, 0), title, font=font_title)
    title_w = title_bbox[2] - title_bbox[0]
    d.text(((IMG_WIDTH - title_w) / 2, 30), title, font=font_title, fill=COLOR_TITLE) 

    sub_text = f"📊 Total Group Messages: {total_count}"
    sub_bbox = d.textbbox((0, 0), sub_text, font=font_sub)
    sub_w = sub_bbox[2] - sub_bbox[0]
    d.text(((IMG_WIDTH - sub_w) / 2, 90), sub_text, font=font_sub, fill=COLOR_SUBTITLE) 

    d.line([(100, HEADER_HEIGHT - 20), (IMG_WIDTH - 100, HEADER_HEIGHT - 20)], fill=COLOR_DIVIDER, width=2)

    # --- Draw List ---
    y_pos = HEADER_HEIGHT
    
    if not leaderboard_data:
        no_data = "No messages found yet."
        nd_bbox = d.textbbox((0, 0), no_data, font=font_text)
        nd_w = nd_bbox[2] - nd_bbox[0]
        d.text(((IMG_WIDTH - nd_w) / 2, y_pos + 50), no_data, font=font_text, fill=COLOR_TEXT_COUNT)

    # Data is (display_name, count, user_id)
    for i, (display_name, count, user_id) in enumerate(leaderboard_data):
        rank = i + 1
        
        if rank == 1: row_color = COLOR_RANK_1
        elif rank == 2: row_color = COLOR_RANK_2
        elif rank == 3: row_color = COLOR_RANK_3
        else: row_color = COLOR_TEXT_NAME

        # Display Name Logic: Fallback to User ID if name is problematic (Image Fix)
        # Stricter check: must contain at least one letter, number, or standard symbol
        if not display_name or not re.search(r'[a-zA-Z0-9\s]', display_name):
            username_display = str(user_id) 
            row_color = COLOR_TEXT_COUNT 
        else:
            username_display = f"{display_name[:25]}" + ('...' if len(display_name) > 25 else '')

        # Vertical position for text (centered in ROW_HEIGHT=55, font size=36)
        y_text_pos = y_pos + 10 # Adjusted for 55 height

        # 1. Rank Number
        d.text((60, y_text_pos), f"#{rank}", font=font_rank, fill=row_color)

        # 2. Message Count (Right Aligned)
        count_str = f"{count} msgs"
        c_bbox = d.textbbox((0, 0), count_str, font=font_text)
        c_w = c_bbox[2] - c_bbox[0]
        d.text((IMG_WIDTH - c_w - 60, y_text_pos), count_str, font=font_text, fill=COLOR_TEXT_COUNT)

        # 3. Username/User ID
        d.text((160, y_text_pos), username_display, font=font_text, fill=row_color)

        d.line([(60, y_pos + 48), (IMG_WIDTH - 60, y_pos + 48)], fill=COLOR_BG, width=1) # Adjusted line position
        
        y_pos += ROW_HEIGHT # Increments by 55

    # Final save
    bio = io.BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)
    return bio

# --- Leaderboard Core Logic (Unchanged) ---
async def get_leaderboard_data(chat_id: int, scope: str):
    conn = get_db_connection()
    if not conn:
        return ("Database Error", "Unknown", [], 0)

    time_filter = ""
    chat_filter = ""
    title = ""

    if scope == 'daily':
        time_filter = "message_time >= NOW() - INTERVAL '1 day'"
        title = "Today's Top Chatters"
        chat_filter = f"chat_id = {chat_id}"
    elif scope == 'weekly':
        time_filter = "message_time >= NOW() - INTERVAL '7 days'"
        title = "Weekly Top Chatters"
        chat_filter = f"chat_id = {chat_id}"
    elif scope == 'alltime':
        title = "All-Time Legends"
        chat_filter = f"chat_id = {chat_id}"
    else:
        logger.warning(f"Invalid leaderboard scope received: {scope}")
        return ("Invalid Scope", "Error", [], 0)

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
            uc.total_messages,
            uc.user_id  
        FROM UserCounts uc
        JOIN LatestUsernames lu ON uc.user_id = lu.user_id
        ORDER BY uc.total_messages DESC
        LIMIT 10;
    """
    total_query = f"SELECT COUNT(*) FROM messages {where_clause};"
    chat_name_query = "SELECT chat_name FROM chats WHERE chat_id = %s;"


    try:
        with conn.cursor() as cur:
            cur.execute(query)
            results = cur.fetchall() 
            
            cur.execute(total_query)
            total_count = cur.fetchone()[0]

            cur.execute(chat_name_query, (chat_id,))
            chat_name_result = cur.fetchone()
            if chat_name_result:
                chat_name = chat_name_result[0]
            else:
                chat_name = "This Chat"

        return (title, chat_name, results, total_count)

    except Exception as e:
        logger.error(f"Failed to fetch leaderboard: {e}. Query: {query}")
        return ("Database Query Error", "Error", [], 0)
    finally:
        if conn: conn.close()

# --- Format Leaderboard Text (Verified Loosened Fallback Logic - Unchanged) ---
def format_leaderboard_text(title: str, chat_name: str, data: list, total_count: int):
    safe_title = escape_markdown(title, version=2)

    if not data:
        return f"*{safe_title}*\n\nNo data found\."

    leaderboard_text = f"*{safe_title}* 🏆\n"
    leaderboard_text += f"📊 *Total Messages:* `{total_count}`\n"
    leaderboard_text += "━━━━━━━━━━━━━━━━━━\n"

    # Data is (display_name, count, user_id)
    medals = ["🥇", "🥈", "🥉"]
    for rank, (display_name, count, user_id) in enumerate(data, 1):
        
        # LOGIC FOR CAPTION NAME: Only fallback to User ID if the name is truly empty 
        # or has NO letters/numbers (This is necessary to prevent boxes '□□□□' in the text caption).
        if not display_name or not re.search(r'[a-zA-Z0-9]', display_name):
            username_display = str(user_id) 
        else:
            username_display = display_name
        
        rank_icon = medals[rank-1] if rank <= 3 else f"*{rank}\.*"
        
        escaped_username = escape_markdown(username_display, version=2)
        leaderboard_text += f"{rank_icon} {escaped_username} • `{count}`\n"
        
    leaderboard_text += "━━━━━━━━━━━━━━━━━━"


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

# --- Ranking Command (Unchanged) ---
async def ranking_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    try:
        sent_message = await update.message.reply_text("🏆 Generating ranking, please wait...")
    except Exception as e:
        logger.error(f"Failed to send loading message: {e}")
        return

    title, chat_name, data, total = await get_leaderboard_data(chat_id, 'daily')

    if title == "Database Error":
        await sent_message.edit_text("Could not connect to the database.")
        return

    # Pass total_count to image generator
    image_bytes = generate_leaderboard_image(title, data, chat_name, total)
    caption_text = format_leaderboard_text(title, chat_name, data, total)
    reply_markup = create_leaderboard_keyboard('daily', chat_id)

    try:
        await sent_message.delete()
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=image_bytes,
            caption=caption_text,
            reply_markup=reply_markup,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Failed to send ranking photo: {e}. Sending text fallback.")
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption_text,
            reply_markup=reply_markup,
            parse_mode=constants.ParseMode.MARKDOWN_V2
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

    title, chat_name, data, total = await get_leaderboard_data(chat_id, scope)

    if title == "Database Error":
        await query.edit_message_caption(caption="Could not connect to the database.")
        return

    # Pass total_count to image generator
    image_bytes = generate_leaderboard_image(title, data, chat_name, total)
    caption_text = format_leaderboard_text(title, chat_name, data, total)
    reply_markup = create_leaderboard_keyboard(scope, chat_id)

    try:
        await query.edit_message_media(
            media=InputMediaPhoto(media=image_bytes, caption=caption_text, parse_mode=constants.ParseMode.MARKDOWN_V2),
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

            await update.message.reply_text(profile_text, parse_mode=constants.ParseMode.MARKDOWN_V2)
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

# --- Quiz Counter DB Functions (Unchanged) ---

def increment_and_get_quiz_count(chat_id):
    conn = get_db_connection()
    if not conn: return 0
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE chats
                SET quiz_message_count = quiz_message_count + 1
                WHERE chat_id = %s
                RETURNING quiz_message_count;
            """, (chat_id,))
            result = cur.fetchone()
            conn.commit()
            if result:
                return result[0]
            else:
                logger.warning(f"Could not increment count for chat {chat_id}, maybe not registered? (This is normal if it's the very first message)")
                return 0
    except Exception as e:
        logger.error(f"Failed to increment quiz count for {chat_id}: {e}")
        conn.rollback()
        return 0
    finally:
        if conn: conn.close()

def reset_quiz_count(chat_id):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE chats
                SET quiz_message_count = 0
                WHERE chat_id = %s;
            """, (chat_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to reset quiz count for {chat_id}: {e}")
        conn.rollback()
    finally:
        if conn: conn.close()

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
