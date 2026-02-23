from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from asgiref.sync import sync_to_async
from django.db.models import Q
from Trade.services.offers_service import upsert_offer_line_in_channel

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
    CallbackQueryHandler,
)

from Users.models.models import CustomUser
from Trade.models.models import TradeRequest, TradeOffer
from Trade.services.offers_service import (
    build_offer_manage_keyboard,
    build_offer_message,
)
from bot.flow.registration import get_or_create_user, is_profile_complete
from bot.handlers import build_main_menu_keyboard
from decouple import config


REQUIRED_CHANNEL = "@excoinmarket"
START_OFFER_RE = re.compile(r"^offer_(\d+)$")

RATE, NOTE, CONFIRM = range(3)

CB_HOME = "offerflow:home"
CB_PROFILE = "offerflow:profile"

BTN_CANCEL = "❌ انصراف"
BTN_SEND = "✅ بله، ارسال کن"
BTN_NO_NOTE = "📝 بدون توضیحات"


@sync_to_async
def _get_sender_last_offer_price(sender_id: int, request_id: int) -> int | None:
    return (
        TradeOffer.objects
        .filter(sender_id=sender_id, request_id=request_id)
        .order_by("-id")
        .values_list("unit_price_irt", flat=True)
        .first()
    )


@sync_to_async
def _request_is_closed(request_id: int) -> bool:
    return TradeRequest.objects.filter(
        id=request_id,
        status=TradeRequest.Status.CLOSED
    ).exists()


@dataclass
class OfferDraft:
    request_id: int
    request_rate: Optional[int] = None
    proposed_rate: Optional[int] = None
    note: Optional[str] = None
    request_title: Optional[str] = None


def _rk(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(x) for x in row] for row in rows],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _rk_with_cancel(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    if not rows:
        rows = []
    if [BTN_CANCEL] not in rows:
        rows.append([BTN_CANCEL])
    return _rk(rows)


def _main_menu_kb() -> ReplyKeyboardMarkup:
    try:
        kb = build_main_menu_keyboard()
        if kb:
            return kb
    except Exception:
        pass
    return _rk([["🏠 منوی اصلی"], ["👤 پروفایل"]])


def _main_menu_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🏠 منوی اصلی", callback_data=CB_HOME),
                InlineKeyboardButton("👤 پروفایل", callback_data=CB_PROFILE),
            ]
        ]
    )


async def _go_home(message_obj):
    await message_obj.reply_text("🏠 برگشتی به منوی اصلی.", reply_markup=build_main_menu_keyboard())


async def _go_profile(message_obj):
    await message_obj.reply_text("👤 پروفایل", reply_markup=_main_menu_kb())


async def offerflow_inline_nav_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    try:
        await q.answer()
    except Exception:
        pass

    if q.data == CB_HOME:
        await _go_home(q.message)
        return

    if q.data == CB_PROFILE:
        await _go_profile(q.message)
        return


