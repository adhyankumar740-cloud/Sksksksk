# leaderboard_manager.py (FINAL VERSION 19: FIXED unsafe fetchone()[0] for total_count)

import os
import psycopg2
from datetime import datetime, timedelta 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants, InputMediaPhoto
from telegram.ext import ContextTypes, CallbackContext
from telegram.helpers import escape_markdown
import logging
import asyncio
import telegram.error
import io
from PIL import Image, ImageDraw, ImageFont, ImageOps
import re 
import pytz 

logger = logging.getLogger(__name__)

# --- ⚙️ Image & Font Configuration (Unchanged) ---
FONT_MAIN = "Roboto-Bold.ttf"
FONT_NAMES = "NotoSans-Regular.ttf" 
FONT_FALLBACK = "arial.ttf" 
BACKGROUND_IMAGE_PATH = "25552 (1).jpg" 

# Image Dimensions 
IMG_WIDTH = 900  
HEADER_HEIGHT = 160  
ROW_HEIGHT = 40      
FOOTER_HEIGHT = 40   

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

# --- Database Setup (FIXED in V18 - Retained) ---
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
                # Fix from V18: Corrected typo from 'check_and_column' to 'check_and_add_column'
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


# --- 🖼️ Leaderboard Image Generator (Unchanged) ---
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
    font_title = get_font(FONT_MAIN, 45) 
    font_sub = get_font(FONT_MAIN, 28)    
    font_text = get_font(FONT_NAMES, 24) 
    font_rank = get_font(FONT_MAIN, 26) 
    
    # Dynamic Height Calculation 
    content_height = max(100, len(leaderboard_data) * ROW_HEIGHT) 
    total_height = HEADER_HEIGHT + content_height + FOOTER_HEIGHT

    # --- Load Background Image (STRICT ACTION: Scale/Stretch to exact dynamic size) ---
    try:
        bg_img = Image.open(BACKGROUND_IMAGE_PATH).convert("RGB")
        
        # Strict Action: Scale/Stretch the BG image to exactly match the dynamic dimensions.
        bg_img = bg_img.resize((IMG_WIDTH, total_height), Image.LANCZOS)
        
        img = Image.new('RGB', (IMG_WIDTH, total_height), color=COLOR_BG)
        
        # Paste the stretched background image, ensuring full coverage
        img.paste(bg_img, (0, 0)) 
            
    except Exception as e:
        logger.error(f"Error loading background image: {e}. Using solid color fallback.")
        img = Image.new('RGB', (IMG_WIDTH, total_height), color=COLOR_BG)
        
    d = ImageDraw.Draw(img)
    # --- End Background Load ---


    # --- Draw Header ---
    title_bbox = d.textbbox((0, 0), title, font=font_title)
    title_w = title_bbox[2] - title_bbox[0]
    d.text(((IMG_WIDTH - title_w) / 2, 35), title, font=font_title, fill=COLOR_TITLE) 

    sub_text = f"📊 Total Messages: {total_count}" 
    sub_bbox = d.textbbox((0, 0), sub_text, font=font_sub)
    sub_w = sub_bbox[2] - sub_bbox[0]
    d.text(((IMG_WIDTH - sub_w) / 2, 95), sub_text, font=font_sub, fill=COLOR_SUBTITLE) 

    # FIX: Reduced divider line width from 2 to 1 for a lighter look
    d.line([(60, HEADER_HEIGHT - 20), (IMG_WIDTH - 60, HEADER_HEIGHT - 20)], fill=COLOR_DIVIDER, width=1) 

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

        # Display Name Logic (IN IMAGE)
        if not display_name or not re.search(r'[a-zA-Z0-9\s]', display_name):
            username_display = str(user_id) 
            row_color = COLOR_TEXT_COUNT 
        else:
            # Shorten display name if too long
            username_display = f"{display_name[:25]}" + ('...' if len(display_name) > 25 else '')

        # Vertical position for text 
        y_text_pos = y_pos + 6 

        # 1. Rank Number (No #)
        d.text((60, y_text_pos), f"{rank}", font=font_rank, fill=row_color)

        # 2. Message Count (Right Aligned)
        count_str = f"{count} msgs"
        c_bbox = d.textbbox((0, 0), count_str, font=font_text)
        c_w = c_bbox[2] - c_bbox[0]
        d.text((IMG_WIDTH - c_w - 60, y_text_pos), count_str, font=font_text, fill=COLOR_TEXT_COUNT)

        # 3. Username/User ID
        d.text((160, y_text_pos), username_display, font=font_text, fill=row_color)
        
        y_pos += ROW_HEIGHT

    # Final save
    bio = io.BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)
    return bio

