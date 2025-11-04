# leaderboard_manager.py

import os
import psycopg2
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import ContextTypes, CallbackContext
import logging

logger = logging.getLogger(__name__)

# --- Database Connection and Setup ---

def get_db_connection():
    """Establishes and returns a connection to the PostgreSQL database."""
    # DATABASE_URL should be set in Render environment variables
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
    """Creates the necessary tables if they don't exist."""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                # 1. messages table: Stores all messages for all time
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id BIGSERIAL PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        username VARCHAR(255),
                        message_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                # 2. chats table: To track which chats are active
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS chats (
                        chat_id BIGINT PRIMARY KEY,
                        chat_name VARCHAR(255),
                        last_activity TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
            conn.commit()
            logger.info("Database setup complete.")
        except Exception as e:
            logger.error(f"Database setup failed: {e}")
        finally:
            conn.close()

# --- Async Functions (to be called from main.py) ---

async def update_message_count_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Called on every message to insert a record into the database.
    This replaces the in-memory counter.
    """
    conn = get_db_connection()
    if not conn:
        return
        
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = user.id
    username = f"@{user.username}" if user.username else user.first_name

    try:
        with conn.cursor() as cur:
            # Insert message record
            cur.execute("""
                INSERT INTO messages (chat_id, user_id, username)
                VALUES (%s, %s, %s);
            """, (chat_id, user_id, username))
            
            # Update chat activity (for global tracking)
            cur.execute("""
                INSERT INTO chats (chat_id, chat_name, last_activity)
                VALUES (%s, %s, NOW())
                ON CONFLICT (chat_id) DO UPDATE SET last_activity = NOW(), chat_name = %s;
            """, (chat_id, update.effective_chat.title or str(chat_id), update.effective_chat.title or str(chat_id)))
            
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to update message count in DB: {e}")
    finally:
        if conn:
            conn.close()


async def get_leaderboard_data(chat_id: int, scope: str):
    """Fetches and processes leaderboard data based on the scope (local/global/timeframe)."""
    conn = get_db_connection()
    if not conn:
        return "Database is offline. Leaderboard unavailable."

    # Define time constraints based on scope
    time_filter = ""
    title = ""
    
    if scope == 'daily':
        time_filter = "AND message_time >= NOW() - INTERVAL '1 day'"
        title = "Aaj Ka Leaderboard"
    elif scope == 'weekly':
        time_filter = "AND message_time >= NOW() - INTERVAL '7 days'"
        title = "Hafte Bhar Ka Leaderboard"
    elif scope == 'monthly':
        time_filter = "AND message_time >= NOW() - INTERVAL '30 days'"
        title = "Mahine Bhar Ka Leaderboard"
    elif scope == 'alltime':
        title = "Shuru Se Ab Tak"
    
    # Define chat filter based on scope
    chat_filter = f"WHERE chat_id = {chat_id}" if scope in ['daily', 'weekly', 'monthly', 'alltime'] else ""
    
    # For GLOBAL scope, we ignore chat_id filter but add time filter
    if scope == 'global_daily':
        chat_filter = "WHERE message_time >= NOW() - INTERVAL '1 day'"
        title = "🏆 Global Leaderboard (24 Hrs)"
    elif scope == 'global_alltime':
        chat_filter = ""
        title = "🌍 Global Leaderboard (All Time)"
        
    # Combine filters
    if scope in ['daily', 'weekly', 'monthly']:
        query_filter = f"WHERE chat_id = {chat_id} {time_filter}"
    elif scope == 'alltime':
        query_filter = f"WHERE chat_id = {chat_id}"
    elif scope.startswith('global'):
        query_filter = chat_filter 
    else: # Default is local daily
        query_filter = f"WHERE chat_id = {chat_id} AND message_time >= NOW() - INTERVAL '1 day'"
        title = "Aaj Ka Leaderboard (Local)"


    query = f"""
        SELECT username, COUNT(*) AS total_messages
        FROM messages
        {query_filter}
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
        logger.error(f"Failed to fetch leaderboard: {e}")
        return "Database query error."
    finally:
        if conn:
            conn.close()


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /leaderboard command and shows inline buttons."""
    
    chat_id = update.effective_chat.id
    
    # Default to local daily leaderboard
    leaderboard_text = await get_leaderboard_data(chat_id, 'daily')
    
    # Inline Buttons Setup
    keyboard = [
        # Local (Current Group)
        [InlineKeyboardButton("Aaj (Local)", callback_data=f"lb_daily:{chat_id}"),
         InlineKeyboardButton("Hafte bhar (Local)", callback_data=f"lb_weekly:{chat_id}"),
         InlineKeyboardButton("All Time (Local)", callback_data=f"lb_alltime:{chat_id}")],
        # Global
        [InlineKeyboardButton("Global (24 Hrs)", callback_data=f"lb_global_daily:{chat_id}"),
         InlineKeyboardButton("Global (All Time)", callback_data=f"lb_global_alltime:{chat_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        leaderboard_text,
        reply_markup=reply_markup,
        parse_mode=constants.ParseMode.MARKDOWN
    )


async def leaderboard_callback(update: Update, context: CallbackContext):
    """Handles button clicks on the leaderboard."""
    query = update.callback_query
    await query.answer()
    
    # callback_data format: lb_SCOPE:CHAT_ID
    try:
        scope, chat_id_str = query.data.split('_')[1].split(':')
        chat_id = int(chat_id_str)
    except:
        await query.edit_message_text("Invalid button data.")
        return

    new_leaderboard_text = await get_leaderboard_data(chat_id, scope)

    # Buttons ko wapas daalna hai
    keyboard = [
        [InlineKeyboardButton("Aaj (Local)", callback_data=f"lb_daily:{chat_id}"),
         InlineKeyboardButton("Hafte bhar (Local)", callback_data=f"lb_weekly:{chat_id}"),
         InlineKeyboardButton("All Time (Local)", callback_data=f"lb_alltime:{chat_id}")],
        [InlineKeyboardButton("Global (24 Hrs)", callback_data=f"lb_global_daily:{chat_id}"),
         InlineKeyboardButton("Global (All Time)", callback_data=f"lb_global_alltime:{chat_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        new_leaderboard_text,
        reply_markup=reply_markup,
        parse_mode=constants.ParseMode.MARKDOWN
    )

# --- Profile Command ---

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the user's message statistics across all groups."""
    conn = get_db_connection()
    if not conn:
        return await update.message.reply_text("Database is offline. Profile unavailable.")

    user = update.effective_user
    user_id = user.id
    username = f"@{user.username}" if user.username else user.first_name
    
    profile_text = f"👤 *{username}'s Profile Stats* 📈\n\n"
    
    try:
        with conn.cursor() as cur:
            # Get total messages (all groups, all time)
            cur.execute("""
                SELECT COUNT(*) FROM messages WHERE user_id = %s;
            """, (user_id,))
            total_messages = cur.fetchone()[0]
            
            profile_text += f"**Total Messages (All Time):** {total_messages}\n\n"
            
            # Get group-wise stats
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
                    # Show group name (database se) and count
                    profile_text += f"• {chat_name[:25]}...: {count}\n"
            
        await update.message.reply_text(profile_text, parse_mode=constants.ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Failed to fetch user profile: {e}")
        await update.message.reply_text("Database query error while fetching profile.")
    finally:
        if conn:
            conn.close()

# --- Utility for main.py to get all active chats ---
def get_all_active_chat_ids():
    """Fetches all active chat IDs from the database (for global quiz broadcast)."""
    conn = get_db_connection()
    if not conn:
        return set()
    
    try:
        with conn.cursor() as cur:
            # We fetch all active chats (where the bot is expected to be)
            cur.execute("SELECT chat_id FROM chats;")
            chat_ids = {row[0] for row in cur.fetchall()}
            return chat_ids
    except Exception as e:
        logger.error(f"Failed to fetch active chat IDs for broadcast: {e}")
        return set()
    finally:
        if conn:
            conn.close()
