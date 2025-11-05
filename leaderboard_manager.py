# leaderboard_manager.py

import os
import psycopg2
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import ContextTypes, CallbackContext
import logging
import asyncio
import telegram.error

logger = logging.getLogger(__name__)

LEADERBOARD_PHOTO_URL_KEY = os.environ.get('TELEGRAM_LEADERBOARD_PHOTO_URL', 'https://via.placeholder.com/600x200?text=Leaderboard+Image+Placeholder')

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
    """Creates the necessary tables and performs schema migration if needed."""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                # 1. messages table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id BIGSERIAL PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        username VARCHAR(255),
                        message_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                # 2. chats table (with required columns)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS chats (
                        chat_id BIGINT PRIMARY KEY,
                        chat_name VARCHAR(255),
                        chat_type VARCHAR(50),
                        last_activity TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                # 3. Migration check (if the table existed without chat_type)
                try:
                    cur.execute("SELECT chat_type FROM chats LIMIT 1;")
                except psycopg2.ProgrammingError:
                    logger.warning("Adding 'chat_type' column to existing 'chats' table.")
                    cur.execute("ALTER TABLE chats ADD COLUMN chat_type VARCHAR(50);")
                
            conn.commit()
            logger.info("Database setup complete.")
        except Exception as e:
            logger.error(f"Database setup failed: {e}")
        finally:
            conn.close()

# --- Chat Registration (Same) ---

