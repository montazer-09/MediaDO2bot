#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════╗
# ║     🎬 بوت التحميل الاحترافي - الحل النهائي              ║
# ║  ✅ بدون cookies - بدون تجديد - يعمل دائماً              ║
# ║  🥇 يستخدم Cobalt أولاً ثم yt-dlp كاحتياط               ║
# ╚══════════════════════════════════════════════════════════╝

import os, re, logging, asyncio, tempfile, shutil, json, time, httpx
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
#       🥇 الطريقة 1: Cobalt API (بدون cookies!)
# ══════════════════════════════════════════════════════

# سيرفرات Cobalt المجانية - نجرب كلها بالترتيب
COBALT_INSTANCES = [
    "https://cobalt.api.timelessnesses.me",
    "https://cobalt.syncope.co",
    "https://cobalt.catvibers.me",
    "https://api.cobalt.tools",
]

async def cobalt_download(url: str, mode: str, quality: str, out_dir: str) -> str | None:
    """
    تحميل عبر Cobalt API - لا يحتاج cookies أبداً!
    يجرب كل السيرفرات المجانية
    """
    # إعداد جودة الفيديو
    vq_map = {"best": "1080", "high": "720", "medium": "480", "low": "360"}
    vq = vq_map.get(quality, "1080")

    payload = {
        "url": url,
        "downloadMode": "audio" if mode == "audio" else "auto",
        "videoQuality": vq,
        "audioFormat": "mp3",
        "filenameStyle": "basic",
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Android 13) Chrome/120",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        for instance in COBALT_INSTANCES:
            try:
                logger.info(f"جرب Cobalt: {instance}")
                r = await client.post(f"{instance}/", json=payload, headers=headers)
                if r.status_code != 200:
                    continue

                data = r.json()
                status = data.get("status", "")

                # ✅ رابط مباشر
                if status in ("stream", "redirect", "tunnel") and "url" in data:
                    dl_url = data["url"]
                    ext = "mp3" if mode == "audio" else "mp4"
                    out_path = os.path.join(out_dir, f"video.{ext}")

                    # تحميل الملف
                    async with client.stream("GET", dl_url, follow_redirects=True) as resp:
                        if resp.status_code == 200:
                            with open(out_path, "wb") as f:
                                async for chunk in resp.aiter_bytes(8192):
                                    f.write(chunk)
                            if os.path.getsize(out_path) > 1000:
                                logger.info(f"✅ Cobalt نجح: {instance}")
                                return out_path

                # ✅ picker (يوتيوب أحياناً يعطي روابط متعددة)
                elif status == "picker" and data.get("picker"):
                    dl_url = data["picker"][0].get("url")
                    if dl_url:
                        ext = "mp4"
                        out_path = os.path.join(out_dir, f"video.{ext}")
                        async with client.stream("GET", dl_url, follow_redirects=True) as resp:
                            if resp.status_code == 200:
                                with open(out_path, "wb") as f:
                                    async for chunk in resp.aiter_bytes(8192):
                                        f.write(chunk)
                                if os.path.getsize(out_path) > 1000:
                                    return out_path

            except Exception as e:
                logger.warning(f"Cobalt {instance} فشل: {e}")
                continue

    return None  # كل السيرفرات فشلت، جرب yt-dlp

# ══════════════════════════════════════════════════════
#       🥈 الطريقة 2: yt-dlp (احتياط مع cookies)
# ══════════════════════════════════════════════════════

USER_AGENTS = [
    "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip",
    "com.google.ios.youtube/19.09.3 (iPhone14,3; U; CPU iOS 15_6 like Mac OS X)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
]

PLAYER_CLIENTS = [
    ["android"],
    ["ios"],
    ["web"],
    ["tv_embedded"],
    ["android", "web", "ios"],
]

VIDEO_FMTS = {
    "best":   "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "high":   "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[height<=720]/best",
    "medium": "bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/best[height<=480]/best",
    "low":    "bestvideo[ext=mp4][height<=360]+bestaudio[ext=m4a]/best[height<=360]/best",
}

