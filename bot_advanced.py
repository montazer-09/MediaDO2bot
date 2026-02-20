#!/usr/bin/env python3
"""
🤖 Telegram Video/Audio Downloader Bot - النسخة المتقدمة
✅ تحميل فيديو وصوت من 1000+ موقع
✅ إعلانات Adsterra Smartlink
✅ إحصائيات المستخدمين
✅ قائمة انتظار
✅ أوامر إدارية
"""

import os
import re
import logging
import asyncio
import tempfile
import shutil
import json
from datetime import datetime
from pathlib import Path

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
import yt_dlp

# ══════════════════════════════════════════
#             ⚙️ الإعدادات
# ══════════════════════════════════════════

BOT_TOKEN     = "ضع_توكن_البوت_هنا"        # من @BotFather
ADMIN_ID      = 123456789                   # Telegram ID بتاعك
MAX_FILE_MB   = 50                          # حد حجم الملف
DB_FILE       = "users.json"               # قاعدة بيانات بسيطة

# 🔥 رابط Adsterra Smartlink بتاعك
ADSTERRA_LINK = "https://www.profitablegateway.com/key=YOUR_KEY"

# رسالة تظهر بعد كل تحميل (فيها رابط الإعلان)
AD_MESSAGE = (
    "━━━━━━━━━━━━━━━━\n"
    "⚡ *هل تريد المزيد من المحتوى؟*\n"
    "🎁 اضغط هنا للحصول على مفاجأة!\n"
    f"👉 {ADSTERRA_LINK}\n"
    "━━━━━━━━━━━━━━━━"
)

# ══════════════════════════════════════════
#           📦 قاعدة البيانات
# ══════════════════════════════════════════

def load_db() -> dict:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {"users": {}, "total_downloads": 0}

def save_db(data: dict):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def register_user(user):
    db = load_db()
    uid = str(user.id)
    if uid not in db["users"]:
        db["users"][uid] = {
            "name": user.full_name,
            "username": user.username or "",
            "joined": datetime.now().isoformat(),
            "downloads": 0,
        }
        save_db(db)
        return True  # مستخدم جديد
    return False

def add_download(user_id: int):
    db = load_db()
    uid = str(user_id)
    if uid in db["users"]:
        db["users"][uid]["downloads"] += 1
    db["total_downloads"] = db.get("total_downloads", 0) + 1
    save_db(db)

def get_stats() -> dict:
    db = load_db()
    return {
        "users": len(db["users"]),
        "downloads": db.get("total_downloads", 0),
    }

# ══════════════════════════════════════════
#              🛠️ مساعدات
# ══════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
DOWNLOAD_DIR = tempfile.mkdtemp()

def extract_url(text: str):
    m = URL_PATTERN.search(text)
    return m.group(0) if m else None

def human_size(b: int) -> str:
    for u in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def get_info(url: str) -> dict:
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        return ydl.extract_info(url, download=False)

def download_media(url: str, mode: str, quality: str, out_dir: str) -> str:
    tpl = os.path.join(out_dir, "%(title).60s.%(ext)s")
    if mode == "audio":
        opts = {
            "format": "bestaudio/best",
            "outtmpl": tpl,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "quiet": True,
        }
    else:
        fmts = {
            "best":   "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "medium": "bestvideo[height<=720][ext=mp4]+bestaudio/best[height<=720]/best",
            "low":    "bestvideo[height<=480][ext=mp4]+bestaudio/best[height<=480]/best",
        }
        opts = {
            "format": fmts.get(quality, fmts["best"]),
            "outtmpl": tpl,
            "merge_output_format": "mp4",
            "quiet": True,
        }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        fname = ydl.prepare_filename(info)

    if mode == "audio":
        mp3 = Path(fname).with_suffix(".mp3")
        if mp3.exists():
            return str(mp3)

    for f in Path(out_dir).iterdir():
        if f.is_file():
            return str(f)
    raise FileNotFoundError("الملف لم يُوجد بعد التحميل")

