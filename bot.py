#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════╗
# ║       🎬 بوت التحميل الاحترافي - النسخة الكاملة         ║
# ║  يدعم: YouTube • TikTok • Instagram • Twitter • وأكثر   ║
# ╚══════════════════════════════════════════════════════════╝

import os, re, logging, asyncio, tempfile, shutil, json, time
from datetime import datetime
from pathlib import Path
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMember, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
import yt_dlp

# ══════════════════════════════════════════════════════
#                    ⚙️ الإعدادات
# ══════════════════════════════════════════════════════

BOT_TOKEN    = os.environ.get("BOT_TOKEN", "ضع_توكنك_هنا")
ADMIN_ID     = int(os.environ.get("ADMIN_ID", "123456789"))
CHANNEL_ID   = os.environ.get("CHANNEL_ID", "@اسم_قناتك")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/اسم_قناتك")
SMARTLINK    = os.environ.get("SMARTLINK", "https://www.effectivegatecpm.com/key=YOUR_KEY")

MAX_FILE_MB  = 50
DB_FILE      = "data.json"
DOWNLOAD_DIR = tempfile.mkdtemp()

# ══════════════════════════════════════════════════════
#                  🎨 رسائل البوت
# ══════════════════════════════════════════════════════

MSG = {
"start": """
🎬 *أهلاً بك في بوت التحميل الاحترافي!*

أنا أستطيع تحميل الفيديو والصوت من أكثر من *1000 موقع* بضغطة واحدة!

🌍 *المواقع المدعومة:*
▸ YouTube & YouTube Shorts
▸ TikTok & Instagram Reels
▸ Twitter/X & Facebook
▸ SoundCloud & Spotify
▸ Vimeo & Dailymotion
▸ Reddit & Pinterest
▸ وأكثر من 1000 موقع آخر!

📌 *فقط أرسل الرابط وأنا أتكفل بالباقي!*
""",

"not_subscribed": """
⛔️ *عذراً! يجب الاشتراك أولاً*

للاستمرار في استخدام البوت يجب:
✅ الاشتراك في قناتنا

بعد الاشتراك اضغط *تحققت* ✅
""",

"subscribed":  "✅ *شكراً! تم التحقق من اشتراكك*\n\nأرسل الرابط الآن 👇",
"checking":    "🔍 *جاري فحص الرابط...*",
"invalid_url": "❌ أرسل رابطاً صحيحاً يبدأ بـ `https://`",

"downloading": (
    "⬇️ *جاري التحميل...*\n"
    "📌 {title}\n"
    "📊 الجودة: {quality}\n\n"
    "⏳ يرجى الانتظار..."
),

"uploading": "📤 *جاري الرفع...*\n📦 الحجم: {size}",
"done":      "✅ *اكتمل التحميل!*\n📌 {title}",

"too_big": (
    "❌ *الملف كبير جداً!*\n\n"
    "📦 الحجم: {size}\n"
    "⚠️ الحد المسموح: 50MB\n\n"
    "💡 *الحلول:*\n"
    "▸ جرب جودة أقل (480p أو 360p)\n"
    "▸ أو حمّل الصوت فقط (MP3)"
),

"yt_blocked": (
    "⚠️ *يوتيوب يمنع التحميل مؤقتاً*\n\n"
    "💡 *الحلول:*\n"
    "▸ انتظر دقيقتين وأعد المحاولة\n"
    "▸ جرب رابط من TikTok أو Instagram\n\n"
    "🔄 *البوت سيحاول تلقائياً بطريقة أخرى...*"
),

"private_video":  "🔒 *الفيديو خاص ولا يمكن تحميله*",
"unavailable":    "❌ *الفيديو غير متاح أو تم حذفه*",
"copyright":      "❌ *الفيديو محمي بحقوق الملكية*",
"flood":          "⏳ *انتظر لحظة!*\n\nأرسل طلباً واحداً كل 5 ثوانٍ.",
"session_expired":"❌ *انتهت الجلسة*\n\nأرسل الرابط مرة أخرى",
"cancelled":      "❌ *تم الإلغاء*",

"error": "❌ *حدث خطأ:*\n`{error}`\n\n🔄 حاول مرة أخرى",

"ad": (
    "━━━━━━━━━━━━━━━━━━━\n"
    "⚡️ *هل أعجبك البوت؟*\n"
    "👉 [اضغط هنا لدعمنا]({link})\n"
    "━━━━━━━━━━━━━━━━━━━"
),
}

