import logging
import os
import re
import aiohttp
import random
import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Constants
BOT_TOKEN = "7875448627:AAE_DW_twG-gFz3PRFLrhitFTqOgBEiWmLI"
ADMIN_ID = 7886196630  # Replace with your admin ID
DEFAULT_USER_LIMIT = 50
ADMIN_PANEL_PASSWORD = "admin123"  # Change to a secure password
REQUIRED_CHANNEL = "@aixflycom"  # Channel username that users must join

AUTH_URL = "https://takipciyurdu.com/api/twitter-takipci/auth"
CREDIT_URL = "https://takipciyurdu.com/api/twitter-takipci/credit"
FOLLOW_URL = "https://takipciyurdu.com/api/twitter-takipci/follow"
REFERRER = "https://takipciyurdu.com/twitter/twitter-takipci-hilesi"

# Logging setup
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

DB_FILE = "bot_sessions.db"
BOT_STATUS = "online"  # Track bot status

# Bot Banners
ONLINE_BANNER = """
░█████╗░██╗██╗░░██╗███████╗██╗░░██╗░░░██╗
██╔══██╗██║╚██╗██╔╝██╔════╝██║░░╚██╗░██╔╝
███████║██║░╚███╔╝░█████╗░░██║░░░╚████╔╝░
██╔══██║██║░██╔██╗░██╔══╝░░██║░░░░╚██╔╝░░
██║░░██║██║██╔╝░██╗██║░░░░░███████╗██║░░░
╚═╝░░╚═╝╚═╝╚═╝░░╚═╝╚═╝░░░░░╚══════╝╚═╝░░░
                                                    
Aixfly X Premium Bot v1.0
➖➖➖➖➖➖➖➖➖➖➖➖
✅ Secure & Fast Twitter Growth
🚀 Automated Follower System
💎 Premium Service Quality
"""

OFFLINE_BANNER = """
░█████╗░██╗██╗░░██╗███████╗██╗░░██╗░░░██╗
██╔══██╗██║╚██╗██╔╝██╔════╝██║░░╚██╗░██╔╝
███████║██║░╚███╔╝░█████╗░░██║░░░╚████╔╝░
██╔══██║██║░██╔██╗░██╔══╝░░██║░░░░╚██╔╝░░
██║░░██║██║██╔╝░██╗██║░░░░░███████╗██║░░░
╚═╝░░╚═╝╚═╝╚═╝░░╚═╝╚═╝░░░░░╚══════╝╚═╝░░░

Aixfly X Premium Bot v1.0
➖➖➖➖➖➖➖➖➖➖➖➖
🔴 Bot is currently OFFLINE
🛑 Services temporarily unavailable
"""

# --- Database Helpers ---

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            chat_id INTEGER PRIMARY KEY,
            token TEXT,
            secret TEXT,
            apiId TEXT,
            step TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            has_joined_channel BOOLEAN DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_limits (
            chat_id INTEGER PRIMARY KEY,
            get_auth_limit INTEGER DEFAULT 0,
            get_auth_used INTEGER DEFAULT 0,
            last_reset_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS global_settings (
            id INTEGER PRIMARY KEY DEFAULT 1,
            default_get_auth_limit INTEGER DEFAULT 3,
            check_constraint CHECK (id = 1)
        )
    """)
    
    # Initialize global settings if not exists
    cursor.execute("INSERT OR IGNORE INTO global_settings (id, default_get_auth_limit) VALUES (1, ?)", (DEFAULT_USER_LIMIT,))
    conn.commit()
    conn.close()

def save_session(chat_id, token, secret, apiId, step="awaiting_pin"):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO sessions (chat_id, token, secret, apiId, step)
        VALUES (?, ?, ?, ?, ?)
    """, (chat_id, token, secret, apiId, step))
    conn.commit()
    conn.close()

def get_session(chat_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT token, secret, apiId, step FROM sessions WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "token": row[0],
            "secret": row[1],
            "apiId": row[2],
            "step": row[3]
        }
    return None

