"""
Telegram Bot for Rohit Giveaway Mini App
Features:
- Strict Channel Gatekeeper: NO Giveaway App link until ALL channels are joined!
- Public & Private Channels support (both in permanent code & dynamic /addchannel)
- Owner-only /ownerhelp, /addchannel, /removechannel, /channels, /owners, /addowner, /delowner
- Instant 1-Second Referral Tracking & Notification to Referrer
- Dynamic /invite, /link, /referral commands (gatekept by channel verification)
- Real-time +1 Free Spin credit in Firebase Realtime Database
- Safe Callback Queries (completely prevents "BadRequest: Message is not modified")
- Resilience against mobile network/Termux drops (handles ReadError/TimedOut gracefully)
- Admin commands: /withdrawals, /payouts, /broadcast, /owners, /addowner, /delowner
- User status commands: /spins, /balance, /invite
"""

import logging
import json
import time
import re
import urllib.request
import urllib.error
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from telegram.request import HTTPXRequest
from telegram.error import NetworkError, TimedOut, Conflict, BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# -------------------------------------------------------------------------
# 1. CORE BOT CONFIGURATION
# -------------------------------------------------------------------------
TOKEN = "8639853090:AAGSrArc6Xtm5309WpZeGih1H7evsvJstWE"
BOT_USERNAME = "Giveaway_by_rohit_bot"
WEB_URL = "https://cashback-psi-fawn.vercel.app/"
RTDB_URL = "https://telebot-26c11-default-rtdb.firebaseio.com"

# -------------------------------------------------------------------------
# 2. PERMANENT CHANNELS (Public & Private Dono Yahan Code Me Set Kar Sakte Hain)
# -------------------------------------------------------------------------
# Public Channel ke liye: id = "@channelusername", url = "https://t.me/channelusername"
# Private Channel ke liye: id = "-100xxxxxxxxxx", url = "https://t.me/+xxxxxx"
PERMANENT_CHANNELS = [
    {
        "id": "@sauravsanganya",
        "name": "📢 Official Giveaway Channel",
        "url": "https://t.me/sauravsanganya",
        "is_private": False,
    },
    # Example Private Channel (Aap apna private channel id aur invite link yahan add kar sakte hain):
    # {
    #     "id": "-1002345678901",
    #     "name": "🔒 VIP Private Channel",
    #     "url": "https://t.me/+AbCdEfGhIjKl",
    #     "is_private": True,
    # },
]

# -------------------------------------------------------------------------
# 3. PERMANENT OWNERS (Only Ye ID / Username /ownerhelp Chala Sakte Hain)
# -------------------------------------------------------------------------
# Yahan apna Telegram numeric User ID ya username bina '@' ke likhein:
DEFAULT_OWNERS = [
    "sauravsanganya",
    "rohit",
    "adminrohit",
    "ravikumar",
]

# ----------------- Logging Setup -----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("giveaway_bot")