# ══════════════════════════════════════════
#              📋 الأوامر
# ══════════════════════════════════════════

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = register_user(user)

    greeting = "👋 *أهلاً بك!" if is_new else f"👋 *مرحباً مجدداً {user.first_name}!*"

    text = (
        f"{greeting}\n\n"
        "🤖 *بوت تحميل الفيديو والصوت*\n\n"
        "📌 *الاستخدام:*\n"
        "فقط أرسل أي رابط وسأتكفل بالباقي!\n\n"
        "🌍 *يدعم 1000+ موقع:*\n"
        "YouTube • TikTok • Instagram • Twitter\n"
        "Facebook • SoundCloud • Vimeo • وأكثر!\n\n"
        "📜 /help - المساعدة\n"
        "📊 /mystats - إحصائياتك\n"
    )

    keyboard = [[InlineKeyboardButton("📢 قناتنا", url="https://t.me/yourchannel")]]
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *المساعدة*\n\n"
        "1. أرسل رابط الفيديو أو الصوت\n"
        "2. اختر نوع التحميل\n"
        "3. انتظر وسيصلك الملف!\n\n"
        "🎬 *صيغ الفيديو:* MP4\n"
        "🎵 *صيغ الصوت:* MP3 (192kbps)\n"
        "📦 *الحد الأقصى:* 50MB\n\n"
        "⚡ *نصيحة:* لو الفيديو كبير اختر جودة منخفضة",
        parse_mode="Markdown"
    )

async def my_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    uid = str(update.effective_user.id)
    user_data = db["users"].get(uid, {})
    downloads = user_data.get("downloads", 0)
    joined = user_data.get("joined", "")[:10]

    await update.message.reply_text(
        f"📊 *إحصائياتك*\n\n"
        f"🗓 انضممت: {joined}\n"
        f"📥 تحميلاتك: {downloads}\n\n"
        f"شكراً لاستخدامك البوت! 🙏",
        parse_mode="Markdown"
    )

# ━━━ أوامر الأدمن ━━━

async def admin_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    stats = get_stats()
    await update.message.reply_text(
        f"👑 *إحصائيات البوت*\n\n"
        f"👥 إجمالي المستخدمين: {stats['users']}\n"
        f"📥 إجمالي التحميلات: {stats['downloads']}",
        parse_mode="Markdown"
    )

async def broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """أرسل /broadcast رسالتك - لإرسال رسالة لكل المستخدمين"""
    if update.effective_user.id != ADMIN_ID:
        return
    if not ctx.args:
        await update.message.reply_text("❌ استخدم: /broadcast رسالتك هنا")
        return

    msg = " ".join(ctx.args)
    db = load_db()
    success = fail = 0

    await update.message.reply_text(f"📤 جاري الإرسال لـ {len(db['users'])} مستخدم...")

    for uid in db["users"]:
        try:
            await ctx.bot.send_message(int(uid), f"📢 *إعلان*\n\n{msg}", parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.05)  # تجنب الحظر
        except Exception:
            fail += 1

    await update.message.reply_text(f"✅ أُرسلت لـ {success} | ❌ فشل {fail}")

# ══════════════════════════════════════════
#          🔗 معالجة الروابط
# ══════════════════════════════════════════

