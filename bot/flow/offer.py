from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from asgiref.sync import sync_to_async
from django.db.models import Q

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
)
from telegram.ext import (
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)

from Users.models.models import CustomUser
from Trade.models.models import TradeRequest, TradeOffer
from Trade.services.offers_service import (
    build_offer_manage_keyboard,
    upsert_offer_line_in_channel,
    channel_post_link,
)

from bot.flow.registration import get_or_create_user, is_profile_complete
from bot.handlers import build_main_menu_keyboard


REQUIRED_CHANNEL = "@excoinmarket"
START_OFFER_RE = re.compile(r"^offer_(\d+)$")

RATE, NOTE, CONFIRM = range(3)

BTN_CANCEL = "❌ انصراف"
BTN_NO_NOTE = "📝 بدون توضیحات"
BTN_SEND = "✅ ارسال کن"


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
    rows = rows or []
    if [BTN_CANCEL] not in rows:
        rows.append([BTN_CANCEL])
    return _rk(rows)


def _main_menu_kb() -> ReplyKeyboardMarkup:
    kb = build_main_menu_keyboard()
    return kb if kb else _rk([["🏠 منوی اصلی"], ["👤 پروفایل"]])


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
    role_val = getattr(req, "role", None)
    currency = getattr(req, "currency", "—")
    return f"درخواست #{req.id} ({role_val} {currency})"  # role value خام


def _offer_preview(d: OfferDraft) -> str:
    return (
        "🧾 پیش‌نمایش پیشنهاد شما:\n\n"
        f"📌 آگهی: {d.request_title or f'#{d.request_id}'}\n"
        f"💱 نرخ درخواست (تومان/واحد): {d.request_rate if d.request_rate is not None else '—'}\n"
        f"✅ نرخ پیشنهادی شما (تومان/واحد): {d.proposed_rate}\n"
        f"📝 توضیحات: {d.note if d.note else '—'}\n\n"
        "مطمئنی می‌خوای ارسال بشه؟"
    )


async def offer_start_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.effective_message
    tg = update.effective_user
    if not msg or not tg:
        return ConversationHandler.END

    if not context.args:
        return ConversationHandler.END

    m = START_OFFER_RE.match(str(context.args[0]).strip())
    if not m:
        return ConversationHandler.END

    request_id = int(m.group(1))

    user = await get_or_create_user(tg.id, tg.username)

    if not is_profile_complete(user):
        await msg.reply_text(
            "❌ ثبت‌نامت کامل نیست.\n"
            "از منوی «پروفایل» ثبت‌نام رو کامل کن و دوباره اقدام کن.",
            reply_markup=_main_menu_kb(),
        )
        return ConversationHandler.END

    if not await is_member_of_required_channel(context, tg.id):
        await msg.reply_text(
            "❌ شما عضو کانال ما نیستی.\n"
            f"اول عضو {REQUIRED_CHANNEL} شو، بعد دوباره تلاش کن.",
            reply_markup=_main_menu_kb(),
        )
        return ConversationHandler.END

    try:
        req = await _get_trade_request_for_offer(request_id)
    except TradeRequest.DoesNotExist:
        await msg.reply_text("❌ این درخواست پیدا نشد یا دیگر فعال نیست.", reply_markup=_main_menu_kb())
        return ConversationHandler.END

    req_rate = int(req.unit_price_irt) if req.unit_price_irt is not None else None

    context.user_data["offer_draft"] = OfferDraft(
        request_id=req.id,
        request_rate=req_rate,
        proposed_rate=None,
        note=None,
        request_title=_req_title(req),
    )

    rows = []
    if req_rate is not None:
        rows.append([f"✅ نرخ درخواست را تایید می‌کنم ({req_rate})"])

    await msg.reply_text(
        f"داری برای «{_req_title(req)}» پیشنهاد می‌دی.\n\n"
        "نرخ پیشنهادی‌ت برای هر واحد رو وارد کن"
        + (" یا نرخ همین درخواست رو تایید کن:" if req_rate is not None else ":"),
        reply_markup=_rk_with_cancel(rows),
    )
    return RATE


