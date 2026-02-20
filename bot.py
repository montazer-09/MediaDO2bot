#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════╗
# ║     🎬 بوت التحميل الاحترافي - نسخة مُصلحة              ║
# ║  ✅ يحل مشكلة يوتيوب نهائياً                             ║
# ╚══════════════════════════════════════════════════════════╝

import os, re, logging, asyncio, tempfile, shutil, json, time, uuid
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
AD_WAIT      = 15
MAX_FILE_MB  = 50
DB_FILE      = "data.json"
COOKIES_FILE = "cookies.txt"
DOWNLOAD_DIR = tempfile.mkdtemp()

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════
#         🔧 yt-dlp - كل الطرق الممكنة ليوتيوب
# ══════════════════════════════════════════════════════

def build_ydl_opts(mode: str, quality: str, out_dir: str = None) -> list[dict]:
    """
    يبني قائمة من الخيارات المختلفة للمحاولة بالترتيب.
    كل dict = طريقة مختلفة لتجاوز حماية يوتيوب.
    """
    tpl = os.path.join(out_dir, "%(title).60s.%(ext)s") if out_dir else None

    # الجزء المشترك في كل الخيارات
    def base(ua: str) -> dict:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "http_headers": {
                "User-Agent": ua,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            },
            "retries": 5,
            "fragment_retries": 5,
            "socket_timeout": 30,
        }
        if tpl:
            opts["outtmpl"] = tpl
        # ✅ إضافة cookies لو موجود
        if os.path.exists(COOKIES_FILE):
            opts["cookiefile"] = COOKIES_FILE
        return opts

    # صيغ الفيديو
    video_fmt = {
        "best":   "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "high":   "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[height<=720]/best",
        "medium": "bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/best[height<=480]/best",
        "low":    "bestvideo[ext=mp4][height<=360]+bestaudio[ext=m4a]/best[height<=360]/best",
    }.get(quality, "best")

    audio_pp = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]

    # ══ الطرق بالترتيب من الأقوى للأضعف ══

    # الطريقة 1: Android client (الأفضل لتجاوز الحماية)
    m1 = base("com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip")
    m1["extractor_args"] = {"youtube": {"player_client": ["android"], "player_skip": []}}

    # الطريقة 2: iOS client
    m2 = base("com.google.ios.youtube/19.09.3 (iPhone14,3; U; CPU iOS 15_6 like Mac OS X)")
    m2["extractor_args"] = {"youtube": {"player_client": ["ios"], "player_skip": []}}

    # الطريقة 3: TV Embedded client
    m3 = base("Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/538.1 (KHTML, like Gecko) Version/6.0 TV Safari/538.1")
    m3["extractor_args"] = {"youtube": {"player_client": ["tv_embedded"], "player_skip": ["webpage"]}}

    # الطريقة 4: Web Chrome عادي
    m4 = base("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")
    m4["extractor_args"] = {"youtube": {"player_client": ["web"], "player_skip": ["webpage"]}}

    # الطريقة 5: أندرويد موبايل
    m5 = base("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/120.0.6099.230 Mobile Safari/537.36")
    m5["extractor_args"] = {"youtube": {"player_client": ["android", "web", "ios"], "player_skip": ["webpage"]}}

    all_methods = [m1, m2, m3, m4, m5]

    # أضف صيغة التحميل لكل طريقة
    result = []
    for m in all_methods:
        opts = dict(m)
        if mode == "audio":
            opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
            opts["postprocessors"] = audio_pp
        else:
            opts["format"] = video_fmt
            opts["merge_output_format"] = "mp4"
        result.append(opts)

    return result


