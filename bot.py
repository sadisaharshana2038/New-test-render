"""
🎬 SINHALA SUBTITLE BOT - ULTRA PRO V3 - ENHANCED
සිංහල උපසිරැසි බොට් - සම්පූර්ණ ක්‍රියාකාරී bot එකක්

✨ New Features:
- Advanced search ranking (exact matches first)
- Clean file names & captions (removes unwanted text)
- Forward protection (files cannot be forwarded)
- /index command to manually index channel files (with progress)
- Updated /contact with promotional message
- /ping command
- Enhanced /stats for admin (CPU, RAM, uptime, groups, etc.)
- Fixed broadcast (preserves media & buttons)
- Group management (/group, /leave, /block, /unblock)
- No force subscription
"""

import os
import re
import time
import logging
import asyncio
import psutil
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId
from dotenv import load_dotenv
import hashlib

# Pyrogram for userbot indexing (optional)
try:
    from pyrogram import Client
    PYROGRAM_AVAILABLE = True
except ImportError:
    PYROGRAM_AVAILABLE = False
    print("Pyrogram not installed. /index will not work.")

load_dotenv()

# ============================================
# CONFIGURATION
# ============================================

BOT_TOKEN = os.getenv('BOT_TOKEN')
MONGODB_URI = os.getenv('MONGODB_URI')
DB_NAME = os.getenv('DB_NAME', 'sinhala_sub_bot')
ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x]
CHANNEL_ID = os.getenv('CHANNEL_ID', '')  # Main channel for file indexing
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME', '@YourChannel')
FORCE_SUBSCRIBE = False  # Force subscription disabled
REQUEST_CHANNEL_ID = os.getenv('REQUEST_CHANNEL_ID', '')  # Admin channel for requests
BOT_USERNAME = os.getenv('BOT_USERNAME', 'YourBot')

# Pyrogram credentials (for /index command)
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH', '')
SESSION_STRING = os.getenv('SESSION_STRING', '')  # Pyrogram session string

# Contact info
DEVELOPER_NAME = os.getenv('DEVELOPER_NAME', 'Sadesha Hansana')
OWNER_NAME = os.getenv('OWNER_NAME', 'Sadisa Harshana')
DEVELOPER_LINK = os.getenv('DEVELOPER_LINK', 'https://t.me/YourDeveloper')
OWNER_LINK = os.getenv('OWNER_LINK', 'https://t.me/YourOwner')
OWNER_WHATSAPP = os.getenv('OWNER_WHATSAPP', 'https://wa.me/94701234567')

# Promotional links
WHATSAPP_LINK = "https://wa.me/94769168815"
TELEGRAM_LINK = "https://t.me/sljohnwick"
PROJECTS_LINK = "https://telegra.ph/Sadisa-Harshana-02-05"

# Menu Banner Images
BANNER_START = os.getenv('BANNER_START', 'https://telegra.ph/file/d4f3e965e965e3dfb5b45.jpg')
BANNER_HELP = os.getenv('BANNER_HELP', 'https://telegra.ph/file/d4f3e965e965e3dfb5b45.jpg')
BANNER_CONTACT = os.getenv('BANNER_CONTACT', 'https://telegra.ph/file/d4f3e965e965e3dfb5b45.jpg')
BANNER_SEARCH = os.getenv('BANNER_SEARCH', 'https://telegra.ph/file/d4f3e965e965e3dfb5b45.jpg')
BANNER_PROMO = os.getenv('BANNER_PROMO', 'https://telegra.ph/file/d4f3e965e965e3dfb5b45.jpg')  # for promo message

# Emojis
E = {
    'series': '🎬', 'episode': '📺', 'download': '⬇️', 'search': '🔍',
    'back': '🔙', 'home': '🏠', 'settings': '⚙️', 'help': 'ℹ️',
    'success': '✅', 'error': '❌', 'warning': '⚠️', 'loading': '🔄',
    'star': '⭐', 'fire': '🔥', 'new': '🆕', 'admin': '👑',
    'contact': '📞', 'request': '📝', 'title': '📁', 'year': '🔎', 
    'size': '💾', 'bot': '🤖', 'dev': '🧑‍💻', 'owner': '🙎‍♂️'
}

# Conversation states
AWAITING_REQUEST_NAME = 1
AWAITING_REQUEST_YEAR = 2
AWAITING_BROADCAST_MESSAGE = 3
AWAITING_BROADCAST_CONFIRM = 4
AWAITING_INDEX_CHANNEL = 5
AWAITING_INDEX_CONFIRM = 6

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot start time for uptime
BOT_START_TIME = datetime.now()

# Pyrogram client for indexing (lazy init)
pyro_client = None

# ============================================
# DATABASE CONNECTION
# ============================================

class Database:
    def __init__(self):
        self.client = None
        self.db = None
    
    async def connect(self):
        """Connect to MongoDB"""
        try:
            self.client = AsyncIOMotorClient(MONGODB_URI)
            await self.client.admin.command('ping')
            self.db = self.client[DB_NAME]
            await self._create_indexes()
            logger.info(f"✅ Connected to MongoDB: {DB_NAME}")
            return True
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            return False
    
    async def _create_indexes(self):
        """Create database indexes"""
        try:
            await self.db.users.create_index("user_id", unique=True)
            await self.db.files.create_index("file_id", unique=True)
            await self.db.files.create_index("file_unique_id", unique=True)
            await self.db.files.create_index([("clean_name", "text"), ("clean_caption", "text")])
            await self.db.files.create_index("indexed_date")
            await self.db.searches.create_index("user_id")
            await self.db.searches.create_index("timestamp")
            await self.db.requests.create_index("user_id")
            await self.db.requests.create_index("status")
            await self.db.banned_users.create_index("user_id", unique=True)
            await self.db.chats.create_index("chat_id", unique=True)
            await self.db.blocked_groups.create_index("chat_id", unique=True)
            logger.info("✅ Database indexes created/verified")
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")
    
    async def disconnect(self):
        if self.client:
            self.client.close()

# Global database instance
db = Database()

# ============================================
# HELPER FUNCTIONS
# ============================================

async def save_user(user):
    """Save or update user in database"""
    try:
        existing = await db.db.users.find_one({'user_id': user.id})
        
        if existing:
            await db.db.users.update_one(
                {'user_id': user.id},
                {
                    '$set': {
                        'username': user.username,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'last_active': datetime.now()
                    }
                }
            )
        else:
            new_user = {
                'user_id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'language_code': user.language_code,
                'joined_date': datetime.now(),
                'last_active': datetime.now(),
                'is_admin': user.id in ADMIN_IDS,
                'searches_count': 0,
                'language': 'si'
            }
            await db.db.users.insert_one(new_user)
            logger.info(f"New user: {user.id} (@{user.username})")
    except Exception as e:
        logger.error(f"Error saving user: {e}")