# ══════════════════════════════════════════════════════
#              🔧 خيارات yt-dlp الاحترافية
# ══════════════════════════════════════════════════════

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

def get_base_opts(ua_index: int = 0) -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "http_headers": {
            "User-Agent": USER_AGENTS[ua_index % len(USER_AGENTS)],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "DNT": "1",
            "Connection": "keep-alive",
        },
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web", "ios"],
                "player_skip": ["webpage"],
            },
        },
        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 30,
    }

FORMATS = {
    "video": {
        "best":   "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[height<=1080]/best",
        "high":   "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[height<=720]/best",
        "medium": "bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/best[height<=480]/best",
        "low":    "bestvideo[ext=mp4][height<=360]+bestaudio[ext=m4a]/best[height<=360]/best",
    },
    "audio": {
        "best": "bestaudio[ext=m4a]/bestaudio/best",
    }
}

def get_info(url: str) -> dict:
    errors = []
    for i in range(len(USER_AGENTS)):
        try:
            opts = {**get_base_opts(i), "extract_flat": False}
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as e:
            errors.append(str(e))
            time.sleep(1)
    raise Exception(errors[-1])

def download_media(url: str, mode: str, quality: str, out_dir: str) -> str:
    tpl = os.path.join(out_dir, "%(title).60s.%(ext)s")
    errors = []

    for attempt in range(len(USER_AGENTS)):
        try:
            base = get_base_opts(attempt)
            if mode == "audio":
                opts = {
                    **base,
                    "format": FORMATS["audio"]["best"],
                    "outtmpl": tpl,
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }],
                }
            else:
                opts = {
                    **base,
                    "format": FORMATS["video"].get(quality, FORMATS["video"]["best"]),
                    "outtmpl": tpl,
                    "merge_output_format": "mp4",
                }

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                fname = ydl.prepare_filename(info)

            if mode == "audio":
                mp3 = Path(fname).with_suffix(".mp3")
                if mp3.exists():
                    return str(mp3)

            files = [f for f in Path(out_dir).iterdir() if f.is_file()]
            if files:
                return str(max(files, key=lambda f: f.stat().st_size))

        except Exception as e:
            errors.append(f"#{attempt+1}: {str(e)}")
            time.sleep(2)

    raise Exception(errors[-1] if errors else "فشل التحميل")

# ══════════════════════════════════════════════════════
#                 📦 قاعدة البيانات
# ══════════════════════════════════════════════════════

def load_db() -> dict:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}, "total_downloads": 0}

def save_db(data: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def register_user(user) -> bool:
    db = load_db()
    uid = str(user.id)
    is_new = uid not in db["users"]
    if is_new:
        db["users"][uid] = {
            "name": user.full_name,
            "username": user.username or "",
            "joined": datetime.now().strftime("%Y-%m-%d"),
            "downloads": 0,
        }
    db["users"][uid]["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_db(db)
    return is_new

def add_download(uid: int):
    db = load_db()
    if str(uid) in db["users"]:
        db["users"][str(uid)]["downloads"] += 1
    db["total_downloads"] = db.get("total_downloads", 0) + 1
    save_db(db)

# ══════════════════════════════════════════════════════
#              🔒 نظام الاشتراك الإجباري
# ══════════════════════════════════════════════════════

async def is_subscribed(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in [
            ChatMember.MEMBER,
            ChatMember.ADMINISTRATOR,
            ChatMember.OWNER,
        ]
    except Exception:
        return True

async def sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📢 اشترك الآن", url=CHANNEL_LINK),
        InlineKeyboardButton("✅ تحققت", callback_data="check_sub"),
    ]])

