import os
import re
from asgiref.sync import async_to_sync
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError

from Trade.models.models import TradeRequest

BOT_USERNAME = "excoinmarket_bot"

STATUS_EMOJI = {
    "PENDING": "📥",
    "ACCEPTED": "✅",
    "REJECTED": "❌",
}

MARKER = "👥 *پیشنهاددهنده‌ها:*"


# -----------------------
# Keyboards
# -----------------------
def build_offer_manage_keyboard(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید", callback_data=f"offer_accept:{offer_id}"),
            InlineKeyboardButton("❌ رد", callback_data=f"offer_reject:{offer_id}"),
        ],
        [
            InlineKeyboardButton("👤 اطلاعات کاربر", callback_data=f"offer_user:{offer_id}")
        ]
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
# Messages
# -----------------------
def build_offer_message(offer):
    user = offer.sender
    joined = user.date_joined.strftime("%Y/%m/%d")

    return (
        f"📩 *پیشنهاد جدید*  |  🆔 پیشنهاد: #{offer.id}\n\n"
        f"💰 نرخ پیشنهادی: {offer.unit_price_irt:,} تومان\n"
        f"📝 توضیحات: {offer.message or '—'}\n\n"
    )


# -----------------------
# Helpers
# -----------------------
def _emoji_for(status: str) -> str:
    return STATUS_EMOJI.get(status, STATUS_EMOJI["PENDING"])


def _render_offer_line(offer_id: int, offer_name: str, status: str) -> str:
    return f"{_emoji_for(status)} [{offer_id}] {offer_name}".strip()


def _normalize_line_text(s: str) -> str:
    if not s:
        return ""

    s = s.strip()

    for emo in STATUS_EMOJI.values():
        s = s.replace(emo, "")

    s = re.sub(r"\[\s*\d+\s*\]", "", s)

    s = " ".join(s.split()).strip()
    return s


def _extract_offer_id(line: str) -> int | None:
    m = re.search(r"\[\s*(\d+)\s*\]", line or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _split_base_text(base_text: str) -> tuple[str, list[str]]:
    if MARKER not in base_text:
        return base_text.rstrip(), []

    head, tail = base_text.split(MARKER, 1)
    lines = [ln.rstrip() for ln in tail.strip().splitlines() if ln.strip()]
    return head.rstrip(), lines


# -----------------------
# Core: Upsert
# -----------------------
def upsert_offer_line_in_channel(req_id: int, offer_id: int, offer_name: str, status: str = "PENDING") -> bool:
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

    new_line = _render_offer_line(offer_id=offer_id, offer_name=offer_name, status=status)

    head, lines = _split_base_text(base_text)

    found = False
    for i, ln in enumerate(lines):
        existing_id = _extract_offer_id(ln)
        if existing_id == offer_id:
            lines[i] = new_line
            found = True
            break

    if not found:
        name_norm = _normalize_line_text(offer_name)
        if name_norm:
            for i, ln in enumerate(lines):
                if _extract_offer_id(ln) is None and _normalize_line_text(ln) == name_norm:
                    lines[i] = new_line
                    found = True
                    break

    if not found:
        lines.append(new_line)

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
        new_text = head + "\n\n" + MARKER + "\n" + "\n".join(lines) + "\n"
    else:
        new_text = head

    bot = Bot(token=token)

    try:
        async_to_sync(bot.edit_message_text)(
            chat_id=req.channel_chat_id,
            message_id=req.channel_message_id,
            text=new_text,
            parse_mode="Markdown",
            reply_markup=None if req.status == TradeRequest.Status.CLOSED else build_channel_keyboard(req.id),
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


# -----------------------
# Wrappers
# -----------------------
def add_offer_name_to_channel(req_id: int, offer_name: str, offer_id: int) -> bool:
    return upsert_offer_line_in_channel(
        req_id=req_id,
        offer_id=offer_id,
        offer_name=offer_name,
        status="PENDING",
    )


def set_offer_status_in_channel(req_id: int, offer_id: int, offer_name: str, status: str) -> bool:
    return upsert_offer_line_in_channel(
        req_id=req_id,
        offer_id=offer_id,
        offer_name=offer_name,
        status=status,
    )

def channel_post_link(req: TradeRequest) -> str | None:
    try:
        msg_id = getattr(req, "channel_message_id", None)
        chat_id = getattr(req, "channel_chat_id", None)

        username = getattr(req, "channel_username", None)

        if not msg_id or not chat_id:
            return None

        if username:
            u = str(username).lstrip("@")
            return f"https://t.me/{u}/{int(msg_id)}"

        s = str(chat_id)
        if s.startswith("-100"):
            internal = s.replace("-100", "", 1)
            return f"https://t.me/c/{internal}/{int(msg_id)}"

        return None
    except Exception:
        return None