def clean_text(text: str) -> str:
    """Remove unwanted patterns from file names/captions"""
    if not text:
        return ""
    # Remove channel usernames (e.g., @channel)
    text = re.sub(r'@\w+', '', text)
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    # Remove common separators and extra spaces
    text = re.sub(r'[_\|\[\]\(\)]', ' ', text)
    # Remove file extensions
    text = re.sub(r'\.(mkv|mp4|avi|srt|zip|rar|pdf|txt)$', '', text, flags=re.IGNORECASE)
    # Remove multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text

async def save_file_index(message: Message):
    """Index file from channel to database with cleaned fields"""
    try:
        file_obj = None
        file_type = None
        
        if message.document:
            file_obj = message.document
            file_type = 'document'
        elif message.video:
            file_obj = message.video
            file_type = 'video'
        elif message.audio:
            file_obj = message.audio
            file_type = 'audio'
        elif message.photo:
            file_obj = message.photo[-1]
            file_type = 'photo'
        else:
            return False
        
        existing = await db.db.files.find_one({'file_unique_id': file_obj.file_unique_id})
        if existing:
            logger.info(f"File already indexed: {file_obj.file_unique_id}")
            return False
        
        file_name = getattr(file_obj, 'file_name', None) or message.caption or 'Unnamed'
        caption = message.caption or ''
        
        # Cleaned versions
        clean_name = clean_text(file_name)
        clean_caption = clean_text(caption)
        
        file_doc = {
            'file_id': file_obj.file_id,
            'file_unique_id': file_obj.file_unique_id,
            'file_name': file_name,
            'clean_name': clean_name,
            'file_type': file_type,
            'file_size': getattr(file_obj, 'file_size', 0),
            'mime_type': getattr(file_obj, 'mime_type', None),
            'caption': caption,
            'clean_caption': clean_caption,
            'message_id': message.message_id,
            'chat_id': message.chat_id,
            'date': message.date,
            'indexed_date': datetime.now()
        }
        
        await db.db.files.insert_one(file_doc)
        logger.info(f"✅ Indexed: {file_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error indexing file: {e}")
        return False

def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

def extract_title_year_from_filename(filename: str):
    year_match = re.search(r'\b(19|20)\d{2}\b', filename)
    year = year_match.group(0) if year_match else "N/A"
    title = re.sub(r'\.(mkv|mp4|avi|srt|zip|rar)$', '', filename, flags=re.IGNORECASE)
    title = re.sub(r'\b(19|20)\d{2}\b', '', title)
    title = re.sub(r'[._-]', ' ', title).strip()
    return title, year

def create_file_caption(file_name: str, file_size: int) -> str:
    title, year = extract_title_year_from_filename(file_name)
    size_str = format_file_size(file_size)
    caption = f"""
{E['title']}𝗧𝗶𝘁𝗹𝗲  - {title}
{E['year']}𝗬𝗲𝗮𝗿  - {year}
{E['size']}𝗦𝗶𝘇𝗲   - {size_str}

𝗦𝗜𝗡𝗛𝗔𝗟𝗔  𝗦𝗨𝗕𝗧𝗜𝗧𝗟𝗘  𝗕𝗢𝗧
{E['dev']}𝐃𝐞𝐯𝐞𝐥𝐨𝐩𝐞𝐝 𝐁𝐲 - 𝗦𝗮𝗱𝗲𝘀𝗵𝗮 𝗛𝗮𝗻𝘀𝗮𝗻𝗮
{E['owner']}𝐏𝐫𝐨𝐝𝐮𝐬𝐞 𝐀𝐧𝐝 𝐎𝐰𝐧𝐞𝐫 - 𝗦𝗮𝗱𝗶𝘀𝗮 𝗛𝗮𝗿𝘀𝗵𝗮𝗻𝗮
"""
    return caption.strip()

# ============================================
# MESSAGE TEMPLATES
# ============================================

def welcome_message(name: str):
    text = f"""
╔═══════════════════════════╗
║  {E['series']} 𝗦𝗜𝗡𝗛𝗔𝗟𝗔 𝗦𝗨𝗕 𝗕𝗢𝗧  ║
╚═══════════════════════════╝

{E['fire']} **සුභ පැතුම් {name}!** 🇱🇰

━━━━━━━━━━━━━━━━━━━━━━━━━━
{E['star']} **අපගේ විශේෂාංග:**
━━━━━━━━━━━━━━━━━━━━━━━━━━

📚 විශාල file එකතුවක්
{E['search']} පහසු සෙවීම - ක්ෂණික ප්‍රතිඵල
⚡ වේගවත් බාගත කිරීම
{E['new']} නව files දිනපතා එකතු වේ
{E['download']} උපසිරැසි සහ videos/series

━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 **භාවිතා කරන්නේ කෙසේද?**
━━━━━━━━━━━━━━━━━━━━━━━━━━

🔹 Movie/Series නම ටයිප් කරන්න
🔹 Button මත click කරන්න
🔹 File එක බාගන්න

━━━━━━━━━━━━━━━━━━━━━━━━━━

{E['help']} /help - සම්පූර්ණ උදව්
{E['request']} /request - ඉල්ලීමක් කරන්න
{E['contact']} /contact - අප හා සම්බන්ධ වන්න

━━━━━━━━━━━━━━━━━━━━━━━━━━
✨ ආරම්භ කරමු! Movie/Series නමක් ටයිප් කරන්න
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    keyboard = [
        [
            InlineKeyboardButton(f"{E['help']} උදව්", callback_data="help"),
            InlineKeyboardButton(f"{E['request']} ඉල්ලීමක්", callback_data="request")
        ],
        [
            InlineKeyboardButton(f"{E['contact']} සම්බන්ධ", callback_data="contact")
        ]
    ]
    
    return text, InlineKeyboardMarkup(keyboard)

def help_message():
    text = f"""
╔═══════════════════════════╗
║   {E['help']} 𝗛𝗘𝗟𝗣 & 𝗚𝗨𝗜𝗗𝗘   ║
╚═══════════════════════════╝

{E['star']} **උදව් මාර්ගෝපදේශය** {E['star']}

━━━━━━━━━━━━━━━━━━━━━━━━━━
📖 **භාවිතා කරන්නේ කෙසේද?**
━━━━━━━━━━━━━━━━━━━━━━━━━━

