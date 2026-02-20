#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════╗
# ║     🎬 بوت التحميل الاحترافي - النسخة النهائية           ║
# ║  ✅ يحل مشكلة يوتيوب عبر Cookies                         ║
# ║  ✅ رابط الإعلان إجباري قبل التحميل                       ║
# ╚══════════════════════════════════════════════════════════╝

import os, re, logging, asyncio, tempfile, shutil, json, time, uuid, httpx
from datetime import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import yt_dlp

# ══════════════════════════════════════════════════════
#                    ⚙️ الإعدادات
# ══════════════════════════════════════════════════════

BOT_TOKEN    = os.environ.get("BOT_TOKEN", "8187868264:AAEnxSh8kgXxMkfaVZPqovmyMRb2i9LP6Bg")
ADMIN_ID     = int(os.environ.get("ADMIN_ID", "7935901153"))
CHANNEL_ID   = os.environ.get("CHANNEL_ID", "@Video_Grabber")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/Video_Grabber")
SMARTLINK    = os.environ.get("SMARTLINK", "https://www.effectivegatecpm.com/awzbbi353?key=16d6ee5ad7058950ed0a6c70dec83b95")

# ⏰ ثواني الانتظار الإجباري بعد الضغط على رابط الإعلان
AD_WAIT_SECONDS = 15

MAX_FILE_MB  = 50
DB_FILE      = "data.json"
COOKIES_FILE = "cookies.txt"   # ← ارفع هذا الملف مع البوت لحل مشكلة يوتيوب
DOWNLOAD_DIR = tempfile.mkdtemp()

# ══════════════════════════════════════════════════════
#              📦 قاعدة البيانات
# ══════════════════════════════════════════════════════

def load_db() -> dict:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}, "total_downloads": 0, "ad_clicks": {}}

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

# تخزين حالة الإعلان لكل مستخدم في الميموري
# {user_id: {"token": str, "clicked_at": float, "url": str, "title": str}}
ad_state: dict = {}

# ══════════════════════════════════════════════════════
#          🔧 خيارات yt-dlp مع دعم Cookies
# ══════════════════════════════════════════════════════

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/120.0.6099.230 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Version/17.2 Mobile Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
]

def get_base_opts(ua: int = 0) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "http_headers": {
            "User-Agent": USER_AGENTS[ua % len(USER_AGENTS)],
            "Accept-Language": "en-US,en;q=0.9",
        },
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web", "ios"],
                "player_skip": ["webpage"],
            }
        },
        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 30,
    }
    # ✅ الحل الرئيسي لمشكلة يوتيوب: استخدام cookies
    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    return opts

FORMATS = {
    "video": {
        "best":   "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[height<=1080]/best",
        "high":   "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[height<=720]/best",
        "medium": "bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/best[height<=480]/best",
        "low":    "bestvideo[ext=mp4][height<=360]+bestaudio[ext=m4a]/best[height<=360]/best",
    },
    "audio": "bestaudio[ext=m4a]/bestaudio/best",
}

def get_info(url: str) -> dict:
    for i in range(len(USER_AGENTS)):
        try:
            with yt_dlp.YoutubeDL({**get_base_opts(i), "extract_flat": False}) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as e:
            if i == len(USER_AGENTS) - 1:
                raise
            time.sleep(1)