def get_info(url: str) -> dict:
    """جلب معلومات الفيديو مع 5 طرق مختلفة"""
    methods = build_ydl_opts("video", "best")
    last_error = None

    for i, opts in enumerate(methods):
        # للمعلومات فقط - بدون تحميل
        info_opts = {k: v for k, v in opts.items() if k not in ["outtmpl", "postprocessors", "format", "merge_output_format"]}
        info_opts["extract_flat"] = False
        try:
            logger.info(f"محاولة get_info #{i+1}")
            with yt_dlp.YoutubeDL(info_opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as e:
            last_error = e
            logger.warning(f"محاولة #{i+1} فشلت: {e}")
            time.sleep(1)

    raise last_error


def download_media(url: str, mode: str, quality: str, out_dir: str) -> str:
    """تحميل الفيديو/الصوت مع 5 طرق مختلفة"""
    methods = build_ydl_opts(mode, quality, out_dir)
    last_error = None

    for i, opts in enumerate(methods):
        try:
            logger.info(f"محاولة تحميل #{i+1}")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                fname = ydl.prepare_filename(info)

            # البحث عن الملف المحمّل
            if mode == "audio":
                mp3 = Path(fname).with_suffix(".mp3")
                if mp3.exists():
                    return str(mp3)

            files = [f for f in Path(out_dir).iterdir() if f.is_file()]
            if files:
                return str(max(files, key=lambda f: f.stat().st_size))

        except Exception as e:
            last_error = e
            logger.warning(f"تحميل #{i+1} فشل: {e}")
            time.sleep(2)
            # امسح الملفات الناقصة قبل المحاولة التالية
            for f in Path(out_dir).iterdir():
                try:
                    f.unlink()
                except Exception:
                    pass

    raise last_error

# ══════════════════════════════════════════════════════
#              تصنيف الأخطاء (مُصلح)
# ══════════════════════════════════════════════════════

def classify_error(err: str) -> str:
    e = str(err).lower()
    # ✅ مُصلح: يوتيوب يعطي رسائل مختلفة كلها تعني "تسجيل دخول"
    if any(x in e for x in [
        "sign in", "signin", "login", "log in",
        "confirm", "bot", "not a bot",
        "login_required", "age", "age-restricted",
        "this video is unavailable",  # ← هذا كان السبب!
        "join this channel",
        "private video",
        "members-only",
    ]):
        # إذا عندنا cookies وما زال يعطي نفس الخطأ
        if os.path.exists(COOKIES_FILE):
            return "yt_cookies_expired"
        return "yt_blocked"

    if any(x in e for x in ["private", "خاص"]):
        return "private"

    if any(x in e for x in [
        "no video formats", "format not available",
        "copyright", "removed by",
    ]):
        return "unavailable"

    return "unknown"

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
#            🔒 اشتراك إجباري + إعلان إجباري
# ══════════════════════════════════════════════════════

async def is_subscribed(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except Exception:
        return True

# حالة الإعلان: {user_id: {token, clicked_at, url, title}}
ad_state: dict = {}

def start_ad(user_id: int, url: str, title: str):
    ad_state[user_id] = {"clicked_at": None, "url": url, "title": title}

def click_ad(user_id: int):
    if user_id in ad_state:
        ad_state[user_id]["clicked_at"] = time.time()

def check_ad(user_id: int) -> tuple[bool, int]:
    s = ad_state.get(user_id)
    if not s or s["clicked_at"] is None:
        return False, AD_WAIT
    remaining = AD_WAIT - (time.time() - s["clicked_at"])
    return remaining <= 0, max(0, int(remaining) + 1)

# ══════════════════════════════════════════════════════
#                 🛠️ مساعدات
# ══════════════════════════════════════════════════════

URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
user_last_req: dict = {}

def is_flooding(uid: int) -> bool:
    now = time.time()
    if now - user_last_req.get(uid, 0) < 5:
        return True
    user_last_req[uid] = now
    return False

def extract_url(text: str):
    m = URL_PATTERN.search(text)
    return m.group(0) if m else None

def human_size(b: int) -> str:
    for u in ["B","KB","MB","GB"]:
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def quality_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 1080p", callback_data="q|video|best"),
         InlineKeyboardButton("🎬 720p",  callback_data="q|video|high")],
        [InlineKeyboardButton("🎬 480p",  callback_data="q|video|medium"),
         InlineKeyboardButton("🎬 360p",  callback_data="q|video|low")],
        [InlineKeyboardButton("🎵 صوت MP3", callback_data="q|audio|best")],
        [InlineKeyboardButton("❌ إلغاء",   callback_data="cancel")],
    ])