# --- Leaderboard Core Logic (MODIFIED to safely fetch total_count) ---
async def get_leaderboard_data(chat_id: int, scope: str, current_user_id: int = None):
    conn = get_db_connection()
    if not conn:
        return ("Database Error", "Unknown", [], 0, None)

    ist_tz = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.now(ist_tz)
    
    # Placeholders for parameterized query components
    params = []
    time_filter_clause = ""
    chat_filter_clause = ""
    title = ""

    # Scope Logic
    if scope == 'global':
        title = "Global All-Time Legends"
    elif scope == 'daily':
        title = "Today's Top Chatters"
        chat_filter_clause = "chat_id = %s"
        params.append(chat_id)
        
        # Calculate start of 'Today' in IST (12:00 AM IST)
        start_of_day_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        time_filter_clause = "message_time >= %s"
        params.append(start_of_day_ist) 
        
    elif scope == 'weekly':
        title = "Weekly Top Chatters"
        chat_filter_clause = "chat_id = %s"
        params.append(chat_id)
        
        # Calculate 7 days ago in IST
        seven_days_ago_ist = now_ist - timedelta(days=7) 
        time_filter_clause = "message_time >= %s"
        params.append(seven_days_ago_ist) 
        
    elif scope == 'alltime':
        title = "All-Time Legends (Local Chat)" 
        chat_filter_clause = "chat_id = %s"
        params.append(chat_id)
    else:
        logger.warning(f"Invalid leaderboard scope received: {scope}")
        return ("Invalid Scope", "Error", [], 0, None)

    filters = []
    if chat_filter_clause: filters.append(chat_filter_clause)
    if time_filter_clause: filters.append(time_filter_clause)
    where_clause = " WHERE " + " AND ".join(filters) if filters else ""
    
    # The SQL query uses placeholders (%s) which will be filled by the params list during execution
    
    # 1. Query for Top 10 users
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
    
    # 2. Query for Current User's Stats (Rank and Count)
    current_user_data = None
    if current_user_id:
        user_stats_params = list(params)
        user_stats_params.append(current_user_id) 

        user_stats_query = f"""
            WITH UserCounts AS (
                SELECT
                    user_id,
                    COUNT(*) AS total_messages,
                    RANK() OVER (ORDER BY COUNT(*) DESC) as user_rank
                FROM messages
                {where_clause}
                GROUP BY user_id
            )
            SELECT
                uc.total_messages,
                uc.user_rank
            FROM UserCounts uc
            WHERE uc.user_id = %s;
        """
        try:
            with conn.cursor() as cur:
                # Pass user_stats_params for execution
                cur.execute(user_stats_query, user_stats_params)
                stats_result = cur.fetchone()
                if stats_result:
                    current_user_data = (int(stats_result[1]), stats_result[0])
        except Exception as e:
            logger.error(f"Failed to fetch current user stats: {e}")
            
    chat_name = "All Registered Chats" # Default for global
    total_count = 0 # Initialize for safety

    try:
        with conn.cursor() as cur:
            # Execute the main query with main parameters
            cur.execute(query, params)
            results = cur.fetchall() 
            
            # Execute the total count query with main parameters
            cur.execute(total_query, params)
            
            # FIX: Safely fetch total_count to prevent list index out of range/NoneType error
            total_count_result = cur.fetchone()
            if total_count_result:
                total_count = total_count_result[0]
            else:
                total_count = 0 # Fallback in case COUNT(*) fails to return a row

            if scope != 'global':
                chat_name_query = "SELECT chat_name FROM chats WHERE chat_id = %s;"
                cur.execute(chat_name_query, (chat_id,))
                chat_name_result = cur.fetchone()
                if chat_name_result:
                    chat_name = chat_name_result[0]
                else:
                    chat_name = "This Chat"

        return (title, chat_name, results, total_count, current_user_data)

    except Exception as e:
        logger.error(f"Failed to fetch leaderboard: {e}. Query: {query}")
        return ("Database Query Error", "Error", [], 0, None)
    finally:
        if conn: conn.close()

