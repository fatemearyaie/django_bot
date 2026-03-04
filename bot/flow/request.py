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
from datetime import timedelta
from django.utils import timezone

from Users.models import CustomUser
from Trade.models.models import TradeRequest, TradeOffer

from Trade.services.request_services import publish_trade_request_to_channel


TR_ROLE, TR_CURRENCY, TR_AMOUNT, TR_UNIT_PRICE, TR_METHOD, TR_DESC, TR_CONFIRM, TR_EDIT_MENU, TR_EDIT_VALUE = range(9)

def build_channel_link(req: TradeRequest) -> str | None:
    try:
        if not req.channel_chat_id or not req.channel_message_id:
            return None

        chat_id = str(req.channel_chat_id)
        msg_id = req.channel_message_id

        if chat_id.startswith("-100"):
            internal = chat_id.replace("-100", "", 1)
            return f"https://t.me/c/{internal}/{msg_id}"

        return None
    except Exception:
        return None


def deal_method_fa(value: str) -> str:
    return dict(TradeRequest.DealMethod.choices).get(value, value)

side_key = ReplyKeyboardMarkup(
    [[KeyboardButton("خریدارم"), KeyboardButton("فروشنده ام")]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

currency_key = ReplyKeyboardMarkup(
    [
        [KeyboardButton("EUR"), KeyboardButton("USD")],
        [KeyboardButton("AED")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

method_key = ReplyKeyboardMarkup(
    [
        [KeyboardButton("انتقال آنی"), KeyboardButton("حواله بانکی")],
        [KeyboardButton("سایر"), KeyboardButton("مسترکارت")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

amount_key = ReplyKeyboardMarkup(
    [
        [KeyboardButton("100"), KeyboardButton("200"), KeyboardButton("300")],
        [KeyboardButton("400"), KeyboardButton("500"), KeyboardButton("600")],
        [KeyboardButton("700"), KeyboardButton("800"), KeyboardButton("900")],
        [KeyboardButton("1000")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

confirm_key = ReplyKeyboardMarkup(
    [[KeyboardButton("❌ اصلاح"), KeyboardButton("✅ تایید و ارسال")]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

no_desc_key = ReplyKeyboardMarkup(
    [[KeyboardButton("📝 بدون توضیحات")]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


def build_edit_request_inline_keyboard_v2():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✏️ اصلاح نقش (خریدار/فروشنده)", callback_data="req_edit:role")],
            [InlineKeyboardButton("💱 اصلاح ارز", callback_data="req_edit:currency")],
            [InlineKeyboardButton("💰 اصلاح مقدار", callback_data="req_edit:amount")],
            [InlineKeyboardButton("🏷 اصلاح قیمت هر واحد", callback_data="req_edit:unit_price_irt")],
            [InlineKeyboardButton("💳 اصلاح روش معامله", callback_data="req_edit:deal_method")],
            [InlineKeyboardButton("🪧 اصلاح توضیحات", callback_data="req_edit:description")],
            [InlineKeyboardButton("↩️ برگشت به پیش‌نمایش", callback_data="req_edit:back")],
        ]
    )





MYREQ_PAGE_SIZE = 1


@sync_to_async
def get_user_by_tg(tg_id: int):
    return CustomUser.objects.filter(telegram_id=tg_id).first()


def _role_fa(role: str) -> str:
    return "خریدار" if role == TradeRequest.Role.BUYER else "فروشنده"


def _req_status_fa(status: str) -> str:
    mapping = {
        TradeRequest.Status.DRAFT: "پیش‌نویس",
        TradeRequest.Status.PENDING_ADMIN: "در انتظار تایید ادمین",
        TradeRequest.Status.APPROVED: "♻ فعال",
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
    page = max(0, min(page, max_page))

    items, total = await fetch_user_requests(user.id, page)
    r = items[0]
    offers = await fetch_offers_for_request(r.id)

    link = build_channel_link(r)
    if link:
        req_id_text = f'<a href="{link}">#{r.id}</a>'
    else:
        req_id_text = f"#{r.id}"

    text = (
        f"📥 <b>درخواست‌های من</b> (صفحه {page+1} از {max_page+1})\n\n"
        "🧾 <b>درخواست</b>\n"
        f"🆔 {req_id_text}\n\n"
        f"👤 نقش: {_role_fa(r.role)} | 💱 ارز: {r.currency}\n"
        f"💰 مقدار: {r.amount}\n"
        f"🏷 قیمت واحد: {r.unit_price_irt:,} تومان\n"
        f"💳 روش معامله: {r.get_deal_method_display()}\n"
        f"🪧 توضیحات: {r.description or '—'}\n"
        f"📌 وضعیت: {_req_status_fa(r.status)}\n"
        "—————————————————————\n"
        f"📨 <b>پیشنهادها</b> ({len(offers)})"
    )

    if not offers:
        text += "\n\nهنوز پیشنهادی نداری."
    else:
        shown = offers[:25]
        for o in shown:
            text += (
                f"\n\n— <b>پیشنهاد</b> #{o.id}"
                f"\n👤"
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
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    else:
        await message_obj.reply_text(
            text,
            parse_mode="HTML",
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


def is_profile_ok(user: CustomUser) -> bool:
    return bool(
        user
        and user.is_registered
        and user.name
        and user.last_name
        and user.country_id
        and user.phone
    )


@sync_to_async
def set_confirm_window(req_id: int):
    now = timezone.now()
    TradeRequest.objects.filter(pk=req_id).update(
        confirmed_at=now,
        editable_until=now + timedelta(minutes=10),
    )


@sync_to_async
def get_request_for_owner(req_id: int, owner_id: int):
    return TradeRequest.objects.filter(id=req_id, owner_id=owner_id).first()


def _is_request_editable(req: TradeRequest) -> bool:
    if not req:
        return False
    if req.status == TradeRequest.Status.CLOSED:
        return False
    if not req.editable_until:
        return False
    return timezone.now() <= req.editable_until


@sync_to_async
def delete_request_for_owner(req_id: int, owner_id: int):
    req = TradeRequest.objects.filter(id=req_id, owner_id=owner_id).first()
    if not req:
        return 0
    if req.status == TradeRequest.Status.CLOSED:
        return 0
    if not req.editable_until or timezone.now() > req.editable_until:
        return 0
    deleted_count, _ = TradeRequest.objects.filter(id=req_id, owner_id=owner_id).delete()
    return deleted_count


@sync_to_async
def update_request_for_owner(req_id: int, owner_id: int, data: dict):
    req = TradeRequest.objects.filter(id=req_id, owner_id=owner_id).first()
    if not req:
        return 0
    if req.status == TradeRequest.Status.CLOSED:
        return 0
    if not req.editable_until or timezone.now() > req.editable_until:
        return 0

    return TradeRequest.objects.filter(id=req_id, owner_id=owner_id).update(
        role=data["role"],
        currency=data["currency"],
        amount=data["amount"],
        unit_price_irt=data["unit_price_irt"],
        deal_method=data["deal_method"],
        description=data["description"],
        fee_irt=data["fee_irt"],
        updated_at=timezone.now(),
    )


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
    if t == "انتقال آنی":
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

    role_is_buy = data["role"] == TradeRequest.Role.BUYER
    dot = "🟢" if role_is_buy else "🔴"
    role_fa = "خرید" if role_is_buy else "فروش"

    try:
        currency_fa = TradeRequest.Currency(data["currency"]).label
    except ValueError:
        currency_fa = str(data["currency"])

    preview = (
        "🧾 *پیش‌نمایش درخواست شما*\n\n"
        f"*{dot}   {role_fa} : {data['amount']} {currency_fa}*\n\n"
        f"*💬 نرخ پیشنهادی: {data['unit_price_irt']} تومان*\n\n"
        f" 🪧 نوع حواله: {deal_method_fa(data['deal_method'])}  \n"
        f" 🪧 توضیحات درخواست: {data['description'] or '—'}\n\n"
        "✅ از ارسال مطمئنی؟"
    )
    await message_obj.reply_text(
        preview,
        parse_mode="Markdown",
        reply_markup=confirm_key
    )

async def tr_edit_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    action = q.data.split(":", 1)[1]

    if action == "back":
        await q.message.reply_text("🔁 برگشتیم به پیش‌نمایش:", reply_markup=ReplyKeyboardRemove())
        await send_preview(q.message, context)
        return TR_CONFIRM

    context.user_data["tr_edit_field"] = action

    if action == "role":
        await q.message.reply_text("⬅ خریدار یا فروشنده ارز هستین؟", reply_markup=side_key)
        return TR_EDIT_VALUE

    if action == "currency":
        await q.message.reply_text("⬅ نوع ارز درخواستی خود را مشخص کنید:", reply_markup=currency_key)
        return TR_EDIT_VALUE

    if action == "amount":
        await q.message.reply_text("⬅ مقدار ارز رو انتخاب کنید یا مقدار ارز مد نظرتون رو وارد کنید.", reply_markup=amount_key)
        return TR_EDIT_VALUE

    if action == "unit_price_irt":
        await q.message.reply_text("⬅ نرخ پیشنهادی شما برای هر ارز مد نظرتون چند تومان است؟", reply_markup=ReplyKeyboardRemove())
        return TR_EDIT_VALUE

    if action == "deal_method":
        await q.message.reply_text("⬅ روش انجام معامله موردنظر شما کدام است؟", reply_markup=method_key)
        return TR_EDIT_VALUE

    if action == "description":
        await q.message.reply_text("⬅ در صورت تمایل، توضیحات تکمیلی خود را در این بخش وارد کنید:", reply_markup=no_desc_key)
        return TR_EDIT_VALUE

    await q.message.reply_text("❌ گزینه نامعتبر.")
    return TR_EDIT_MENU


async def tr_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = context.user_data.get("tr_edit_field")
    data = context.user_data.get("tr", {})

    if not field:
        await update.message.reply_text("❌ خطا. دوباره اصلاح رو بزن.")
        return TR_CONFIRM

    txt = (update.message.text or "").strip()

    if field == "role":
        role = map_role(txt)
        if not role:
            await update.message.reply_text("❌ یکی از گزینه‌ها رو انتخاب کن.", reply_markup=side_key)
            return TR_EDIT_VALUE
        data["role"] = role

    elif field == "currency":
        cur = txt.upper()
        allowed = {c[0] for c in TradeRequest.Currency.choices}
        if cur not in allowed:
            await update.message.reply_text("❌ ارز نامعتبره.", reply_markup=currency_key)
            return TR_EDIT_VALUE
        data["currency"] = cur

    elif field == "amount":
        amount = parse_amount(txt)
        if amount is None:
            await update.message.reply_text("❌ مقدار نامعتبره.")
            return TR_EDIT_VALUE
        data["amount"] = amount

    elif field == "unit_price_irt":
        unit_price = parse_unit_price(txt)
        if unit_price is None:
            await update.message.reply_text("❌ قیمت نامعتبره. فقط عدد صحیح. مثال: 75000")
            return TR_EDIT_VALUE
        data["unit_price_irt"] = unit_price

    elif field == "deal_method":
        method = map_method(txt)
        if not method:
            await update.message.reply_text("❌ یکی از گزینه‌ها رو انتخاب کن.", reply_markup=method_key)
            return TR_EDIT_VALUE
        data["deal_method"] = method

    elif field == "description":
        if txt == "📝 بدون توضیحات" or txt == "-":
            txt = ""
        data["description"] = txt

    context.user_data["tr"] = data
    context.user_data.pop("tr_edit_field", None)

    await update.message.reply_text("✅ اصلاح شد.", reply_markup=ReplyKeyboardRemove())
    await send_preview(update.message, context)
    return TR_CONFIRM


async def req_manage_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    user = await get_user_by_tg(q.from_user.id)
    if not user:
        await q.message.reply_text("❌ اول باید ثبت‌نام کنی (از بخش 👤پروفایل).")
        return ConversationHandler.END

    try:
        _, action, req_id_str = q.data.split(":", 2)
        req_id = int(req_id_str)
    except Exception:
        await q.message.reply_text("❌ داده نامعتبر.")
        return ConversationHandler.END

    req = await get_request_for_owner(req_id, user.id)
    if not req:
        await q.message.reply_text("❌ این درخواست پیدا نشد یا مال شما نیست.", reply_markup=build_main_menu_keyboard())
        return ConversationHandler.END

    if not _is_request_editable(req):
        await q.message.reply_text(
            "⛔️ مهلت ۱۰ دقیقه‌ای گذشته و دیگه نمی‌تونی این درخواست رو ویرایش/حذف کنی.",
            reply_markup=build_main_menu_keyboard(),
        )
        return ConversationHandler.END

    if action == "del":
        deleted = await delete_request_for_owner(req_id, user.id)
        if deleted:
            await q.message.reply_text(f"🗑 درخواست #{req_id} حذف شد.", reply_markup=build_main_menu_keyboard())
        else:
            await q.message.reply_text("❌ حذف انجام نشد.", reply_markup=build_main_menu_keyboard())
        return ConversationHandler.END

    if action == "edit":
        context.user_data["tr"] = {
            "role": req.role,
            "currency": req.currency,
            "amount": req.amount,
            "unit_price_irt": req.unit_price_irt,
            "deal_method": req.deal_method,
            "description": req.description or "",
        }
        context.user_data["editing_req_id"] = req_id

        await q.message.reply_text(
            f"✏️ ویرایش درخواست #{req_id}\nکدوم بخش رو می‌خوای اصلاح کنی؟",
            reply_markup=build_edit_request_inline_keyboard_v2(),
        )
        return TR_EDIT_MENU

    await q.message.reply_text("❌ عملیات نامعتبر.")
    return ConversationHandler.END


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
    context.user_data.pop("editing_req_id", None)

    await update.message.reply_text("⬅ خریدار یا فروشنده ارز هستین؟", reply_markup=side_key)
    return TR_ROLE


async def tr_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = map_role(update.message.text)
    if not role:
        await update.message.reply_text("❌ لطفاً یکی از گزینه‌ها رو انتخاب کن.", reply_markup=side_key)
        return TR_ROLE

    context.user_data["tr"]["role"] = role
    await update.message.reply_text("⬅ نوع ارز درخواستی خود را مشخص کنید:", reply_markup=currency_key)
    return TR_CURRENCY


async def tr_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur = (update.message.text or "").strip().upper()
    allowed = {c[0] for c in TradeRequest.Currency.choices}
    if cur not in allowed:
        await update.message.reply_text("❌ ارز نامعتبره. یکی از گزینه‌ها رو انتخاب کن.", reply_markup=currency_key)
        return TR_CURRENCY

    context.user_data["tr"]["currency"] = cur
    await update.message.reply_text("⬅ مقدار ارز رو انتخاب کنید یا مقدار ارز مد نظرتون رو وارد کنید.", reply_markup=amount_key)
    return TR_AMOUNT


async def tr_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = parse_amount(update.message.text)
    if amount is None:
        await update.message.reply_text("❌ مقدار نامعتبره.")
        return TR_AMOUNT

    context.user_data["tr"]["amount"] = amount

    await update.message.reply_text(
        "⬅ نرخ پیشنهادی شما برای هر ارز مد نظرتون چند تومان است؟",
        reply_markup=ReplyKeyboardRemove(),
    )
    return TR_UNIT_PRICE


async def tr_unit_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    unit_price = parse_unit_price(update.message.text)
    if unit_price is None:
        await update.message.reply_text("❌ قیمت نامعتبره. فقط عدد صحیح وارد کن. مثال: 75000")
        return TR_UNIT_PRICE

    context.user_data["tr"]["unit_price_irt"] = unit_price
    await update.message.reply_text("⬅ روش انجام معامله موردنظر شما کدام است؟", reply_markup=method_key)
    return TR_METHOD


async def tr_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    method = map_method(update.message.text)
    if not method:
        await update.message.reply_text("❌ لطفاً یکی از گزینه‌ها رو انتخاب کن.", reply_markup=method_key)
        return TR_METHOD

    context.user_data["tr"]["deal_method"] = method
    await update.message.reply_text(
        "⬅ در صورت تمایل، توضیحات تکمیلی خود را در این بخش وارد کنید:",
        reply_markup=no_desc_key,
    )
    return TR_DESC


async def tr_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = (update.message.text or "").strip()
    if desc == "📝 بدون توضیحات" or desc == "-":
        desc = ""

    context.user_data["tr"]["description"] = desc
    await send_preview(update.message, context)
    return TR_CONFIRM


async def tr_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if text == "❌ اصلاح":
        await update.message.reply_text(
            "کدوم بخش رو می‌خوای اصلاح کنی؟",
            reply_markup=build_edit_request_inline_keyboard_v2()
        )
        return TR_EDIT_MENU

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

    editing_req_id = context.user_data.get("editing_req_id")
    if editing_req_id:
        req = await get_request_for_owner(editing_req_id, user.id)
        if not req:
            await update.message.reply_text("❌ درخواست پیدا نشد.", reply_markup=build_main_menu_keyboard())
            context.user_data.pop("tr", None)
            context.user_data.pop("editing_req_id", None)
            return ConversationHandler.END

        if not _is_request_editable(req):
            await update.message.reply_text(
                "⛔️ مهلت ۱۰ دقیقه‌ای گذشته و دیگه نمی‌تونی این درخواست رو ویرایش/حذف کنی.",
                reply_markup=build_main_menu_keyboard()
            )
            context.user_data.pop("tr", None)
            context.user_data.pop("editing_req_id", None)
            return ConversationHandler.END

        await update_request_for_owner(editing_req_id, user.id, data)

        await update.message.reply_text(
            f"✅ درخواست #{editing_req_id} ویرایش شد.",
            reply_markup=build_main_menu_keyboard()
        )
        context.user_data.pop("tr", None)
        context.user_data.pop("editing_req_id", None)
        return ConversationHandler.END

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

    await set_confirm_window(req.id)

    ok = False
    try:
        ok = await sync_to_async(publish_trade_request_to_channel)(req.id)
    except Exception:
        ok = False

    if not ok:
        await update.message.reply_text(
            "⚠️ درخواستت ثبت شد ولی انتشار در کانال ناموفق بود.دوباره تلاش کن",
            reply_markup=build_main_menu_keyboard(),
        )

    await update.message.reply_text(
        "🏠 برگشتی به منوی اصلی.",
        reply_markup=build_main_menu_keyboard(),
    )

    context.user_data.pop("tr", None)
    return ConversationHandler.END


async def tr_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("tr", None)
    context.user_data.pop("editing_req_id", None)
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

            CallbackQueryHandler(req_manage_cb, pattern=r"^req_manage:(edit|del):\d+$"),
        ],
        states={
            TR_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_role)],
            TR_CURRENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_currency)],
            TR_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_amount)],
            TR_UNIT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_unit_price)],
            TR_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_method)],
            TR_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_desc)],
            TR_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_confirm)],

            TR_EDIT_MENU: [
                CallbackQueryHandler(
                    tr_edit_menu_callback,
                    pattern=r"^req_edit:(role|currency|amount|unit_price_irt|deal_method|description|back)$",
                )
            ],
            TR_EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_edit_value)],
        },
        fallbacks=[CommandHandler("cancel", tr_cancel)],
        per_user=True,
        per_chat=True,
        name="trade_request_conversation",
        allow_reentry=True,
    )