def download_media(url: str, mode: str, quality: str, out_dir: str) -> str:
    tpl = os.path.join(out_dir, "%(title).60s.%(ext)s")
    last_error = None

    for attempt in range(len(USER_AGENTS)):
        try:
            base = get_base_opts(attempt)
            if mode == "audio":
                opts = {
                    **base, "format": FORMATS["audio"],
                    "outtmpl": tpl,
                    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
                }
            else:
                opts = {
                    **base,
                    "format": FORMATS["video"].get(quality, FORMATS["video"]["best"]),
                    "outtmpl": tpl, "merge_output_format": "mp4",
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
            last_error = e
            time.sleep(2)

    raise Exception(str(last_error))

# ══════════════════════════════════════════════════════
#            🔒 نظام الاشتراك الإجباري
# ══════════════════════════════════════════════════════

async def is_subscribed(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except Exception:
        return True

# ══════════════════════════════════════════════════════
#           💰 نظام الإعلان الإجباري
# ══════════════════════════════════════════════════════

def create_ad_token(user_id: int, url: str, title: str) -> str:
    """إنشاء token فريد لكل طلب تحميل"""
    token = str(uuid.uuid4())[:8].upper()
    ad_state[user_id] = {
        "token": token,
        "clicked_at": None,  # لم يضغط بعد
        "url": url,
        "title": title,
        "mode": None,
        "quality": None,
    }
    return token

def mark_ad_clicked(user_id: int):
    """تسجيل وقت ضغط المستخدم على الإعلان"""
    if user_id in ad_state:
        ad_state[user_id]["clicked_at"] = time.time()

def can_download(user_id: int) -> tuple[bool, int]:
    """
    هل يمكن للمستخدم التحميل؟
    يرجع: (يمكن_التحميل, ثواني_المتبقية)
    """
    state = ad_state.get(user_id)
    if not state or state["clicked_at"] is None:
        return False, AD_WAIT_SECONDS
    elapsed = time.time() - state["clicked_at"]
    remaining = AD_WAIT_SECONDS - elapsed
    if remaining > 0:
        return False, int(remaining) + 1
    return True, 0

# ══════════════════════════════════════════════════════
#                 🛠️ مساعدات
# ══════════════════════════════════════════════════════

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
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
    if any(x in e for x in ["sign in", "confirm", "bot detection", "login_required"]):
        return "yt_blocked"
    if "private" in e:
        return "private"
    if any(x in e for x in ["not available", "unavailable", "removed", "deleted"]):
        return "unavailable"
    if "copyright" in e:
        return "copyright"
    if "too large" in e or "filesize" in e:
        return "too_large"
    return "unknown"

def quality_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 1080p HD", callback_data="q|video|best"),
         InlineKeyboardButton("🎬 720p",     callback_data="q|video|high")],
        [InlineKeyboardButton("🎬 480p",     callback_data="q|video|medium"),
         InlineKeyboardButton("🎬 360p",     callback_data="q|video|low")],
        [InlineKeyboardButton("🎵 صوت MP3",  callback_data="q|audio|best")],
        [InlineKeyboardButton("❌ إلغاء",    callback_data="cancel")],
    ])

def ad_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👆 اضغط هنا أولاً", url=SMARTLINK)],
        [InlineKeyboardButton(f"✅ ضغطت، تحقق بعد {AD_WAIT_SECONDS} ثانية", callback_data="ad_verify")],
    ])

# ══════════════════════════════════════════════════════
#                  📋 الأوامر
# ══════════════════════════════════════════════════════

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = register_user(user)

    if not await is_subscribed(ctx.bot, user.id):
        await update.message.reply_text(
            "⛔️ *يجب الاشتراك في قناتنا أولاً!*\n\nبعد الاشتراك اضغط تحققت ✅",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📢 اشترك", url=CHANNEL_LINK),
                InlineKeyboardButton("✅ تحققت", callback_data="check_sub"),
            ]])
        )
        return

    greeting = f"🎉 *أهلاً بك {user.first_name}!*\n" if is_new else f"👋 *مرحباً {user.first_name}!*\n"
    await update.message.reply_text(
        greeting +
        "\n🎬 *بوت التحميل الاحترافي*\n\n"
        "📌 أرسل أي رابط فيديو أو صوت!\n\n"
        "🌍 *يدعم 1000+ موقع:*\n"
        "▸ YouTube • TikTok • Instagram\n"
        "▸ Twitter/X • Facebook • SoundCloud\n"
        "▸ Vimeo • Reddit • وأكثر!\n\n"
        "⬇️ *أرسل الرابط الآن*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📢 قناتنا", url=CHANNEL_LINK),
            InlineKeyboardButton("❓ مساعدة", callback_data="show_help"),
        ]])
    )

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *دليل الاستخدام*\n\n"
        "1️⃣ أرسل رابط الفيديو\n"
        "2️⃣ اضغط على رابط الإعلان *(إجباري)*\n"
        "3️⃣ انتظر 15 ثانية\n"
        "4️⃣ اضغط تحقق واختر الجودة\n"
        "5️⃣ استلم الملف! ✅\n\n"
        "⚠️ *ملاحظات:*\n"
        "▸ الحجم الأقصى: 50MB\n"
        "▸ يوتيوب: ارفع `cookies.txt` للأدمن\n"
        "▸ انتظر 5 ثوانٍ بين كل طلب",
        parse_mode="Markdown"
    )

async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    info = db["users"].get(str(update.effective_user.id), {})
    await update.message.reply_text(
        f"📊 *إحصائياتك*\n\n"
        f"📅 انضممت: {info.get('joined','—')}\n"
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
    has_cookies = "✅ موجود" if os.path.exists(COOKIES_FILE) else "❌ غير موجود (يوتيوب لن يعمل)"
    await update.message.reply_text(
        f"👑 *لوحة الأدمن*\n\n"
        f"👥 المستخدمون: {len(db['users'])}\n"
        f"🆕 اليوم: {new_today}\n"
        f"📥 التحميلات: {db.get('total_downloads', 0)}\n"
        f"🍪 cookies.txt: {has_cookies}\n\n"
        f"📢 لإرسال رسالة:\n`/broadcast رسالتك`",
        parse_mode="Markdown"
    )

async def broadcast_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not ctx.args:
        await update.message.reply_text("استخدم: `/broadcast رسالتك`", parse_mode="Markdown")
        return
    msg_text = " ".join(ctx.args)
    db = load_db()
    ok = fail = 0
    status = await update.message.reply_text(f"📤 جاري الإرسال لـ {len(db['users'])} مستخدم...")
    for uid in db["users"]:
        try:
            await ctx.bot.send_message(int(uid), f"📢 *إعلان*\n\n{msg_text}", parse_mode="Markdown")
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.04)
    await status.edit_text(f"✅ نجح: {ok} | ❌ فشل: {fail}", parse_mode="Markdown")

