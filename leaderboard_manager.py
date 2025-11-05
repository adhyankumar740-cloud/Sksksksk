import os
import psycopg2
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import ContextTypes, CallbackContext
import logging
import asyncio
import telegram.error

logger = logging.getLogger(__name__)

# This URL is used as a fallback. 
# 💡 We will try to send this, and if it fails, we'll send a text-only message.
LEADERBOARD_PHOTO_URL_KEY = os.environ.get('TELEGRAM_LEADERBOARD_PHOTO_URL', 'https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/Placeholder_of_a_man.svg/600px-Placeholder_of_a_man.svg.png')

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
                
                # Migration: Add 'chat_type' if it doesn't exist
                try:
                    cur.execute("SELECT chat_type FROM chats LIMIT 1;")
                except psycopg2.ProgrammingError:
                    conn.rollback() # Rollback transaction to issue ALTER
                    logger.warning("Adding 'chat_type' column to existing 'chats' table.")
                    cur.execute("ALTER TABLE chats ADD COLUMN chat_type VARCHAR(50);")
                    conn.commit()
                
                # 💡 FIX 1: Migration: Add 'is_active' if it doesn't exist
                try:
                    cur.execute("SELECT is_active FROM chats LIMIT 1;")
                except psycopg2.ProgrammingError:
                    conn.rollback() # Rollback transaction to issue ALTER
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

# --- Chat Registration (Updated) ---

def register_chat(update: Update):
    conn = get_db_connection()
    if not conn: return
    chat = update.effective_chat
    chat_id = chat.id
    chat_name = chat.title or (chat.username or chat.first_name)
    chat_type = chat.type
    try:
        with conn.cursor() as cur:
            # 💡 FIX 2: Set is_active = TRUE on registration or conflict
            # This re-activates a chat if the bot is re-added
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

# --- Message Count Update (Same) ---

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

# --- Leaderboard Core Logic (Same) ---

async def get_leaderboard_data(chat_id: int, scope: str):
    conn = get_db_connection()
    if not conn: return "*Database is offline.* Leaderboard unavailable."
    
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
        if conn: conn.close()

