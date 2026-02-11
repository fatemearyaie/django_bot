import os
from asgiref.sync import async_to_sync
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError
from Trade.models.models import TradeRequest

BOT_USERNAME = None

def init_bot_username():
    global BOT_USERNAME
    token = os.environ["API_TOKEN"]
    me = async_to_sync(Bot(token=token).get_me)()
    BOT_USERNAME = me.username


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


def add_offer_name_to_channel(req_id: int, offer_name: str) -> bool:
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

    base_text = req.channel_post_text or ""
    if not base_text.strip():
        print("No channel_post_text to edit from")
        return False

    marker = "👥 *پیشنهاددهنده‌ها:*"

    if marker in base_text:
        head, tail = base_text.split(marker, 1)
        existing = [x.strip().lstrip("•").strip() for x in tail.strip().splitlines() if x.strip()]
        if offer_name not in existing:
            existing.append(offer_name)
        lines = "\n".join([f"• {n}" for n in existing])
        new_text = head.rstrip() + "\n\n" + marker + "\n" + lines + "\n"
    else:
        new_text = base_text.rstrip() + "\n\n" + marker + "\n" + f"• {offer_name}\n"

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
