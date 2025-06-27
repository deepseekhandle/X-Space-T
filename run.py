import logging
import os
import re
import aiohttp
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
CHANNEL_USERNAME = "aixflycom"  # Channel username without @
CHANNEL_LINK = f"https://t.me/{CHANNEL_USERNAME}"
DEFAULT_USER_LIMIT = 5000

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
    # Only sessions and limits needed
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
        SELECT u.chat_id, 
               COALESCE(ul.get_auth_limit, g.default_get_auth_limit) as limit,
               COALESCE(ul.get_auth_used, 0) as used
        FROM user_limits ul
        JOIN global_settings g ON 1=1
        JOIN (SELECT DISTINCT chat_id FROM user_limits) u ON u.chat_id = ul.chat_id
    """)
    users = cursor.fetchall()
    conn.close()
    return users

# --- Channel Join Check ---

async def is_user_in_channel(bot, user_id):
    try:
        member = await bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.info(f"User {user_id} not in channel or error: {e}")
        return False

async def prompt_join_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔗 Join Channel", url=CHANNEL_LINK)],
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_join")]
    ]
    text = (
        f"🚫 To use this bot, you must join our channel:\n\n"
        f"👉 [@{CHANNEL_USERNAME}]({CHANNEL_LINK})\n\n"
        "After joining, click 'Refresh'."
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )

# --- Menu Helpers ---

async def show_main_menu(update: Update, message_text: str = None):
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

# --- Telegram Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_in_channel(context.bot, user_id):
        await prompt_join_channel(update, context)
        return
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
        await show_main_menu(update, "Main Menu:")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Channel join check
    if query.data == "refresh_join":
        if await is_user_in_channel(context.bot, user_id):
            await query.edit_message_text("✅ You have joined the channel!")
            await show_main_menu(update)
        else:
            await prompt_join_channel(update, context)
        return

    if not await is_user_in_channel(context.bot, user_id):
        await prompt_join_channel(update, context)
        return

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
            increment_user_limit_usage(user_id)
            await handle_get_auth(query)
        return

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

import random

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
                    await asyncio.sleep(random.uniform(5, 7))
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
    if not await is_user_in_channel(context.bot, user_id):
        await prompt_join_channel(update, context)
        return
    if BOT_STATUS == "offline":
        await update.message.reply_text(
            "🔴 The bot is currently offline. Please try again later.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh Status", callback_data="refresh_status")]
            ])
        )
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
                    await update.message.reply_text(
                        f"📋 Start Port: `{pending_count}`\n",
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

async def notify_users(app, message, banner=None):
    return  # No notification system needed for this version

async def post_init(application: Application) -> None:
    pass

async def post_stop(application: Application) -> None:
    global BOT_STATUS
    BOT_STATUS = "offline"

# --- Main ---

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
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