def delete_session(chat_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()
    logger.info(f"Session for chat_id {chat_id} deleted.")

def is_user_in_channel(chat_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT has_joined_channel FROM users WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    return row and row[0] == 1 if row else False

def save_user(chat_id, username, first_name, last_name, has_joined_channel=False):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO users (chat_id, username, first_name, last_name, has_joined_channel)
        VALUES (?, ?, ?, ?, ?)
    """, (chat_id, username, first_name, last_name, has_joined_channel))
    conn.commit()
    conn.close()

def update_channel_status(chat_id, status):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET has_joined_channel = ? WHERE chat_id = ?", (status, chat_id))
    conn.commit()
    conn.close()

def get_all_user_ids():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id FROM users WHERE has_joined_channel = 1")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows] if rows else []

def get_user_limit(chat_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT get_auth_limit, get_auth_used 
        FROM user_limits 
        WHERE chat_id = ?
    """, (chat_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {"limit": row[0], "used": row[1]}
    
    # If no specific limit set, use global default
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT default_get_auth_limit FROM global_settings WHERE id = 1")
    default_limit = cursor.fetchone()[0]
    conn.close()
    
    return {"limit": default_limit, "used": 0}

def increment_user_limit_usage(chat_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO user_limits (chat_id, get_auth_limit, get_auth_used)
        VALUES (?, (SELECT default_get_auth_limit FROM global_settings WHERE id = 1), 0)
    """, (chat_id,))
    cursor.execute("""
        UPDATE user_limits 
        SET get_auth_used = get_auth_used + 1 
        WHERE chat_id = ?
    """, (chat_id,))
    conn.commit()
    conn.close()

def reset_user_limits(chat_id=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    if chat_id:
        cursor.execute("""
            UPDATE user_limits 
            SET get_auth_used = 0, 
                last_reset_date = CURRENT_TIMESTAMP 
            WHERE chat_id = ?
        """, (chat_id,))
    else:
        cursor.execute("""
            UPDATE user_limits 
            SET get_auth_used = 0, 
                last_reset_date = CURRENT_TIMESTAMP
        """)
    conn.commit()
    conn.close()

def set_user_limit(chat_id, new_limit):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_limits (chat_id, get_auth_limit, get_auth_used)
        VALUES (?, ?, COALESCE((SELECT get_auth_used FROM user_limits WHERE chat_id = ?), 0))
    """, (chat_id, new_limit, chat_id))
    conn.commit()
    conn.close()

def get_global_setting(setting_name):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"SELECT {setting_name} FROM global_settings WHERE id = 1")
    value = cursor.fetchone()[0]
    conn.close()
    return value

def set_global_setting(setting_name, value):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE global_settings SET {setting_name} = ? WHERE id = 1", (value,))
    conn.commit()
    conn.close()

def get_all_users_with_limits():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.chat_id, u.username, u.first_name, u.last_name, 
               COALESCE(ul.get_auth_limit, g.default_get_auth_limit) as limit,
               COALESCE(ul.get_auth_used, 0) as used
        FROM users u
        CROSS JOIN global_settings g
        LEFT JOIN user_limits ul ON u.chat_id = ul.chat_id
        WHERE u.has_joined_channel = 1
    """)
    users = cursor.fetchall()
    conn.close()
    return users

# --- Menu Helpers ---

async def show_main_menu(update: Update, message_text: str = None):
    user_id = update.effective_user.id
    
    # Different menu for admin
    if user_id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("🚀 Get Twitter Follower", callback_data="get_auth")],
            [InlineKeyboardButton("🛠️ Admin Panel", callback_data="admin_panel")],
            [InlineKeyboardButton("ℹ️ Bot Info", callback_data="bot_info"),
             InlineKeyboardButton("🆘 Help", callback_data="help")],
            [InlineKeyboardButton("🔍 Check Credits", callback_data="check_credits")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("🚀 Get Twitter Follower", callback_data="get_auth")],
            [InlineKeyboardButton("ℹ️ Bot Info", callback_data="bot_info"),
             InlineKeyboardButton("🆘 Help", callback_data="help")],
            [InlineKeyboardButton("🔍 Check Credits", callback_data="check_credits")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = message_text or "Welcome to Aixfly X Premium Bot! Please select an option:"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

# --- Admin Panel Functions ---

async def show_admin_panel(query):
    keyboard = [
        [InlineKeyboardButton("👥 User Management", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Limit Management", callback_data="admin_limits")],
        [InlineKeyboardButton("⚙️ Global Settings", callback_data="admin_settings")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="back_to_menu")]
    ]
    
    total_users = len(get_all_user_ids())
    default_limit = get_global_setting("default_get_auth_limit")
    
    await query.edit_message_text(
        f"🛠️ Admin Panel\n\n"
        f"📊 Stats:\n"
        f"• Total Users: {total_users}\n"
        f"• Default Daily Limit: {default_limit}\n\n"
        "Select an option to manage:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_user_management(query):
    users = get_all_users_with_limits()
    
    if not users:
        await query.edit_message_text("No users found.")
        return
    
    keyboard = []
    for user in users:
        keyboard.append([
            InlineKeyboardButton(
                f"👤 {user[2]} (@{user[1] or 'N/A'}) - {user[5]}/{user[4]}",
                callback_data=f"user_detail_{user[0]}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")
    ])
    
    await query.edit_message_text(
        "👥 User Management\n\n"
        "Select a user to manage their limits:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_user_detail(query, user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.chat_id, u.username, u.first_name, u.last_name, 
               COALESCE(ul.get_auth_limit, g.default_get_auth_limit) as limit,
               COALESCE(ul.get_auth_used, 0) as used
        FROM users u
        CROSS JOIN global_settings g
        LEFT JOIN user_limits ul ON u.chat_id = ul.chat_id
        WHERE u.chat_id = ? AND u.has_joined_channel = 1
    """, (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        await query.answer("User not found")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("1️⃣ Set 1", callback_data=f"setlimit_{user_id}_1"),
            InlineKeyboardButton("3️⃣ Set 3", callback_data=f"setlimit_{user_id}_3"),
            InlineKeyboardButton("5️⃣ Set 5", callback_data=f"setlimit_{user_id}_5")
        ],
        [
            InlineKeyboardButton("🔢 Custom Limit", callback_data=f"customlimit_{user_id}"),
            InlineKeyboardButton("♻️ Reset Usage", callback_data=f"resetlimit_{user_id}")
        ],
        [
            InlineKeyboardButton("🚫 Ban User", callback_data=f"banuser_{user_id}"),
            InlineKeyboardButton("🔙 Back to Users", callback_data="admin_users")
        ]
    ]
    
    await query.edit_message_text(
        f"👤 User Details\n\n"
        f"ID: {user[0]}\n"
        f"Name: {user[2]} {user[3] or ''}\n"
        f"Username: @{user[1] or 'N/A'}\n"
        f"Current Limit: {user[5]}/{user[4]}\n\n"
        "Select an action:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def prompt_custom_limit(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    query = update.callback_query
    await query.answer()
    
    context.user_data['awaiting_custom_limit'] = True
    context.user_data['target_user_id'] = user_id
    
    await query.edit_message_text(
        f"Please enter the new custom limit for user {user_id} (1-100):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data=f"user_detail_{user_id}")]
        ])
    )