# --- Leaderboard Command (Rewritten for stability) ---

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    initial_caption = "🏆 Loading Leaderboard... 📊"
    sent_message = None
    is_photo = False # Flag to track what was actually sent

    # 💡 FIX 3: Try to send photo, if fails, send text.
    try:
        sent_message = await context.bot.send_photo(
            chat_id=chat_id,
            photo=LEADERBOARD_PHOTO_URL_KEY,
            caption=initial_caption
        )
        is_photo = True
    except Exception as e:
        logger.warning(f"Failed to send leaderboard photo ({e}), sending text fallback.")
        try:
            sent_message = await update.message.reply_text(
                initial_caption, 
                parse_mode=constants.ParseMode.MARKDOWN
            )
            is_photo = False
        except Exception as text_e:
            logger.error(f"Error sending text fallback: {text_e}")
            return # Total failure, can't send anything

    # Get data
    leaderboard_text = await get_leaderboard_data(chat_id, 'daily')
    
    keyboard = [
        [InlineKeyboardButton("Aaj (Local)", callback_data=f"lb_daily:{chat_id}"),
         InlineKeyboardButton("Hafte bhar (Local)", callback_data=f"lb_weekly:{chat_id}"),
         InlineKeyboardButton("All Time (Local)", callback_data=f"lb_alltime:{chat_id}")],
        [InlineKeyboardButton("Global (24 Hrs)", callback_data=f"lb_global_daily:{chat_id}"),
         InlineKeyboardButton("Global (All Time)", callback_data=f"lb_global_alltime:{chat_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Now, edit the message we sent (guaranteed to exist if we're here)
    try:
        if is_photo:
            await context.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=sent_message.message_id,
                caption=leaderboard_text,
                reply_markup=reply_markup,
                parse_mode=constants.ParseMode.MARKDOWN
            )
        else:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=sent_message.message_id,
                text=leaderboard_text,
                reply_markup=reply_markup,
                parse_mode=constants.ParseMode.MARKDOWN
            )
    except Exception as e:
         logger.error(f"Failed to edit initial message {sent_message.message_id}: {e}")
         # Final fallback: send new if edit fails
         await update.message.reply_text(
             leaderboard_text, 
             reply_markup=reply_markup, 
             parse_mode=constants.ParseMode.MARKDOWN
         )

# --- Leaderboard Callback (Fixed to preserve photo) ---

async def leaderboard_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    try:
        # Check data format: lb_scope:chat_id
        parts = query.data.split('_', 1)[1].split(':')
        scope = parts[0]
        # Handle different scopes (daily, weekly, global_daily, etc.)
        if len(parts) > 2: # e.g., global_daily:chat_id
            scope = f"{parts[0]}_{parts[1]}"
            chat_id_str = parts[2]
        else:
            chat_id_str = parts[1]
            
        chat_id = int(chat_id_str)
    except (IndexError, ValueError) as e:
        logger.error(f"Invalid callback data: {query.data} | Error: {e}")
        try:
            await query.edit_message_text(text="Invalid button data.")
        except:
            pass 
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
        # 💡 FIX 4: Check if the message we are editing has a photo.
        # This stops the photo from disappearing!
        if query.message.photo:
            await query.edit_message_caption(
                caption=new_leaderboard_text,
                reply_markup=reply_markup,
                parse_mode=constants.ParseMode.MARKDOWN
            )
        else:
            # If it's text-only, edit the text
            await query.edit_message_text(
                text=new_leaderboard_text,
                reply_markup=reply_markup,
                parse_mode=constants.ParseMode.MARKDOWN
            )
    except telegram.error.BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.warning(f"Failed to edit message: {e}")
        pass
    except Exception as e:
        logger.error(f"Error during final leaderboard edit: {e}")

# --- Profile Command (Same) ---

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    if not conn: return await update.message.reply_text("*Database is offline.* Profile unavailable.")
    
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
        if conn: conn.close()

# --- Broadcast Feature (Rewritten for Async) ---

async def send_broadcast_and_handle_errors(context: ContextTypes.DEFAULT_TYPE, chat_id, from_chat_id, message_id):
    """
    Helper function for broadcast_command to send and handle errors.
    """
    try:
        await context.bot.copy_message(
            chat_id=chat_id,
            from_chat_id=from_chat_id,
            message_id=message_id
        )
        return (chat_id, "Success")
    except (telegram.error.Forbidden, telegram.error.BadRequest) as e:
        logger.warning(f"Broadcast failed for {chat_id} (Forbidden/Bad Request). Deactivating: {e}")
        deactivate_chat_in_db(chat_id) # 💡 Use our new function
        return (chat_id, "Failed_Deactivated")
    except Exception as e:
        logger.error(f"Broadcast failed for {chat_id} (Other): {e}")
        return (chat_id, "Failed_Error")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in [constants.ChatType.PRIVATE]:
        await update.message.reply_text("यह कमांड केवल बॉट के DM में इस्तेमाल किया जा सकता है।")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("कृपया उस मैसेज का जवाब (Reply) दें जिसे आप ब्रॉडकास्ट करना चाहते हैं।")
        return

    broadcast_message = update.message.reply_to_message
    chat_ids = get_all_active_chat_ids() # 💡 Already fetches only active chats
    
    if not chat_ids:
        await update.message.reply_text("ब्रॉडकास्ट करने के लिए कोई सक्रिय चैट नहीं मिली।")
        return

    await update.message.reply_text(f"ब्रॉडकास्ट शुरू हो रहा है... {len(chat_ids)} चैट्स को भेजा जाएगा।")
    
    # 💡 FIX 5: Run all broadcasts concurrently
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

    await update.message.reply_text(f"✅ ब्रॉडकास्ट पूरा हुआ! {success_count} / {len(tasks)} चैट्स को सफलतापूर्वक भेजा गया।")

# --- Utility to get all active chats (Updated) ---

def get_all_active_chat_ids():
    conn = get_db_connection()
    if not conn: return set()
    
    try:
        with conn.cursor() as cur:
            # 💡 FIX 6: Only select active chats
            cur.execute("SELECT chat_id FROM chats WHERE is_active = TRUE;")
            chat_ids = {row[0] for row in cur.fetchall()}
            return chat_ids
    except Exception as e:
        logger.error(f"Failed to fetch active chat IDs for broadcast: {e}")
        return set()
    finally:
        if conn: conn.close()

# --- 💡 NEW FUNCTION (Required by main.py) ---

def deactivate_chat_in_db(chat_id):
    """
    Marks a chat as inactive in the database (e.g., if bot is kicked).
    """
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