def build_opts(ua_i: int, pc_i: int, mode: str, quality: str, out_dir: str) -> dict:
    tpl = os.path.join(out_dir, "%(title).60s.%(ext)s")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "outtmpl": tpl,
        "http_headers": {"User-Agent": USER_AGENTS[ua_i % len(USER_AGENTS)]},
        "extractor_args": {"youtube": {"player_client": PLAYER_CLIENTS[pc_i % len(PLAYER_CLIENTS)]}},
        "retries": 3,
        "socket_timeout": 30,
    }
    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    if mode == "audio":
        opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    else:
        opts["format"] = VIDEO_FMTS.get(quality, VIDEO_FMTS["best"])
        opts["merge_output_format"] = "mp4"
    return opts

def ytdlp_get_info(url: str) -> dict:
    for ua_i in range(len(USER_AGENTS)):
        for pc_i in range(len(PLAYER_CLIENTS)):
            try:
                base = {"quiet": True, "no_warnings": True, "nocheckcertificate": True,
                        "http_headers": {"User-Agent": USER_AGENTS[ua_i]},
                        "extractor_args": {"youtube": {"player_client": PLAYER_CLIENTS[pc_i]}}}
                if os.path.exists(COOKIES_FILE):
                    base["cookiefile"] = COOKIES_FILE
                with yt_dlp.YoutubeDL(base) as ydl:
                    return ydl.extract_info(url, download=False)
            except Exception:
                time.sleep(0.5)
    raise Exception("فشلت كل محاولات جلب المعلومات")

def ytdlp_download(url: str, mode: str, quality: str, out_dir: str) -> str:
    last_error = None
    for ua_i in range(len(USER_AGENTS)):
        for pc_i in range(len(PLAYER_CLIENTS)):
            try:
                opts = build_opts(ua_i, pc_i, mode, quality, out_dir)
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
                time.sleep(1)
                for f in Path(out_dir).iterdir():
                    try: f.unlink()
                    except: pass
    raise last_error or Exception("فشل yt-dlp")

# ══════════════════════════════════════════════════════
#          🎯 الدالة الرئيسية: تجمع الطريقتين
# ══════════════════════════════════════════════════════

async def smart_download(url: str, mode: str, quality: str, out_dir: str) -> str:
    """
    1. يجرب Cobalt أولاً (بدون cookies)
    2. لو فشل يجرب yt-dlp (مع cookies لو موجودة)
    """
    # الطريقة 1: Cobalt
    logger.info("جرب Cobalt...")
    result = await cobalt_download(url, mode, quality, out_dir)
    if result:
        return result

    # الطريقة 2: yt-dlp
    logger.info("Cobalt فشل، جرب yt-dlp...")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, ytdlp_download, url, mode, quality, out_dir)

