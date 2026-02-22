import os
import re
from datetime import datetime
from asgiref.sync import async_to_sync
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError

from Trade.models.models import TradeRequest, TradeOffer

BOT_USERNAME = "excoinmarket_bot"

STATUS_EMOJI = {
    "PENDING": "📥",
    "ACCEPTED": "✅",
    "REJECTED": "❌",
}

MARKER = "👥 *پیشنهادها:*"


# -----------------------
# Keyboards
# -----------------------
def build_offer_manage_keyboard(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید", callback_data=f"offer_accept:{offer_id}"),
            InlineKeyboardButton("❌ رد", callback_data=f"offer_reject:{offer_id}"),
        ],
        [InlineKeyboardButton("👤 اطلاعات کاربر", callback_data=f"offer_user:{offer_id}")]
    ])


def build_offer_after_accept_keyboard(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 اطلاعات کاربر", callback_data=f"offer_user:{offer_id}")]
    ])


def build_channel_keyboard(req_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 پیشنهاد بده", url=f"https://t.me/{BOT_USERNAME}?start=offer_{req_id}")]
    ])


# -----------------------
# Channel link helper
# -----------------------
def channel_post_link(req: TradeRequest) -> str | None:
    """
    اگر کانال public username داشته باشی بهتره از اون بسازی.
    ولی اگر نداری، با chat_id=-100xxxx و message_id میشه t.me/c/... ساخت.
    """
    msg_id = getattr(req, "channel_message_id", None)
    chat_id = getattr(req, "channel_chat_id", None)
    if not msg_id or not chat_id:
        return None

    # public username option (اگر داری)
    username = getattr(req, "channel_username", None)  # اگر فیلد نداری، None میمونه
    if username:
        return f"https://t.me/{username}/{msg_id}"

    # private/supergroup style: -1001234567890 -> 1234567890 -> remove leading 100 => 1234567890? (Telegram uses /c/<id_without_-100>/<msg>)
    s = str(chat_id)
    if s.startswith("-100"):
        internal = s[4:]
        return f"https://t.me/c/{internal}/{msg_id}"

    return None


# -----------------------
# Rendering
# -----------------------
def _emoji_for(status: str) -> str:
    return STATUS_EMOJI.get(status, STATUS_EMOJI["PENDING"])


def _offer_line_text(offer: TradeOffer, status: str) -> str:
    # پیشنهاددهنده و آیدی نیاد؛ فقط ساعت و مبلغ
    t = getattr(offer, "created_at", None)
    if isinstance(t, datetime):
        t_str = t.strftime("%H:%M")
    else:
        t_str = "—"

    price = getattr(offer, "unit_price_irt", None)
    price_str = f"{price:,}" if isinstance(price, int) else (str(price) if price is not None else "—")

    return f"{_emoji_for(status)} ⏰ {t_str} | 💰 {price_str} تومان"


def _split_base_text(base_text: str) -> tuple[str, list[str]]:
    if MARKER not in base_text:
        return base_text.rstrip(), []
    head, tail = base_text.split(MARKER, 1)
    lines = [ln.rstrip() for ln in tail.strip().splitlines() if ln.strip()]
    return head.rstrip(), lines


def _extract_offer_id(line: str) -> int | None:
    m = re.search(r"\[\s*(\d+)\s*\]", line or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _wrap_with_offer_id(offer_id: int, line: str) -> str:
    # برای اینکه بتونیم همان offer را update کنیم، یک tag مخفی/متنی می‌گذاریم
    # اما “آیدی پیشنهاد” نمایش داده نمیشه چون داخل [] هست و خودت قبلاً می‌خواستی نیاد.
    # اگر می‌خوای کلاً حتی داخل متن هم نباشه، باید ساختار ذخیره جداگانه داشته باشی.
    return f"[{offer_id}] {line}"


def _strip_visible_id_part(line: str) -> str:
    # فقط برای normalizing نمایش (اگر لازم شد) — فعلاً استفاده نمی‌کنیم
    return re.sub(r"^\[\s*\d+\s*\]\s*", "", (line or "")).strip()


# -----------------------
# Core: Upsert
# -----------------------
def upsert_offer_line_in_channel(req_id: int, offer_id: int, status: str = "PENDING") -> bool:
    token = os.environ.get("API_TOKEN")
    if not token:
        print("API_TOKEN not set")
        return False

    req = TradeRequest.objects.filter(pk=req_id).first()
    if not req:
        print("TradeRequest not found:", req_id)
        return False

    if not req.channel_chat_id or not req.channel_message_id:
        print("No channel message info to edit")
        return False

    base_text = (req.channel_post_text or "").strip()
    if not base_text:
        print("No channel_post_text to edit from")
        return False

    offer = TradeOffer.objects.filter(pk=offer_id).first()
    if not offer:
        print("TradeOffer not found:", offer_id)
        return False

    new_line_visible = _offer_line_text(offer, status=status)
    new_line = _wrap_with_offer_id(offer_id, new_line_visible)

    head, lines = _split_base_text(base_text)

    found = False
    for i, ln in enumerate(lines):
        if _extract_offer_id(ln) == offer_id:
            lines[i] = new_line
            found = True
            break

    if not found:
        lines.append(new_line)

    # dedupe by offer_id
    deduped = []
    seen_ids = set()
    for ln in reversed(lines):
        oid = _extract_offer_id(ln)
        if oid is None:
            deduped.append(ln)
            continue
        if oid in seen_ids:
            continue
        seen_ids.add(oid)
        deduped.append(ln)
    lines = list(reversed(deduped))

    if lines:
        # نمایش نهایی: id مخفی داخل [] هست ولی می‌تونی اگر خواستی حذفش کنی:
        # نمایش واقعی: متن را بدون [] بساز اما برای update بعدی id لازم است.
        new_text = head + "\n\n" + MARKER + "\n" + "\n".join(lines) + "\n"
    else:
        new_text = head

    # CLOSED check robust
    CLOSED = getattr(TradeRequest.Status, "CLOSED", "CLOSED")
    is_closed = (getattr(req, "status", None) == CLOSED)

    bot = Bot(token=token)

    try:
        async_to_sync(bot.edit_message_text)(
            chat_id=req.channel_chat_id,
            message_id=req.channel_message_id,
            text=new_text,
            parse_mode="Markdown",
            reply_markup=None if is_closed else build_channel_keyboard(req.id),
            disable_web_page_preview=True,
        )
        TradeRequest.objects.filter(pk=req.pk).update(channel_post_text=new_text)
        return True

    except TelegramError as e:
        print("TELEGRAM channel edit ERROR:", repr(e))
        return False
    except Exception as e:
        print("TELEGRAM channel edit ERROR:", type(e), repr(e))
        return False


def set_offer_status_in_channel(req_id: int, offer_id: int, status: str) -> bool:
    return upsert_offer_line_in_channel(
        req_id=req_id,
        offer_id=offer_id,
        status=status,
    )