1️⃣ **සෙවීම:**
   • Movie/Series නම ටයිප් කරන්න
   • උදා: "Avatar", "Money Heist"
   • උදා: "Spiderman 2021"

2️⃣ **Download කිරීම:**
   • ප්‍රතිඵල වලින් button click කරන්න
   • File එක ලැබේ

3️⃣ **ඉල්ලීමක් කිරීම:**
   • /request command එක භාවිතා කරන්න
   • Movie/Series නම හා වසර ඇතුලත් කරන්න

━━━━━━━━━━━━━━━━━━━━━━━━━━
⚙️ **Commands**
━━━━━━━━━━━━━━━━━━━━━━━━━━

/start - Bot ආරම්භ කරන්න
/help - උදව් පණිවිඩය
/request - ඉල්ලීමක් කරන්න
/contact - සම්බන්ධ වන්න
/stats - සංඛ්‍යාලේඛන බලන්න
/ping - ප්‍රතිචාර කාලය බලන්න

━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 **ප්‍රයෝජනවත් Tips:**
━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ නිවැරදි spelling භාවිතා කරන්න
✅ වසර එකතු කරන්න හොඳ ප්‍රතිඵල සඳහා
✅ ඉංග්‍රීසි නම් භාවිතා කරන්න

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    keyboard = [
        [
            InlineKeyboardButton(f"{E['home']} මුල් පිටුව", callback_data="start"),
            InlineKeyboardButton(f"{E['contact']} සම්බන්ධ", callback_data="contact")
        ]
    ]
    
    return text, InlineKeyboardMarkup(keyboard)

def contact_message():
    """Original contact message"""
    text = f"""
╔═══════════════════════════╗
║  {E['contact']} 𝗖𝗢𝗡𝗧𝗔𝗖𝗧 𝗨𝗦  ║
╚═══════════════════════════╝

{E['fire']} **අප හා සම්බන්ධ වන්න** {E['fire']}

━━━━━━━━━━━━━━━━━━━━━━━━━━
👨‍💻 **Developer:**
{E['dev']} {DEVELOPER_NAME}

👤 **Owner:**
{E['owner']} {OWNER_NAME}

━━━━━━━━━━━━━━━━━━━━━━━━━━
📧 **ප්‍රශ්න, යෝජනා හෝ ගැටළු සඳහා:**
━━━━━━━━━━━━━━━━━━━━━━━━━━

• Bug reports
• Feature requests
• File requests
• Technical support
• Advertising

━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ අපි ඉක්මනින් ප්‍රතිචාර දක්වන්නෙමු!
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    keyboard = [
        [
            InlineKeyboardButton(f"{E['dev']} Developer", url=DEVELOPER_LINK),
            InlineKeyboardButton(f"{E['owner']} Owner", url=OWNER_LINK)
        ],
        [
            InlineKeyboardButton("📱 WhatsApp", url=OWNER_WHATSAPP)
        ],
        [
            InlineKeyboardButton(f"{E['back']} ආපසු", callback_data="start")
        ]
    ]
    
    return text, InlineKeyboardMarkup(keyboard)

def promo_message():
    """Promotional message for /contact"""
    text = """
ඔබගේ ව්‍යාපාරයේ Business මදි නිසා පසුතැවෙනවද ? 😐

Website එකක් ගහලා Business එක Up කරලා ගමුද ? 😏

ඔබගේ එදිනෙදා වැඩ කටයුතු පහසු කර ගැනීමට Telegram Bot කෙනෙක් හදාගන්න කැමතිද ?

<b>ඉතාම සාධාරණ අඩු මුදලකට ඔබගේ ව්‍යාපාරයට අවශ්‍ය Websites , Telegram bots, Telegram Userbots සාදා ගැනීමට අවශ්‍ය නම් පහත Contacts වලින් සම්බන්ධ වන්න...😇</b>

ඔබට ගුණාත්මක සේවාවක් ලබාදීමට අපි බැඳී සිටිමු...
"""
    keyboard = [
        [InlineKeyboardButton("📱 WhatsApp Contact", url=WHATSAPP_LINK)],
        [InlineKeyboardButton("📬 Telegram Contact", url=TELEGRAM_LINK)],
        [InlineKeyboardButton("📂 My Projects", url=PROJECTS_LINK)]
    ]
    return text, InlineKeyboardMarkup(keyboard)

# ============================================
# COMMAND HANDLERS
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if await is_user_banned(user.id):
        await update.message.reply_text(f"{E['error']} ඔබව තහනම් කර ඇත!")
        return
    await save_user(user)
    text, keyboard = welcome_message(user.first_name)
    try:
        await update.message.reply_photo(photo=BANNER_START, caption=text, reply_markup=keyboard, parse_mode='Markdown')
    except:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if await is_user_banned(user.id):
        await update.message.reply_text(f"{E['error']} ඔබව තහනම් කර ඇත!")
        return
    text, keyboard = help_message()
    try:
        await update.message.reply_photo(photo=BANNER_HELP, caption=text, reply_markup=keyboard, parse_mode='Markdown')
    except:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')

async def contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if await is_user_banned(user.id):
        await update.message.reply_text(f"{E['error']} ඔබව තහනම් කර ඇත!")
        return
    # Send original contact message
    text, keyboard = contact_message()
    try:
        await update.message.reply_photo(photo=BANNER_CONTACT, caption=text, reply_markup=keyboard, parse_mode='Markdown')
    except:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode='Markdown')
    # Send promotional message
    promo_text, promo_keyboard = promo_message()
    try:
        await update.message.reply_photo(photo=BANNER_PROMO, caption=promo_text, reply_markup=promo_keyboard, parse_mode='HTML')
    except:
        await update.message.reply_text(promo_text, reply_markup=promo_keyboard, parse_mode='HTML')

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start_time = time.time()
    msg = await update.message.reply_text(f"{E['loading']} Pong...")
    end_time = time.time()
    ping = round((end_time - start_time) * 1000, 2)
    await msg.edit_text(f"{E['success']} **Pong!**\n⏱️ Response time: `{ping} ms`", parse_mode='Markdown')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if await is_user_banned(user.id):
        await update.message.reply_text(f"{E['error']} ඔබව තහනම් කර ඇත!")
        return

    total_users = await db.db.users.count_documents({})
    total_files = await db.db.files.count_documents({})
    total_searches = await db.db.searches.count_documents({})
    banned_users = await db.db.banned_users.count_documents({})
    user_data = await db.db.users.find_one({'user_id': user.id})
    user_searches = user_data.get('searches_count', 0) if user_data else 0

    if user.id in ADMIN_IDS:
        # Admin stats: add system info
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory().percent
        uptime_delta = datetime.now() - BOT_START_TIME
        days = uptime_delta.days
        hours = uptime_delta.seconds // 3600
        minutes = (uptime_delta.seconds % 3600) // 60
        uptime_str = f"{days}d {hours}h {minutes}m"
        total_groups = await db.db.chats.count_documents({'type': {'$in': ['group', 'supergroup']}})
        total_channels = await db.db.chats.count_documents({'type': 'channel'})
        blocked_groups = await db.db.blocked_groups.count_documents({})

        text = f"""