# ══════════════════════════════════════════════════════
#                 🛠️ مساعدات
# ══════════════════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
user_last_request: dict = {}

def is_flooding(user_id: int) -> bool:
    now = time.time()
    if now - user_last_request.get(user_id, 0) < 5:
        return True
    user_last_request[user_id] = now
    return False

def extract_url(text: str):
    m = URL_PATTERN.search(text)
    return m.group(0) if m else None

def human_size(b: int) -> str:
    for u in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def classify_error(err: str) -> str:
    e = err.lower()
    if any(x in e for x in ["sign in", "confirm", "bot detection"]):
        return "yt_blocked"
    if any(x in e for x in ["private video", "private"]):
        return "private"
    if any(x in e for x in ["not available", "unavailable", "removed", "deleted"]):
        return "unavailable"
    if "copyright" in e:
        return "copyright"
    return "unknown"

def quality_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 1080p HD", callback_data="video|best"),
            InlineKeyboardButton("🎬 720p",     callback_data="video|high"),
        ],
        [
            InlineKeyboardButton("🎬 480p",     callback_data="video|medium"),
            InlineKeyboardButton("🎬 360p",     callback_data="video|low"),
        ],
        [
            InlineKeyboardButton("🎵 صوت MP3 192kbps", callback_data="audio|best"),
        ],
        [
            InlineKeyboardButton("❌ إلغاء", callback_data="cancel"),
        ],
    ])

# ══════════════════════════════════════════════════════
#                  📋 الأوامر
# ══════════════════════════════════════════════════════

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = register_user(user)

    if not await is_subscribed(ctx.bot, user.id):
        await update.message.reply_text(
            MSG["not_subscribed"], parse_mode="Markdown",
            reply_markup=await sub_keyboard()
        )
        return

    greeting = (
        f"🎉 *أهلاً بك للمرة الأولى {user.first_name}!*\n"
        if is_new else
        f"👋 *مرحباً مجدداً {user.first_name}!*\n"
    )
    await update.message.reply_text(
        greeting + MSG["start"],
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📢 قناتنا", url=CHANNEL_LINK),
            InlineKeyboardButton("❓ مساعدة", callback_data="show_help"),
        ]])
    )

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *دليل الاستخدام*\n\n"
        "1️⃣ أرسل رابط الفيديو أو الصوت\n"
        "2️⃣ اختر الجودة المناسبة\n"
        "3️⃣ انتظر وسيصلك الملف! ✅\n\n"
        "📌 *الأوامر:*\n"
        "/start — 🏠 الرئيسية\n"
        "/help  — 📖 المساعدة\n"
        "/stats — 📊 إحصائياتك\n\n"
        "⚠️ *ملاحظات:*\n"
        "▸ الحجم الأقصى: 50MB\n"
        "▸ الصيغ: MP4 • MP3\n"
        "▸ انتظر 5 ثوانٍ بين كل طلب\n"
        "▸ يوتيوب قد يُبطئ التحميل أحياناً",
        parse_mode="Markdown"
    )

async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = load_db()
    info = db["users"].get(str(user.id), {})
    await update.message.reply_text(
        f"📊 *إحصائياتك*\n\n"
        f"👤 {info.get('name', user.full_name)}\n"
        f"📅 انضممت: {info.get('joined', '—')}\n"
        f"📥 تحميلاتك: {info.get('downloads', 0)}\n\n"
        f"━━━━━━━━━━━━━\n"
        f"👥 إجمالي المستخدمين: {len(db['users'])}\n"
        f"📦 إجمالي التحميلات: {db.get('total_downloads', 0)}",
        parse_mode="Markdown"
    )