async def is_member_of_required_channel(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ("creator", "administrator", "member")
    except Exception:
        return False


@sync_to_async
def _get_trade_request_for_offer(request_id: int) -> TradeRequest:
    return (
        TradeRequest.objects.select_related("owner")
        .filter(id=request_id)
        .filter(~Q(status=TradeRequest.Status.CLOSED))
        .get()
    )


@sync_to_async
def _get_sender_from_tg_id(tg_id: int) -> CustomUser:
    return CustomUser.objects.get(telegram_id=tg_id)


@sync_to_async
def _create_offer(req: TradeRequest, sender: CustomUser, unit_price_irt: int, message: str) -> TradeOffer:
    return TradeOffer.objects.create(
        request=req,
        sender=sender,
        unit_price_irt=unit_price_irt,
        message=message or "",
    )


def _req_title(req: TradeRequest) -> str:
    role_fa = "خریدار" if req.role == TradeRequest.Role.BUYER else "فروشنده"
    return f"درخواست #{req.id} ({role_fa} {req.currency})"


def _channel_post_link(req: TradeRequest) -> str | None:
    try:
        msg_id = getattr(req, "channel_message_id", None)
        chat_id = getattr(req, "channel_chat_id", None)
        username = getattr(req, "channel_username", None)
        if not msg_id or not chat_id:
            return None

        if username:
            u = str(username).lstrip("@")
            return f"https://t.me/{u}/{int(msg_id)}"

        # حالت supergroup/channel private: -1001234567890 -> 1234567890
        s = str(chat_id)
        if s.startswith("-100"):
            internal = s.replace("-100", "", 1)
            return f"https://t.me/c/{internal}/{int(msg_id)}"

        return None
    except Exception:
        return None


def _ad_text(req: TradeRequest) -> str:
    link = _channel_post_link(req)
    if link:
        return f"[مشاهده آگهی]({link})"
    return f"#{req.id}"


def _offer_preview(d: OfferDraft) -> str:
    fee = int(config("TRADE_REQUEST_FEE"))

    return (
        "🧾 پیش‌نمایش پیشنهاد شما:\n\n"
        f"📌 آگهی: {d.request_title or f'#{d.request_id}'}\n"
        f"💱 نرخ درخواست (تومان/واحد): {d.request_rate if d.request_rate is not None else '—'}\n"
        f"✅ نرخ پیشنهادی شما (تومان/واحد): {d.proposed_rate}\n"
        f"📝 توضیحات: {d.note if d.note else '—'}\n"
        f"کارمزد: {fee}\n\n"
        "مطمئنی می‌خوای ارسال بشه؟"
    )

async def offer_start_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.effective_message
    tg = update.effective_user

    print("START ARGS:", context.args)


    if not msg or not tg:
        return ConversationHandler.END

    if not context.args:
        # fallback به start عمومی
        from bot.main import start as start_public
        await start_public(update, context)
        return ConversationHandler.END

    arg = str(context.args[0]).strip()
    m = START_OFFER_RE.match(arg)
    if not m:
        from bot.main import start as start_public
        await start_public(update, context)
        return ConversationHandler.END

    request_id = int(m.group(1))

    user = await get_or_create_user(tg.id, tg.username)

    if not is_profile_complete(user):
        await msg.reply_text(
            "❌ ثبت‌نامت کامل نیست.\n"
            "لطفاً از منوی «پروفایل» وارد شو و فرایند ثبت‌نام را کامل کن، سپس دوباره از روی پیام کانال روی «پیشنهاد بده» بزن.",
            reply_markup=_main_menu_kb(),
        )
        return ConversationHandler.END

    if not await is_member_of_required_channel(context, tg.id):
        await msg.reply_text(
            "❌ شما عضو کانال ما نیستی.\n"
            f"اول عضو {REQUIRED_CHANNEL} شو، بعد دوباره از روی همون پیام کانال روی «پیشنهاد بده» بزن.",
            reply_markup=_main_menu_kb(),
        )
        return ConversationHandler.END

    try:
        req = await _get_trade_request_for_offer(request_id)
    except TradeRequest.DoesNotExist:
        await msg.reply_text(
            "❌ این درخواست پیدا نشد یا دیگر فعال نیست.",
            reply_markup=_main_menu_kb(),
        )
        return ConversationHandler.END
    except Exception:
        await msg.reply_text(
            "❌ خطا در دریافت درخواست. دوباره تلاش کن.",
            reply_markup=_main_menu_kb(),
        )
        return ConversationHandler.END

    req_rate = int(req.unit_price_irt) if req.unit_price_irt is not None else None

    context.user_data["offer_draft"] = OfferDraft(
        request_id=req.id,
        request_rate=req_rate,
        proposed_rate=None,
        note=None,
        request_title=_req_title(req),
    )

    rows = [[f"✅ نرخ درخواست فروشنده/خریدار را تایید می‌کنم ({req_rate})"]] if req_rate is not None else []
    await msg.reply_text(
        f"داری برای «{_req_title(req)}» پیشنهاد می‌دی.\n\n"
        "یا نرخ پیشنهادی‌ت برای هر واحد ارز رو وارد کن"
        + ("، یا نرخ همین درخواست رو تایید کن:" if req_rate is not None else ":"),
        reply_markup=_rk_with_cancel(rows),
    )
    return RATE

async def offer_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.effective_message
    if not msg:
        return ConversationHandler.END

    d: OfferDraft | None = context.user_data.get("offer_draft")
    if not d:
        await msg.reply_text("❌ نشست شما منقضی شده. دوباره از روی پیام کانال اقدام کن.", reply_markup=_main_menu_kb())
        return ConversationHandler.END

    text = (msg.text or "").strip()
    if text == BTN_CANCEL:
        return await offer_cancel(update, context)

    if text.startswith("✅ نرخ درخواست"):
        if d.request_rate is None:
            await msg.reply_text("❌ نرخ درخواست موجود نیست. لطفاً نرخ پیشنهادی را دستی وارد کن.")
            return RATE
        d.proposed_rate = int(d.request_rate)
    else:
        try:
            cleaned = text.replace(",", "").replace(" ", "")
            rate = float(cleaned)
            if rate <= 0:
                raise ValueError()
            d.proposed_rate = int(round(rate))
        except Exception:
            rows = [[f"✅ نرخ درخواست فروشنده/خریدار را تایید می‌کنم ({d.request_rate})"]] if d.request_rate is not None else []
            await msg.reply_text(
                "❌ نرخ نامعتبره.\n"
                "لطفاً فقط عدد وارد کن یا از دکمه تایید نرخ استفاده کن.",
                reply_markup=_rk_with_cancel(rows) if rows else _rk_with_cancel([]),
            )
            return RATE

    context.user_data["offer_draft"] = d

    await msg.reply_text(
        "اگر توضیحی داری اضافه کن؛ یا دکمه بدون توضیحات رو بزن",
        reply_markup=_rk_with_cancel([[BTN_NO_NOTE]]),
    )
    return NOTE


async def offer_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.effective_message
    if not msg:
        return ConversationHandler.END

    d: OfferDraft | None = context.user_data.get("offer_draft")
    if not d or d.proposed_rate is None:
        await msg.reply_text("❌ نشست شما منقضی/ناقصه. دوباره از روی پیام کانال اقدام کن.", reply_markup=_main_menu_kb())
        return ConversationHandler.END

    text = (msg.text or "").strip()
    if text == BTN_CANCEL:
        return await offer_cancel(update, context)

    if text == BTN_NO_NOTE:
        d.note = None
    else:
        if len(text) > 700:
            await msg.reply_text("❌ توضیحات خیلی طولانیه. لطفاً کوتاه‌تر بنویس (حداکثر 700 کاراکتر).")
            return NOTE
        d.note = text

    context.user_data["offer_draft"] = d

    await msg.reply_text(
        _offer_preview(d),
        reply_markup=_rk_with_cancel([[BTN_SEND]]),
    )
    return CONFIRM


async def offer_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.effective_message
    tg = update.effective_user
    if not msg or not tg:
        return ConversationHandler.END

    d: OfferDraft | None = context.user_data.get("offer_draft")
    if not d or d.proposed_rate is None:
        await msg.reply_text("❌ نشست شما منقضی شده. دوباره از روی پیام کانال اقدام کن.", reply_markup=_main_menu_kb())
        return ConversationHandler.END

    text = (msg.text or "").strip()
    if text == BTN_CANCEL:
        return await offer_cancel(update, context)

    # دیگه "نه منصرف شدم" نداریم. فقط ارسال/انصراف.
    if text != BTN_SEND:
        await msg.reply_text(
            "لطفاً فقط یکی از گزینه‌ها رو انتخاب کن.",
            reply_markup=_rk_with_cancel([[BTN_SEND]]),
        )
        return CONFIRM

    if not await is_member_of_required_channel(context, tg.id):
        context.user_data.pop("offer_draft", None)
        await msg.reply_text(
            "❌ شما عضو کانال ما نیستی.\n"
            f"اول عضو {REQUIRED_CHANNEL} شو، بعد دوباره تلاش کن.",
            reply_markup=_main_menu_kb(),
        )
        return ConversationHandler.END

    try:
        sender = await _get_sender_from_tg_id(tg.id)
    except Exception:
        context.user_data.pop("offer_draft", None)
        await msg.reply_text("❌ کاربر شما در سیستم پیدا نشد. اول ثبت‌نام رو کامل کن.", reply_markup=_main_menu_kb())
        return ConversationHandler.END

    try:
        req = await _get_trade_request_for_offer(d.request_id)
    except Exception:
        context.user_data.pop("offer_draft", None)
        await msg.reply_text("❌ این درخواست دیگر فعال نیست.", reply_markup=_main_menu_kb())
        return ConversationHandler.END

    if getattr(req, "status", None) == TradeRequest.Status.CLOSED:
        context.user_data.pop("offer_draft", None)
        await msg.reply_text(
            "⛔️ این درخواست بسته شده و امکان ثبت پیشنهاد جدید نیست.",
            reply_markup=_main_menu_kb(),
        )
        return ConversationHandler.END

    best_prev = await _get_sender_last_offer_price(sender.id, req.id)
    if best_prev is not None and int(d.proposed_rate) <= int(best_prev):
        await msg.reply_text(
            f"❌ شما قبلاً برای این درخواست پیشنهاد {best_prev:,} تومان/واحد ثبت کرده‌اید.\n"
            "پیشنهاد جدید باید *بالاتر* از پیشنهاد قبلی شما باشد.\n\n"
            "اگر می‌خواهی نرخ را تغییر بدهی، دوباره روی درخواست کلیک کن و عدد بالاتر وارد کن.",
            parse_mode="Markdown",
            reply_markup=_rk_with_cancel([[BTN_SEND]]),
        )
        return CONFIRM

    try:
        offer = await _create_offer(
            req=req,
            sender=sender,
            unit_price_irt=int(d.proposed_rate),
            message=d.note or "",
        )
    except Exception:
        context.user_data.pop("offer_draft", None)
        await msg.reply_text("❌ خطا در ثبت پیشنهاد. لطفاً دوباره تلاش کن.", reply_markup=_main_menu_kb())
        return ConversationHandler.END

    try:
        offer_label = f"💰 {offer.unit_price_irt:,} | 🕒 {offer.created_at.strftime('%Y/%m/%d %H:%M')}"
        await sync_to_async(upsert_offer_line_in_channel)(
            req.id,
            offer.id,
            offer_label,
            "PENDING"
        )
    except Exception:
        pass

    try:
        method_text = req.get_deal_method_display() if req.deal_method else "—"
        ad_text = _ad_text(req)

        if req.owner and getattr(req.owner, "telegram_id", None):
            await context.bot.send_message(
                chat_id=req.owner.telegram_id,
                parse_mode="Markdown",
                text=(
                    "📩 *پیشنهاد جدید*\n\n"
                    f"📌 آگهی: {ad_text}\n"
                    f"🔁 روش معامله: `{method_text}`\n"
                    f"💰 مبلغ/نرخ پیشنهاد: {offer.unit_price_irt:,} تومان/واحد\n"
                    f"🕒 زمان ثبت: {offer.created_at.strftime('%Y/%m/%d %H:%M')}\n"
                    f"📝 توضیحات: {offer.message or '—'}\n"
                ),
                reply_markup=build_offer_manage_keyboard(offer.id),
            )
    except Exception:
        pass

    context.user_data.pop("offer_draft", None)

    await msg.reply_text(
        f"✅ پیشنهاد شما برای «{d.request_title or f'#{d.request_id}'}» ارسال شد.\n"
        "لطفاً منتظر تایید/رد درخواست‌دهنده باشید.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def offer_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("offer_draft", None)
    msg = update.effective_message
    if msg:
        await msg.reply_text("✅ انصراف انجام شد.", reply_markup=build_main_menu_keyboard())
    return ConversationHandler.END


MYOFFERS_PAGE_SIZE = 1


def _status_fa(s: str) -> str:
    mapping = {
        getattr(TradeOffer.Status, "PENDING", "PENDING"): "در انتظار",
        getattr(TradeOffer.Status, "ACCEPTED", "ACCEPTED"): "✅ تایید شده",
        getattr(TradeOffer.Status, "REJECTED", "REJECTED"): "❌ رد شده",
    }
    return mapping.get(s, s)

def deal_method_fa(req: TradeRequest) -> str:
    value = getattr(req, "deal_method", None)
    if not value:
        return "—"
    return dict(TradeRequest.DealMethod.choices).get(value, str(value))

def _req_status_fa(s: str) -> str:
    mapping = {
        TradeRequest.Status.DRAFT: "پیش‌نویس",
        TradeRequest.Status.PENDING_ADMIN: "در انتظار تایید ادمین",
        TradeRequest.Status.APPROVED: "تایید شده",
        TradeRequest.Status.CLOSED: "بسته شده",
    }
    return mapping.get(s, s)


def _role_fa(role: str) -> str:
    return "خریدار" if role == TradeRequest.Role.BUYER else "فروشنده"


@sync_to_async
def get_user_by_tg(tg_id: int):
    return CustomUser.objects.filter(telegram_id=tg_id).first()


@sync_to_async
def fetch_user_offers(user_id: int, page: int):
    qs = (
        TradeOffer.objects
        .select_related("request", "request__owner")
        .filter(sender_id=user_id)
        .order_by("-created_at")
    )
    total = qs.count()
    start = page * MYOFFERS_PAGE_SIZE
    end = start + MYOFFERS_PAGE_SIZE
    return list(qs[start:end]), total


def build_myoffers_pagination_keyboard(page: int, total: int) -> InlineKeyboardMarkup:
    max_page = max((total - 1) // MYOFFERS_PAGE_SIZE, 0)
    rows = []

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"offers:{page-1}"))
    if page < max_page:
        nav.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"offers:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("🏠 منوی اصلی", callback_data="offers:home")])
    return InlineKeyboardMarkup(rows)


async def send_my_offers_list(message_obj, user: CustomUser, page: int, *, edit: bool = False):
    items, total = await fetch_user_offers(user.id, page)

    if total == 0:
        if edit:
            await message_obj.edit_text("📨 هنوز هیچ پیشنهادی ثبت نکردی.")
            await message_obj.reply_text("🏠 برگشتی به منوی اصلی.", reply_markup=build_main_menu_keyboard())
        else:
            await message_obj.reply_text("📨 هنوز هیچ پیشنهادی ثبت نکردی.", reply_markup=build_main_menu_keyboard())
        return

    max_page = max((total - 1) // MYOFFERS_PAGE_SIZE, 0)
    page = max(0, min(page, max_page))
    items, total = await fetch_user_offers(user.id, page)

    o = items[0]
    req = getattr(o, "request", None)

    req_id = getattr(req, "id", "—")
    currency = getattr(req, "currency", "—")
    role = getattr(req, "role", None)
    role_fa = _role_fa(role) if role else "—"
    req_rate = getattr(req, "unit_price_irt", None)
    req_status = _req_status_fa(getattr(req, "status", "—")) if req else "—"

    offer_status = _status_fa(getattr(o, "status", "—"))

    header = (
        f"📨 *پیشنهادهای من* (صفحه {page+1} از {max_page+1})\n\n"
        f"🧾 *درخواست مربوطه*\n"
        f"🆔 درخواست #{req_id}\n"
        f"👤 نقش: {role_fa} | 💱 ارز: {currency}\n"
        f"🏷 نرخ درخواست: {f'{req_rate:,}' if isinstance(req_rate, int) else (req_rate if req_rate is not None else '—')} تومان/واحد\n"
        f"📌 وضعیت درخواست: {req_status}\n"
        "\n—————————————————————\n"
    )

    offer_block = (
        f"📌 *پیشنهاد شما*\n"
        f"🧾 پیشنهاد #{o.id}\n"
        f"💰 نرخ پیشنهادی: {o.unit_price_irt:,} تومان/واحد\n"
        f"📌 وضعیت پیشنهاد: {offer_status}\n"
        f"🕒 {o.created_at.strftime('%Y/%m/%d %H:%M')}\n"
    )

    note = (getattr(o, "message", "") or "").strip()
    if note:
        offer_block += f"\n📝 توضیحات: {note}"

    text = header + offer_block
    kb = build_myoffers_pagination_keyboard(page, total)

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


async def my_offers_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    user = await get_user_by_tg(tg.id)
    if not user:
        await update.effective_message.reply_text("❌ اول باید ثبت‌نام کنی.", reply_markup=build_main_menu_keyboard())
        return
    await send_my_offers_list(update.effective_message, user, page=0, edit=False)


async def my_offers_page_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "offers:home":
        await q.message.reply_text("🏠 برگشتی به منوی اصلی.", reply_markup=build_main_menu_keyboard())
        return

    user = await get_user_by_tg(q.from_user.id)
    if not user:
        await q.message.reply_text("❌ اول باید ثبت‌نام کنی.", reply_markup=build_main_menu_keyboard())
        return

    try:
        page = int(q.data.split(":", 1)[1])
    except Exception:
        page = 0

    await send_my_offers_list(q.message, user, page=page, edit=True)


def get_my_offers_handlers():
    return [
        CommandHandler("offers", my_offers_entry),
        MessageHandler(filters.Regex(r"^📬پیشنهادهای من$"), my_offers_entry),
        CallbackQueryHandler(my_offers_page_cb, pattern=r"^offers:(\d+|home)$"),
        CallbackQueryHandler(offerflow_inline_nav_cb, pattern=r"^offerflow:(home|profile)$"),
    ]


def build_offer_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler(
                "start",
                offer_start_entry,
            )
        ],
        states={
            RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, offer_rate)],
            NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, offer_note)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, offer_confirm)],
        },
        fallbacks=[CommandHandler("cancel", offer_cancel)],
        name="offer_flow",
        persistent=False,
        allow_reentry=True,
        per_user=True,
        per_chat=True,
    )