async def show_limit_management(query):
    default_limit = get_global_setting("default_get_auth_limit")
    total_users = len(get_all_user_ids())
    
    keyboard = [
        [
            InlineKeyboardButton("Set Default to 1", callback_data="admin_setdefault_1"),
            InlineKeyboardButton("Set Default to 3", callback_data="admin_setdefault_3"),
            InlineKeyboardButton("Set Default to 5", callback_data="admin_setdefault_5")
        ],
        [InlineKeyboardButton("Reset All User Limits", callback_data="admin_reset_all_limits")],
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(
        f"📊 Limit Management\n\n"
        f"Current Default Limit: {default_limit}\n"
        f"Affects {total_users} users\n\n"
        "Set new default limit (affects new users):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_global_settings(query):
    default_limit = get_global_setting("default_get_auth_limit")
    
    keyboard = [
        [InlineKeyboardButton("📊 Limit Settings", callback_data="admin_limits")],
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(
        f"⚙️ Global Settings\n\n"
        f"• Default Daily Limit: {default_limit}\n"
        f"• Bot Status: {'🟢 ONLINE' if BOT_STATUS == 'online' else '🔴 OFFLINE'}\n\n"
        "Select an option to manage:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- Channel Verification ---

async def check_channel_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    try:
        # Check if user is member of the channel
        member = await context.bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            # User is in channel
            save_user(user_id, user.username, user.first_name, user.last_name, has_joined_channel=True)
            return True
        else:
            # User is not in channel
            save_user(user_id, user.username, user.first_name, user.last_name, has_joined_channel=False)
            return False
    except Exception as e:
        logger.error(f"Error checking channel membership for user {user_id}: {e}")
        return False

async def prompt_join_channel(update: Update):
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL[1:]}")],
        [InlineKeyboardButton("✅ I've Joined", callback_data="check_membership")]
    ]
    
    await update.message.reply_text(
        f"📢 To use this bot, you must join our channel:\n\n"
        f"👉 {REQUIRED_CHANNEL}\n\n"
        "After joining, click the 'I've Joined' button below.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- Notification System ---

async def notify_users(app, message, banner=None):
    """Send notification to all approved users"""
    user_ids = get_all_user_ids()
    if not user_ids:
        logger.info("No users to notify")
        return
        
    for user_id in user_ids:
        try:
            full_message = (banner + "\n\n" + message) if banner else message
            await app.bot.send_message(
                chat_id=user_id,
                text=full_message,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Main Menu", callback_data="back_to_menu")]
                ])
            )
        except Exception as e:
            logger.error(f"Failed to send notification to user {user_id}: {e}")

# --- Telegram Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Save user info (regardless of channel status)
    save_user(user_id, user.username, user.first_name, user.last_name)
    
    # Check if user has joined channel
    if not await check_channel_membership(update, context):
        await prompt_join_channel(update)
        return
    
    # User has joined channel - proceed
    delete_session(user_id)
    banner = OFFLINE_BANNER if BOT_STATUS == "offline" else ONLINE_BANNER
    await update.message.reply_text(banner)
    
    if BOT_STATUS == "offline":
        await update.message.reply_text(
            "⚠️ The bot is currently offline. Please try again later.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh Status", callback_data="refresh_status")]
            ])
        )
    else:
        await show_main_menu(update)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Handle channel membership check
    if query.data == "check_membership":
        if await check_channel_membership(update, context):
            await query.edit_message_text("✅ Thank you for joining! You can now use the bot.")
            await show_main_menu(update)
        else:
            await query.answer("❌ You haven't joined the channel yet. Please join and try again.", show_alert=True)
        return

    # Check if user has joined channel
    if not is_user_in_channel(user_id):
        await query.edit_message_text(
            "❌ You must join our channel to use this bot.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL[1:]}")],
                [InlineKeyboardButton("✅ I've Joined", callback_data="check_membership")]
            ])
        )
        return

    # Handle admin panel access
    if query.data == "admin_panel":
        if user_id != ADMIN_ID:
            await query.answer("🚫 You are not authorized to access the admin panel.")
            return
        
        await show_admin_panel(query)
        return
    
    # Handle admin panel actions
    if query.data.startswith("admin_"):
        if user_id != ADMIN_ID:
            await query.answer("🚫 You are not authorized to perform this action.")
            return
        
        if query.data == "admin_users":
            await show_user_management(query)
        elif query.data == "admin_limits":
            await show_limit_management(query)
        elif query.data == "admin_settings":
            await show_global_settings(query)
        elif query.data.startswith("admin_setdefault_"):
            new_default = int(query.data.split("_")[2])
            set_global_setting("default_get_auth_limit", new_default)
            await query.answer(f"✅ Default limit set to {new_default}")
            await show_global_settings(query)
        elif query.data == "admin_reset_all_limits":
            reset_user_limits()
            await query.answer("✅ All user limits reset!")
            await show_limit_management(query)
        elif query.data == "admin_back":
            await show_admin_panel(query)
        return
    
    # Handle user management actions
    if query.data.startswith("user_detail_"):
        target_user_id = int(query.data.split("_")[2])
        await show_user_detail(query, target_user_id)
    elif query.data.startswith("setlimit_"):
        if user_id != ADMIN_ID:
            await query.answer("🚫 Unauthorized")
            return
        parts = query.data.split("_")
        target_user_id = int(parts[1])
        new_limit = int(parts[2])
        set_user_limit(target_user_id, new_limit)
        await query.answer(f"✅ Limit set to {new_limit}")
        await show_user_detail(query, target_user_id)
    elif query.data.startswith("customlimit_"):
        if user_id != ADMIN_ID:
            await query.answer("🚫 Unauthorized")
            return
        target_user_id = int(query.data.split("_")[1])
        await prompt_custom_limit(update, context, target_user_id)
    elif query.data.startswith("resetlimit_"):
        if user_id != ADMIN_ID:
            await query.answer("🚫 Unauthorized")
            return
        target_user_id = int(query.data.split("_")[1])
        reset_user_limits(target_user_id)
        await query.answer("✅ Usage reset")
        await show_user_detail(query, target_user_id)
    elif query.data.startswith("banuser_"):
        if user_id != ADMIN_ID:
            await query.answer("🚫 Unauthorized")
            return
        target_user_id = int(query.data.split("_")[1])
        update_channel_status(target_user_id, False)
        await query.answer("✅ User banned")
        await show_user_management(query)

    # Handle "Get Twitter Follower" with limit check
    if query.data == "get_auth":
        if BOT_STATUS == "offline":
            await query.edit_message_text(
                "⚠️ The bot is currently offline. Please try again later.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Refresh Status", callback_data="refresh_status"),
                    InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]
                ])
            )
        else:
            # Check user's limit
            limit_info = get_user_limit(user_id)
            if limit_info["used"] >= limit_info["limit"]:
                await query.edit_message_text(
                    f"⚠️ You've reached your daily limit of {limit_info['limit']} authorizations.\n\n"
                    "Please try again tomorrow or contact admin for assistance.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]
                    ])
                )
                return
            
            # Increment usage counter
            increment_user_limit_usage(user_id)
            
            # Proceed with authorization
            await handle_get_auth(query)
        return
    
    # Handle other menu options
    if query.data == "bot_info":
        banner = OFFLINE_BANNER if BOT_STATUS == "offline" else ONLINE_BANNER
        await query.edit_message_text(
            f"{banner}\n\n"
            "🔹 Aixfly X Premium Twitter Growth Service\n"
            "🔹 Secure and fast follower system\n"
            "🔹 No password required - uses Twitter OAuth\n\n"
            f"Status: {'🔴 OFFLINE' if BOT_STATUS == 'offline' else '🟢 ONLINE'}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]
            ])
        )
    elif query.data == "help":
        await query.edit_message_text(
            "🆘 Help Guide:\n\n"
            "1. Click 'Get Twitter Follower'\n"
            "2. Authorize with Twitter\n"
            "3. Enter the 7-digit PIN you receive\n"
            "4. The bot will automatically process your follows\n\n"
            "For issues, contact @AixflySupport",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]
            ])
        )
    elif query.data == "check_credits":
        if BOT_STATUS == "offline":
            await query.edit_message_text(
                "⚠️ The bot is currently offline. Credit checking is unavailable.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Refresh Status", callback_data="refresh_status"),
                    InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]
                ])
            )
        else:
            session = get_session(user_id)
            if session:
                await query.edit_message_text("🔍 Checking your credits...")
                # Implement credit checking logic here
                await query.edit_message_text("⚠️ Please complete the authorization process first to check credits.")
            else:
                await query.edit_message_text("⚠️ No active session found. Please start the authorization process first.")
            await show_main_menu(update)
    elif query.data == "back_to_menu":
        await show_main_menu(update)
    elif query.data == "refresh_status":
        if BOT_STATUS == "offline":
            await query.edit_message_text(
                "🔴 The bot is still offline. Please try again later.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Refresh Again", callback_data="refresh_status"),
                    InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]
                ])
            )
        else:
            await query.edit_message_text(
                "🟢 The bot is now online!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Main Menu", callback_data="back_to_menu")]
                ])
            )
            await show_main_menu(update)