def register_chat(update: Update):
    conn = get_db_connection()
    if not conn:
        return
    
    chat = update.effective_chat
    chat_id = chat.id
    chat_name = chat.title or (chat.username or chat.first_name)
    chat_type = chat.type

    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO chats (chat_id, chat_name, chat_type, last_activity)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (chat_id) DO UPDATE 
                SET last_activity = NOW(), chat_name = %s, chat_type = %s;
            """, (chat_id, chat_name, chat_type, chat_name, chat_type))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to register chat: {e}")
    finally:
        if conn:
            conn.close()

# --- Message Count Update (Same) ---

async def update_message_count_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    if not conn:
        return
        
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
        if conn:
            conn.close()

# --- Leaderboard Core Logic (FIXED) ---

async def get_leaderboard_data(chat_id: int, scope: str):
    """Fetches and processes leaderboard data based on the scope. FIXES DOUBLE WHERE."""
    conn = get_db_connection()
    if not conn:
        return "*Database is offline.* Leaderboard unavailable."

    # Define constraints
    time_filter = ""
    chat_filter = ""
    title = ""
    
    if scope == 'daily':
        time_filter = "message_time >= NOW() - INTERVAL '1 day'"
        title = "Aaj Ka Leaderboard (Local)"
        chat_filter = f"chat_id = {chat_id}"
    elif scope == 'weekly':
        time_filter = "message_time >= NOW() - INTERVAL '7 days'"
        title = "Hafte Bhar Ka Leaderboard (Local)"
        chat_filter = f"chat_id = {chat_id}"
    elif scope == 'alltime':
        title = "Shuru Se Ab Tak (Local)"
        chat_filter = f"chat_id = {chat_id}"
    elif scope == 'global_daily':
        time_filter = "message_time >= NOW() - INTERVAL '1 day'"
        title = "🌍 Global Leaderboard (24 Hrs)"
    elif scope == 'global_alltime':
        title = "🌍 Global Leaderboard (All Time)"
    
    # Combine filters using AND
    filters = []
    if chat_filter:
        filters.append(chat_filter)
    if time_filter:
        filters.append(time_filter)
        
    where_clause = " WHERE " + " AND ".join(filters) if filters else ""

    query = f"""
        SELECT username, COUNT(*) AS total_messages
        FROM messages
        {where_clause}
        GROUP BY username
        ORDER BY total_messages DESC
        LIMIT 10;
    """

    try:
        with conn.cursor() as cur:
            cur.execute(query)
            results = cur.fetchall()
        
        if not results:
            return f"*{title}*:\nKoi data nahi mila."
            
        leaderboard_text = f"*{title}* 🏆\n\n"
        for rank, (username, count) in enumerate(results, 1):
            leaderboard_text += f"*{rank}.* {username}: {count} messages\n"
            
        return leaderboard_text
        
    except Exception as e:
        logger.error(f"Failed to fetch leaderboard: {e}. Query: {query}")
        return "Database query error."
    finally:
        if conn:
            conn.close()

# --- Leaderboard Command (Same) ---

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    try:
        photo_message = await context.bot.send_photo(
            chat_id=chat_id,
            photo=LEADERBOARD_PHOTO_URL_KEY,
            caption="🏆 Loading Leaderboard... 📊"
        )
        photo_message_id = photo_message.message_id
    except telegram.error.BadRequest as e:
        logger.warning(f"Failed to send leaderboard photo: {e}")
        photo_message_id = None
    except Exception as e:
        logger.error(f"Error sending photo: {e}")
        photo_message_id = None

    leaderboard_text = await get_leaderboard_data(chat_id, 'daily')
    
    keyboard = [
        [InlineKeyboardButton("Aaj (Local)", callback_data=f"lb_daily:{chat_id}"),
         InlineKeyboardButton("Hafte bhar (Local)", callback_data=f"lb_weekly:{chat_id}"),
         InlineKeyboardButton("All Time (Local)", callback_data=f"lb_alltime:{chat_id}")],
        [InlineKeyboardButton("Global (24 Hrs)", callback_data=f"lb_global_daily:{chat_id}"),
         InlineKeyboardButton("Global (All Time)", callback_data=f"lb_global_alltime:{chat_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if photo_message_id:
        try:
            await context.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=photo_message_id,
                caption=leaderboard_text,
                reply_markup=reply_markup,
                parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception as e:
             logger.error(f"Failed to edit photo caption: {e}")
             await update.message.reply_text(leaderboard_text, reply_markup=reply_markup, parse_mode=constants.ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(
            leaderboard_text,
            reply_markup=reply_markup,
            parse_mode=constants.ParseMode.MARKDOWN
        )

# --- Leaderboard Callback (Same) ---

async def leaderboard_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    try:
        scope, chat_id_str = query.data.split('_')[1].split(':')
        chat_id = int(chat_id_str)
    except:
        await query.edit_message_caption(caption="Invalid button data.")
        return

    new_leaderboard_text = await get_leaderboard_data(chat_id, scope)

    keyboard = [
        [InlineKeyboardButton("Aaj (Local)", callback_data=f"lb_daily:{chat_id}"),
         InlineKeyboardButton("Hafte bhar (Local)", callback_data=f"lb_weekly:{chat_id}"),
         InlineKeyboardButton("All Time (Local)", callback_data=f"lb_alltime:{chat_id}")],
        [InlineKeyboardButton("Global (24 Hrs)", callback_data=f"lb_global_daily:{chat_id}"),
         InlineKeyboardButton("Global (All Time)", callback_data=f"lb_global_alltime:{chat_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_caption(
            caption=new_leaderboard_text,
            reply_markup=reply_markup,
            parse_mode=constants.ParseMode.MARKDOWN
        )
    except telegram.error.BadRequest as e:
        logger.warning(f"Failed to edit message: {e}")
        pass

# --- Profile Command (Same) ---

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    if not conn:
        return await update.message.reply_text("*Database is offline.* Profile unavailable.")

    user = update.effective_user
    user_id = user.id
    username = f"@{user.username}" if user.username else user.first_name
    
    profile_text = f"👤 *{username}'s Profile Stats* 📈\n\n"
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM messages WHERE user_id = %s;
            """, (user_id,))
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
                profile_text += "Koi group data nahi mila."
            else:
                for chat_id, chat_name, count in group_stats:
                    profile_text += f"• {chat_name[:25]}...: {count}\n"
            
        await update.message.reply_text(profile_text, parse_mode=constants.ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Failed to fetch user profile: {e}")
        await update.message.reply_text("Database query error while fetching profile.")
    finally:
        if conn:
            conn.close()

# --- Broadcast Feature (Same) ---

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in [constants.ChatType.PRIVATE]:
        await update.message.reply_text("यह कमांड केवल बॉट के DM में इस्तेमाल किया जा सकता है।")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("कृपया उस मैसेज का जवाब (Reply) दें जिसे आप ब्रॉडकास्ट करना चाहते हैं।")
        return

    broadcast_message = update.message.reply_to_message
    
    chat_ids = get_all_active_chat_ids()
    
    if not chat_ids:
        await update.message.reply_text("ब्रॉडकास्ट करने के लिए कोई सक्रिय चैट नहीं मिली।")
        return

    success_count = 0
    await update.message.reply_text(f"ब्रॉडकास्ट शुरू हो रहा है... {len(chat_ids)} चैट्स को भेजा जाएगा।")
    
    for chat_id in list(chat_ids):
        try:
            await context.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=update.effective_chat.id,
                message_id=broadcast_message.message_id
            )
            success_count += 1
            await asyncio.sleep(0.5) 

        except Exception as e:
            logger.warning(f"Failed to broadcast to {chat_id}: {e}")

    await update.message.reply_text(f"✅ ब्रॉडकास्ट पूरा हुआ! {success_count} चैट्स को सफलतापूर्वक भेजा गया।")


# --- Utility to get all active chats (Same) ---

def get_all_active_chat_ids():
    conn = get_db_connection()
    if not conn:
        return set()
    
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT chat_id FROM chats;")
            chat_ids = {row[0] for row in cur.fetchall()}
            return chat_ids
    except Exception as e:
        logger.error(f"Failed to fetch active chat IDs for broadcast: {e}")
        return set()
    finally:
        if conn:
            conn.close()