# ----------------- Database Helpers -----------------
def get_user_from_db(user_id: str) -> dict | None:
    """Fetch user profile from Firebase RTDB."""
    try:
        req = urllib.request.Request(f"{RTDB_URL}/users/{user_id}.json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read().decode("utf-8")
            if data and data != "null":
                return json.loads(data)
    except Exception as e:
        logger.warning(f"Error fetching user {user_id}: {e}")
    return None


def is_already_referred(referrer_id: str, new_user_id: str) -> bool:
    """Check if this new user has already been credited to the referrer."""
    try:
        req = urllib.request.Request(f"{RTDB_URL}/referrals/{referrer_id}/{new_user_id}.json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read().decode("utf-8")
            return data is not None and data != "null"
    except Exception:
        return False


def save_referral_record(referrer_id: str, new_user_id: str, name: str, username: str):
    """Save referral relationship in Firebase RTDB."""
    try:
        payload = json.dumps({
            "joinerId": str(new_user_id),
            "name": name,
            "username": username or "",
            "timestamp": int(time.time() * 1000),
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{RTDB_URL}/referrals/{referrer_id}/{new_user_id}.json",
            data=payload,
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception as e:
        logger.warning(f"Error saving referral record: {e}")


def award_spins_to_referrer(referrer_id: str, new_user_name: str) -> dict:
    """
    Increment spins and friends count in Firebase Realtime Database.
    Returns the updated referrer stats.
    """
    now_ms = int(time.time() * 1000)
    current = get_user_from_db(referrer_id)

    if current:
        new_spins = (current.get("spins") or 0) + 1
        new_friends = (current.get("friendsJoined") or 0) + 1
        new_earned = (current.get("spinsEarned") or 0) + 1

        patch_data = {
            "spins": new_spins,
            "friendsJoined": new_friends,
            "spinsEarned": new_earned,
        }
        try:
            req = urllib.request.Request(
                f"{RTDB_URL}/users/{referrer_id}.json",
                data=json.dumps(patch_data).encode("utf-8"),
                method="PATCH",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception as e:
            logger.warning(f"Error updating referrer {referrer_id}: {e}")

        # Add transaction record in Firebase
        tx_id = f"tx_{now_ms}_{str(new_friends)}"
        tx_data = {
            "id": tx_id,
            "userId": str(referrer_id),
            "type": "referral_bonus",
            "amount": 0,
            "description": f"Friend {new_user_name} joined! +1 Lucky Spin awarded",
            "status": "completed",
            "createdAt": now_ms,
        }
        try:
            req = urllib.request.Request(
                f"{RTDB_URL}/transactions/{tx_id}.json",
                data=json.dumps(tx_data).encode("utf-8"),
                method="PUT",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception:
            pass

        return {"spins": new_spins, "friendsJoined": new_friends}
    else:
        new_user = {
            "id": str(referrer_id),
            "telegramId": str(referrer_id),
            "name": f"User #{referrer_id}",
            "username": f"user_{referrer_id}",
            "balance": 0,
            "spins": 2,  # 1 signup bonus + 1 referral spin
            "friendsJoined": 1,
            "spinsEarned": 2,
            "createdAt": now_ms,
            "isVerified": True,
            "claimedWelcomeSpin": True,
        }
        try:
            req = urllib.request.Request(
                f"{RTDB_URL}/users/{referrer_id}.json",
                data=json.dumps(new_user).encode("utf-8"),
                method="PUT",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception as e:
            logger.warning(f"Error creating referrer: {e}")

        return {"spins": 2, "friendsJoined": 1}


# ----------------- Dynamic Channels & Owners Storage -----------------
_CHANNELS_CACHE = []
_OWNERS_CACHE = set(o.lower().lstrip("@") for o in DEFAULT_OWNERS)
_LAST_SYNC_TIME = 0


def load_channels_from_db() -> list[dict]:
    """
    Combines permanent channels from code with dynamic channels
    stored in Firebase Realtime Database.
    """
    global _CHANNELS_CACHE, _LAST_SYNC_TIME
    now = time.time()
    if _CHANNELS_CACHE and (now - _LAST_SYNC_TIME < 15):
        return _CHANNELS_CACHE

    combined = []
    # 1. Add permanent channels from code
    for p in PERMANENT_CHANNELS:
        combined.append(dict(p))

    # 2. Add dynamic channels from Firebase RTDB
    try:
        req = urllib.request.Request(f"{RTDB_URL}/bot_config/channels.json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read().decode("utf-8")
            if data and data != "null":
                parsed = json.loads(data)
                items = list(parsed.values()) if isinstance(parsed, dict) else parsed
                for item in items:
                    if isinstance(item, dict) and item.get("id"):
                        # Avoid duplicates
                        if not any(c.get("id") == item["id"] for c in combined):
                            combined.append(item)
    except Exception as e:
        logger.warning(f"Notice reading channels from DB: {e}")

    _CHANNELS_CACHE = combined
    _LAST_SYNC_TIME = now
    return _CHANNELS_CACHE


def save_channel_to_db(channel_info: dict) -> bool:
    """Save or update a channel in Firebase RTDB."""
    global _CHANNELS_CACHE
    try:
        safe_key = str(channel_info["id"]).replace("@", "at_").replace("-", "neg_").replace(".", "_")
        payload = json.dumps(channel_info).encode("utf-8")
        req = urllib.request.Request(
            f"{RTDB_URL}/bot_config/channels/{safe_key}.json",
            data=payload,
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5):
            pass

        # Update cache
        existing = [c for c in _CHANNELS_CACHE if str(c.get("id")) != str(channel_info["id"])]
        existing.append(channel_info)
        _CHANNELS_CACHE = existing
        return True
    except Exception as e:
        logger.error(f"Error saving channel to RTDB: {e}")
        return False


def delete_channel_from_db(channel_identifier: str) -> bool:
    """Delete a channel from Firebase RTDB."""
    global _CHANNELS_CACHE
    clean_id = channel_identifier.strip()
    try:
        safe_key = clean_id.replace("@", "at_").replace("-", "neg_").replace(".", "_")
        req = urllib.request.Request(
            f"{RTDB_URL}/bot_config/channels/{safe_key}.json",
            method="DELETE",
        )
        with urllib.request.urlopen(req, timeout=5):
            pass

        _CHANNELS_CACHE = [c for c in _CHANNELS_CACHE if str(c.get("id")).lower() != clean_id.lower()]
        return True
    except Exception as e:
        logger.error(f"Error deleting channel from RTDB: {e}")
        return False


def load_owners_from_db() -> set[str]:
    """Load authorized owner IDs / usernames from Firebase RTDB."""
    global _OWNERS_CACHE
    try:
        req = urllib.request.Request(f"{RTDB_URL}/bot_config/owners.json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read().decode("utf-8")
            if data and data != "null":
                parsed = json.loads(data)
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        if isinstance(v, dict) and "identifier" in v:
                            _OWNERS_CACHE.add(str(v["identifier"]).lower().lstrip("@"))
                        else:
                            _OWNERS_CACHE.add(str(k).lower().lstrip("@"))
                elif isinstance(parsed, list):
                    for item in parsed:
                        if item:
                            _OWNERS_CACHE.add(str(item).lower().lstrip("@"))
    except Exception as e:
        logger.warning(f"Notice reading owners from DB: {e}")
    return _OWNERS_CACHE


def save_owner_to_db(identifier: str) -> bool:
    """Save an authorized owner ID or username to Firebase RTDB."""
    clean = identifier.strip().lower().lstrip("@")
    safe_key = clean.replace(".", "_").replace("-", "neg_")
    try:
        payload = json.dumps({
            "identifier": clean,
            "addedAt": int(time.time() * 1000),
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{RTDB_URL}/bot_config/owners/{safe_key}.json",
            data=payload,
            method="PUT",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
        _OWNERS_CACHE.add(clean)
        return True
    except Exception as e:
        logger.error(f"Error saving owner: {e}")
        return False


def delete_owner_from_db(identifier: str) -> bool:
    """Remove an owner from Firebase RTDB."""
    clean = identifier.strip().lower().lstrip("@")
    safe_key = clean.replace(".", "_").replace("-", "neg_")
    try:
        req = urllib.request.Request(
            f"{RTDB_URL}/bot_config/owners/{safe_key}.json",
            method="DELETE",
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
        _OWNERS_CACHE.discard(clean)
        return True
    except Exception as e:
        logger.error(f"Error removing owner: {e}")
        return False


def is_owner(user_id: int | str, username: str | None = None) -> bool:
    """
    STRICT OWNER AUTHENTICATION:
    Only returns True if user's Telegram ID or username is in the saved owner list!
    """
    owners = load_owners_from_db()
    uid_str = str(user_id).strip()

    if uid_str in owners:
        return True

    if username:
        clean_user = username.strip().lower().lstrip("@")
        if clean_user in owners:
            return True

    return False


async def process_and_notify_referral(
    bot,
    referrer_id: str,
    new_user_id: int,
    new_user_name: str,
    new_user_username: str,
):
    """
    Processes referral within 1 second and immediately sends a Telegram
    notification to the referrer with their updated spin count.
    """
    clean_ref = str(referrer_id).replace("ref_", "").strip()
    clean_new_user = str(new_user_id).strip()

    if not clean_ref:
        return

    is_self_test = (clean_ref == clean_new_user)

    if not is_self_test and is_already_referred(clean_ref, clean_new_user):
        logger.info(f"Referral already credited between {clean_ref} and {clean_new_user}")
        return

    save_referral_record(clean_ref, clean_new_user, new_user_name, new_user_username)
    stats = award_spins_to_referrer(clean_ref, new_user_name)
    logger.info(f"Awarded +1 spin to referrer {clean_ref}! Total spins: {stats['spins']}")

    try:
        user_mention = f"@{new_user_username}" if new_user_username else new_user_name
        if is_self_test:
            ref_alert = (
                f"🎉 <b>Referral Test Successful!</b>\n\n"
                f"🎁 <b>+1 Free Lucky Spin</b> has been credited to your account!\n\n"
                f"🎡 Available Spins: <b>{stats['spins']}</b>\n"
                f"👥 Total Friends: <b>{stats['friendsJoined']}</b>\n\n"
                f"🚀 Open the app to spin the wheel and win cash!"
            )
        else:
            ref_alert = (
                f"🎉 <b>New Referral Joined!</b>\n\n"
                f"👤 <b>{new_user_name}</b> ({user_mention}) just joined using your invite link!\n\n"
                f"🎁 <b>+1 Free Lucky Spin</b> has been credited to your account instantly!\n\n"
                f"🎡 Available Spins: <b>{stats['spins']}</b>\n"
                f"👥 Total Friends Invited: <b>{stats['friendsJoined']}</b>\n\n"
                f"🚀 Open the app and spin the wheel to win instant cash!"
            )

        if clean_ref.isdigit():
            await bot.send_message(
                chat_id=int(clean_ref),
                text=ref_alert,
                parse_mode="HTML",
                reply_markup=build_success_keyboard(),
            )
            logger.info(f"Referral notification delivered to {clean_ref}")
    except Exception as e:
        logger.warning(f"Could not send Telegram message to {clean_ref}: {e}")


# ----------------- Keyboard Builders -----------------
def build_success_keyboard(referrer_id: str | None = None) -> InlineKeyboardMarkup:
    """
    CRITICAL: ONLY called after 100% successful verification across ALL channels!
    Gives the user the 'Open Giveaway App & Spin' button.
    """
    app_url = WEB_URL
    if referrer_id:
        clean_ref = str(referrer_id).replace("ref_", "").strip()
        sep = "&" if "?" in app_url else "?"
        app_url = f"{app_url}{sep}start=ref_{clean_ref}"

    channels = load_channels_from_db()
    keyboard = [
        [
            InlineKeyboardButton(
                "🚀 Open Giveaway App & Spin",
                web_app=WebAppInfo(url=app_url),
            )
        ]
    ]

    for ch in channels[:2]:
        name = ch.get("name") or "Official Channel"
        url = ch.get("url")
        if url:
            keyboard.append([InlineKeyboardButton(f"📢 {name}", url=url)])

    return InlineKeyboardMarkup(keyboard)


def build_join_keyboard(missing_channels: list[dict], referrer_id: str | None = None) -> InlineKeyboardMarkup:
    """
    GATEKEEPER KEYBOARD:
    Shown when user has NOT joined all channels.
    CONTAINS ZERO GIVEAWAY LINKS. Only Join Channel buttons + Verify button!
    """
    callback_data = f"check_{referrer_id}" if referrer_id else "check_none"
    keyboard = []

    for ch in missing_channels:
        name = ch.get("name") or ch.get("id") or "Join Channel"
        url = ch.get("url")
        if not url:
            cid = str(ch.get("id", ""))
            url = f"https://t.me/{cid.lstrip('@')}" if cid.startswith("@") else f"https://t.me/c/{cid.replace('-100', '')}/1"
        keyboard.append([
            InlineKeyboardButton(f"📢 Join {name}", url=url)
        ])

    keyboard.append([
        InlineKeyboardButton("✅ I Have Joined All (Verify)", callback_data=callback_data)
    ])

    return InlineKeyboardMarkup(keyboard)


def build_invite_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Build keyboard for sharing referral link with 1 click."""
    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
    share_text = f"🎁 Join Rohit Giveaway! Spin the Lucky Wheel to win instant real cash directly into your UPI/Bank Account! Use my link: {ref_link}"
    share_url = f"https://t.me/share/url?url={ref_link}&text={urllib.parse.quote(share_text)}"

    keyboard = [
        [
            InlineKeyboardButton("📲 Share Link with Friends (1 Click)", url=share_url),
        ],
        [
            InlineKeyboardButton("🚀 Open Giveaway App", web_app=WebAppInfo(url=f"{WEB_URL}?start=ref_{user_id}")),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_owner_panel_keyboard() -> InlineKeyboardMarkup:
    """
    Interactive control panel keyboard for authorized owners.
    Removed 'Open Admin Web App' as requested.
    """
    keyboard = [
        [
            InlineKeyboardButton("📢 Active Channels", callback_data="owner_channels"),
            InlineKeyboardButton("➕ Add Channel", callback_data="owner_addchannel_guide"),
        ],
        [
            InlineKeyboardButton("👑 Owner List", callback_data="owner_list"),
            InlineKeyboardButton("💳 Withdrawals", callback_data="owner_withdrawals"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# ----------------- Multi-Channel Verification (Public & Private) -----------------
async def check_user_channels_membership(bot, user_id: int) -> tuple[bool, list[dict]]:
    """
    Checks if the user has joined EVERY SINGLE required channel (both Public & Private).
    Returns (all_joined: bool, missing_channels: list[dict]).
    """
    channels = load_channels_from_db()
    if not channels:
        return True, []

    missing = []
    for ch in channels:
        ch_id = ch.get("id")
        if not ch_id:
            continue
        try:
            # Handle numeric IDs (e.g. -100xxxxxxxxxx for private channels)
            target_chat = int(ch_id) if str(ch_id).lstrip("-").isdigit() else str(ch_id)
            member = await bot.get_chat_member(chat_id=target_chat, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                missing.append(ch)
        except BadRequest as e:
            # User not found in chat means user hasn't joined!
            logger.info(f"User {user_id} not joined in {ch_id}: {e}")
            missing.append(ch)
        except Exception as e:
            logger.warning(f"Error checking membership for {ch_id} (user {user_id}): {e}")
            # If bot cannot check (e.g., bot not added to private channel), don't block user
            pass

    return len(missing) == 0, missing


# ----------------- Command Handlers -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /start command.
    STRICT RULE: If user has not joined all channels, NO GIVEAWAY APP LINK IS GIVEN!
    """
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    user_id = user.id
    first_name = user.first_name or "Friend"
    username = user.username or ""

    referrer_id = None
    if context.args and len(context.args) > 0:
        raw_arg = context.args[0]
        referrer_id = raw_arg.replace("ref_", "").strip()

    all_joined, missing_channels = await check_user_channels_membership(context.bot, user_id)

    if all_joined:
        # User has joined ALL channels -> Safe to give Giveaway WebApp link!
        if referrer_id:
            await process_and_notify_referral(
                context.bot,
                referrer_id,
                user_id,
                first_name,
                username,
            )

        ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
        welcome_text = (
            f"🎉 <b>Welcome to Rohit Giveaway, {first_name}!</b>\n\n"
            "🎁 <b>Sign Up Bonus: 1 Free Lucky Spin ready!</b>\n"
            "🤝 <b>Referral Bonus: 1 Spin per friend invite!</b>\n\n"
            f"🔗 <b>Your Personal Invite Link:</b>\n"
            f"<code>{ref_link}</code>\n\n"
            "Share this link with your friends to earn unlimited free spins!\n"
            "Click below to open the app and start spinning to win instant cash!"
        )
        await update.message.reply_html(
            welcome_text,
            reply_markup=build_success_keyboard(referrer_id),
        )
    else:
        # User has NOT joined all channels -> NEVER GIVE GIVEAWAY APP LINK!
        channel_names = "\n• ".join([c.get("name") or str(c.get("id")) for c in missing_channels])
        must_join_text = (
            f"👋 Hello <b>{first_name}</b>!\n\n"
            "⚠️ <b>Access Locked!</b>\n"
            "Giveaway App open karne aur <b>Free Lucky Spin</b> paane ke liye, "
            "aapko hamare sabhi official channels join karna zaroori hai:\n\n"
            f"• <b>{channel_names}</b>\n\n"
            "Neeche diye gaye buttons se sabhi channels join karein aur <b>Verify</b> par tap karein!"
        )
        await update.message.reply_html(
            must_join_text,
            reply_markup=build_join_keyboard(missing_channels, referrer_id),
        )


async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /invite command:
    User must be joined in all channels to get invite link or open app!
    """
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "Friend"

    # Check channels first!
    all_joined, missing_channels = await check_user_channels_membership(context.bot, user_id)
    if not all_joined:
        await update.message.reply_html(
            "⚠️ <b>Pehle Sabhi Channels Join Karein!</b>\n\n"
            "Apna referral link aur spins unlock karne ke liye sabhi channels join karke Verify karein:",
            reply_markup=build_join_keyboard(missing_channels),
        )
        return

    db_user = get_user_from_db(str(user_id))
    spins = db_user.get("spins", 1) if db_user else 1
    friends = db_user.get("friendsJoined", 0) if db_user else 0

    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
    text = (
        f"🤝 <b>Invite & Earn Lucky Spins, {first_name}!</b>\n\n"
        f"🎁 For every friend who joins using your link, you get <b>+1 Free Lucky Spin</b>!\n"
        f"🎁 Every friend also gets <b>1 Free Sign Up Spin</b>!\n\n"
        f"📊 <b>Your Current Stats:</b>\n"
        f"🎡 Spins Available: <b>{spins}</b>\n"
        f"👥 Friends Joined: <b>{friends}</b>\n\n"
        f"🔗 <b>Your Invite Link:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        "Tap the button below to share directly with your friends on Telegram!"
    )
    await update.message.reply_html(
        text,
        reply_markup=build_invite_keyboard(user_id),
    )


async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Callback query handler for 'Verify' button.
    Only reveals 'Open Giveaway App' if 100% of channels are joined!
    """
    query = update.callback_query
    if not query or not query.from_user:
        return

    user_id = query.from_user.id
    first_name = query.from_user.first_name or "Friend"
    username = query.from_user.username or ""

    referrer_id = None
    if query.data and query.data.startswith("check_"):
        ref_val = query.data.replace("check_", "").strip()
        if ref_val and ref_val != "none":
            referrer_id = ref_val

    all_joined, missing_channels = await check_user_channels_membership(context.bot, user_id)

    if all_joined:
        await query.answer("✅ Verification successful! Welcome to the Giveaway!", show_alert=False)

        if referrer_id:
            await process_and_notify_referral(
                context.bot,
                referrer_id,
                user_id,
                first_name,
                username,
            )

        ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
        success_text = (
            f"✅ <b>Verification Successful!</b>\n\n"
            f"Welcome to Rohit Giveaway, {first_name}! Your account is verified.\n"
            "🎁 <b>1 Sign Up Lucky Spin</b> has been unlocked for you!\n\n"
            f"🔗 <b>Your Personal Invite Link:</b>\n"
            f"<code>{ref_link}</code>"
        )
        try:
            await query.edit_message_text(
                text=success_text,
                parse_mode="HTML",
                reply_markup=build_success_keyboard(referrer_id),
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                logger.warning(f"edit_message_text notice: {e}")
    else:
        # Native alert modal listing missing channels - NO APP LINK GIVEN
        ch_list = "\n• ".join([c.get("name") or str(c.get("id")) for c in missing_channels])
        await query.answer(
            f"❌ You have not joined all channels yet!\n\nPlease join:\n• {ch_list}\n\nThen tap Verify again.",
            show_alert=True,
        )


verify_join = check_membership


async def check_spins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User command /spins or /balance to check their stats."""
    if not update.effective_user or not update.message:
        return

    user_id = str(update.effective_user.id)
    first_name = update.effective_user.first_name or "Friend"

    all_joined, missing_channels = await check_user_channels_membership(context.bot, int(user_id))
    if not all_joined:
        await update.message.reply_html(
            "⚠️ <b>Pehle Sabhi Channels Join Karein!</b>\n\n"
            "Giveaway app aur balance unlock karne ke liye sabhi channels join karke Verify karein:",
            reply_markup=build_join_keyboard(missing_channels),
        )
        return

    db_user = get_user_from_db(user_id)
    if db_user:
        spins = db_user.get("spins", 0)
        friends = db_user.get("friendsJoined", 0)
        balance = db_user.get("balance", 0)
        text = (
            f"👤 <b>Account Stats for {first_name}:</b>\n\n"
            f"🎡 <b>Available Spins:</b> {spins}\n"
            f"👥 <b>Friends Joined:</b> {friends}\n"
            f"💰 <b>Wallet Balance:</b> ₹{balance:.2f}\n\n"
            "👉 Open the app to spin or withdraw cash!"
        )
    else:
        text = (
            f"👋 Hello {first_name}!\n\n"
            "🎁 You have <b>1 Free Sign Up Spin</b> waiting in the app!\n"
            "Tap below to open and start winning cash!"
        )

    await update.message.reply_html(
        text,
        reply_markup=build_success_keyboard(),
    )


# ----------------- OWNER COMMANDS & MANAGEMENT -----------------

async def owner_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /ownerhelp command:
    ONLY works if user's ID or username is registered in DEFAULT_OWNERS or Firebase!
    """
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    user_id = user.id
    username = user.username or ""

    if not is_owner(user_id, username):
        await update.message.reply_html(
            "⛔ <b>Access Denied!</b>\n\n"
            "This command is restricted. Only authorized bot owners can use <code>/ownerhelp</code>."
        )
        logger.warning(f"Unauthorized /ownerhelp attempt by ID: {user_id}, @{username}")
        return

    channels = load_channels_from_db()
    owners = load_owners_from_db()

    help_text = (
        "👑 <b>ROHIT GIVEAWAY - OWNER CONTROL PANEL</b>\n\n"
        "Welcome Owner! Yahan se aap Public & Private channels add/remove kar sakte hain.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📢 <b>CHANNEL MANAGEMENT COMMANDS:</b>\n\n"
        "1️⃣ <b>Public Channel Add Karein:</b>\n"
        "<code>/addchannel @channel_username [Channel Name]</code>\n"
        "<i>Example:</i> <code>/addchannel @sauravsanganya Official Channel</code>\n\n"
        "2️⃣ <b>Private Channel Add Karein:</b>\n"
        "<code>/addchannel &lt;chat_id&gt; &lt;invite_link&gt; [Channel Name]</code>\n"
        "<i>Example:</i> <code>/addchannel -1002345678901 https://t.me/+AbCdEfGh VIP Private Channel</code>\n"
        "<i>(Note: Bot channel me Admin hona chahiye)</i>\n\n"
        "3️⃣ <b>Channel Remove Karein:</b>\n"
        "<code>/removechannel &lt;@username ya chat_id&gt;</code>\n\n"
        "4️⃣ <b>Sabhi Channels Dekhein:</b>\n"
        "<code>/channels</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👥 <b>OWNER ACCESS:</b>\n"
        "• <code>/addowner &lt;user_id ya @username&gt;</code>\n"
        "• <code>/delowner &lt;user_id ya @username&gt;</code>\n"
        "• <code>/owners</code> - <i>Authorized owners list</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💳 <b>FINANCE & BROADCAST:</b>\n"
        "• <code>/withdrawals</code> - <i>Pending withdrawal requests</i>\n"
        "• <code>/broadcast &lt;message&gt;</code> - <i>Send notice to all users</i>\n\n"
        f"📊 <b>Active Channels:</b> {len(channels)} | <b>Owners:</b> {len(owners)}"
    )

    await update.message.reply_html(
        help_text,
        reply_markup=build_owner_panel_keyboard(),
    )


async def add_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /addchannel command:
    Supports Public (@channel) and Private (-100... + invite link) channels!
    """
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    if not is_owner(user.id, user.username):
        await update.message.reply_html("⛔ <b>Access Denied!</b> Only owners can add channels.")
        return

    if not context.args or len(context.args) == 0:
        await update.message.reply_html(
            "⚠️ <b>Usage:</b>\n\n"
            "<b>Public Channel:</b>\n"
            "<code>/addchannel @username Channel Name</code>\n\n"
            "<b>Private Channel:</b>\n"
            "<code>/addchannel -1001234567890 https://t.me/+joinlink VIP Channel</code>"
        )
        return

    arg0 = context.args[0].strip()

    # Check if this is a Private Channel with ID (-100...)
    if arg0.startswith("-100") or (arg0.startswith("-") and arg0[1:].isdigit()):
        channel_id = arg0
        if len(context.args) < 2:
            await update.message.reply_html(
                "⚠️ Private channel ke liye invite link bhi zaroori hai:\n"
                "<code>/addchannel -100xxxxxxxxxx https://t.me/+xxxxxx Channel Name</code>"
            )
            return

        channel_url = context.args[1].strip()
        title = " ".join(context.args[2:]).strip() if len(context.args) > 2 else f"Private Channel {channel_id}"
        is_private = True
    else:
        # Public Channel: handle @username or https://t.me/username
        match = re.search(r"t\.me/([a-zA-Z0-9_]+)", arg0)
        if match:
            uname = match.group(1)
            channel_id = f"@{uname}"
            channel_url = f"https://t.me/{uname}"
        else:
            channel_id = f"@{arg0.lstrip('@')}"
            channel_url = f"https://t.me/{arg0.lstrip('@')}"

        title = " ".join(context.args[1:]).strip() if len(context.args) > 1 else channel_id
        is_private = False

    status_msg = await update.message.reply_text(f"🔄 Checking access to {channel_id}...")

    # Verify if bot can access the chat
    try:
        target_chat = int(channel_id) if is_private else channel_id
        chat = await context.bot.get_chat(chat_id=target_chat)
        if chat.title and (not title or title == channel_id):
            title = chat.title
        if not is_private and chat.username:
            channel_url = f"https://t.me/{chat.username}"
    except Exception as e:
        logger.warning(f"Could not verify chat with get_chat: {e}")

    channel_info = {
        "id": channel_id,
        "name": title,
        "url": channel_url,
        "is_private": is_private,
        "addedBy": str(user.id),
        "addedAt": int(time.time() * 1000),
    }

    success = save_channel_to_db(channel_info)

    if success:
        # Also update web settings if it's the primary channel
        if not is_private:
            try:
                req = urllib.request.Request(
                    f"{RTDB_URL}/settings.json",
                    data=json.dumps({"telegramChannelUrl": channel_url}).encode("utf-8"),
                    method="PATCH",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=5):
                    pass
            except Exception:
                pass

        kind = "🔒 Private" if is_private else "📢 Public"
        await status_msg.edit_text(
            f"✅ <b>{kind} Channel Successfully Added!</b>\n\n"
            f"🏷️ <b>Name:</b> {title}\n"
            f"🆔 <b>ID:</b> <code>{channel_id}</code>\n"
            f"🔗 <b>Link:</b> {channel_url}\n\n"
            f"Ab jab tak koi user is channel me join nahi hoga, tab tak giveaway app link nahi milega!",
            parse_mode="HTML",
        )
    else:
        await status_msg.edit_text("❌ Failed to save channel to database. Please check connection.")


async def remove_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /removechannel <@channel_username or id>
    Removes a channel from mandatory verification.
    """
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    if not is_owner(user.id, user.username):
        await update.message.reply_html("⛔ <b>Access Denied!</b> Only owners can remove channels.")
        return

    if not context.args or len(context.args) == 0:
        channels = load_channels_from_db()
        lines = [f"• <code>{c.get('id')}</code> ({c.get('name')})" for c in channels]
        await update.message.reply_html(
            "⚠️ <b>Usage:</b>\n<code>/removechannel &lt;@username ya chat_id&gt;</code>\n\n"
            "<b>Current Active Channels:</b>\n" + ("\n".join(lines) if lines else "None")
        )
        return

    raw_ident = context.args[0].strip()
    success = delete_channel_from_db(raw_ident)
    if success:
        await update.message.reply_html(
            f"🗑️ <b>Channel Removed!</b>\n\n"
            f"Channel <code>{raw_ident}</code> has been removed from mandatory verification."
        )
    else:
        await update.message.reply_html("❌ Could not remove channel from database.")


async def list_channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/channels command: Lists all mandatory verification channels (Public & Private)."""
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    if not is_owner(user.id, user.username):
        await update.message.reply_html("⛔ <b>Access Denied!</b>")
        return

    channels = load_channels_from_db()
    if not channels:
        await update.message.reply_html(
            "ℹ️ No mandatory channels configured.\nUse <code>/addchannel @username</code> to add one!"
        )
        return

    text = f"📢 <b>Mandatory Verification Channels ({len(channels)}):</b>\n\n"
    for i, ch in enumerate(channels, 1):
        name = ch.get("name") or "Channel"
        cid = ch.get("id")
        url = ch.get("url") or "No link"
        kind = "🔒 Private" if ch.get("is_private") else "📢 Public"
        text += f"<b>{i}. {name}</b> ({kind})\n   ID: <code>{cid}</code>\n   Link: {url}\n\n"

    text += "💡 To add a public channel: <code>/addchannel @channel_name</code>\n💡 To add private: <code>/addchannel &lt;id&gt; &lt;link&gt; Title</code>\n💡 To remove: <code>/removechannel &lt;id/name&gt;</code>"
    await update.message.reply_html(text)


async def add_owner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/addowner <user_id or @username>"""
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    if not is_owner(user.id, user.username):
        await update.message.reply_html("⛔ <b>Access Denied!</b>")
        return

    if not context.args or len(context.args) == 0:
        await update.message.reply_html("⚠️ <b>Usage:</b> <code>/addowner &lt;user_id or @username&gt;</code>")
        return

    new_owner = context.args[0].strip()
    save_owner_to_db(new_owner)
    await update.message.reply_html(f"✅ User <code>{new_owner}</code> has been added as an authorized Bot Owner!")


async def del_owner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/delowner <user_id or @username>"""
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    if not is_owner(user.id, user.username):
        await update.message.reply_html("⛔ <b>Access Denied!</b>")
        return

    if not context.args or len(context.args) == 0:
        await update.message.reply_html("⚠️ <b>Usage:</b> <code>/delowner &lt;user_id or @username&gt;</code>")
        return

    target = context.args[0].strip()
    delete_owner_from_db(target)
    await update.message.reply_html(f"🗑️ Removed <code>{target}</code> from Owner privileges.")


async def list_owners_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/owners command to list all authorized owners."""
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    if not is_owner(user.id, user.username):
        await update.message.reply_html("⛔ <b>Access Denied!</b>")
        return

    owners = load_owners_from_db()
    text = "👑 <b>Authorized Bot Owners:</b>\n\n"
    for o in sorted(owners):
        text += f"• <code>{o}</code>\n"
    text += "\nTo add another owner: <code>/addowner &lt;id or @username&gt;</code>"
    await update.message.reply_html(text)


async def check_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command /withdrawals or /payouts to check pending requests in Telegram chat."""
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    if not is_owner(user.id, user.username):
        await update.message.reply_html("⛔ <b>Access Denied!</b>")
        return

    status_msg = await update.message.reply_text("🔄 Checking Firebase database for withdrawals...")

    try:
        req = urllib.request.Request(
            f"{RTDB_URL}/withdrawals.json",
            headers={"User-Agent": "TelegramBot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if not data:
            await status_msg.edit_text("ℹ️ No withdrawal requests found in database.")
            return

        items = list(data.values()) if isinstance(data, dict) else data
        pending = [x for x in items if isinstance(x, dict) and x.get("status") == "pending"]

        if not pending:
            await status_msg.edit_text(f"✅ Total {len(items)} withdrawals on record. 0 Pending!")
            return

        text = f"⚡ <b>Found {len(pending)} PENDING Withdrawal(s):</b>\n\n"
        for i, w in enumerate(pending[:10], start=1):
            amt = w.get("amount", 0)
            user_name = w.get("userName", "User")
            user_id = w.get("userId", "N/A")
            method = w.get("method", "upi").upper()
            detail = w.get("upiId") if method == "UPI" else f"A/C: {w.get('accountNumber')} (IFSC: {w.get('ifsc')})"
            text += f"<b>{i}. ₹{amt}</b> by {user_name} (#{user_id})\n   Type: {method} ({detail})\n\n"

        await status_msg.edit_text(text, parse_mode="HTML")
    except Exception as e:
        await status_msg.edit_text(f"❌ Error fetching withdrawals: {e}")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/broadcast <message> - Owner command to send notification to users."""
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    if not is_owner(user.id, user.username):
        await update.message.reply_html("⛔ <b>Access Denied!</b>")
        return

    if not context.args or len(context.args) == 0:
        await update.message.reply_html("⚠️ <b>Usage:</b> <code>/broadcast &lt;Your message here&gt;</code>")
        return

    broadcast_text = " ".join(context.args)
    status_msg = await update.message.reply_text("🔄 Preparing broadcast to all users...")

    try:
        req = urllib.request.Request(f"{RTDB_URL}/users.json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if not data or not isinstance(data, dict):
            await status_msg.edit_text("ℹ️ No users found in database to broadcast.")
            return

        user_ids = list(data.keys())
        sent = 0
        failed = 0

        for uid in user_ids:
            if uid.isdigit():
                try:
                    await context.bot.send_message(
                        chat_id=int(uid),
                        text=f"📢 <b>Announcement:</b>\n\n{broadcast_text}",
                        parse_mode="HTML",
                        reply_markup=build_success_keyboard(),
                    )
                    sent += 1
                except Exception:
                    failed += 1
                time.sleep(0.04)  # Safe rate limit

        await status_msg.edit_text(f"✅ Broadcast finished!\nDelivered: {sent} | Inactive: {failed}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Error in broadcast: {e}")


# ----------------- Owner Callback Query Handlers -----------------
async def owner_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route callbacks for owner interactive control buttons."""
    query = update.callback_query
    if not query or not query.data:
        return

    user_id = query.from_user.id
    username = query.from_user.username or ""

    if not is_owner(user_id, username):
        await query.answer("⛔ Only authorized owners can use these actions.", show_alert=True)
        return

    data = query.data

    if data == "owner_channels":
        await query.answer()
        channels = load_channels_from_db()
        text = f"📢 <b>Active Channels ({len(channels)}):</b>\n\n"
        for i, ch in enumerate(channels, 1):
            kind = "🔒 Private" if ch.get("is_private") else "📢 Public"
            text += f"<b>{i}. {ch.get('name')}</b> ({kind})\nID: <code>{ch.get('id')}</code>\nLink: {ch.get('url')}\n\n"
        text += "To add public: <code>/addchannel @channel_name</code>\nTo add private: <code>/addchannel &lt;id&gt; &lt;link&gt; Title</code>\nTo remove: <code>/removechannel &lt;id/name&gt;</code>"
        await query.message.reply_html(text)

    elif data == "owner_addchannel_guide":
        await query.answer()
        guide = (
            "➕ <b>HOW TO ADD CHANNELS:</b>\n\n"
            "<b>1. Public Channel:</b>\n"
            "<code>/addchannel @channel_username Channel Name</code>\n\n"
            "<b>2. Private Channel:</b>\n"
            "<code>/addchannel -1001234567890 https://t.me/+joinlink Channel Name</code>\n\n"
            "<i>(Zaroori: Bot ko channel me Administrator banayein with Invite Users permission!)</i>"
        )
        await query.message.reply_html(guide)

    elif data == "owner_list":
        await query.answer()
        owners = load_owners_from_db()
        text = "👑 <b>Authorized Owners:</b>\n\n" + "\n".join([f"• <code>{o}</code>" for o in sorted(owners)])
        text += "\n\nAdd new: <code>/addowner &lt;id or username&gt;</code>"
        await query.message.reply_html(text)

    elif data == "owner_withdrawals":
        await query.answer()
        await check_withdrawals(update, context)


# ----------------- Error Handler -----------------
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Suppress harmless network errors and log unexpected issues."""
    err = context.error
    if isinstance(err, (TimedOut, NetworkError)):
        logger.warning(f"Transient network notice: {err}")
    elif isinstance(err, BadRequest) and "Message is not modified" in str(err):
        pass
    else:
        logger.error(f"Telegram Exception encountered: {err}")


# ----------------- Main Bot Lifecycle -----------------
def main():
    """Start Telegram bot with high resilience against network drops."""
    logger.info("Initializing Rohit Giveaway Telegram Bot...")

    load_channels_from_db()
    load_owners_from_db()

    request = HTTPXRequest(
        connect_timeout=25.0,
        read_timeout=25.0,
        write_timeout=25.0,
        pool_timeout=25.0,
    )

    app = ApplicationBuilder().token(TOKEN).request(request).build()

    # User commands (Gatekept by channel check)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["invite", "link", "referral"], invite_command))
    app.add_handler(CommandHandler(["spins", "balance", "stats"], check_spins))

    # Owner commands (Protected by is_owner check)
    app.add_handler(CommandHandler(["ownerhelp", "owner", "adminhelp"], owner_help_command))
    app.add_handler(CommandHandler(["addchannel", "newchannel"], add_channel_command))
    app.add_handler(CommandHandler(["removechannel", "delchannel"], remove_channel_command))
    app.add_handler(CommandHandler(["channels", "listchannels"], list_channels_command))
    app.add_handler(CommandHandler("addowner", add_owner_command))
    app.add_handler(CommandHandler("delowner", del_owner_command))
    app.add_handler(CommandHandler("owners", list_owners_command))
    app.add_handler(CommandHandler(["withdrawals", "payouts"], check_withdrawals))
    app.add_handler(CommandHandler("broadcast", broadcast_command))

    # Callback Query Handlers
    app.add_handler(CallbackQueryHandler(check_membership, pattern=r"^check_"))
    app.add_handler(CallbackQueryHandler(owner_callback_router, pattern=r"^owner_"))

    # Error handling
    app.add_error_handler(global_error_handler)

    logger.info(f"Bot @{BOT_USERNAME} successfully started! Running polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