async def smart_get_info(url: str) -> dict:
    """جلب معلومات الفيديو - يحاول yt-dlp أولاً للمعلومات"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, ytdlp_get_info, url)

# ══════════════════════════════════════════════════════
#              تصنيف الأخطاء
# ══════════════════════════════════════════════════════

def classify_error(err: str) -> str:
    e = str(err).lower()
    if any(x in e for x in ["sign in","signin","login","confirm","bot","not a bot",
                              "login_required","age","this video is unavailable",
                              "join this channel","private video","members-only"]):
        return "yt_blocked"
    if "private" in e:
        return "private"
    if any(x in e for x in ["copyright","removed by","no video formats","format not available"]):
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

async def is_subscribed(bot, uid: int) -> bool:
    try:
        m = await bot.get_chat_member(CHANNEL_ID, uid)
        return m.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except Exception:
        return True

ad_state: dict = {}

def start_ad(uid: int, url: str, title: str):
    ad_state[uid] = {"clicked_at": None, "url": url, "title": title}

def click_ad(uid: int):
    if uid in ad_state:
        ad_state[uid]["clicked_at"] = time.time()

def check_ad(uid: int) -> tuple[bool, int]:
    s = ad_state.get(uid)
    if not s or s["clicked_at"] is None:
        return False, AD_WAIT
    rem = AD_WAIT - (time.time() - s["clicked_at"])
    return rem <= 0, max(0, int(rem) + 1)

# ══════════════════════════════════════════════════════
#                 🛠️ مساعدات
# ══════════════════════════════════════════════════════

URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
flood_map: dict = {}

def is_flooding(uid: int) -> bool:
    now = time.time()
    if now - flood_map.get(uid, 0) < 5:
        return True
    flood_map[uid] = now
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
        [InlineKeyboardButton("🎬 1080p",    callback_data="q|video|best"),
         InlineKeyboardButton("🎬 720p",     callback_data="q|video|high")],
        [InlineKeyboardButton("🎬 480p",     callback_data="q|video|medium"),
         InlineKeyboardButton("🎬 360p",     callback_data="q|video|low")],
        [InlineKeyboardButton("🎵 صوت MP3",  callback_data="q|audio|best")],
        [InlineKeyboardButton("❌ إلغاء",    callback_data="cancel")],
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
            "⛔️ *يجب الاشتراك أولاً!*\nاشترك ثم اضغط تحققت ✅",
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
    ck = "✅ موجود" if os.path.exists(COOKIES_FILE) else "➖ غير موجود (ليس ضرورياً)"
    await update.message.reply_text(
        f"👑 *لوحة الأدمن*\n\n"
        f"👥 المستخدمون: {len(db['users'])}\n"
        f"🆕 اليوم: {new_today}\n"
        f"📥 التحميلات: {db.get('total_downloads',0)}\n"
        f"🍪 cookies.txt: {ck}\n\n"
        f"📢 `/broadcast رسالتك`",
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
        info = await smart_get_info(url)
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
            f"3️⃣ اضغط *تحقق* ✅",
            parse_mode="Markdown",
            reply_markup=ad_kb()
        )
    except Exception as e:
        err_type = classify_error(str(e))
        msgs = {
            "yt_blocked":  "⚠️ *يوتيوب يحتاج تسجيل دخول*\n\n💡 جرب رابط من:\nTikTok • Instagram • Twitter",
            "private":     "🔒 *الفيديو خاص*",
            "unavailable": "❌ *الفيديو محذوف أو محظور*",
        }
        if err_type == "unknown" and user.id == ADMIN_ID:
            await msg.edit_text(f"❌ خطأ:\n`{str(e)[:300]}`", parse_mode="Markdown")
        else:
            await msg.edit_text(msgs.get(err_type, "❌ فشل التحميل\n\nجرب رابط آخر"), parse_mode="Markdown")

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
            "📖 *المساعدة*\n\n1️⃣ أرسل الرابط\n2️⃣ اضغط الإعلان\n"
            "3️⃣ انتظر 15 ثانية\n4️⃣ اضغط تحقق\n5️⃣ اختر الجودة ✅",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back")]])
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
        ok, rem = check_ad(uid)
        if not ok:
            await query.answer(f"⏳ انتظر {rem} ثانية أخرى!", show_alert=True)
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
            f"{emoji} *جاري التحميل...*\n📌 {title}\n"
            f"📊 {'MP3' if mode=='audio' else ql}\n\n⏳ انتظر...",
            parse_mode="Markdown"
        )

        tmp = tempfile.mkdtemp(dir=DOWNLOAD_DIR)
        try:
            path = await smart_download(url, mode, quality, tmp)

            size_bytes = os.path.getsize(path)
            if size_bytes / 1024 / 1024 > MAX_FILE_MB:
                await query.edit_message_text(
                    f"❌ *الملف كبير!*\n📦 {human_size(size_bytes)}\n💡 جرب جودة أقل",
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
            msgs = {
                "yt_blocked":  "⚠️ *يوتيوب يرفض التحميل*\nجرب رابط من TikTok أو Instagram",
                "private":     "🔒 الفيديو خاص",
                "unavailable": "❌ الفيديو غير متاح",
            }
            if err_type == "unknown" and uid == ADMIN_ID:
                await query.edit_message_text(f"❌ خطأ:\n`{str(e)[:300]}`", parse_mode="Markdown")
            else:
                await query.edit_message_text(
                    msgs.get(err_type, "❌ فشل التحميل\n\nجرب جودة أقل أو رابط آخر"),
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
    logger.info("✅ البوت جاهز! يستخدم Cobalt + yt-dlp")

def main():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  🎬 بوت التحميل الاحترافي")
    print("  🥇 Cobalt + yt-dlp")
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