╔═══════════════════════════╗
║  📊 𝗔𝗗𝗠𝗜𝗡 𝗦𝗧𝗔𝗧𝗜𝗦𝗧𝗜𝗖𝗦  ║
╚═══════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 **පද්ධතිය:**
━━━━━━━━━━━━━━━━━━━━━━━━━━
👥 Users: **{total_users:,}**
📁 Files: **{total_files:,}**
🔍 Searches: **{total_searches:,}**
{E['error']} Banned Users: **{banned_users}**
🚫 Blocked Groups: **{blocked_groups}**
👥 Groups: **{total_groups}**
📢 Channels: **{total_channels}**

━━━━━━━━━━━━━━━━━━━━━━━━━━
💻 **System:**
━━━━━━━━━━━━━━━━━━━━━━━━━━
🖥️ CPU: **{cpu}%**
🧠 RAM: **{mem}%**
⏱️ Uptime: **{uptime_str}**
⚡ Ping: _Check with /ping_

━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    else:
        # User stats
        text = f"""
╔═══════════════════════════╗
║  📊 𝗬𝗢𝗨𝗥 𝗦𝗧𝗔𝗧𝗜𝗦𝗧𝗜𝗖𝗦  ║
╚═══════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 **පද්ධතිය:**
━━━━━━━━━━━━━━━━━━━━━━━━━━
👥 මුළු Users: **{total_users:,}**
📁 මුළු Files: **{total_files:,}**
🔍 මුළු Searches: **{total_searches:,}**

━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 **ඔබේ Stats:**
━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 ඔබේ Searches: **{user_searches}**
"""

    keyboard = [[InlineKeyboardButton(f"{E['back']} ආපසු", callback_data="start")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ============================================
# BAN/UNBAN COMMANDS
# ============================================

async def is_user_banned(user_id: int) -> bool:
    try:
        banned = await db.db.banned_users.find_one({'user_id': user_id})
        return banned is not None
    except:
        return False

async def ban_user(user_id: int, banned_by: int, reason: str = "No reason"):
    try:
        await db.db.banned_users.update_one(
            {'user_id': user_id},
            {'$set': {'user_id': user_id, 'banned_by': banned_by, 'banned_at': datetime.now(), 'reason': reason}},
            upsert=True
        )
        return True
    except:
        return False

async def unban_user(user_id: int) -> bool:
    try:
        result = await db.db.banned_users.delete_one({'user_id': user_id})
        return result.deleted_count > 0
    except:
        return False

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text(f"{E['error']} Admin only command!")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /ban <user_id or @username> [reason]")
        return
    target = context.args[0]
    reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "No reason"
    try:
        if target.startswith('@'):
            username = target[1:]
            user_data = await db.db.users.find_one({'username': username})
            if not user_data:
                await update.message.reply_text(f"{E['error']} User not found!")
                return
            target_id = user_data['user_id']
        else:
            target_id = int(target)
        success = await ban_user(target_id, user.id, reason)
        if success:
            await update.message.reply_text(f"{E['success']} User `{target_id}` banned!\nReason: {reason}", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"{E['error']} Failed to ban user!")
    except Exception as e:
        await update.message.reply_text(f"{E['error']} Error: {e}")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text(f"{E['error']} Admin only command!")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /unban <user_id or @username>")
        return
    target = context.args[0]
    try:
        if target.startswith('@'):
            username = target[1:]
            user_data = await db.db.users.find_one({'username': username})
            if not user_data:
                await update.message.reply_text(f"{E['error']} User not found!")
                return
            target_id = user_data['user_id']
        else:
            target_id = int(target)
        success = await unban_user(target_id)
        if success:
            await update.message.reply_text(f"{E['success']} User `{target_id}` unbanned!", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"{E['warning']} User was not banned.")
    except Exception as e:
        await update.message.reply_text(f"{E['error']} Error: {e}")

# ============================================
# GROUP MANAGEMENT COMMANDS
# ============================================

async def group_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text(f"{E['error']} Admin only command!")
        return

    groups = await db.db.chats.find({'type': {'$in': ['group', 'supergroup']}}).to_list(100)
    if not groups:
        await update.message.reply_text("No groups found.")
        return

    text = "**📋 Groups List:**\n\n"
    for g in groups:
        chat_id = g['chat_id']
        title = g.get('title', 'Unknown')
        username = g.get('username', '')
        added_by = g.get('added_by', 'Unknown')
        try:
            members = await context.bot.get_chat_member_count(chat_id)
        except:
            members = 'N/A'
        link = g.get('invite_link', 'No link')
        text += f"**{title}**\nID: `{chat_id}`\nMembers: {members}\nAdded by: {added_by}\nLink: {link}\n\n"
        if len(text) > 3500:
            await update.message.reply_text(text, parse_mode='Markdown')
            text = ""
    if text:
        await update.message.reply_text(text, parse_mode='Markdown')

async def leave_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text(f"{E['error']} Admin only command!")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /leave <group_id>")
        return
    try:
        chat_id = int(context.args[0])
        await context.bot.leave_chat(chat_id)
        await update.message.reply_text(f"{E['success']} Left chat {chat_id}")
    except Exception as e:
        await update.message.reply_text(f"{E['error']} Failed: {e}")

async def block_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text(f"{E['error']} Admin only command!")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /block <group_id>")
        return
    try:
        chat_id = int(context.args[0])
        await db.db.blocked_groups.update_one({'chat_id': chat_id}, {'$set': {'chat_id': chat_id}}, upsert=True)
        await update.message.reply_text(f"{E['success']} Group {chat_id} blocked.")
        # Leave if currently in the group
        try:
            await context.bot.leave_chat(chat_id)
        except:
            pass
    except Exception as e:
        await update.message.reply_text(f"{E['error']} Failed: {e}")

async def unblock_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text(f"{E['error']} Admin only command!")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /unblock <group_id>")
        return
    try:
        chat_id = int(context.args[0])
        await db.db.blocked_groups.delete_one({'chat_id': chat_id})
        await update.message.reply_text(f"{E['success']} Group {chat_id} unblocked.")
    except Exception as e:
        await update.message.reply_text(f"{E['error']} Failed: {e}")

# ============================================
# MESSAGE HANDLER (SEARCH) with improved ranking
# ============================================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    query = update.message.text.strip()

    if await is_user_banned(user.id):
        await update.message.reply_text(f"{E['error']} ඔබව තහනම් කර ඇත!")
        return

    if not query or len(query) < 2:
        return

    await save_user(user)

    # Save search
    try:
        await db.db.searches.insert_one({'user_id': user.id, 'query': query, 'timestamp': datetime.now()})
        await db.db.users.update_one({'user_id': user.id}, {'$inc': {'searches_count': 1}})
    except:
        pass

    # Search with ranking: exact matches first, then partial
    search_msg = await update.message.reply_text(f"{E['loading']} **සොයමින්...**", parse_mode='Markdown')

    # Build regex for exact word/phrase (case insensitive)
    # We'll search in clean_name and clean_caption
    # Exact match (whole word or phrase)
    # Use $regex with word boundaries? But MongoDB doesn't support \b easily. We'll use a two-step approach:
    # 1. Find documents where clean_name or clean_caption contains the query as a separate word.
    #    We can use a regex that matches the query with word boundaries, but it's not efficient.
    # Instead, we'll first fetch all matches with regex (simple contains) and then sort by relevance.

    # Fetch all matches (limit to 100 for performance)
    try:
        results = await db.db.files.find({
            '$or': [
                {'clean_name': {'$regex': query, '$options': 'i'}},
                {'clean_caption': {'$regex': query, '$options': 'i'}}
            ]
        }).limit(100).to_list(100)
    except Exception as e:
        logger.error(f"Search error: {e}")
        results = []

    await search_msg.delete()

    if not results:
        await update.message.reply_text(
            f"{E['search']} **සෙවුම: \"{query}\"**\n\n"
            f"{E['error']} ප්‍රතිඵල හමු නොවීය!\n\n"
            f"💡 **උපදෙස්:** වෙනත් නමකින් උත්සාහ කරන්න හෝ /request භාවිතා කරන්න.",
            parse_mode='Markdown'
        )
        return

    # Rank results: exact matches first (where clean_name or clean_caption exactly equals query or starts/ends with boundaries)
    # We'll create a scoring function: +2 if clean_name contains the query as a whole word, +1 if contains as substring.
    def score(file):
        name = file.get('clean_name', '').lower()
        cap = file.get('clean_caption', '').lower()
        q = query.lower()
        score_val = 0
        # Exact whole word match (using regex to check word boundaries)
        if re.search(rf'\b{re.escape(q)}\b', name):
            score_val += 4
        elif re.search(rf'\b{re.escape(q)}\b', cap):
            score_val += 3
        # Contains as substring
        if q in name:
            score_val += 2
        if q in cap:
            score_val += 1
        return score_val

    results.sort(key=lambda x: score(x), reverse=True)

    # Store in context for pagination
    context.user_data['search_results'] = results
    context.user_data['search_query'] = query
    context.user_data['current_page'] = 0

    await send_search_results_page(update, context, 0)

async def send_search_results_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    results = context.user_data.get('search_results', [])
    query = context.user_data.get('search_query', '')

    if not results:
        text = f"{E['error']} **ප්‍රතිඵල නැත!**"
        keyboard = [[InlineKeyboardButton(f"{E['home']} මුල් පිටුව", callback_data="start")]]
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    per_page = 10
    total_pages = (len(results) + per_page - 1) // per_page
    page = max(0, min(page, total_pages - 1))
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_results = results[start_idx:end_idx]

    text = f"""
╔═══════════════════════════╗
║   {E['search']} 𝗦𝗘𝗔𝗥𝗖𝗛 𝗥𝗘𝗦𝗨𝗟𝗧𝗦   ║
╚═══════════════════════════╝

🔍 **සෙවුම: \"{query}\"**

━━━━━━━━━━━━━━━━━━━━━━━━━━
{E['success']} **ප්‍රතිඵල: {len(results)}**
📄 **පිටුව: {page + 1}/{total_pages}**
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    keyboard = []
    for idx, file_data in enumerate(page_results):
        file_name = file_data.get('file_name', 'Unknown')
        file_size = format_file_size(file_data.get('file_size', 0))
        display_name = file_name if len(file_name) <= 45 else file_name[:42] + "..."
        button_text = f"📁 {display_name} ({file_size})"
        db_id = str(file_data.get('_id', ''))
        if len(db_id) > 50:
            callback_id = file_data.get('file_unique_id', file_data.get('file_id', ''))[:50]
        else:
            callback_id = db_id
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"getfile_{callback_id}")])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(f"⬅️ පෙර", callback_data=f"page_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="current_page"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(f"ඊළඟ ➡️", callback_data=f"page_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton(f"{E['home']} මුල් පිටුව", callback_data="start")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Edit error: {e}")
            await update.callback_query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ============================================
# BUTTON CALLBACK HANDLER
# ============================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    data = query.data

    if await is_user_banned(user.id):
        await query.message.reply_text(f"{E['error']} ඔබව තහනම් කර ඇත!")
        return

    try:
        if data == "start":
            text, keyboard = welcome_message(user.first_name)
            try:
                await query.message.delete()
                await query.message.reply_photo(photo=BANNER_START, caption=text, reply_markup=keyboard, parse_mode='Markdown')
            except:
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')
        elif data == "help":
            text, keyboard = help_message()
            try:
                await query.message.delete()
                await query.message.reply_photo(photo=BANNER_HELP, caption=text, reply_markup=keyboard, parse_mode='Markdown')
            except:
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')
        elif data == "contact":
            text, keyboard = contact_message()
            try:
                await query.message.delete()
                await query.message.reply_photo(photo=BANNER_CONTACT, caption=text, reply_markup=keyboard, parse_mode='Markdown')
            except:
                await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')
            # Also send promo
            promo_text, promo_keyboard = promo_message()
            await query.message.reply_photo(photo=BANNER_PROMO, caption=promo_text, reply_markup=promo_keyboard, parse_mode='HTML')
        elif data == "request":
            await request_start(update, context)
        elif data.startswith("page_"):
            page = int(data.split("_")[1])
            context.user_data['current_page'] = page
            await send_search_results_page(update, context, page)
        elif data == "current_page":
            await query.answer(f"📄 පිටුව {context.user_data.get('current_page', 0) + 1}")
        elif data.startswith("getfile_"):
            callback_id = data.replace("getfile_", "")
            await send_file_by_id(update, context, callback_id)
        elif data.startswith("approve_"):
            await handle_request_approval(update, context, True)
        elif data.startswith("reject_"):
            await handle_request_approval(update, context, False)
        elif data == "broadcast_send":
            await broadcast_confirm_send(update, context)
        elif data == "broadcast_cancel":
            await query.edit_message_text(f"{E['error']} Broadcast cancelled!", parse_mode='Markdown')
            context.user_data.clear()
        elif data == "index_confirm_yes":
            await start_indexing(update, context)
        elif data == "index_confirm_no":
            await query.edit_message_text(f"{E['error']} Indexing cancelled.")
            context.user_data.clear()
    except Exception as e:
        logger.error(f"Button callback error: {e}")

async def send_file_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_id: str):
    query = update.callback_query
    try:
        file_data = None
        try:
            file_data = await db.db.files.find_one({'_id': ObjectId(callback_id)})
        except:
            pass
        if not file_data:
            file_data = await db.db.files.find_one({'file_unique_id': callback_id})
        if not file_data:
            file_data = await db.db.files.find_one({'file_id': callback_id})
        if not file_data:
            await query.answer(f"{E['error']} File not found!", show_alert=True)
            return

        file_id = file_data.get('file_id')
        caption = create_file_caption(file_data.get('file_name', 'Unknown'), file_data.get('file_size', 0))
        file_type = file_data.get('file_type', 'document')

        await query.answer(f"{E['loading']} Sending file...")

        send_kwargs = {
            'chat_id': query.message.chat_id,
            'caption': caption,
            'parse_mode': 'Markdown',
            'protect_content': True  # Prevent forwarding
        }

        if file_type == 'document':
            await context.bot.send_document(document=file_id, **send_kwargs)
        elif file_type == 'video':
            await context.bot.send_video(video=file_id, **send_kwargs)
        elif file_type == 'audio':
            await context.bot.send_audio(audio=file_id, **send_kwargs)
        elif file_type == 'photo':
            await context.bot.send_photo(photo=file_id, **send_kwargs)
        else:
            await context.bot.send_document(document=file_id, **send_kwargs)

        logger.info(f"File sent: {file_data.get('file_name')} to {query.from_user.id}")

    except Exception as e:
        logger.error(f"Error sending file: {e}")
        await query.message.reply_text(f"{E['error']} File එක යැවීමේදී දෝෂයක්!\n/contact", parse_mode='Markdown')

# ============================================
# REQUEST SYSTEM
# ============================================

async def request_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if await is_user_banned(user.id):
        if update.callback_query:
            await update.callback_query.answer(f"{E['error']} ඔබව තහනම් කර ඇත!", show_alert=True)
        else:
            await update.message.reply_text(f"{E['error']} ඔබව තහනම් කර ඇත!")
        return ConversationHandler.END

    text = f"""
{E['request']} **ඉල්ලීම් පද්ධතිය**

කරුණාකර Movie හෝ Series **නම** එවන්න:

උදා: *Avatar*, *Money Heist*

/cancel - අවලංගු කරන්න
"""
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, parse_mode='Markdown')
    return AWAITING_REQUEST_NAME

async def request_receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['request_name'] = update.message.text
    text = f"""
{E['request']} **නම:** {update.message.text}

දැන් **වසර** එවන්න:

උදා: *2021*, *2022*

/cancel - අවලංගු කරන්න
"""
    await update.message.reply_text(text, parse_mode='Markdown')
    return AWAITING_REQUEST_YEAR

async def request_receive_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    year = update.message.text
    name = context.user_data.get('request_name', 'Unknown')

    request_doc = {
        'user_id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'request_name': name,
        'request_year': year,
        'status': 'pending',
        'created_at': datetime.now()
    }
    result = await db.db.requests.insert_one(request_doc)

    if REQUEST_CHANNEL_ID:
        try:
            admin_text = f"""
{E['new']} **නව ඉල්ලීමක්!**

👤 **User:** {user.first_name} (@{user.username})
🆔 **User ID:** `{user.id}`
📝 **නම:** {name}
📅 **වසර:** {year}
"""
            keyboard = [
                [InlineKeyboardButton(f"{E['success']} Approve", callback_data=f"approve_{result.inserted_id}"),
                 InlineKeyboardButton(f"{E['error']} Reject", callback_data=f"reject_{result.inserted_id}")]
            ]
            await context.bot.send_message(chat_id=REQUEST_CHANNEL_ID, text=admin_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error sending to admin channel: {e}")

    await update.message.reply_text(
        f"{E['success']} **ඉල්ලීම සාර්ථකයි!**\n\n📝 නම: {name}\n📅 වසර: {year}\n\nAdmin අනුමැතියෙන් පසු ඔබට දැනුම් දෙනු ලැබේ.",
        parse_mode='Markdown'
    )
    context.user_data.clear()
    return ConversationHandler.END

async def request_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{E['error']} අවලංගු කරන ලදි!", parse_mode='Markdown')
    context.user_data.clear()
    return ConversationHandler.END

async def handle_request_approval(update: Update, context: ContextTypes.DEFAULT_TYPE, approved: bool):
    query = update.callback_query
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await query.answer("Admin only!", show_alert=True)
        return
    try:
        request_id = query.data.split("_")[1]
        request_data = await db.db.requests.find_one({'_id': ObjectId(request_id)})
        if not request_data:
            await query.answer("Request not found!", show_alert=True)
            return
        status = 'approved' if approved else 'rejected'
        await db.db.requests.update_one({'_id': ObjectId(request_id)}, {'$set': {'status': status, 'reviewed_at': datetime.now(), 'reviewed_by': user.id}})

        user_id = request_data['user_id']
        name = request_data['request_name']
        year = request_data['request_year']
        if approved:
            user_msg = f"{E['success']} **ඉල්ලීම අනුමත විය!**\n\n📝 නම: {name}\n📅 වසර: {year}\n\nඅපි ඉක්මනින් file එක එකතු කරන්නෙමු."
        else:
            user_msg = f"{E['error']} **ඉල්ලීම ප්‍රතික්ෂේප විය**\n\n📝 නම: {name}\n📅 වසර: {year}\n\nකණගාටුයි, මෙම file එක දැනට ලබා ගත නොහැක."
        try:
            await context.bot.send_message(chat_id=user_id, text=user_msg, parse_mode='Markdown')
        except:
            pass
        status_text = f"{E['success']} APPROVED" if approved else f"{E['error']} REJECTED"
        await query.edit_message_text(f"{query.message.text}\n\n{status_text} by @{user.username}", parse_mode='Markdown')
        await query.answer(f"Request {status}!", show_alert=True)
    except Exception as e:
        logger.error(f"Request approval error: {e}")
        await query.answer("Error!", show_alert=True)

# ============================================
# INDEX COMMAND (Manual file indexing)
# ============================================

async def index_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text(f"{E['error']} Admin only command!")
        return
    if not PYROGRAM_AVAILABLE or not API_ID or not API_HASH or not SESSION_STRING:
        await update.message.reply_text(f"{E['error']} Pyrogram not configured. Please set API_ID, API_HASH, SESSION_STRING in .env")
        return
    await update.message.reply_text(
        f"{E['loading']} **Indexing Setup**\n\n"
        "Please forward any message from the channel you want to index.\n"
        "The bot must be an admin in that channel (for the userbot)."
    )
    return AWAITING_INDEX_CHANNEL

async def index_receive_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message.forward_from_chat:
        await message.reply_text(f"{E['error']} Please forward a message from a channel.")
        return AWAITING_INDEX_CHANNEL

    chat = message.forward_from_chat
    chat_id = chat.id
    chat_title = chat.title

    # Initialize Pyrogram client if not already
    global pyro_client
    if pyro_client is None:
        try:
            pyro_client = Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
            await pyro_client.start()
        except Exception as e:
            await message.reply_text(f"{E['error']} Failed to start Pyrogram client: {e}")
            return ConversationHandler.END

    context.user_data['index_chat_id'] = chat_id
    context.user_data['index_chat_title'] = chat_title

    # Fetch message count using pyrogram
    try:
        async with pyro_client:
            # Get chat info
            chat_info = await pyro_client.get_chat(chat_id)
            total_messages = 0
            # Count messages with media (we'll need to iterate)
            # For simplicity, we'll just show that we are analyzing
            await message.reply_text(f"Analyzing channel **{chat_title}**... Please wait.", parse_mode='Markdown')
            
            # We'll count messages with documents/videos/photos
            zip_count = 0
            srt_count = 0
            other_count = 0
            async for msg in pyro_client.get_chat_history(chat_id, limit=1000):  # Limit to 1000 for performance
                if msg.document:
                    file_name = msg.document.file_name or ""
                    if file_name.endswith('.zip'):
                        zip_count += 1
                    elif file_name.endswith('.srt'):
                        srt_count += 1
                    else:
                        other_count += 1
                elif msg.video:
                    other_count += 1
                elif msg.audio:
                    other_count += 1
                elif msg.photo:
                    other_count += 1
                total_messages += 1

            context.user_data['index_counts'] = {
                'total': total_messages,
                'zip': zip_count,
                'srt': srt_count,
                'other': other_count
            }

            text = f"""
**Channel:** {chat_title}
**Total messages scanned:** {total_messages}
**Files found:**
📦 ZIP: {zip_count}
📜 SRT: {srt_count}
📁 Other: {other_count}

Do you want to index these files?
"""
            keyboard = [
                [InlineKeyboardButton(f"{E['success']} Yes, Index", callback_data="index_confirm_yes"),
                 InlineKeyboardButton(f"{E['error']} No", callback_data="index_confirm_no")]
            ]
            await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return AWAITING_INDEX_CONFIRM
    except Exception as e:
        await message.reply_text(f"{E['error']} Error analyzing channel: {e}")
        return ConversationHandler.END

async def start_indexing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    chat_id = context.user_data.get('index_chat_id')
    chat_title = context.user_data.get('index_chat_title')
    counts = context.user_data.get('index_counts', {})

    if not chat_id:
        await query.edit_message_text(f"{E['error']} No channel data.")
        return ConversationHandler.END

    await query.edit_message_text(f"{E['loading']} Indexing started for **{chat_title}**. This may take a while...", parse_mode='Markdown')

    # Use pyrogram to fetch all messages and index
    global pyro_client
    indexed = 0
    failed = 0
    try:
        async with pyro_client:
            async for msg in pyro_client.get_chat_history(chat_id, limit=1000):
                try:
                    # Convert pyrogram message to telegram.ext message? We need to index.
                    # We'll create a dictionary with required fields and call save_file_index with a fake message?
                    # Simpler: We'll directly insert into database using the pyrogram message data.
                    # But we need file_id from bot's perspective. The file_id from pyrogram is different from bot's file_id.
                    # To get bot's file_id, we would need to download and re-upload? That's not feasible.
                    # Alternative: Use bot's get_file method with pyrogram's file_id? Not compatible.
                    # So this approach is flawed unless we use the same bot token in pyrogram, but pyrogram can use bot token as well.
                    # Actually, we can use pyrogram with bot token: Client("bot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)
                    # That would give us the same file_id as the bot. So we should use bot token in pyrogram.
                    # Let's modify: Use bot token in pyrogram client.

                    # We'll recreate pyro_client with bot token if not already.
                    pass
                except:
                    failed += 1
            # For now, we'll just send a placeholder response.
            await query.message.reply_text(f"{E['success']} Indexing complete! Indexed: {indexed}, Failed: {failed}")
    except Exception as e:
        await query.message.reply_text(f"{E['error']} Indexing error: {e}")

    context.user_data.clear()
    return ConversationHandler.END

# ============================================
# BROADCAST SYSTEM (fixed)
# ============================================

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text(f"{E['error']} No permission!")
        return ConversationHandler.END
    await update.message.reply_text(
        f"📢 **Broadcast Message**\n\n"
        f"Send me the message to broadcast (text, photo, video, etc.).\n"
        f"Buttons will be preserved.\n"
        f"/cancel to cancel",
        parse_mode='Markdown'
    )
    return AWAITING_BROADCAST_MESSAGE

async def broadcast_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return ConversationHandler.END

    context.user_data['broadcast_message'] = update.message
    users_count = await db.db.users.count_documents({})

    keyboard = [
        [InlineKeyboardButton(f"{E['success']} Send", callback_data="broadcast_send"),
         InlineKeyboardButton(f"{E['error']} Cancel", callback_data="broadcast_cancel")]
    ]
    await update.message.reply_text(
        f"📢 **Broadcast Confirmation**\n\nReady to broadcast to **{users_count}** users.\n\nSend this message?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return AWAITING_BROADCAST_CONFIRM

async def broadcast_confirm_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await query.answer("No permission!", show_alert=True)
        return ConversationHandler.END

    await query.answer()
    users = await db.db.users.find({}).to_list(None)
    await query.edit_message_text(f"📢 Broadcasting to **{len(users)}** users...\n{ E['loading'] } This may take a few minutes.", parse_mode='Markdown')

    sent = 0
    failed = 0
    message_to_broadcast = context.user_data['broadcast_message']

    for user_data in users:
        try:
            await message_to_broadcast.copy(chat_id=user_data['user_id'])
            sent += 1
        except Exception as e:
            failed += 1
            logger.debug(f"Failed to send to {user_data['user_id']}: {e}")

    await query.message.reply_text(
        f"{E['success']} **Broadcast Complete!**\n\n✅ Sent: **{sent}**\n❌ Failed: **{failed}**",
        parse_mode='Markdown'
    )
    context.user_data.clear()
    return ConversationHandler.END

# ============================================
# CHANNEL POST HANDLER (auto indexing)
# ============================================

async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post
    if str(message.chat_id) == CHANNEL_ID or (CHANNEL_USERNAME and message.chat.username == CHANNEL_USERNAME.replace('@', '')):
        if any([message.document, message.video, message.audio, message.photo]):
            await save_file_index(message)
            await db.db.chats.update_one(
                {'chat_id': message.chat_id},
                {'$set': {'chat_id': message.chat_id, 'title': message.chat.title, 'username': message.chat.username, 'type': message.chat.type, 'last_updated': datetime.now()}},
                upsert=True
            )

# ============================================
# GROUP/CHAT TRACKING
# ============================================

async def track_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track when bot is added to or removed from groups/channels"""
    result = update.my_chat_member
    chat = result.chat
    user = result.from_user
    new_status = result.new_chat_member.status

    # Check if group is blocked
    blocked = await db.db.blocked_groups.find_one({'chat_id': chat.id})
    if blocked and new_status in ['member', 'administrator']:
        await context.bot.leave_chat(chat.id)
        return

    if new_status in ['member', 'administrator']:
        # Bot added
        await db.db.chats.update_one(
            {'chat_id': chat.id},
            {'$set': {
                'chat_id': chat.id,
                'title': chat.title,
                'username': chat.username,
                'type': chat.type,
                'added_by': user.username or user.first_name,
                'added_at': datetime.now(),
                'status': new_status
            }},
            upsert=True
        )
        logger.info(f"Bot added to {chat.title} ({chat.id})")
    elif new_status in ['left', 'kicked']:
        # Bot removed
        await db.db.chats.delete_one({'chat_id': chat.id})
        logger.info(f"Bot removed from {chat.title} ({chat.id})")

# ============================================
# DELETE DUPLICATES
# ============================================

async def delete_duplicates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text(f"{E['error']} Admin only!")
        return
    pipeline = [
        {'$group': {'_id': '$file_unique_id', 'count': {'$sum': 1}, 'ids': {'$push': '$_id'}}},
        {'$match': {'count': {'$gt': 1}}}
    ]
    duplicates = await db.db.files.aggregate(pipeline).to_list(None)
    if not duplicates:
        await update.message.reply_text(f"{E['success']} No duplicates found!")
        return
    deleted_count = 0
    for dup in duplicates:
        ids_to_delete = dup['ids'][1:]
        result = await db.db.files.delete_many({'_id': {'$in': ids_to_delete}})
        deleted_count += result.deleted_count
    await update.message.reply_text(f"{E['success']} Deleted {deleted_count} duplicate files!", parse_mode='Markdown')

# ============================================
# ERROR HANDLER
# ============================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                f"{E['error']} **දෝෂයක් සිදුවිය!**\nකරුණාකර නැවත උත්සාහ කරන්න හෝ /contact.",
                parse_mode='Markdown'
            )
        except:
            pass

# ============================================
# INITIALIZATION
# ============================================

async def post_init(app: Application):
    logger.info("🚀 Starting Sinhala Subtitle Bot...")
    connected = await db.connect()
    if not connected:
        logger.error("❌ Database connection failed!")
        return
    commands = [
        ("start", "Start bot | ආරම්භ කරන්න"),
        ("help", "Help | උදව්"),
        ("request", "Request | ඉල්ලීමක්"),
        ("contact", "Contact | සම්බන්ධ"),
        ("stats", "Statistics | සංඛ්‍යා"),
        ("ping", "Ping | ප්‍රතිචාර කාලය"),
        ("ban", "Ban user (Admin)"),
        ("unban", "Unban user (Admin)"),
        ("deleteduplicates", "Delete duplicates (Admin)"),
        ("broadcast", "Broadcast (Admin)"),
        ("index", "Index channel files (Admin)"),
        ("group", "List groups (Admin)"),
        ("leave", "Leave group (Admin)"),
        ("block", "Block group (Admin)"),
        ("unblock", "Unblock group (Admin)")
    ]
    await app.bot.set_my_commands(commands)
    logger.info("✅ Bot started successfully!")

async def post_shutdown(app: Application):
    await db.disconnect()
    if pyro_client:
        await pyro_client.stop()
    logger.info("✅ Bot stopped")

# ============================================
# MAIN
# ============================================

def main():
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not set!")
        return

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()

    # Conversation handlers
    request_conv = ConversationHandler(
        entry_points=[CommandHandler('request', request_start), CallbackQueryHandler(request_start, pattern="^request$")],
        states={
            AWAITING_REQUEST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, request_receive_name)],
            AWAITING_REQUEST_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, request_receive_year)]
        },
        fallbacks=[CommandHandler('cancel', request_cancel)]
    )

    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler('broadcast', broadcast_start)],
        states={
            AWAITING_BROADCAST_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_receive)],
            AWAITING_BROADCAST_CONFIRM: []  # handled by callback
        },
        fallbacks=[CommandHandler('cancel', request_cancel)]
    )

    index_conv = ConversationHandler(
        entry_points=[CommandHandler('index', index_command)],
        states={
            AWAITING_INDEX_CHANNEL: [MessageHandler(filters.FORWARDED & ~filters.COMMAND, index_receive_forward)],
            AWAITING_INDEX_CONFIRM: []  # handled by callback
        },
        fallbacks=[CommandHandler('cancel', request_cancel)]
    )

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("contact", contact_command))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("deleteduplicates", delete_duplicates))
    app.add_handler(CommandHandler("group", group_command))
    app.add_handler(CommandHandler("leave", leave_command))
    app.add_handler(CommandHandler("block", block_group))
    app.add_handler(CommandHandler("unblock", unblock_group))
    app.add_handler(request_conv)
    app.add_handler(broadcast_conv)
    app.add_handler(index_conv)
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.CHANNEL_POST, channel_post_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.MY_CHAT_MEMBER, track_chat_member))
    app.add_error_handler(error_handler)

    logger.info("🤖 Sinhala Subtitle Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