def ad_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👆 اضغط هنا أولاً ← إجباري", url=SMARTLINK)],
        [InlineKeyboardButton(f"✅ ضغطت — تحقق بعد {AD_WAIT}ث", callback_data="ad_verify")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")],
    ])

def sub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📢 اشترك", url=CHANNEL_LINK),
        InlineKeyboardButton("✅ تحققت", callback_data="check_sub"),
    ]])

# ══════════════════════════════════════════════════════
#                  📋 الأوامر
# ══════════════════════════════════════════════════════

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = register_user(user)
    if not await is_subscribed(ctx.bot, user.id):
        await update.message.reply_text(
            "⛔️ *يجب الاشتراك أولاً!*\nاشترك في قناتنا ثم اضغط تحققت ✅",
            parse_mode="Markdown", reply_markup=sub_kb()
        )
        return
    g = f"🎉 *أهلاً بك {user.first_name}!*\n" if is_new else f"👋 *مرحباً {user.first_name}!*\n"
    await update.message.reply_text(
        g + "\n🎬 *بوت التحميل الاحترافي*\n\n"
        "أرسل أي رابط فيديو أو صوت!\n\n"
        "🌍 *يدعم:*\n"
        "▸ YouTube • TikTok • Instagram\n"
        "▸ Twitter/X • Facebook • SoundCloud\n"
        "▸ وأكثر من 1000 موقع!\n\n"
        "⬇️ *أرسل الرابط الآن*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📢 قناتنا", url=CHANNEL_LINK),
            InlineKeyboardButton("❓ مساعدة", callback_data="show_help"),
        ]])
    )

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *كيف أستخدم البوت؟*\n\n"
        "1️⃣ أرسل رابط الفيديو\n"
        "2️⃣ اضغط رابط الإعلان *(إجباري)*\n"
        "3️⃣ انتظر 15 ثانية\n"
        "4️⃣ اضغط تحقق\n"
        "5️⃣ اختر الجودة واستلم الملف ✅\n\n"
        "⚠️ *الحد الأقصى:* 50MB\n"
        "⚠️ *انتظر 5 ثوانٍ بين كل طلب*",
        parse_mode="Markdown"
    )

async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    info = db["users"].get(str(update.effective_user.id), {})
    await update.message.reply_text(
        f"📊 *إحصائياتك*\n\n"
        f"📅 انضممت: {info.get('joined','—')}\n"
        f"📥 تحميلاتك: {info.get('downloads',0)}\n\n"
        f"━━━━━━━━━━━━━\n"
        f"👥 المستخدمون: {len(db['users'])}\n"
        f"📦 التحميلات: {db.get('total_downloads',0)}",
        parse_mode="Markdown"
    )

async def admin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    db = load_db()
    today = datetime.now().strftime("%Y-%m-%d")
    new_today = sum(1 for u in db["users"].values() if u.get("joined") == today)
    ck = "✅ موجود — يوتيوب يعمل!" if os.path.exists(COOKIES_FILE) else "❌ غير موجود — يوتيوب لن يعمل!"
    await update.message.reply_text(
        f"👑 *لوحة الأدمن*\n\n"
        f"👥 المستخدمون: {len(db['users'])}\n"
        f"🆕 اليوم: {new_today}\n"
        f"📥 التحميلات: {db.get('total_downloads',0)}\n"
        f"🍪 cookies.txt: {ck}\n\n"
        f"📢 إرسال للجميع:\n`/broadcast رسالتك`",
        parse_mode="Markdown"
    )