# --- Format Leaderboard Text (Unchanged) ---
def format_leaderboard_text(title: str, chat_name: str, data: list, total_count: int, user_stats: tuple, current_user_name: str):
    # Escape the entire title once for safe usage inside Markdown V2 static strings
    safe_title = escape_markdown(title, version=2) 
    leaderboard_text = ""
    
    # --- 1. User Stats Section ---
    if user_stats:
        rank, count = user_stats
        
        # Escape user name before using it
        escaped_user_name = escape_markdown(current_user_name, version=2)
        
        # FIX: Escaping static characters: \', \(, \)
        leaderboard_text += f"👤 *{escaped_user_name}\'s Stats \({safe_title}\)*\n"
        leaderboard_text += "━━━━━━━━━━━━━━━━━━\n"
        
        # Get the first word of the title (e.g., 'Today' from "Today's Top Chatters") and escape it.
        first_word_of_title = escape_markdown(title.split(' ')[0], version=2)
        leaderboard_text += f"*{first_word_of_title}* Rank: `{rank}`\n" 
        
        leaderboard_text += f"Messages: `{count}`\n"
        leaderboard_text += "━━━━━━━━━━━━━━━━━━\n\n"
        
    # --- 2. Top 10 Section ---
    leaderboard_text += f"*{safe_title} Top 10*\n" 
    
    # FIX: Escaping static characters: \(, \)
    leaderboard_text += f"📊 *Total Messages \(Scope\):* `{total_count}`\n"
    leaderboard_text += "━━━━━━━━━━━━━━━━━━\n"

    if not data:
        # FIX: Escaping static period \.
        leaderboard_text += "No data found for the Top 10\."
        return leaderboard_text

    # Data is (display_name, count, user_id)
    medals = ["🥇", "🥈", "🥉"]
    for rank, (display_name, count, user_id) in enumerate(data, 1):
        
        username_display = display_name if display_name else ''
        rank_icon = medals[rank-1] if rank <= 3 else f"*{rank}\.*"
        
        # Ensure name is properly escaped before inserting into MDV2
        escaped_username = escape_markdown(username_display, version=2)
        
        if not escaped_username.strip():
            escaped_username = " "

        # FIX: Escaping static period \.
        leaderboard_text += f"{rank_icon} {escaped_username} • `{count}`\n"
        
    leaderboard_text += "━━━━━━━━━━━━━━━━━━"


    return leaderboard_text

