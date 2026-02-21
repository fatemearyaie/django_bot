from decimal import Decimal, InvalidOperation
from decouple import config
from bot.handlers import build_main_menu_keyboard

from telegram import (
    Update,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove,
)

from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from asgiref.sync import sync_to_async

from Users.models import CustomUser
from Trade.models.models import TradeRequest, TradeOffer

from Trade.services.request_services import publish_trade_request_to_channel


TR_ROLE, TR_CURRENCY, TR_AMOUNT, TR_UNIT_PRICE, TR_METHOD, TR_DESC, TR_CONFIRM = range(7)

side_key = ReplyKeyboardMarkup(
    [[KeyboardButton("خریدارم"), KeyboardButton("فروشنده ام")]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

currency_key = ReplyKeyboardMarkup(
    [
        [KeyboardButton("EUR"), KeyboardButton("USD")],
        [KeyboardButton("AED")],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

method_key = ReplyKeyboardMarkup(
    [
        [KeyboardButton("انتقال آنی پی پال"), KeyboardButton("حواله بانکی")],
        [KeyboardButton("سایر"), KeyboardButton("مسترکارت")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

amount_key = ReplyKeyboardMarkup(
    [
        [KeyboardButton("100"), KeyboardButton("200"), KeyboardButton("300")],
        [KeyboardButton("400"), KeyboardButton("500"), KeyboardButton("600")],
        [KeyboardButton("700"), KeyboardButton("800"), KeyboardButton("900")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

confirm_key = ReplyKeyboardMarkup(
    [[KeyboardButton("✅ تایید و ارسال"), KeyboardButton("❌ لغو")]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

no_desc_key = ReplyKeyboardMarkup(
    [[KeyboardButton("📝 بدون توضیحات")]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


MYREQ_PAGE_SIZE = 1


@sync_to_async
def get_user_by_tg(tg_id: int):
    return CustomUser.objects.filter(telegram_id=tg_id).first()


def is_profile_ok(user: CustomUser) -> bool:
    return bool(
        user
        and user.is_registered
        and user.name
        and user.last_name
        and user.country_id
        and user.phone
    )


def _role_fa(role: str) -> str:
    return "خریدار" if role == TradeRequest.Role.BUYER else "فروشنده"


def _req_status_fa(status: str) -> str:
    mapping = {
        TradeRequest.Status.DRAFT: "پیش‌نویس",
        TradeRequest.Status.PENDING_ADMIN: "در انتظار تایید ادمین",
        TradeRequest.Status.APPROVED: "✅ فعال",
        TradeRequest.Status.CLOSED: "⛔️ بسته شده",
    }
    return mapping.get(status, status)


def _offer_status_fa(status: str) -> str:
    mapping = {
        TradeOffer.Status.PENDING: "در انتظار",
        TradeOffer.Status.ACCEPTED: "✅ تایید شده",
        TradeOffer.Status.REJECTED: "❌ رد شده",
    }
    return mapping.get(status, status)


@sync_to_async
def fetch_user_requests(user_id: int, page: int):
    qs = TradeRequest.objects.filter(owner_id=user_id).order_by("-created_at")
    total = qs.count()
    start = page * MYREQ_PAGE_SIZE
    end = start + MYREQ_PAGE_SIZE
    items = list(qs[start:end])
    return items, total


@sync_to_async
def fetch_offers_for_request(req_id: int):
    return list(
        TradeOffer.objects
        .select_related("sender")
        .filter(request_id=req_id)
        .order_by("-created_at")
    )


def build_myreq_list_keyboard(page: int, total: int) -> InlineKeyboardMarkup:
    max_page = max((total - 1) // MYREQ_PAGE_SIZE, 0)

    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"myreq:{page-1}"))
    if page < max_page:
        nav.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"myreq:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="myreq_home")])
    return InlineKeyboardMarkup(rows)


async def send_my_requests_list(message_obj, user: CustomUser, page: int, *, edit: bool = False):
    items, total = await fetch_user_requests(user.id, page)

    if total == 0:
        if edit:
            await message_obj.edit_text("📥 هنوز هیچ درخواستی ثبت نکردی.")
            await message_obj.reply_text("🏠 برگشتی به منوی اصلی.", reply_markup=build_main_menu_keyboard())
        else:
            await message_obj.reply_text("📥 هنوز هیچ درخواستی ثبت نکردی.", reply_markup=build_main_menu_keyboard())
        return

    max_page = max((total - 1) // MYREQ_PAGE_SIZE, 0)
    if page < 0:
        page = 0
    if page > max_page:
        page = max_page

    items, total = await fetch_user_requests(user.id, page)
    r = items[0]
    offers = await fetch_offers_for_request(r.id)

    text = (
        f"📥 *درخواست‌های من* (صفحه {page+1} از {max_page+1})\n\n"
        "🧾 *درخواست*\n"
        f"*🆔 #{r.id}*\n\n"
        f"👤 نقش: {_role_fa(r.role)} | 💱 ارز: {r.currency}\n"
        f"💰 مقدار: {r.amount}\n"
        f"🏷 قیمت واحد: {r.unit_price_irt:,} تومان\n"
        f"💳 روش معامله: {r.deal_method}\n"
        f"📝 توضیحات: {r.description or '—'}\n"
        f"📌 وضعیت: {_req_status_fa(r.status)}\n"
        "\n—————————————————————\n"
        f"📨 *پیشنهادها* ({len(offers)})"
    )

    if not offers:
        text += "\n\nهنوز پیشنهادی نداری."
    else:
        shown = offers[:25]
        for o in shown:
            sender_name = (o.sender.name or o.sender.username or "—")
            text += (
                f"\n\n— *پیشنهاد* #{o.id}"
                f"\n👤 {sender_name}"
                f"\n💰 {o.unit_price_irt:,} تومان"
                f"\n📌 وضعیت: {_offer_status_fa(o.status)}"
                + (f"\n📝 {o.message}" if o.message else "")
            )

        if len(offers) > len(shown):
            text += f"\n\n… {len(offers) - len(shown)} پیشنهاد دیگر نمایش داده نشد."

    kb = build_myreq_list_keyboard(page, total)

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


async def my_requests_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    user = await get_user_by_tg(tg.id)
    if not user:
        await update.message.reply_text("❌ اول باید از بخش 👤پروفایل ثبت‌نام کنی.")
        return
    await send_my_requests_list(update.message, user, page=0, edit=False)


async def my_requests_page_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "myreq_home":
        await q.message.reply_text("🏠 برگشتی به منوی اصلی.", reply_markup=build_main_menu_keyboard())
        return

    user = await get_user_by_tg(q.from_user.id)
    if not user:
        await q.message.reply_text("❌ اول باید از بخش 👤پروفایل ثبت‌نام کنی.")
        return

    try:
        page = int(q.data.split(":", 1)[1])
    except Exception:
        page = 0

    await send_my_requests_list(q.message, user, page=page, edit=True)


@sync_to_async
def create_exchange_request(
    owner: CustomUser,
    role: str,
    currency: str,
    amount: Decimal,
    unit_price_irt: int,
    deal_method: str,
    description: str,
    fee_irt: int,
):
    # ✅ مستقیم فعال (بدون تایید ادمین)
    return TradeRequest.objects.create(
        owner=owner,
        role=role,
        currency=currency,
        amount=amount,
        unit_price_irt=unit_price_irt,
        fee_irt=fee_irt,
        deal_method=deal_method,
        description=description,
        status=TradeRequest.Status.APPROVED,
    )


def map_role(text: str) -> str | None:
    t = (text or "").strip()
    if t == "خریدارم":
        return TradeRequest.Role.BUYER
    if t == "فروشنده ام":
        return TradeRequest.Role.SELLER
    return None


def map_method(text: str) -> str | None:
    t = (text or "").strip()
    if t == "انتقال آنی پی پال":
        return TradeRequest.DealMethod.PAYPAL
    if t == "حواله بانکی":
        return TradeRequest.DealMethod.TRANSFER
    if t == "مسترکارت":
        return TradeRequest.DealMethod.MASTER
    if t == "سایر":
        return TradeRequest.DealMethod.OTHER
    return None


def parse_amount(text: str) -> Decimal | None:
    t = (text or "").strip().replace(",", ".")
    try:
        val = Decimal(t)
        if val <= 0:
            return None
        return val
    except (InvalidOperation, ValueError):
        return None


def parse_unit_price(text: str) -> int | None:
    t = (text or "").strip().replace(",", "").replace("_", "")
    if not t.isdigit():
        return None
    v = int(t)
    if v <= 0:
        return None
    return v


def get_fee_irt() -> int:
    return int(config("TRADE_REQUEST_FEE"))


async def send_preview(message_obj, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.get("tr", {})

    preview = (
        "🧾 پیش‌نمایش درخواست شما:\n\n"
        f"👤 نقش: {'خریدار' if data['role'] == TradeRequest.Role.BUYER else 'فروشنده'}\n"
        f"💱 ارز: {data['currency']}\n"
        f"💰 مقدار: {data['amount']}\n"
        f"🏷 قیمت هر واحد (تومان): {data['unit_price_irt']}\n"
        f"🔁 روش معامله: {data['deal_method']}\n"
        f"📝 توضیحات: {data['description'] or '—'}\n"
        "\n✅ از ارسال مطمئنی؟"
    )
    await message_obj.reply_text(preview, reply_markup=confirm_key)


async def new_request_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    user = await get_user_by_tg(tg.id)

    if not is_profile_ok(user):
        await update.message.reply_text(
            "❌ برای ثبت درخواست باید اول ثبت‌نامت کامل باشه.\n"
            "لطفاً از بخش 👤پروفایل ثبت‌نام رو کامل کن."
        )
        return ConversationHandler.END

    context.user_data["tr"] = {}

    await update.message.reply_text("✅ خریدار هستی یا فروشنده؟", reply_markup=side_key)
    return TR_ROLE


async def tr_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = map_role(update.message.text)
    if not role:
        await update.message.reply_text("❌ لطفاً یکی از گزینه‌ها رو انتخاب کن.", reply_markup=side_key)
        return TR_ROLE

    context.user_data["tr"]["role"] = role
    await update.message.reply_text("💱 ارز مورد نظرت چیه؟", reply_markup=currency_key)
    return TR_CURRENCY


async def tr_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur = (update.message.text or "").strip().upper()
    allowed = {c[0] for c in TradeRequest.Currency.choices}
    if cur not in allowed:
        await update.message.reply_text("❌ ارز نامعتبره. یکی از گزینه‌ها رو انتخاب کن.", reply_markup=currency_key)
        return TR_CURRENCY

    context.user_data["tr"]["currency"] = cur
    await update.message.reply_text("💰 مقدار ارز رو انتخاب کن یا مقدار ارز مد نظرت رو وارد کن", reply_markup=amount_key)
    return TR_AMOUNT


async def tr_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = parse_amount(update.message.text)
    if amount is None:
        await update.message.reply_text("❌ مقدار نامعتبره.")
        return TR_AMOUNT

    context.user_data["tr"]["amount"] = amount

    # ✅ کیبورد مقدار جمع بشه
    await update.message.reply_text(
        "🏷 قیمت برای هر واحد ارز به تومان را وارد کن (فقط عدد):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return TR_UNIT_PRICE


async def tr_unit_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    unit_price = parse_unit_price(update.message.text)
    if unit_price is None:
        await update.message.reply_text("❌ قیمت نامعتبره. فقط عدد صحیح وارد کن. مثال: 75000")
        return TR_UNIT_PRICE

    context.user_data["tr"]["unit_price_irt"] = unit_price
    await update.message.reply_text("🔁 روش معاملت چیه؟", reply_markup=method_key)
    return TR_METHOD


async def tr_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    method = map_method(update.message.text)
    if not method:
        await update.message.reply_text("❌ لطفاً یکی از گزینه‌ها رو انتخاب کن.", reply_markup=method_key)
        return TR_METHOD

    context.user_data["tr"]["deal_method"] = method
    await update.message.reply_text(
        "📝 توضیحاتی داری؟ (اگر نداری «📝 بدون توضیحات» رو بزن)",
        reply_markup=no_desc_key,
    )
    return TR_DESC


async def tr_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = (update.message.text or "").strip()
    if desc == "📝 بدون توضیحات" or desc == "-":
        desc = ""

    context.user_data["tr"]["description"] = desc
    await update.message.reply_text("✅ دریافت شد.", reply_markup=ReplyKeyboardRemove())
    await send_preview(update.message, context)
    return TR_CONFIRM


async def tr_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if text == "❌ لغو":
        context.user_data.pop("tr", None)
        await update.message.reply_text("❌ ثبت درخواست لغو شد.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    if text != "✅ تایید و ارسال":
        await update.message.reply_text("❌ یکی از گزینه‌ها رو انتخاب کن.", reply_markup=confirm_key)
        return TR_CONFIRM

    tg = update.effective_user
    user = await get_user_by_tg(tg.id)
    if not is_profile_ok(user):
        await update.message.reply_text("❌ پروفایل کامل نیست. نمی‌تونم درخواست ثبت کنم.")
        return ConversationHandler.END

    data = context.user_data.get("tr", {})
    fee = get_fee_irt()
    data["fee_irt"] = fee

    req = await create_exchange_request(
        owner=user,
        role=data["role"],
        currency=data["currency"],
        amount=data["amount"],
        unit_price_irt=data["unit_price_irt"],
        deal_method=data["deal_method"],
        description=data.get("description", ""),
        fee_irt=fee,
    )

    ok = False
    try:
        ok = await sync_to_async(publish_trade_request_to_channel)(req.id)
    except Exception:
        ok = False

    if ok:
        await update.message.reply_text(
            "✅ درخواستت ثبت شد و مستقیم توی کانال منتشر شد.",
            reply_markup=build_main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            "⚠️ درخواستت ثبت شد ولی انتشار در کانال ناموفق بود. (لاگ سرور رو چک کن)",
            reply_markup=build_main_menu_keyboard(),
        )

    context.user_data.pop("tr", None)
    return ConversationHandler.END


async def tr_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("tr", None)
    await update.message.reply_text("❌ ثبت درخواست لغو شد.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def get_my_requests_handlers():
    return [
        CommandHandler("requests", my_requests_entry),
        MessageHandler(filters.Regex(r"^📥درخواست‌های من$"), my_requests_entry),

        CallbackQueryHandler(my_requests_page_cb, pattern=r"^myreq:\d+$"),
        CallbackQueryHandler(my_requests_page_cb, pattern=r"^myreq_home$"),
    ]


def get_trade_request_conversation():
    return ConversationHandler(
        entry_points=[
            CommandHandler("new_request", new_request_entry),
            MessageHandler(filters.Regex(r"^➕ثبت درخواست جدید$"), new_request_entry),
        ],
        states={
            TR_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_role)],
            TR_CURRENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_currency)],
            TR_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_amount)],
            TR_UNIT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_unit_price)],
            TR_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_method)],
            TR_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_desc)],
            TR_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_confirm)],
        },
        fallbacks=[CommandHandler("cancel", tr_cancel)],
        per_user=True,
        per_chat=True,
        name="trade_request_conversation",
        allow_reentry=True,
    )