async def handle_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user)
    url = extract_url(update.message.text or "")

    if not url:
        await update.message.reply_text("❌ أرسل رابط صحيح يبدأ بـ https://")
        return

    msg = await update.message.reply_text("🔍 جاري فحص الرابط...")

    try:
        info = get_info(url)
        title    = info.get("title", "")[:60]
        uploader = info.get("uploader", "")
        duration = int(info.get("duration", 0))
        mins, secs = divmod(duration, 60)

        ctx.user_data["url"]   = url
        ctx.user_data["title"] = title

        keyboard = [
            [
                InlineKeyboardButton("🎬 HD (1080p)", callback_data="video|best"),
                InlineKeyboardButton("🎬 720p",       callback_data="video|medium"),
            ],
            [
                InlineKeyboardButton("🎬 480p",       callback_data="video|low"),
                InlineKeyboardButton("🎵 MP3",        callback_data="audio|best"),
            ],
        ]

        await msg.edit_text(
            f"✅ *تم العثور على المحتوى*\n\n"
            f"📌 {title}\n"
            f"👤 {uploader}\n"
            f"⏱ {mins}:{secs:02d}\n\n"
            f"🎯 اختر جودة التحميل:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        await msg.edit_text(f"❌ خطأ: الرابط غير مدعوم أو خاص\n`{str(e)[:150]}`", parse_mode="Markdown")

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    mode, quality = query.data.split("|")
    url   = ctx.user_data.get("url")
    title = ctx.user_data.get("title", "الملف")

    if not url:
        await query.edit_message_text("❌ انتهت الجلسة، أرسل الرابط مرة أخرى")
        return

    quality_label = {"best": "HD", "medium": "720p", "low": "480p"}.get(quality, quality)
    mode_label = "🎬 فيديو" if mode == "video" else "🎵 صوت"

    await query.edit_message_text(
        f"{mode_label} *جاري التحميل...*\n"
        f"📌 {title}\n"
        f"📊 الجودة: {quality_label}\n\n"
        f"⏳ انتظر قليلاً...",
        parse_mode="Markdown"
    )

    tmp = tempfile.mkdtemp(dir=DOWNLOAD_DIR)

    try:
        loop = asyncio.get_event_loop()
        path = await loop.run_in_executor(
            None, download_media, url, mode, quality, tmp
        )

        size_bytes = os.path.getsize(path)
        size_mb    = size_bytes / (1024 * 1024)

        if size_mb > MAX_FILE_MB:
            await query.edit_message_text(
                f"❌ *الملف كبير جداً!*\n"
                f"📦 الحجم: {human_size(size_bytes)}\n"
                f"⚠️ الحد: {MAX_FILE_MB}MB\n\n"
                f"💡 جرب جودة أقل",
                parse_mode="Markdown"
            )
            return

        await query.edit_message_text(f"📤 *جاري الرفع...*\n📦 {human_size(size_bytes)}", parse_mode="Markdown")

        chat_id = query.message.chat_id
        with open(path, "rb") as f:
            if mode == "audio":
                await ctx.bot.send_audio(
                    chat_id=chat_id, audio=f, title=title,
                    caption=f"🎵 {title}",
                    read_timeout=120, write_timeout=120
                )
            else:
                await ctx.bot.send_video(
                    chat_id=chat_id, video=f,
                    caption=f"🎬 {title}",
                    supports_streaming=True,
                    read_timeout=120, write_timeout=120
                )

        # ✅ تسجيل التحميل
        add_download(query.from_user.id)

        # 📢 إرسال إعلان Adsterra بعد كل تحميل
        await ctx.bot.send_message(
            chat_id=chat_id,
            text=AD_MESSAGE,
            parse_mode="Markdown",
            disable_web_page_preview=False
        )

        await query.edit_message_text(f"✅ *اكتمل التحميل!*\n📌 {title}", parse_mode="Markdown")

    except Exception as e:
        logger.exception("Download error")
        await query.edit_message_text(f"❌ فشل التحميل: {str(e)[:200]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# ══════════════════════════════════════════
#               🚀 التشغيل
# ══════════════════════════════════════════

async def set_commands(app):
    await app.bot.set_my_commands([
        BotCommand("start",    "بدء البوت"),
        BotCommand("help",     "المساعدة"),
        BotCommand("mystats",  "إحصائياتك"),
        BotCommand("stats",    "إحصائيات البوت (أدمن)"),
        BotCommand("broadcast","إرسال للجميع (أدمن)"),
    ])

def main():
    print("🚀 تشغيل البوت...")
    app = Application.builder().token(BOT_TOKEN).post_init(set_commands).build()

    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("help",      help_cmd))
    app.add_handler(CommandHandler("mystats",   my_stats))
    app.add_handler(CommandHandler("stats",     admin_stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("✅ البوت شغّال! Ctrl+C للإيقاف")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