async def admin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    db = load_db()
    today = datetime.now().strftime("%Y-%m-%d")
    new_today = sum(1 for u in db["users"].values() if u.get("joined") == today)
    await update.message.reply_text(
        f"👑 *لوحة الأدمن*\n\n"
        f"👥 المستخدمون: {len(db['users'])}\n"
        f"🆕 انضموا اليوم: {new_today}\n"
        f"📥 التحميلات: {db.get('total_downloads', 0)}\n\n"
        f"📢 لإرسال رسالة للجميع:\n"
        f"`/broadcast رسالتك هنا`",
        parse_mode="Markdown"
    )

async def broadcast_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not ctx.args:
        await update.message.reply_text(
            "📢 استخدم:\n`/broadcast رسالتك هنا`",
            parse_mode="Markdown"
        )
        return
    msg_text = " ".join(ctx.args)
    db = load_db()
    users = list(db["users"].keys())
    status = await update.message.reply_text(f"📤 جاري الإرسال لـ {len(users)} مستخدم...")
    ok = fail = 0
    for uid in users:
        try:
            await ctx.bot.send_message(
                int(uid),
                f"📢 *رسالة من الأدمن*\n\n{msg_text}",
                parse_mode="Markdown"
            )
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.04)
    await status.edit_text(
        f"✅ *اكتمل*\n✅ نجح: {ok}\n❌ فشل: {fail}",
        parse_mode="Markdown"
    )

# ══════════════════════════════════════════════════════
#               🔗 معالجة الروابط
# ══════════════════════════════════════════════════════

async def handle_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)

    if not await is_subscribed(ctx.bot, user.id):
        await update.message.reply_text(
            MSG["not_subscribed"], parse_mode="Markdown",
            reply_markup=await sub_keyboard()
        )
        return

    if is_flooding(user.id):
        await update.message.reply_text(MSG["flood"], parse_mode="Markdown")
        return

    url = extract_url(update.message.text or "")
    if not url:
        await update.message.reply_text(MSG["invalid_url"], parse_mode="Markdown")
        return

    msg = await update.message.reply_text(MSG["checking"], parse_mode="Markdown")
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, get_info, url)

        title    = info.get("title", "")[:60]
        uploader = info.get("uploader") or info.get("channel") or "—"
        duration = int(info.get("duration") or 0)
        views    = info.get("view_count") or 0
        mins, secs = divmod(duration, 60)
        hrs, mins  = divmod(mins, 60)

        dur_str   = f"{hrs}:{mins:02d}:{secs:02d}" if hrs else f"{mins}:{secs:02d}"
        views_str = f"{views:,}" if views else "—"

        ctx.user_data["url"]   = url
        ctx.user_data["title"] = title

        await msg.edit_text(
            f"✅ *تم العثور على المحتوى!*\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📌 *{title}*\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 {uploader}\n"
            f"⏱ المدة: `{dur_str}`\n"
            f"👁 المشاهدات: `{views_str}`\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🎯 *اختر الجودة:*",
            parse_mode="Markdown",
            reply_markup=quality_keyboard()
        )
    except Exception as e:
        t = classify_error(str(e))
        await msg.edit_text(MSG.get(t, MSG["error"].format(error=str(e)[:200])), parse_mode="Markdown")