async def broadcast_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not ctx.args:
        await update.message.reply_text("استخدم:\n`/broadcast رسالتك`", parse_mode="Markdown")
        return
    msg_text = " ".join(ctx.args)
    db = load_db()
    ok = fail = 0
    s = await update.message.reply_text(f"📤 جاري الإرسال لـ {len(db['users'])} مستخدم...")
    for uid in db["users"]:
        try:
            await ctx.bot.send_message(int(uid), f"📢 *إعلان*\n\n{msg_text}", parse_mode="Markdown")
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.04)
    await s.edit_text(f"✅ نجح: {ok} | ❌ فشل: {fail}", parse_mode="Markdown")

# ══════════════════════════════════════════════════════
#               🔗 معالجة الروابط
# ══════════════════════════════════════════════════════

async def handle_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)

    if not await is_subscribed(ctx.bot, user.id):
        await update.message.reply_text("⛔️ *يجب الاشتراك أولاً!*", parse_mode="Markdown", reply_markup=sub_kb())
        return

    if is_flooding(user.id):
        await update.message.reply_text("⏳ انتظر 5 ثوانٍ بين كل طلب!")
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
        hrs, mins  = divmod(mins, 60)
        dur_str    = f"{hrs}:{mins:02d}:{secs:02d}" if hrs else f"{mins}:{secs:02d}"

        start_ad(user.id, url, title)

        await msg.edit_text(
            f"✅ *تم العثور على المحتوى!*\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📌 *{title}*\n"
            f"👤 {uploader}\n"
            f"⏱ `{dur_str}`\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ *خطوة إجبارية قبل التحميل:*\n"
            f"1️⃣ اضغط الرابط أدناه\n"
            f"2️⃣ انتظر {AD_WAIT} ثانية\n"
            f"3️⃣ اضغط *تحقق* للمتابعة ✅",
            parse_mode="Markdown",
            reply_markup=ad_kb()
        )

    except Exception as e:
        err_type = classify_error(str(e))
        logger.error(f"get_info error: {e}")

        error_msgs = {
            "yt_blocked": (
                "⚠️ *يوتيوب يحتاج تسجيل دخول*\n\n"
                "💡 *الحل:*\n"
                "أرسل ملف `cookies.txt` للأدمن\n\n"
                "📌 أو جرب روابط من:\n"
                "TikTok • Instagram • Twitter"
            ),
            "yt_cookies_expired": (
                "⚠️ *انتهت صلاحية الـ cookies!*\n\n"
                "💡 يجب تجديد ملف `cookies.txt`\n"
                "اتبع نفس خطوات استخراجه من Firefox\n"
                "وارفع الملف الجديد على GitHub"
            ),
            "private": "🔒 *الفيديو خاص ولا يمكن تحميله*",
            "unavailable": (
                "❌ *الفيديو محذوف أو محظور*\n\n"
                "💡 تأكد من صحة الرابط"
            ),
        }
        # ✅ في حالة خطأ غير معروف نظهر الخطأ الحقيقي للأدمن
        if err_type == "unknown":
            if user.id == ADMIN_ID:
                await msg.edit_text(f"❌ *خطأ:*\n`{str(e)[:300]}`", parse_mode="Markdown")
            else:
                await msg.edit_text(
                    "❌ *فشل التحميل*\n\nجرب:\n▸ تأكد من الرابط\n▸ جرب رابط آخر\n▸ انتظر دقيقة وأعد المحاولة",
                    parse_mode="Markdown"
                )
        else:
            await msg.edit_text(error_msgs.get(err_type, "❌ خطأ غير معروف"), parse_mode="Markdown")