async def offer_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.effective_message
    if not msg:
        return ConversationHandler.END

    d: OfferDraft | None = context.user_data.get("offer_draft")
    if not d:
        await msg.reply_text("❌ نشست منقضی شده. دوباره از روی پیام کانال اقدام کن.", reply_markup=_main_menu_kb())
        return ConversationHandler.END

    text = (msg.text or "").strip()
    if text == BTN_CANCEL:
        return await offer_cancel(update, context)

    if text.startswith("✅ نرخ درخواست"):
        if d.request_rate is None:
            await msg.reply_text("❌ نرخ درخواست موجود نیست. عدد وارد کن.", reply_markup=_rk_with_cancel([]))
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
            rows = []
            if d.request_rate is not None:
                rows.append([f"✅ نرخ درخواست را تایید می‌کنم ({d.request_rate})"])
            await msg.reply_text(
                "❌ نرخ نامعتبره. فقط عدد وارد کن یا دکمه تایید نرخ رو بزن.",
                reply_markup=_rk_with_cancel(rows),
            )
            return RATE

    context.user_data["offer_draft"] = d

    await msg.reply_text(
        "اگر توضیحی داری بنویس؛ یا دکمه بدون توضیحات رو بزن.",
        reply_markup=_rk_with_cancel([[BTN_NO_NOTE]]),
    )
    return NOTE


async def offer_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.effective_message
    if not msg:
        return ConversationHandler.END

    d: OfferDraft | None = context.user_data.get("offer_draft")
    if not d or d.proposed_rate is None:
        await msg.reply_text("❌ نشست منقضی/ناقصه. دوباره اقدام کن.", reply_markup=_main_menu_kb())
        return ConversationHandler.END

    text = (msg.text or "").strip()
    if text == BTN_CANCEL:
        return await offer_cancel(update, context)

    if text == BTN_NO_NOTE:
        d.note = None
    else:
        if len(text) > 700:
            await msg.reply_text("❌ توضیحات خیلی طولانیه (حداکثر 700 کاراکتر).", reply_markup=_rk_with_cancel([]))
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
        await msg.reply_text("❌ نشست منقضی شده. دوباره اقدام کن.", reply_markup=_main_menu_kb())
        return ConversationHandler.END

    text = (msg.text or "").strip()
    if text == BTN_CANCEL:
        return await offer_cancel(update, context)

    if text != BTN_SEND:
        await msg.reply_text("لطفاً فقط دکمه ارسال یا انصراف رو بزن.", reply_markup=_rk_with_cancel([[BTN_SEND]]))
        return CONFIRM

    if not await is_member_of_required_channel(context, tg.id):
        context.user_data.pop("offer_draft", None)
        await msg.reply_text("❌ عضو کانال نیستی. اول عضو شو و دوباره تلاش کن.", reply_markup=_main_menu_kb())
        return ConversationHandler.END

    try:
        sender = await _get_sender_from_tg_id(tg.id)
    except Exception:
        context.user_data.pop("offer_draft", None)
        await msg.reply_text("❌ کاربر پیدا نشد. اول ثبت‌نام رو کامل کن.", reply_markup=_main_menu_kb())
        return ConversationHandler.END

    try:
        req = await _get_trade_request_for_offer(d.request_id)
    except Exception:
        context.user_data.pop("offer_draft", None)
        await msg.reply_text("❌ این درخواست دیگر فعال نیست.", reply_markup=_main_menu_kb())
        return ConversationHandler.END

    if getattr(req, "status", None) == TradeRequest.Status.CLOSED:
        context.user_data.pop("offer_draft", None)
        await msg.reply_text("⛔️ این درخواست بسته شده و امکان پیشنهاد جدید نیست.", reply_markup=_main_menu_kb())
        return ConversationHandler.END

    try:
        offer = await _create_offer(
            req=req,
            sender=sender,
            unit_price_irt=int(d.proposed_rate),
            message=d.note or "",
        )
    except Exception:
        context.user_data.pop("offer_draft", None)
        await msg.reply_text("❌ خطا در ثبت پیشنهاد. دوباره تلاش کن.", reply_markup=_main_menu_kb())
        return ConversationHandler.END

    # ✅ کانال: ذخیره ساعت+مبلغ (بدون نام/آیدی پیشنهاددهنده)
    try:
        await sync_to_async(upsert_offer_line_in_channel)(req.id, offer.id, "PENDING")
    except Exception:
        pass

    # ✅ پیام مالک: بدون نام/آیدی پیشنهاددهنده، فقط ساعت+مبلغ و متد(value) و لینک آگهی
    try:
        if req.owner and getattr(req.owner, "telegram_id", None):
            link = channel_post_link(req)
            ad_text = f"[مشاهده آگهی]({link})" if link else f"#{req.id}"

            method_value = getattr(req, "method", None)
            method_text = str(method_value) if method_value is not None else "—"

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
        "✅ پیشنهاد شما ارسال شد. لطفاً منتظر تایید/رد درخواست‌دهنده باشید.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def offer_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("offer_draft", None)
    msg = update.effective_message
    if msg:
        await msg.reply_text("✅ انصراف انجام شد.", reply_markup=build_main_menu_keyboard())
    return ConversationHandler.END


def build_offer_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler(
                "start",
                offer_start_entry,
                filters=filters.Regex(r"^/start\s+offer_\d+$"),
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