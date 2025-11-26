# leaderboard_manager.py (FINAL VERSION WITH BACKGROUND IMAGE & PROGRESS BARS)

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

# --- ⚙️ Image & Font Configuration ---
FONT_MAIN = "Roboto-Bold.ttf"
FONT_NAMES = "NotoSans-Regular.ttf" 
FONT_FALLBACK = "arial.ttf" 
BACKGROUND_IMAGE_PATH = "25552 (1).jpg" # 💡 Background Image path restored

# Image Dimensions
IMG_WIDTH = 1200
HEADER_HEIGHT = 220
ROW_HEIGHT = 70
FOOTER_HEIGHT = 60

# --- 🎨 Stylish Colors (Dark Theme) ---
COLOR_BG = (15, 23, 42)         
COLOR_TITLE = (255, 255, 255)   
COLOR_SUBTITLE = (56, 189, 248) 
COLOR_TEXT_NAME = (226, 232, 240) 
COLOR_TEXT_COUNT = (148, 163, 184) 
COLOR_RANK_1 = (255, 215, 0)    
COLOR_RANK_2 = (192, 192, 192)  
COLOR_RANK_3 = (205, 127, 50)   
COLOR_DIVIDER = (51, 65, 85)
# Bar Colors
BAR_COLOR = (255, 255, 255, 25) # Semi-transparent white bar (Alpha=25)
BAR_MAX_WIDTH = 1080 # Max width of the bar for the top chatter (IMG_WIDTH - 120)

# --- 👑 Bot Owner (Unchanged) ---
OWNER_ID = os.environ.get('OWNER_ID')

# --- Database Connection (Unchanged) ---
def get_db_connection():
    DB_URL = os.environ.get('DATABASE_URL')
    if not DB_URL:
        logger.error("DATABASE_URL environment variable is not set.")
        return None
    try:
        return psycopg2.connect(DB_URL, sslmode='require')
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None

# --- Database Setup, Chat Registration, Message Counting (Unchanged logic) ---
def setup_database():
    # ... (Database setup code) ...
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
            conn.commit()
            logger.info("Database setup complete.")
        except Exception as e:
            logger.error(f"Database setup failed: {e}")
            conn.rollback()
        finally:
            if conn: conn.close()