async def handle_get_auth(query):
    user_id = query.from_user.id
    await query.edit_message_text("🔍 Finding Best Port..")
    delete_session(user_id)

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(AUTH_URL, headers={"accept": "application/json"}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    token = data.get("token")
                    secret = data.get("secret")
                    apiId = data.get("apiId")
                    url = data.get("url")

                    if not all([token, secret, apiId, url]):
                        await query.message.reply_text("⚠️ Authorization details missing.")
                        await show_main_menu(query, "Please try again.")
                        return

                    # Replace twitter.com with x.com in the URL
                    url = url.replace("twitter.com", "x.com")

                    save_session(user_id, token, secret, apiId, "awaiting_pin")
                    await query.message.reply_text(
                        f"✅ Please visit the following URL to authorize and get your PIN. Make Sure the X account login in same browser:\n\n`{url}`\n\n"
                        "After authorization, reply to me with your 7-digit PIN code."
                        " Make sure to complete the authorization within 5 minutes.",
                        parse_mode="Markdown"
                    )
                else:
                    await query.message.reply_text(f"❌ Failed to fetch authorization URL. Status: {resp.status}")
                    await show_main_menu(query, "Please try again.")
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching auth URL for user {user_id}: {e}", exc_info=True)
            await query.message.reply_text("❌ Network error occurred. Please try again later.")
            await show_main_menu(query, "Try again?")
        except Exception as e:
            logger.error(f"Unexpected error fetching auth URL for user {user_id}: {e}", exc_info=True)
            await query.message.reply_text("❌ An unexpected error occurred. Please try again.")
            await show_main_menu(query, "Try again?")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BOT_STATUS
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 You are not authorized to use this command.")
        return

    if not context.args:
        await update.message.reply_text(
            "Admin commands:\n"
            "/admin online - Set bot to online status\n"
            "/admin offline - Set bot to offline status\n"
            "/admin users - List all users\n"
            "/admin limits - Show user limits\n"
            "/admin setlimit <user_id> <limit> - Set user's daily limit\n"
            "/admin resetlimit <user_id> - Reset user's usage\n"
            "/admin setdefault <limit> - Set default daily limit\n"
            "/admin panel - Show admin panel"
        )
        return

    command = context.args[0].lower()

    if command == "online":
        BOT_STATUS = "online"
        await update.message.reply_text("🟢 Bot status set to ONLINE")
        await notify_users(
            context.application,
            "🟢 Aixfly X Bot is now ONLINE and ready to serve you!",
            ONLINE_BANNER
        )
    elif command == "offline":
        BOT_STATUS = "offline"
        await update.message.reply_text("🔴 Bot status set to OFFLINE")
        await notify_users(
            context.application,
            "🔴 Aixfly X Bot is now OFFLINE. Services will resume soon.",
            OFFLINE_BANNER
        )
    elif command == "users":
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id, username, first_name, last_name, has_joined_channel FROM users")
        users = cursor.fetchall()
        conn.close()
        
        if not users:
            await update.message.reply_text("No users in database.")
            return
            
        response = "👥 User List:\n\n"
        for user in users:
            response += (f"ID: {user[0]}\n"
                        f"Username: @{user[1] if user[1] else 'N/A'}\n"
                        f"Name: {user[2]} {user[3] if user[3] else ''}\n"
                        f"Status: {'✅ In channel' if user[4] else '❌ Not in channel'}\n"
                        "------------------------\n")
        
        await update.message.reply_text(response)
    elif command == "limits":
        users = get_all_users_with_limits()
        if not users:
            await update.message.reply_text("No users found.")
            return
            
        response = "📊 User Limits:\n\n"
        for user in users:
            response += (f"ID: {user[0]}\n"
                        f"User: @{user[1] or 'N/A'} ({user[2]})\n"
                        f"Limit: {user[5]}/{user[4]}\n\n")
        
        await update.message.reply_text(response)
    elif command == "setlimit" and len(context.args) >= 3:
        try:
            target_user_id = int(context.args[1])
            new_limit = int(context.args[2])
            set_user_limit(target_user_id, new_limit)
            await update.message.reply_text(f"✅ Limit for user {target_user_id} set to {new_limit}")
        except ValueError:
            await update.message.reply_text("Invalid arguments. Usage: /admin setlimit <user_id> <limit>")
    elif command == "resetlimit" and len(context.args) >= 2:
        try:
            target_user_id = int(context.args[1])
            reset_user_limits(target_user_id)
            await update.message.reply_text(f"✅ Limit reset for user {target_user_id}")
        except ValueError:
            await update.message.reply_text("Invalid user ID. Usage: /admin resetlimit <user_id>")
    elif command == "setdefault" and len(context.args) >= 2:
        try:
            new_default = int(context.args[1])
            set_global_setting("default_get_auth_limit", new_default)
            await update.message.reply_text(f"✅ Default daily limit set to {new_default}")
        except ValueError:
            await update.message.reply_text("Invalid limit value. Usage: /admin setdefault <limit>")
    elif command == "panel":
        keyboard = [
            [InlineKeyboardButton("🛠️ Open Admin Panel", callback_data="admin_panel")]
        ]
        await update.message.reply_text(
            "Admin Panel Options:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text("Invalid admin command.")

async def send_follow_requests(update, http_session, access_token):
    headers = {
        "accept": "*/*",
        "authorization": f"bearer {access_token}",
        "referer": f"{REFERRER}/profile",
    }
    user_id = update.effective_user.id
    status_msg = None

    try:
        async with http_session.get(CREDIT_URL, headers=headers) as credit_resp:
            if credit_resp.status != 200:
                await update.message.reply_text("❌ Failed to get credit info before starting follows. Session cleared.")
                return
            credit_data = await credit_resp.json()
            credit = credit_data.get("credit")
            if credit == -1:
                await update.message.reply_text("⚠️ Your credit is -1. The follow process cannot be started. Session cleared.")
                return
            if not isinstance(credit, int) or credit <= 0:
                await update.message.reply_text(f"⚠️ Your credit is too low ({credit}). Cannot start follow requests. Session cleared.")
                return

        status_msg = await update.message.reply_text(f"🚀 Starting follow process... Sending 0/{credit} follows.")

        for i in range(credit):
            async with http_session.post(FOLLOW_URL, headers=headers) as follow_resp:
                if follow_resp.status != 200:
                    await status_msg.edit_text(f"❌ Follow request #{i+1} failed with status {follow_resp.status}. Stopping at {i}/{credit} follows. Session cleared.")
                    return

                follow_data = await follow_resp.json()
                if follow_data.get("code") == 1:
                    await status_msg.edit_text(f"🚀 Sending Follows: {i+1}/{credit}")
                    await asyncio.sleep(random.uniform(5, 7))  # Random delay between 5 to 7 seconds
                else:
                    await status_msg.edit_text(
                        f"⚠️ Follow failed at {i+1}/{credit}. Message: {follow_data.get('message', 'Unknown error')}. Session cleared."
                    )
                    return

        await status_msg.edit_text(f"✅ Follow process complete! Successfully sent {credit}/{credit} follows.")


    except aiohttp.ClientError as e:
        logger.error(f"Network error during follow requests for user {user_id}: {e}", exc_info=True)
        if status_msg:
            await status_msg.edit_text("❌ A network error occurred during the follow process. Session cleared.")
        else:
            await update.message.reply_text("❌ A network error occurred during the follow process. Session cleared.")
    except Exception as e:
        logger.error(f"Unexpected error during follow requests for user {user_id}: {e}", exc_info=True)
        if status_msg:
            await status_msg.edit_text("⚠️ An unexpected error occurred during the follow process. Session cleared.")
        else:
            await update.message.reply_text("⚠️ An unexpected error occurred during the follow process. Session cleared.")
    finally:
        delete_session(user_id)
        await show_main_menu(update, "Ready for your next task?")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # First check if user has joined channel
    if not is_user_in_channel(user_id):
        await prompt_join_channel(update)
        return

    if BOT_STATUS == "offline":
        await update.message.reply_text(
            "🔴 The bot is currently offline. Please try again later.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh Status", callback_data="refresh_status")]
            ])
        )
        return

    # Handle custom limit setting
    if context.user_data.get('awaiting_custom_limit'):
        target_user_id = context.user_data['target_user_id']
        
        try:
            new_limit = int(text)
            if 1 <= new_limit <= 100:
                set_user_limit(target_user_id, new_limit)
                await update.message.reply_text(
                    f"✅ Custom limit for user {target_user_id} set to {new_limit}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Back to User", callback_data=f"user_detail_{target_user_id}")]
                    ])
                )
            else:
                await update.message.reply_text(
                    "❌ Please enter a number between 1 and 100",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ Cancel", callback_data=f"user_detail_{target_user_id}")]
                    ])
                )
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter a valid number",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancel", callback_data=f"user_detail_{target_user_id}")]
                ])
            )
        
        # Clear the state
        context.user_data.pop('awaiting_custom_limit', None)
        context.user_data.pop('target_user_id', None)
        return

    session = get_session(user_id)
    if not session or session.get("step") != "awaiting_pin":
        await update.message.reply_text("I'm not expecting a PIN code right now. Please use the menu to start a new session.")
        return

    if not re.fullmatch(r"\d{7}", text):
        await update.message.reply_text("❌ Invalid format. Please send a 7-digit PIN code.")
        return

    pin_code = text

    payload = {
        "pinCode": pin_code,
        "token": session["token"],
        "secret": session["secret"],
        "ref_id": None,
        "apiId": session["apiId"]
    }

    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "referer": REFERRER,
    }

    try:
        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(AUTH_URL, headers=headers, json=payload) as auth_resp:
                if auth_resp.status != 200:
                    error_message = await auth_resp.text()
                    await update.message.reply_text(f"❌ PIN verification failed. Status: {auth_resp.status}. Response: `{error_message}`. Session cleared.")
                    delete_session(user_id)
                    await show_main_menu(update, "Please try getting a new authorization URL.")
                    return

                auth_json = await auth_resp.json()
                access_token = auth_json.get("accessToken") or auth_json.get("token") or auth_json.get("access_token")

                if not access_token:
                    await update.message.reply_text(f"❌ Access token missing in API response after PIN verification. Session cleared.\n`{auth_json}`", parse_mode="Markdown")
                    delete_session(user_id)
                    await show_main_menu(update, "Please try getting a new authorization URL.")
                    return

            common_headers = {
                "accept": "*/*",
                "authorization": f"bearer {access_token}",
                "referer": f"{REFERRER}/profile",
            }

            async with http_session.get("https://takipciyurdu.com/api/twitter-takipci/list", headers=common_headers) as list_resp:
                if list_resp.status == 200:
                    list_data = await list_resp.json()
                    pending_count = list_data.get("pendingListCount", "N/A")
                else:
                    pending_count = f"Failed ({list_resp.status})"
                    logger.warning(f"Failed to fetch follower list for user {user_id}. Status: {list_resp.status}")

            async with http_session.get(CREDIT_URL, headers=common_headers) as credit_resp:
                if credit_resp.status == 200:
                    credit_data = await credit_resp.json()
                    credit = credit_data.get("credit")
                    message = credit_data.get("message", "No message.")
                    refId = credit_data.get("refId")

                    await update.message.reply_text(
                        f"📋 Start Port: `{pending_count}`\n",
                        #f"💳 Credit: `{credit}`\n",
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text(f"❌ Failed to fetch credit info. Status: {credit_resp.status}. Session cleared.")
                    delete_session(user_id)
                    await show_main_menu(update, "Please try getting a new authorization URL.")
                    return

            if isinstance(credit, int) and credit > 0:
                await send_follow_requests(update, http_session, access_token)
            else:
                await update.message.reply_text("⚠️ No valid credit available to start following. Session cleared.")
                delete_session(user_id)
                await show_main_menu(update, "Ready for your next task?")

    except aiohttp.ClientError as e:
        logger.error(f"Network error during PIN verification or info fetching for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ A network error occurred during verification. Please check your connection and try again. Session cleared.")
        delete_session(user_id)
        await show_main_menu(update, "Try again?")
    except Exception as e:
        logger.error(f"Error handling pin for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("⚠️ An unexpected error occurred during PIN handling. Session cleared.")
        delete_session(user_id)
        await show_main_menu(update, "Try again?")

# --- Lifecycle Events ---

async def post_init(application: Application) -> None:
    """Perform post-initialization tasks"""
    if BOT_STATUS == "online":
        await notify_users(
            application,
            "🟢 Aixfly X Bot is now ONLINE and ready to serve you!",
            ONLINE_BANNER
        )

async def post_stop(application: Application) -> None:
    """Perform cleanup before stopping"""
    global BOT_STATUS
    BOT_STATUS = "offline"
    await notify_users(
        application,
        "🔴 Aixfly X Bot is now OFFLINE. Services will resume soon.",
        OFFLINE_BANNER
    )

# --- Main ---

def main():
    init_db()

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    logger.info("Aixfly X Bot starting...")
    
    try:
        app.run_polling()
    except KeyboardInterrupt:
        logger.info("Bot stopped by admin")
    finally:
        asyncio.run(post_stop(app))

if __name__ == "__main__":
    main()
