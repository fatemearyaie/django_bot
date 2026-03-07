import os
from asgiref.sync import async_to_sync
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton

from Trade.models.models import TradeRequest
from bot.flow.registration import build_main_menu_keyboard
from html import escape
CHANNEL = "@excoinmarket"
BOT_USERNAME = "excoinmarket_bot"
FOOTER_PREFIX = "ثبت درخواست جدید ⬅️"


def build_channel_post_text(req: TradeRequest) -> str:
    is_buyer = req.role == TradeRequest.Role.BUYER

    role_tag = "#خرید" if is_buyer else "#فروش"
    role_label = "خرید" if is_buyer else "فروش"
    role_dot = "🟢" if is_buyer else "🔴"

    deal_method_fa = req.get_deal_method_display() if getattr(req, "deal_method", None) else "—"
    currency_fa = req.get_currency_display() if getattr(req, "currency", None) else "—"

    amount_text = f"{req.amount:,}" if req.amount is not None else "—"
    unit_price_text = f"{req.unit_price_irt:,} تومان" if req.unit_price_irt is not None else "توافقی"
    desc = escape((req.description or "").strip())
    desc_line = f"📝 توضیحات: {desc}" if desc else ""

    base_text = (
        f"📌 درخواست {req.id} | بابت {role_tag} #{currency_fa}\n\n"
        f"<b>{role_dot}  {role_label} : {amount_text} {currency_fa}</b>\n\n"
        f"<b>💬 نرخ پیشنهادی: {unit_price_text} </b>\n\n"
        f"🪧 نوع حواله: {deal_method_fa}\n"
    )

    if desc_line:
        base_text += f"{desc_line}\n"

    base_text += (
        "\n"
        "پیشنهادهای ارسال شده:\n\n"
        "ثبت درخواست جدید ⬅️ @Excoinmarket_bot"
    )

    return base_text
def build_channel_keyboard(req_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(" ثبت پیشنهاد 💬", url=f"https://t.me/{BOT_USERNAME}?start=offer_{req_id}")]
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
            parse_mode="HTML",
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
                    text=f"📄 درخواست شما با کد پیگیری (#{req.id}) در کانال منتشر شد.\nدر صورت نیاز به ویرایش یا حذف، لطفاً با پشتیبانی هماهنگ کنید.",
                    reply_markup=build_main_menu_keyboard(),
                )
        except Exception as e:
            print("TELEGRAM owner notify ERROR:", type(e), repr(e))

        return True

    except Exception as e:
        print("❌ Channel publish failed:", type(e), repr(e))
        return False