# ══════════════════════════════════════════════════════
#               ⚙️ معالجة الأزرار
# ══════════════════════════════════════════════════════

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid  = query.from_user.id

    if data == "check_sub":
        if await is_subscribed(ctx.bot, uid):
            await query.edit_message_text("✅ *تم التحقق!*\nأرسل الرابط الآن 👇", parse_mode="Markdown")
        else:
            await query.answer("❌ لم تشترك بعد!", show_alert=True)
        return

    if data == "show_help":
        await query.edit_message_text(
            "📖 *المساعدة*\n\n"
            "1️⃣ أرسل الرابط\n"
            "2️⃣ اضغط رابط الإعلان\n"
            "3️⃣ انتظر 15 ثانية\n"
            "4️⃣ اضغط تحقق\n"
            "5️⃣ اختر الجودة ✅",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="back")
            ]])
        )
        return

    if data == "cancel":
        ad_state.pop(uid, None)
        await query.edit_message_text("❌ *تم الإلغاء*", parse_mode="Markdown")
        return

    if data == "ad_verify":
        state = ad_state.get(uid)
        if not state:
            await query.answer("❌ انتهت الجلسة، أرسل الرابط مجدداً", show_alert=True)
            return

        if state["clicked_at"] is None:
            click_ad(uid)
            await query.answer(f"⏳ انتظر {AD_WAIT} ثانية ثم اضغط تحقق!", show_alert=True)
            return

        ok, remaining = check_ad(uid)
        if not ok:
            await query.answer(f"⏳ انتظر {remaining} ثانية أخرى!", show_alert=True)
            return

        await query.edit_message_text(
            f"✅ *شكراً! اختر الجودة:*\n\n📌 {state['title']}",
            parse_mode="Markdown",
            reply_markup=quality_kb()
        )
        return

    if data.startswith("q|"):
        _, mode, quality = data.split("|")
        state = ad_state.get(uid)
        if not state:
            await query.edit_message_text("❌ انتهت الجلسة، أرسل الرابط مجدداً", parse_mode="Markdown")
            return

        url   = state["url"]
        title = state["title"]
        ql    = {"best":"1080p","high":"720p","medium":"480p","low":"360p"}.get(quality, quality)
        emoji = "🎵" if mode == "audio" else "🎬"

        await query.edit_message_text(
            f"{emoji} *جاري التحميل...*\n"
            f"📌 {title}\n"
            f"📊 {'MP3' if mode=='audio' else ql}\n\n"
            f"⏳ انتظر...",
            parse_mode="Markdown"
        )

        tmp = tempfile.mkdtemp(dir=DOWNLOAD_DIR)
        try:
            loop = asyncio.get_event_loop()
            path = await loop.run_in_executor(None, download_media, url, mode, quality, tmp)

            size_bytes = os.path.getsize(path)
            if size_bytes / 1024 / 1024 > MAX_FILE_MB:
                await query.edit_message_text(
                    f"❌ *الملف كبير جداً!*\n📦 {human_size(size_bytes)}\n💡 جرب جودة أقل",
                    parse_mode="Markdown"
                )
                return

            await query.edit_message_text(f"📤 *جاري الرفع...* {human_size(size_bytes)}", parse_mode="Markdown")

            chat_id = query.message.chat_id
            caption = f"{emoji} *{title}*\n🤖 @{ctx.bot.username}"

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

            add_download(uid)
            ad_state.pop(uid, None)
            await query.edit_message_text(f"✅ *اكتمل التحميل!*\n📌 {title}", parse_mode="Markdown")

        except Exception as e:
            err_type = classify_error(str(e))
            logger.error(f"download error: {e}")
            err_msgs = {
                "yt_blocked":         "⚠️ *يوتيوب يرفض التحميل*\nالحل: جدّد ملف cookies.txt",
                "yt_cookies_expired": "⚠️ *انتهت صلاحية الـ cookies*\nجدّد ملف cookies.txt",
                "private":            "🔒 الفيديو خاص",
                "unavailable":        "❌ الفيديو غير متاح",
            }
            if err_type == "unknown":
                msg_txt = f"❌ فشل التحميل\n\nجرب جودة أقل أو رابط آخر"
                if uid == ADMIN_ID:
                    msg_txt = f"❌ *خطأ:*\n`{str(e)[:300]}`"
                await query.edit_message_text(msg_txt, parse_mode="Markdown")
            else:
                await query.edit_message_text(err_msgs.get(err_type, "❌ فشل"), parse_mode="Markdown")
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
    if os.path.exists(COOKIES_FILE):
        logger.info("✅ cookies.txt موجود — يوتيوب سيعمل!")
    else:
        logger.warning("⚠️ cookies.txt غير موجود — يوتيوب لن يعمل!")

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