# --- Helper function for ticked buttons (Unchanged) ---
def create_leaderboard_keyboard(scope: str, chat_id: int):
    daily_text = "Today"
    weekly_text = "Weekly"
    alltime_local_text = "All-Time" 
    
    # Row 2 buttons
    this_chat_text = "This Chat" 
    global_text = "Global Ranking" 
    
    # 1. Handle checkmarks for Row 1 buttons (Daily/Weekly)
    if scope == 'daily':
        daily_text = f"✅ {daily_text}"
    elif scope == 'weekly':
        weekly_text = f"✅ {weekly_text}"
        
    # 2. Handle checkmarks for Row 2 buttons and Row 1 'All-Time'
    if scope == 'alltime':
        alltime_local_text = f"✅ {alltime_local_text}"
        this_chat_text = f"✅ {this_chat_text}"
    elif scope == 'global':
        global_text = f"✅ {global_text}"

    keyboard = [
        # Row 1: Today, Weekly, All-Time (Local)
        [InlineKeyboardButton(daily_text, callback_data=f"lb_daily:{chat_id}"),
         InlineKeyboardButton(weekly_text, callback_data=f"lb_weekly:{chat_id}"),
         InlineKeyboardButton(alltime_local_text, callback_data=f"lb_alltime:{chat_id}")],
        # Row 2: This Chat (All-Time) | Global Ranking
        [InlineKeyboardButton(this_chat_text, callback_data=f"lb_alltime:{chat_id}"), 
         InlineKeyboardButton(global_text, callback_data=f"lb_global:{chat_id}")] 
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Ranking Command (Unchanged) ---
async def ranking_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    current_user_id = update.effective_user.id
    
    current_user_name = update.effective_user.first_name
    if update.effective_user.last_name:
        current_user_name += f" {update.effective_user.last_name}"

    # DM Restriction Logic
    if chat_type == constants.ChatType.PRIVATE:
        await update.message.reply_text("🚫 This command can only be used in a group or supergroup chat\.")
        return
        
    try:
        sent_message = await update.message.reply_text("🏆 Generating ranking, please wait...")
    except Exception as e:
        logger.error(f"Failed to send loading message: {e}")
        return

    # Use 'daily' as default scope
    title, chat_name, data, total, user_stats = await get_leaderboard_data(chat_id, 'daily', current_user_id)

    if title == "Database Error":
        await sent_message.edit_text("Could not connect to the database.")
        return

    # Pass all data to formatter
    image_bytes = generate_leaderboard_image(title, data, chat_name, total)
    caption_text = format_leaderboard_text(title, chat_name, data, total, user_stats, current_user_name)
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
        current_user_id = update.effective_user.id
        current_user_name = update.effective_user.first_name
        if update.effective_user.last_name:
            current_user_name += f" {update.effective_user.last_name}"
            
    except (IndexError, ValueError) as e:
        logger.error(f"Invalid callback data: {query.data} | Error: {e}")
        return

    # scope can be 'daily', 'weekly', 'alltime' (local), or 'global'
    title, chat_name, data, total, user_stats = await get_leaderboard_data(chat_id, scope, current_user_id)

    if title == "Database Error":
        await query.edit_message_caption(caption="Could not connect to the database.")
        return

    # Pass all data to formatter
    image_bytes = generate_leaderboard_image(title, data, chat_name, total)
    caption_text = format_leaderboard_text(title, chat_name, data, total, user_stats, current_user_name)
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
    
    # Escape parentheses in the profile text template
    profile_text = f"👤 *{username}'s Profile Stats* 📈\n\n"

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM messages WHERE user_id = %s;", (user_id,))
            total_messages_result = cur.fetchone()
            total_messages = total_messages_result[0] if total_messages_result else 0
            
            # Escape parentheses in the stats line
            profile_text += f"**Total Messages \(All Time\):** {total_messages}\n\n"

            # Query uses LEFT JOIN and COALESCE (Unchanged robust logic)
            cur.execute("""
                SELECT m.chat_id, COALESCE(c.chat_name, 'Unknown Chat'), COUNT(*) AS count
                FROM messages m
                LEFT JOIN chats c ON m.chat_id = c.chat_id
                WHERE m.user_id = %s
                GROUP BY m.chat_id, COALESCE(c.chat_name, 'Unknown Chat')
                ORDER BY count DESC;
            """, (user_id,))
            group_stats = cur.fetchall()

            profile_text += "*Messages per Group:*\n"
            if not group_stats:
                profile_text += "No group data found\."
            else:
                for chat_id, chat_name, count in group_stats:
                    # Escape chat name (which might contain reserved chars like '(' or ')' from the DB)
                    chat_name_for_display = chat_name[:25]
                    escaped_chat_name = escape_markdown(chat_name_for_display, version=2)
                    
                    suffix = escape_markdown("...", version=2) if len(chat_name) > 25 else ""
                    profile_text += f"• {escaped_chat_name}{suffix}: {count}\n"
            
            # --- NEW: Fetch and Send Profile Photo ---
            photos = await context.bot.get_user_profile_photos(user_id, limit=1)
            photo_file_id = None
            if photos.photos and photos.photos[0]:
                # Get the largest photo file_id of the latest photo
                photo_file_id = photos.photos[0][-1].file_id

            if photo_file_id:
                # Send photo with profile text as caption
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=photo_file_id,
                    caption=profile_text,
                    parse_mode=constants.ParseMode.MARKDOWN_V2
                )
            else:
                # Send text only if no photo found
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
def get_chat_stats():
    """
    Fetches the count of active group/supergroup chats and private chats (DMs).
    Returns: A dictionary like {'groups': int, 'dms': int, 'total_messages': int} or None on error.
    """
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to DB for chat stats.")
        return None
    try:
        with conn.cursor() as cur:
            # Count active group/supergroup chats
            cur.execute("""
                SELECT COUNT(*) FROM chats 
                WHERE is_active = TRUE AND chat_type IN ('group', 'supergroup');
            """)
            group_count = cur.fetchone()[0]

            # Count active private chats (DMs)
            cur.execute("""
                SELECT COUNT(*) FROM chats 
                WHERE is_active = TRUE AND chat_type = 'private';
            """)
            dm_count = cur.fetchone()[0]

            # Count total messages for a general activity metric
            cur.execute("SELECT COUNT(*) FROM messages;")
            total_messages_result = cur.fetchone()
            total_messages = total_messages_result[0] if total_messages_result else 0


        return {
            'groups': group_count,
            'dms': dm_count,
            'total_messages': total_messages,
        }
    except Exception as e:
        logger.error(f"Failed to fetch chat stats: {e}")
        return None
    finally:
        if conn:
            conn.close()

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
