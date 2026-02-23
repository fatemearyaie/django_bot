import os
from asgiref.sync import async_to_sync
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton

from Trade.models.models import TradeRequest
from bot.flow.registration import build_main_menu_keyboard

CHANNEL = "@excoinmarket"          # یا بهتر: channel id عددی
BOT_USERNAME = "excoinmarket_bot"


def build_channel_post_text(req: TradeRequest) -> str:
    role = "خریدار" if req.role == TradeRequest.Role.BUYER else "فروشنده"

    deal_method_fa = req.get_deal_method_display() if getattr(req, "deal_method", None) else "—"
    currency_fa = req.get_currency_display() if getattr(req, "currency", None) else "—"

    amount_text = f"{req.amount:,}" if req.amount is not None else "—"

    unit_price_text = f"{req.unit_price_irt:,}" if req.unit_price_irt is not None else "—"

    return (
        f"📌 درخواست {req.id} \n\n"
        f"👤{role} {amount_text} {currency_fa}\n"
        f"🏷 *قیمت هر واحد (تومان):* {unit_price_text}\n\n"
        f"💳 *روش معامله:* {deal_method_fa}\n"
        f"📝 توضیحات: {req.description or '—'}\n\n\n"
        "\n——————————————\n\n"
    )

def build_channel_keyboard(req_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 پیشنهاد بده", url=f"https://t.me/{BOT_USERNAME}?start=offer_{req_id}")]
    ])


def publish_trade_request_to_channel(req_id: int) -> bool:
    token = os.environ.get("API_TOKEN")
    if not token:
        print("API_TOKEN not set")
        return False

    req = TradeRequest.objects.select_related("owner").filter(pk=req_id).first()
    if not req:
        print("TradeRequest not found:", req_id)
        return False



    bot = Bot(token=token)
    text = build_channel_post_text(req)

    try:
        msg = async_to_sync(bot.send_message)(
            chat_id=CHANNEL,
            text=text,
            parse_mode="Markdown",
            reply_markup=build_channel_keyboard(req.id),
            disable_web_page_preview=True,
        )

        TradeRequest.objects.filter(pk=req.pk).update(
            channel_chat_id=msg.chat.id,
            channel_message_id=msg.message_id,
            channel_post_text=text,
        )

        try:
            if req.owner and req.owner.telegram_id:
                async_to_sync(bot.send_message)(
                    chat_id=req.owner.telegram_id,
                    text=f"✅ درخواست شما (#{req.id}) منتشر شد و در کانال نمایش داده شد اگر احتیاج به حذف یا ویرایش داری با ادمین تماس بگیر.",
                    reply_markup=build_main_menu_keyboard(),

                )
        except Exception as e:
            print("TELEGRAM owner notify ERROR:", type(e), repr(e))

        return True

    except Exception as e:
        print("❌ Channel publish failed:", type(e), repr(e))
        return False