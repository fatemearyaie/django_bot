from __future__ import annotations

from asgiref.sync import sync_to_async
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from Trade.models.models import TradeRequest

START_CURRENCY_PREFIX = "cur_"

CUR_LABEL = {"USD": "دلار", "EUR": "یورو", "AED": "درهم"}

PAGE_SIZE = 1


# Build the public/private Telegram channel link for a request post.
def build_channel_link(req: TradeRequest) -> str | None:
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


# Return the request id as markdown text, linked to the channel post if available.
def _req_id_text_md(req: TradeRequest) -> str:
    link = build_channel_link(req)
    if link:
        return f"[#{req.id}]({link})"
    return f"#{req.id}"


# Convert request role to Persian label.
def _role_fa(role: str) -> str:
    return "خریدار" if role == TradeRequest.Role.BUYER else "فروشنده"


# Convert internal status value to Persian display text.
def _status_fa(status: str) -> str:
    mapping = {
        TradeRequest.Status.DRAFT: "پیش‌نویس",
        TradeRequest.Status.PENDING_ADMIN: "در انتظار تایید ادمین",
        TradeRequest.Status.APPROVED: "✅ فعال",
        TradeRequest.Status.CLOSED: "⛔️ بسته شده",
    }
    return mapping.get(status, status)


# Fetch approved requests for a currency with manual pagination.
@sync_to_async
def _fetch_active_requests(currency: str, page: int):
    qs = (
        TradeRequest.objects
        .filter(currency=currency, status=TradeRequest.Status.APPROVED)
        .order_by("-created_at")
    )
    total = qs.count()
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    return list(qs[start:end]), total


# Build pagination keyboard for browsing request pages.
def _pagination_kb(currency: str, page: int, total: int) -> InlineKeyboardMarkup:
    max_page = max((total - 1) // PAGE_SIZE, 0)
    rows = []

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"curreq:{currency}:{page-1}"))
    if page < max_page:
        nav.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"curreq:{currency}:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="curreq:home")])
    return InlineKeyboardMarkup(rows)


# Render and send/edit the paginated request message for a selected currency.
async def _send_currency_requests(message_obj, currency: str, page: int, *, edit: bool):
    items, total = await _fetch_active_requests(currency, page)

    if total == 0:
        text = f"📭 الان برای *{CUR_LABEL.get(currency, currency)}* هیچ آگهی فعالی نداریم."
        if edit:
            await message_obj.edit_text(text, parse_mode="Markdown")
        else:
            await message_obj.reply_text(text, parse_mode="Markdown")
        return

    max_page = max((total - 1) // PAGE_SIZE, 0)
    page = max(0, min(page, max_page))
    items, total = await _fetch_active_requests(currency, page)
    r = items[0]

    req_id_md = _req_id_text_md(r)
    deal_method_fa = r.get_deal_method_display() if getattr(r, "deal_method", None) else "—"

    text = (
        f"📌 *آگهی‌های فعال {CUR_LABEL.get(currency, currency)}* (صفحه {page+1} از {max_page+1})\n\n"
        f"🆔 درخواست: {req_id_md}\n"
        f"👤 نقش: {_role_fa(r.role)} | 💱 ارز: {r.currency}\n"
        f"💰 مقدار: {r.amount}\n"
        f"🏷 قیمت واحد: {r.unit_price_irt:,} تومان\n"
        f"💳 روش معامله: {deal_method_fa}\n"
        f"📝 توضیحات: {r.description or '—'}\n"
        f"📌 وضعیت: {_status_fa(r.status)}\n"
    )

    kb = _pagination_kb(currency, page, total)

    if edit:
        await message_obj.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    else:
        await message_obj.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=kb,
            disable_web_page_preview=True,
        )


# Handle /start deep-link entry and open the first page for the selected currency.
async def start_currency_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return

    if not context.args:
        return

    arg = str(context.args[0]).strip()
    if not arg.startswith(START_CURRENCY_PREFIX):
        return

    currency = arg.replace(START_CURRENCY_PREFIX, "", 1).upper().strip()
    if currency not in {"USD", "EUR", "AED"}:
        await msg.reply_text("❌ ارز نامعتبره.")
        return

    await _send_currency_requests(msg, currency, page=0, edit=False)


# Handle pagination callbacks and home navigation.
async def currency_requests_page_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    if q.data == "curreq:home":
        from bot.handlers import build_main_menu_keyboard
        await q.message.reply_text("🏠 برگشتی به منوی اصلی.", reply_markup=build_main_menu_keyboard())
        return

    try:
        _, cur, page_str = q.data.split(":")
        page = int(page_str)
        cur = cur.upper()
    except Exception:
        return

    if cur not in {"USD", "EUR", "AED"}:
        return

    await _send_currency_requests(q.message, cur, page=page, edit=True)


# Register command and callback handlers for currency request browsing.
def get_currency_requests_handlers():
    return [
        CommandHandler("start", start_currency_entry),
        CallbackQueryHandler(currency_requests_page_cb, pattern=r"^curreq:(USD|EUR|AED):\d+$"),
        CallbackQueryHandler(currency_requests_page_cb, pattern=r"^curreq:home$"),
    ]