# ══════════════════════════════════════════════════════
#               🔗 معالجة الروابط
# ══════════════════════════════════════════════════════

async def handle_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)

    if not await is_subscribed(ctx.bot, user.id):
        await update.message.reply_text(
            "⛔️ *يجب الاشتراك أولاً!*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📢 اشترك", url=CHANNEL_LINK),
                InlineKeyboardButton("✅ تحققت", callback_data="check_sub"),
            ]])
        )
        return

    if is_flooding(user.id):
        await update.message.reply_text("⏳ انتظر 5 ثوانٍ بين كل طلب!", parse_mode="Markdown")
        return

    url = extract_url(update.message.text or "")
    if not url:
        await update.message.reply_text("❌ أرسل رابطاً صحيحاً يبدأ بـ `https://`", parse_mode="Markdown")
        return

    msg = await update.message.reply_text("🔍 *جاري فحص الرابط...*", parse_mode="Markdown")
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, get_info, url)

        title    = info.get("title", "")[:60]
        uploader = info.get("uploader") or info.get("channel") or "—"
        duration = int(info.get("duration") or 0)
        views    = info.get("view_count") or 0
        mins, secs = divmod(duration, 60)
        hrs,  mins = divmod(mins, 60)

        dur_str   = f"{hrs}:{mins:02d}:{secs:02d}" if hrs else f"{mins}:{secs:02d}"
        views_str = f"{views:,}" if views else "—"

        # ✅ إنشاء token للإعلان الإجباري
        create_ad_token(user.id, url, title)

        # ⚠️ الإعلان الإجباري قبل اختيار الجودة
        await msg.edit_text(
            f"✅ *تم العثور على المحتوى!*\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📌 *{title}*\n"
            f"👤 {uploader}\n"
            f"⏱ `{dur_str}` | 👁 `{views_str}`\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ *خطوة إجبارية:*\n"
            f"1️⃣ اضغط على الرابط أدناه\n"
            f"2️⃣ انتظر {AD_WAIT_SECONDS} ثانية\n"
            f"3️⃣ اضغط *تحقق* للمتابعة",
            parse_mode="Markdown",
            reply_markup=ad_keyboard()
        )

    except Exception as e:
        err_type = classify_error(str(e))
        msgs = {
            "yt_blocked": (
                "⚠️ *يوتيوب يمنع التحميل*\n\n"
                "💡 *الحل:* أرسل ملف `cookies.txt` للأدمن\n"
                "أو جرب رابط من: TikTok • Instagram • Twitter"
            ),
            "private":    "🔒 *الفيديو خاص ولا يمكن تحميله*",
            "unavailable":"❌ *الفيديو غير متاح أو تم حذفه*",
            "copyright":  "❌ *الفيديو محمي بحقوق الملكية*",
        }
        await msg.edit_text(
            msgs.get(err_type, f"❌ خطأ: `{str(e)[:200]}`"),
            parse_mode="Markdown"
        )