def register_chat(update: Update):
    # ... (Chat registration code) ...
    conn = get_db_connection()
    if not conn: return
    chat = update.effective_chat
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO chats (chat_id, chat_name, chat_type, last_activity, is_active)
                VALUES (%s, %s, %s, NOW(), TRUE)
                ON CONFLICT (chat_id) DO UPDATE
                SET last_activity = NOW(), chat_name = %s, chat_type = %s, is_active = TRUE;
            """, (chat.id, chat.title, chat.type, chat.title, chat.type))
        conn.commit()
    except Exception:
        pass
    finally:
        if conn: conn.close()

async def update_message_count_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (Message counting code with username/display name priority) ...
    conn = get_db_connection()
    if not conn: return
    user = update.effective_user
    
    if user.username:
        identifier = user.username
    else:
        identifier = user.first_name + (f" {user.last_name}" if user.last_name else "")
    
    register_chat(update)
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO messages (chat_id, user_id, username) VALUES (%s, %s, %s);", 
                        (update.effective_chat.id, user.id, identifier)) 
        conn.commit()
    except Exception as e:
        logger.error(f"DB Insert Error: {e}")
    finally:
        if conn: conn.close()
        

# --- 🖼️ Advanced Image Generation (MODIFIED: Background & Bar Logic) ---
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
    
    # Dynamic Height Calculation
    content_height = max(300, len(leaderboard_data) * ROW_HEIGHT)
    total_height = HEADER_HEIGHT + content_height + FOOTER_HEIGHT

    # --- Load Background Image (New Logic) ---
    try:
        bg_img = Image.open(BACKGROUND_IMAGE_PATH).convert("RGB")
        # Resize background to fit the new total size
        bg_width, bg_height = bg_img.size
        ratio = IMG_WIDTH / bg_width
        bg_img = bg_img.resize((IMG_WIDTH, int(bg_height * ratio)), Image.LANCZOS)
        
        # Crop/Pad the background to match the total height
        if bg_img.height < total_height:
            # If smaller, create a new image and paste the background, filling the rest with BG color
            img = Image.new('RGB', (IMG_WIDTH, total_height), color=COLOR_BG)
            img.paste(bg_img, (0, 0))
        else:
            # If larger, crop it to the exact height
            img = bg_img.crop((0, 0, IMG_WIDTH, total_height))
            
    except Exception as e:
        logger.error(f"Error loading background image: {e}. Using solid color fallback.")
        img = Image.new('RGB', (IMG_WIDTH, total_height), color=COLOR_BG)
        
    d = ImageDraw.Draw(img)
    # --- End Background Load ---


    # --- Draw Header ---
    title_bbox = d.textbbox((0, 0), title, font=font_title)
    title_w = title_bbox[2] - title_bbox[0]
    d.text(((IMG_WIDTH - title_w) / 2, 50), title, font=font_title, fill=COLOR_TITLE)

    sub_text = f"📊 Total Group Messages: {total_count}"
    sub_bbox = d.textbbox((0, 0), sub_text, font=font_sub)
    sub_w = sub_bbox[2] - sub_bbox[0]
    d.text(((IMG_WIDTH - sub_w) / 2, 120), sub_text, font=font_sub, fill=COLOR_SUBTITLE)

    d.line([(100, HEADER_HEIGHT - 20), (IMG_WIDTH - 100, HEADER_HEIGHT - 20)], fill=COLOR_DIVIDER, width=2)

    # --- Draw List and Progress Bars (New Logic) ---
    y_pos = HEADER_HEIGHT
    
    if not leaderboard_data:
        # ... no data drawing logic ...
        pass
    
    # Get Max Count for Bar Calculation
    max_count = leaderboard_data[0][2] if leaderboard_data and leaderboard_data[0][2] > 0 else 1

    # Create an alpha layer for semi-transparent bars
    alpha_img = Image.new('RGBA', img.size, (0, 0, 0, 0))
    alpha_d = ImageDraw.Draw(alpha_img)

    for i, (user_id, identifier, count) in enumerate(leaderboard_data):
        rank = i + 1
        
        # Color based on Rank
        if rank == 1: row_color = COLOR_RANK_1
        elif rank == 2: row_color = COLOR_RANK_2
        elif rank == 3: row_color = COLOR_RANK_3
        else: row_color = COLOR_TEXT_NAME

        # Display Name Logic (Username/Display Name/User ID)
        display_name = identifier
        if not display_name or not any(c.isalnum() for c in display_name):
            display_name = f"User ID: {user_id}" 
            row_color = COLOR_TEXT_COUNT 

        # --- 💡 Draw Progress Bar ---
        # Calculate bar width based on max count
        bar_width = int((count / max_count) * BAR_MAX_WIDTH)
        bar_height = ROW_HEIGHT - 10 
        bar_x1 = 60
        bar_y1 = y_pos + 5
        bar_x2 = bar_x1 + bar_width
        bar_y2 = y_pos + bar_height
        
        alpha_d.rectangle([(bar_x1, bar_y1), (bar_x2, bar_y2)], fill=BAR_COLOR)
        # --- End Progress Bar ---

        # 1. Rank Number
        d.text((60, y_pos), f"#{rank}", font=font_rank, fill=row_color)

        # 2. Message Count (Right Aligned)
        count_str = f"{count} msgs"
        c_bbox = d.textbbox((0, 0), count_str, font=font_text)
        c_w = c_bbox[2] - c_bbox[0]
        d.text((IMG_WIDTH - c_w - 60, y_pos), count_str, font=font_text, fill=COLOR_TEXT_COUNT)

        # 3. Username/User ID
        d.text((160, y_pos), display_name, font=font_text, fill=row_color)

        y_pos += ROW_HEIGHT

    # Merge alpha layer (bars) onto the main image
    img = Image.alpha_composite(img.convert("RGBA"), alpha_img).convert("RGB")
    
    # Final save
    bio = io.BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)
    return bio

# --- 📊 Fetch Data Logic (Unchanged) ---
async def get_leaderboard_data(chat_id: int, scope: str):
    conn = get_db_connection()
    if not conn: return None, None, [], 0

    if scope == 'daily':
        time_filter = "message_time >= NOW() - INTERVAL '1 day'"
        title = "Today's Top Chatters"
    elif scope == 'weekly':
        time_filter = "message_time >= NOW() - INTERVAL '7 days'"
        title = "Weekly Top Chatters"
    else:
        time_filter = "1=1" 
        title = "All-Time Legends"

    query = f"""
        SELECT user_id, username, COUNT(*) as cnt 
        FROM messages 
        WHERE chat_id = %s AND {time_filter}
        GROUP BY user_id, username 
        ORDER BY cnt DESC 
        LIMIT 10;
    """
    total_query = f"SELECT COUNT(*) FROM messages WHERE chat_id = %s AND {time_filter};"
    name_query = "SELECT chat_name FROM chats WHERE chat_id = %s;"

    try:
        with conn.cursor() as cur:
            cur.execute(query, (chat_id,))
            data = cur.fetchall() 
            
            cur.execute(total_query, (chat_id,))
            total_res = cur.fetchone()
            total_count = total_res[0] if total_res else 0

            cur.execute(name_query, (chat_id,))
            name_res = cur.fetchone()
            chat_name = name_res[0] if name_res else "This Chat"

            return title, chat_name, data, total_count
    except Exception as e:
        logger.error(f"Data Fetch Error: {e}")
        return None, None, [], 0
    finally:
        if conn: conn.close()

# --- 📝 Text Formatting (Unchanged) ---
def format_leaderboard_text(title: str, chat_name: str, data: list, total_count: int):
    safe_title = escape_markdown(title, version=2)
    
    text = f"🏆 *{safe_title}*\n"
    text += f"📊 *Total Messages:* `{total_count}`\n"
    text += "━━━━━━━━━━━━━━━━━━\n"

    if not data:
        text += "_No messages recorded in this period\._"
        return text

    medals = ["🥇", "🥈", "🥉"]
    for i, (user_id, identifier, count) in enumerate(data):
        rank_icon = medals[i] if i < 3 else f"*{i+1}\.*"
        
        display_name = identifier
        if not display_name or not any(c.isalnum() for c in display_name):
            display_name = f"User ID: {user_id}"

        safe_name = escape_markdown(display_name, version=2) 
        text += f"{rank_icon} {safe_name} • `{count}`\n"
    
    text += "━━━━━━━━━━━━━━━━━━"
    return text

# --- 🎹 Keyboards, Commands, and Utilities (Unchanged) ---
def create_keyboard(scope: str, chat_id: int):
    btns = []
    for sc, label in [('daily', 'Today'), ('weekly', 'Weekly'), ('alltime', 'All-Time')]:
        txt = f"✅ {label}" if sc == scope else label
        btns.append(InlineKeyboardButton(txt, callback_data=f"lb_{sc}:{chat_id}"))
    return InlineKeyboardMarkup([btns])

async def ranking_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        msg = await update.message.reply_text("🔄 **Calculating stats...**", parse_mode=constants.ParseMode.MARKDOWN)
    except: return

    title, chat_name, data, total = await get_leaderboard_data(chat_id, 'daily')

    if not title:
        await msg.edit_text("❌ Database Error.")
        return

    img = generate_leaderboard_image(title, data, chat_name, total)
    caption = format_leaderboard_text(title, chat_name, data, total)
    kb = create_keyboard('daily', chat_id)

    await msg.delete()
    if img:
        await context.bot.send_photo(chat_id, photo=img, caption=caption, reply_markup=kb, parse_mode=constants.ParseMode.MARKDOWN_V2)
    else:
        await context.bot.send_message(chat_id, text=caption, reply_markup=kb, parse_mode=constants.ParseMode.MARKDOWN_V2)

async def leaderboard_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    try:
        _, payload = query.data.split('_', 1)
        scope, chat_id_str = payload.split(':')
        chat_id = int(chat_id_str)
    except: return

    title, chat_name, data, total = await get_leaderboard_data(chat_id, scope)
    if not title: return

    img = generate_leaderboard_image(title, data, chat_name, total)
    caption = format_leaderboard_text(title, chat_name, data, total)
    kb = create_keyboard(scope, chat_id)

    try:
        await query.edit_message_media(
            media=InputMediaPhoto(media=img, caption=caption, parse_mode=constants.ParseMode.MARKDOWN_V2),
            reply_markup=kb
        )
    except telegram.error.BadRequest:
        pass 

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("Database offline.")
        return

    user = update.effective_user
    safe_name = escape_markdown(user.first_name, version=2)
    
    txt = f"👤 *{safe_name}'s Profile*\n━━━━━━━━━━━━━━━━━━\n"

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM messages WHERE user_id = %s;", (user.id,))
            total = cur.fetchone()[0]
            txt += f"🔥 *Total Messages:* `{total}`\n\n"

            cur.execute("""
                SELECT c.chat_name, COUNT(*) as cnt 
                FROM messages m 
                JOIN chats c ON m.chat_id = c.chat_id 
                WHERE m.user_id = %s 
                GROUP BY c.chat_name 
                ORDER BY cnt DESC LIMIT 5;
            """, (user.id,))
            rows = cur.fetchall()
            
            if rows:
                txt += "*Top Groups:*\n"
                for name, cnt in rows:
                    txt += f"• {escape_markdown(name, 2)}: `{cnt}`\n"
            else:
                txt += "_No active groups found._"

        await update.message.reply_text(txt, parse_mode=constants.ParseMode.MARKDOWN_V2)
    except Exception as e:
        logger.error(f"Profile Error: {e}")
    finally:
        if conn: conn.close()

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(OWNER_ID): return
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message to broadcast.")
        return

    conn = get_db_connection()
    chat_ids = []
    if conn:
        with conn.cursor() as cur:
            cur.execute("SELECT chat_id FROM chats WHERE is_active = TRUE")
            chat_ids = [row[0] for row in cur.fetchall()]
        conn.close()

    await update.message.reply_text(f"Broadcasting to {len(chat_ids)} chats...")
    
    count = 0
    for cid in chat_ids:
        try:
            await context.bot.copy_message(cid, update.effective_chat.id, update.message.reply_to_message.message_id)
            count += 1
        except: pass
    
    await update.message.reply_text(f"Done. Success: {count}")

def increment_and_get_quiz_count(chat_id):
    conn = get_db_connection()
    if not conn: return 0
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE chats SET quiz_message_count = quiz_message_count + 1 WHERE chat_id = %s RETURNING quiz_message_count;", (chat_id,))
            res = cur.fetchone()
            conn.commit()
            return res[0] if res else 0
    except: return 0
    finally:
        if conn: conn.close()

def reset_quiz_count(chat_id):
    conn = get_db_connection()
    if not conn: return
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE chats SET quiz_message_count = 0 WHERE chat_id = %s;", (chat_id,))
        conn.commit()
    except: pass
    finally:
        if conn: conn.close()

# --- End of File ---
