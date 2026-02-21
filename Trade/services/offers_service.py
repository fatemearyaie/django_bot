import os
from asgiref.sync import async_to_sync
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError

from Trade.models.models import TradeRequest


BOT_USERNAME = "excoinmarket_bot"

STATUS_EMOJI = {
    "PENDING": "🟡",
    "ACCEPTED": "✅",
    "REJECTED": "❌",
}


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


def build_offer_message(offer):
    user = offer.sender
    joined = user.date_joined.strftime("%Y/%m/%d")

    return (
        f"📩 *پیشنهاد جدید*  |  🆔 پیشنهاد: #{offer.id}\n\n"
        f"💰 نرخ پیشنهادی: {offer.unit_price_irt:,} تومان\n"
        f"📝 توضیحات: {offer.message or '—'}\n\n"
        f"👤 {user.name or user.username} | عضو از {joined}"
    )


def _render_offer_line(offer_id: int, offer_name: str, status: str) -> str:
    emoji = STATUS_EMOJI.get(status, "🟡")
    # مهم: (#{offer_id}) برای اینه که بعداً دقیق همون لاین رو پیدا کنیم
    return f"{emoji} {offer_name} (#{offer_id})"


def upsert_offer_line_in_channel(req_id: int, offer_id: int, offer_name: str, status: str = "PENDING") -> bool:
    """
    اگر marker وجود داشت:
      - اگر لاین (#{offer_id}) بود -> آپدیت
      - اگر نبود -> اضافه
    اگر marker نبود -> marker + لاین ساخته میشه
    """
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

    marker = "👥 *پیشنهاددهنده‌ها:*"
    new_line = _render_offer_line(offer_id=offer_id, offer_name=offer_name, status=status)

    if marker in base_text:
        head, tail = base_text.split(marker, 1)
        lines = [ln.rstrip() for ln in tail.strip().splitlines() if ln.strip()]

        target = f"(#{offer_id})"
        found = False
        for i, ln in enumerate(lines):
            if target in ln:
                lines[i] = new_line
                found = True
                break

        if not found:
            lines.append(new_line)

        new_text = head.rstrip() + "\n\n" + marker + "\n" + "\n".join(lines) + "\n"
    else:
        new_text = base_text.rstrip() + "\n\n" + marker + "\n" + new_line + "\n"

    bot = Bot(token=token)

    try:
        async_to_sync(bot.edit_message_text)(
            chat_id=req.channel_chat_id,
            message_id=req.channel_message_id,
            text=new_text,
            parse_mode="Markdown",
            reply_markup=build_channel_keyboard(req.id),
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


# برای سازگاری با اسم قبلی‌ات:
def add_offer_name_to_channel(req_id: int, offer_name: str, offer_id: int | None = None) -> bool:
    """
    قبلاً فقط اسم می‌گرفت.
    الان بهتره offer_id هم بدی.
    اگر offer_id None بود، فقط مثل قدیم اضافه می‌کنه (ولی برای آپدیت وضعیت لازم داری offer_id داشته باشی).
    """
    if offer_id is None:
        # fallback قدیمی: یک لاین pending بدون id قابل پیگیری دقیق نیست
        # پیشنهاد: از این حالت استفاده نکن
        return upsert_offer_line_in_channel(req_id=req_id, offer_id=0, offer_name=offer_name, status="PENDING")

    return upsert_offer_line_in_channel(req_id=req_id, offer_id=offer_id, offer_name=offer_name, status="PENDING")


def set_offer_status_in_channel(req_id: int, offer_id: int, offer_name: str, status: str) -> bool:
    """
    status یکی از: PENDING / ACCEPTED / REJECTED
    """
    return upsert_offer_line_in_channel(req_id=req_id, offer_id=offer_id, offer_name=offer_name, status=status)