# ══════════════════════════════════════════════════════
#               ⚙️ معالجة الأزرار
# ══════════════════════════════════════════════════════

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # ─── اشتراك ───
    if data == "check_sub":
        if await is_subscribed(ctx.bot, user_id):
            await query.edit_message_text("✅ *تم التحقق!*\n\nأرسل الرابط الآن 👇", parse_mode="Markdown")
        else:
            await query.answer("❌ لم تشترك بعد!", show_alert=True)
        return

    # ─── مساعدة ───
    if data == "show_help":
        await query.edit_message_text(
            "📖 *المساعدة*\n\nأرسل أي رابط فيديو وسأحمله!\n\n"
            "الخطوات:\n1️⃣ أرسل الرابط\n2️⃣ اضغط الإعلان\n"
            "3️⃣ انتظر 15 ثانية\n4️⃣ اضغط تحقق\n5️⃣ اختر الجودة ✅",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]])
        )
        return

    # ─── إلغاء ───
    if data == "cancel":
        ad_state.pop(user_id, None)
        await query.edit_message_text("❌ *تم الإلغاء*", parse_mode="Markdown")
        return

    # ─── التحقق من الإعلان ───
    if data == "ad_verify":
        state = ad_state.get(user_id)
        if not state:
            await query.answer("❌ انتهت الجلسة، أرسل الرابط مرة أخرى", show_alert=True)
            return

        # إذا لم يضغط بعد، سجّل الضغط الآن
        if state["clicked_at"] is None:
            mark_ad_clicked(user_id)
            await query.answer(f"⏳ انتظر {AD_WAIT_SECONDS} ثانية ثم اضغط تحقق مجدداً!", show_alert=True)
            return

        can_dl, remaining = can_download(user_id)
        if not can_dl:
            await query.answer(f"⏳ انتظر {remaining} ثانية أخرى!", show_alert=True)
            return

        # ✅ تم التحقق، أظهر اختيار الجودة
        title = state.get("title", "الملف")
        await query.edit_message_text(
            f"✅ *شكراً! اختر الجودة الآن:*\n\n📌 {title}",
            parse_mode="Markdown",
            reply_markup=quality_keyboard()
        )
        return

    # ─── اختيار الجودة والتحميل ───
    if data.startswith("q|"):
        _, mode, quality = data.split("|")
        state = ad_state.get(user_id)

        if not state:
            await query.edit_message_text("❌ انتهت الجلسة، أرسل الرابط مرة أخرى", parse_mode="Markdown")
            return

        url   = state["url"]
        title = state["title"]
        ql    = {"best": "1080p", "high": "720p", "medium": "480p", "low": "360p"}.get(quality, quality)
        emoji = "🎵" if mode == "audio" else "🎬"

        await query.edit_message_text(
            f"{emoji} *جاري التحميل...*\n"
            f"📌 {title}\n"
            f"📊 {'MP3' if mode == 'audio' else ql}\n\n"
            f"⏳ يرجى الانتظار...",
            parse_mode="Markdown"
        )

        tmp = tempfile.mkdtemp(dir=DOWNLOAD_DIR)
        try:
            loop = asyncio.get_event_loop()
            path = await loop.run_in_executor(None, download_media, url, mode, quality, tmp)

            size_bytes = os.path.getsize(path)
            if size_bytes / 1024 / 1024 > MAX_FILE_MB:
                await query.edit_message_text(
                    f"❌ *الملف كبير!*\n📦 {human_size(size_bytes)}\n💡 جرب جودة أقل",
                    parse_mode="Markdown"
                )
                return

            await query.edit_message_text(f"📤 *جاري الرفع..* {human_size(size_bytes)}", parse_mode="Markdown")

            chat_id = query.message.chat_id
            caption = f"{emoji} *{title}*\n\n🤖 @{ctx.bot.username}"

            with open(path, "rb") as f:
                if mode == "audio":
                    await ctx.bot.send_audio(
                        chat_id=chat_id, audio=f, title=title[:60],
                        caption=caption, parse_mode="Markdown",
                        read_timeout=120, write_timeout=120, connect_timeout=60,
                    )
                else:
                    await ctx.bot.send_video(
                        chat_id=chat_id, video=f,
                        caption=caption, parse_mode="Markdown",
                        supports_streaming=True,
                        read_timeout=120, write_timeout=120, connect_timeout=60,
                    )

            add_download(user_id)
            ad_state.pop(user_id, None)  # مسح الحالة بعد التحميل

            await query.edit_message_text(f"✅ *اكتمل التحميل!*\n📌 {title}", parse_mode="Markdown")

        except Exception as e:
            err_type = classify_error(str(e))
            msgs = {
                "yt_blocked": "⚠️ *يوتيوب يرفض التحميل*\n\nالحل: أرسل `cookies.txt` للأدمن",
                "private":    "🔒 الفيديو خاص",
                "unavailable":"❌ الفيديو غير متاح",
            }
            await query.edit_message_text(
                msgs.get(err_type, f"❌ فشل: `{str(e)[:200]}`"),
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
        BotCommand("stats",     "📊 إحصائياتك"),
        BotCommand("admin",     "👑 لوحة الأدمن"),
        BotCommand("broadcast", "📢 إرسال للجميع"),
    ])
    # تحقق من cookies.txt عند البدء
    if os.path.exists(COOKIES_FILE):
        logger.info("✅ cookies.txt موجود - يوتيوب سيعمل!")
    else:
        logger.warning("⚠️ cookies.txt غير موجود - يوتيوب قد لا يعمل!")

def main():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  🎬 بوت التحميل الاحترافي")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━")
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("help",      help_cmd))
    app.add_handler(CommandHandler("stats",     stats_cmd))
    app.add_handler(CommandHandler("admin",     admin_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("✅ البوت شغّال!")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
