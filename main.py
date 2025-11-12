import os
import sqlite3
import logging
import time
from datetime import datetime, timedelta
from typing import List, Optional
import asyncio
import aiosqlite

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from dotenv import load_dotenv
load_dotenv()

# --------- تنظیمات و لاگینگ ---------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

VIEW_CHANNEL_ID = os.environ.get('VIEW_CHANNEL_ID')
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_IDS = os.environ.get('ADMIN_IDS')
# ARCHIVE_CHANNEL_ID = os.environ.get('ARCHIVE_CHANNEL_ID')

# پارامترهای قابل تنظیم
DEFAULT_VIEW_SECONDS = int(os.environ.get('VIEW_SECONDS', '20'))

# --------- دیتابیس ساده SQLite ---------
DB_PATH = os.environ.get('DB_PATH', 'movies_bot.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        description TEXT,
        poster_file_id TEXT,
        video_file_id TEXT,
        created_at TEXT
    )
    ''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT UNIQUE,
        title TEXT
    )
    ''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS user_state (
        user_id INTEGER,
        movie_id INTEGER,
        step INTEGER,
        started_at REAL,
        PRIMARY KEY (user_id, movie_id)
    )
    ''')
    conn.commit()
    conn.close()


async def db_execute(query, params=(), fetch=False):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(query, params) as cur:
            if fetch:
                rows = await cur.fetchall()
                await db.commit()
                return rows
        await db.commit()


# --------- کمکی‌ها ---------

def is_admin(user_id: int) -> bool:
    if not ADMIN_IDS:
        return False
    return str(user_id) in [x.strip() for x in ADMIN_IDS.split(',') if x.strip()]


def parse_start_payload(payload: str) -> Optional[int]:
    # payload expected like: movie_123
    if not payload:
        return None
    if payload.startswith('movie_'):
        try:
            return int(payload.split('_', 1)[1])
        except:
            return None
    return None

# --------- handlers اصلی ---------

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args  # این شامل payload از deep link می‌شود اگر باشد
    payload = None
    if args:
        payload = args[0]
    movie_id = parse_start_payload(payload) if payload else None

    if not movie_id:
        await update.message.reply_text('سلام! لطفاً روی دکمهٔ فیلم در کانال کلیک کنید تا آن را باز کنم.')
        return

    # بارگذاری اطلاعات فیلم
    rows = await db_execute('SELECT id, title, description, poster_file_id FROM movies WHERE id=?', (movie_id,), fetch=True)
    if not rows:
        await update.message.reply_text('فیلم پیدا نشد؛ ممکن است لینک منقضی شده باشد یا فیلم حذف شده باشد.')
        return

    m_id, title, description, poster_file_id = rows[0]

    text = f"*{title}*\n\n{description}\n\nبرای دسترسی به فایل، باید عضو کانال های زیر شوید."

    keyboard = [
        [InlineKeyboardButton('بررسی عضویت', callback_data=f'check_members_{m_id}')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if poster_file_id:
        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=poster_file_id, caption=text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        except Exception as e:
            logger.exception('send_photo failed')
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)


async def callback_check_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # format: check_members_<movie_id>
    parts = data.split('_')
    movie_id = int(parts[-1])
    user = query.from_user

    # لیست کانال‌ها را از دیتابیس بخوانید
    channels = await db_execute('SELECT chat_id, title FROM channels', fetch=True)
    if not channels:
        await query.edit_message_text('فعلاً هیچ کانالی برای بررسی ثبت نشده است. مدیر کانال باید کانال‌ها را با /addchannel ثبت کند.')
        return

    not_member = []
    for chat_id, title in channels:
        try:
            member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user.id)
            status = member.status
            if status in ('left', 'kicked'):
                not_member.append((chat_id, title))
        except Exception as e:
            logger.warning(f'خطا در گرفتن وضعیت کاربر برای {chat_id}: {e}')
            not_member.append((chat_id, title))

    if not_member:
        # پیام برای کانال‌هایی که هنوز عضو نیست
        text = 'شما هنوز عضوِ کانال‌های زیر نیستید. لطفاً به آن‌ها ملحق شوید و سپس دوباره روی "بررسی عضویت" بزنید:\n\n'
        for cid, title in not_member:
            link = f'https://t.me/{cid.lstrip("@")} ' if cid.startswith('@') else f'کانال({cid})'
            text += f'- {title}: {link}\n'

        # دوباره دکمه بررسی عضویت اضافه می‌کنیم
        keyboard = [[InlineKeyboardButton('بررسی عضویت', callback_data=f'check_members_{movie_id}')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # همه عضو بودند => مرحلهٔ دوم
    now = time.time()
    await db_execute('REPLACE INTO user_state (user_id, movie_id, step, started_at) VALUES (?,?,?,?)', (user.id, movie_id, 1, now))

    text = (
        f'تبریک! شما عضو تمام کانال‌های موردنیاز هستید.\n\n'
        f'حالا باید آخرین پست‌های کانال زیر را ببینید:\n'
        f'- کانال موردنظر: {VIEW_CHANNEL_ID}\n\n'
        f'وقتی آماده بودید روی "من پست‌ها را دیدم" بزنید.\n'
    )

    keyboard = [[InlineKeyboardButton('من پست‌ها را دیدم', callback_data=f'check_view_{movie_id}')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def callback_check_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    movie_id = int(data.split('_')[-1])
    user = query.from_user

    # بررسی اینکه ابتدا بررسی عضویت انجام شده باشه (همون state اولیه)
    rows = await db_execute(
        'SELECT step, started_at FROM user_state WHERE user_id=? AND movie_id=?',
        (user.id, movie_id),
        fetch=True,
    )
    if not rows:
        await query.edit_message_text('ابتدا باید بررسی عضویت را انجام دهید. لطفاً دوباره از دکمهٔ بررسی عضویت شروع کنید.')
        return
    step, started_at = rows[0]
    if step != 1:
        await query.edit_message_text('وضعیت شما نامعتبر است؛ لطفاً دوباره تلاش کنید.')
        return

    # محاسبهٔ زمان گذشته از لحظهٔ "شروع بازدید"
    elapsed = time.time() - started_at
    remaining = int(DEFAULT_VIEW_SECONDS - elapsed) if elapsed < DEFAULT_VIEW_SECONDS else 0
    if remaining > 0:
        # کاربر زود کلیک زده — هم alert میده هم متن پیام اصلی تغییر میکنه
        await query.answer(
            f'شما هنوز 10 پست آخر را بازدید نکرده اید؛ لطفا برگردید و پست‌ها را بازدید کنید.',
            show_alert=True
        )
        text = (f'شما هنوز 10 پست آخر را بازدید نکرده اید؛ لطفا برگردید و پست‌ها را بازدید کنید.\n'
                f'- کانال موردنظر: {VIEW_CHANNEL_ID}')

        keyboard = [[InlineKeyboardButton('من پست‌ها را دیدم', callback_data=f'check_view_{movie_id}')]]
        return await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


    # الان تایمر تموم شده؛ وانمود کن داریم بررسی میکنیم (ظاهر بهتر)
    await query.edit_message_text('در حال بررسی مشاهدهٔ پست‌ها... لطفاً کمی صبر کنید.')
    await asyncio.sleep(1)  # تأخیر کوتاه برای طبیعی‌تر شدن

    # بارگذاری اطلاعات فیلم
    rows = await db_execute('SELECT video_file_id, title FROM movies WHERE id=?', (movie_id,), fetch=True)
    if not rows:
        await query.edit_message_text('فیلم پیدا نشد.')
        return
    video_file_id, title = rows[0]
    if not video_file_id:
        await query.edit_message_text('فایل ویدیویی برای این فیلم آپلود نشده است. مدیر باید آن را اضافه کند.')
        return

    # ارسال فیلم (و پاک کردن وضعیت کاربر)
    await query.edit_message_text('در حال ارسال فیلم...')
    try:
        await context.bot.send_chat_action(chat_id=query.from_user.id, action=ChatAction.UPLOAD_VIDEO)
        await context.bot.send_video(chat_id=query.from_user.id, video=video_file_id, caption=f'فیلم: {title}')
    except Exception:
        logger.exception('send_video failed')
        await query.edit_message_text('خطا در ارسال ویدیو. لطفاً با مدیر تماس بگیرید.')
        return

    await db_execute('DELETE FROM user_state WHERE user_id=? AND movie_id=?', (user.id, movie_id))

# --------- دستورات ادمین برای مدیریت فیلم‌ها و کانال‌ها ---------

async def admin_addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text('فقط مدیر اجازهٔ این کار را دارد.')
        return
    if not context.args:
        await update.message.reply_text('استفاده: /addchannel <@username یا chat_id> <عنوان_اختیاری>')
        return
    chat_id = context.args[0]
    title = ' '.join(context.args[1:]) if len(context.args) > 1 else chat_id
    await db_execute('INSERT OR IGNORE INTO channels (chat_id, title) VALUES (?,?)', (chat_id, title))
    await update.message.reply_text(f'کانال ثبت شد: {title} ({chat_id})')


async def admin_listchannels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text('فقط مدیر اجازهٔ این کار را دارد.')
        return
    rows = await db_execute('SELECT chat_id, title FROM channels', fetch=True)
    if not rows:
        await update.message.reply_text('هیچ کانالی ثبت نشده است.')
        return
    text = 'کانال‌های ثبت شده:\n'
    for cid, title in rows:
        text += f'- {title}: {cid}\n'
    await update.message.reply_text(text)


async def admin_addmovie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # این دستور فرض می‌کند مدیر ابتدا فیلم را به ربات فوروارد کرده یا به کانال آرشیو فوروارد کرده است.
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text('فقط مدیر اجازهٔ این کار را دارد.')
        return

    # راهنمایی برای روش ساده: مدیر یک پیام شامل عنوان و توضیحات می‌فرستد و به آن مدیا پاسخ می‌دهد
    if update.message.reply_to_message and (update.message.reply_to_message.video or update.message.reply_to_message.document):
        # مدیر روی پیام ویدیویی یا سند ربات reply می‌کند و در متن عنوان|توضیحات را می‌نویسد
        media_msg = update.message.reply_to_message
        caption_text = update.message.text or ''
        if caption_text.startswith('/addmovie'):
            caption_text = caption_text[len('/addmovie'):].strip()
        parts = caption_text.split('|', 1)
        title = parts[0].strip() if parts else 'بدون عنوان'
        description = parts[1].strip() if len(parts) > 1 else ''

        # فایل آی‌دی از پیام مرجع
        if media_msg.video:
            file_id = media_msg.video.file_id
        else:
            file_id = media_msg.document.file_id
        poster_id = None
        if media_msg.photo:
            poster_id = media_msg.photo[-1].file_id
        # ذخیره در دیتابیس
        now = datetime.utcnow().isoformat()
        await db_execute('INSERT INTO movies (title, description, poster_file_id, video_file_id, created_at) VALUES (?,?,?,?,?)', (title, description, poster_id, file_id, now))
        await update.message.reply_text('فیلم ثبت شد.')
        return

    await update.message.reply_text('برای اضافه کردن فیلم: پیام ویدیویی را به ربات فوروارد کنید، سپس روی پیام ویدیویی در کانال یا چتِ ربات reply کنید و دستور /addmovie را همراه با متن "عنوان | توضیحات" ارسال کنید.')


async def admin_listmovies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text('فقط مدیر اجازهٔ این کار را دارد.')
        return
    rows = await db_execute('SELECT id, title FROM movies ORDER BY id DESC', fetch=True)
    if not rows:
        await update.message.reply_text('هیچ فیلمی ثبت نشده است.')
        return
    text = 'فیلم‌های ثبت‌شده:\n'
    for mid, title in rows:
        text += f'- {mid}: {title} (deep link: t.me/{context.bot.username}?start=movie_{mid})\n'
    await update.message.reply_text(text)

# --------- راه‌اندازی اپلیکیشن ---------

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('دستور نامشخص. از دکمه‌های کانال استفاده کنید یا /help را ببینید.')


def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler('start', start_handler))
    app.add_handler(CallbackQueryHandler(callback_check_members, pattern=r'^check_members_'))
    app.add_handler(CallbackQueryHandler(callback_check_view, pattern=r'^check_view_'))

    # admin
    app.add_handler(CommandHandler('addchannel', admin_addchannel))
    app.add_handler(CommandHandler('listchannels', admin_listchannels))
    app.add_handler(CommandHandler('addmovie', admin_addmovie))
    app.add_handler(CommandHandler('listmovies', admin_listmovies))

    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    logger.info('Starting bot...')
    app.run_polling()


if __name__ == '__main__':
    main()