# ══════════════════════════════════════════════════════
#               ⚙️ معالجة الأزرار
# ══════════════════════════════════════════════════════

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "check_sub":
        if await is_subscribed(ctx.bot, query.from_user.id):
            await query.edit_message_text(MSG["subscribed"], parse_mode="Markdown")
        else:
            await query.answer("❌ لم تشترك بعد!", show_alert=True)
        return

    if data == "show_help":
        await query.edit_message_text(
            "📖 *المساعدة*\n\nأرسل أي رابط فيديو وسأحمله لك!\n\n"
            "▸ YouTube • TikTok • Instagram • Twitter\n"
            "▸ Facebook • SoundCloud • وأكثر!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="back_start")
            ]])
        )
        return

    if data == "cancel":
        await query.edit_message_text(MSG["cancelled"], parse_mode="Markdown")
        return

    if "|" not in data:
        return

    mode, quality = data.split("|")
    url   = ctx.user_data.get("url")
    title = ctx.user_data.get("title", "الملف")

    if not url:
        await query.edit_message_text(MSG["session_expired"], parse_mode="Markdown")
        return

    ql = {"best": "1080p HD", "high": "720p", "medium": "480p", "low": "360p"}.get(quality, quality)
    q_label = "MP3 192kbps" if mode == "audio" else ql

    await query.edit_message_text(
        MSG["downloading"].format(title=title, quality=q_label),
        parse_mode="Markdown"
    )

    tmp = tempfile.mkdtemp(dir=DOWNLOAD_DIR)
    try:
        loop = asyncio.get_event_loop()
        path = await loop.run_in_executor(None, download_media, url, mode, quality, tmp)

        size_bytes = os.path.getsize(path)
        if size_bytes / 1024 / 1024 > MAX_FILE_MB:
            await query.edit_message_text(
                MSG["too_big"].format(size=human_size(size_bytes)),
                parse_mode="Markdown"
            )
            return

        await query.edit_message_text(
            MSG["uploading"].format(size=human_size(size_bytes)),
            parse_mode="Markdown"
        )

        chat_id = query.message.chat_id
        emoji   = "🎵" if mode == "audio" else "🎬"
        caption = f"{emoji} *{title}*\n\n🤖 @{ctx.bot.username}"

        with open(path, "rb") as f:
            if mode == "audio":
                await ctx.bot.send_audio(
                    chat_id=chat_id, audio=f,
                    title=title[:60], caption=caption,
                    parse_mode="Markdown",
                    read_timeout=120, write_timeout=120, connect_timeout=60,
                )
            else:
                await ctx.bot.send_video(
                    chat_id=chat_id, video=f,
                    caption=caption, parse_mode="Markdown",
                    supports_streaming=True,
                    read_timeout=120, write_timeout=120, connect_timeout=60,
                )

        add_download(query.from_user.id)

        # 💰 إعلان Smartlink
        await ctx.bot.send_message(
            chat_id=chat_id,
            text=MSG["ad"].format(link=SMARTLINK),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⚡️ اضغط هنا", url=SMARTLINK)
            ]])
        )

        await query.edit_message_text(
            MSG["done"].format(title=title), parse_mode="Markdown"
        )

    except Exception as e:
        t = classify_error(str(e))
        await query.edit_message_text(
            MSG.get(t, MSG["error"].format(error=str(e)[:200])),
            parse_mode="Markdown"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# ══════════════════════════════════════════════════════
#                   🚀 التشغيل
# ══════════════════════════════════════════════════════

async def on_startup(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start",     "🏠 الرئيسية"),
        BotCommand("help",      "📖 المساعدة"),
        BotCommand("stats",     "📊 الإحصائيات"),
        BotCommand("admin",     "👑 لوحة الأدمن"),
        BotCommand("broadcast", "📢 إرسال للجميع"),
    ])
    logger.info("✅ البوت جاهز!")

def main():
    print("━━━━━━━━━━━━━━━━━━━━━━━")
    print("  🎬 بوت التحميل الاحترافي")
    print("━━━━━━━━━━━━━━━━━━━━━━━")
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(on_startup)
        .build()
    )
    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("help",      help_cmd))
    app.add_handler(CommandHandler("stats",     stats_cmd))
    app.add_handler(CommandHandler("admin",     admin_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("✅ البوت شغّال الآن!")
    print("━━━━━━━━━━━━━━━━━━━━━━━")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
