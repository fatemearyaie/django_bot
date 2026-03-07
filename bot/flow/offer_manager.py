from decimal import Decimal, ROUND_HALF_UP
from html import escape

from telegram import Update
from telegram.ext import ContextTypes
from asgiref.sync import sync_to_async
from telegram.error import BadRequest
from django.db import transaction

from Trade.models.models import TradeOffer, TradeRequest
from Trade.services.offers_service import (
    set_offer_status_in_channel,
    build_offer_after_accept_keyboard,
    channel_post_link,
)
from bot.flow.offer import jalali_with_month_name


def get_trade_fee(currency: str, amount) -> Decimal:
    currency = (currency or "").upper()
    amount = Decimal(str(amount or 0))

    if amount <= 0:
        return Decimal("0")

    if currency == "EUR":
        if amount <= 250:
            return Decimal("1")
        elif amount <= 500:
            return Decimal("1.5")
        else:
            return (amount * Decimal("0.003")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if currency == "USD":
        if amount <= 250:
            return Decimal("1.2")
        elif amount <= 500:
            return Decimal("1.8")
        else:
            return (amount * Decimal("0.0035")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if currency == "AED":
        if amount <= 250:
            return Decimal("4.33")
        elif amount <= 500:
            return Decimal("6.5")
        else:
            return (amount * Decimal("0.013")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return Decimal("0")


def format_money(val) -> str:
    if val is None:
        return "—"

    d = Decimal(str(val))
    if d == d.to_integral():
        return f"{int(d):,}"
    return f"{d:,.2f}"


def calculate_score_from_fee_toman(fee_toman) -> int:
    fee_toman = Decimal(str(fee_toman or 0))

    if fee_toman < Decimal("100000"):
        return 0

    return int(fee_toman // Decimal("100000")) * 5


@sync_to_async
def get_offer_for_owner(offer_id: int, owner_tg_id: int):
    return (
        TradeOffer.objects
        .select_related("sender", "request", "request__owner")
        .filter(id=offer_id, request__owner__telegram_id=owner_tg_id)
        .first()
    )


@sync_to_async
def get_other_rejected_offers(request_id: int, accepted_offer_id: int):
    return list(
        TradeOffer.objects.filter(
            request_id=request_id,
            status=TradeOffer.Status.REJECTED,
        ).exclude(id=accepted_offer_id)
    )


@sync_to_async
def _accept_offer_and_close_request(offer: TradeOffer):
    with transaction.atomic():
        offer.status = TradeOffer.Status.ACCEPTED
        offer.save(update_fields=["status"])

        req = offer.request
        req.status = TradeRequest.Status.CLOSED
        req.save(update_fields=["status"])

        TradeOffer.objects.filter(
            request_id=req.id,
            status=TradeOffer.Status.PENDING
        ).exclude(id=offer.id).update(status=TradeOffer.Status.REJECTED)


@sync_to_async
def _apply_scores_for_accepted_offer(offer_id: int):
    offer = (
        TradeOffer.objects
        .select_related("sender", "request", "sender__invited_by")
        .get(id=offer_id)
    )

    req = offer.request
    user = offer.sender

    amount_val = getattr(req, "amount", None)
    currency_value = getattr(req, "currency", None)
    price_val = getattr(offer, "unit_price_irt", None)

    amount_decimal = Decimal(str(amount_val)) if amount_val is not None else None
    price_decimal = Decimal(str(price_val)) if price_val is not None else None

    fee_in_currency = get_trade_fee(currency_value, amount_decimal) if amount_decimal is not None else Decimal("0")

    fee_toman = Decimal("0")
    if price_decimal is not None:
        fee_toman = (fee_in_currency * price_decimal).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

    accepted_count = TradeOffer.objects.filter(
        sender=user,
        status=TradeOffer.Status.ACCEPTED
    ).count()

    score_to_add = 0

    # 1) بونوس اولین معامله خود کاربر
    if accepted_count == 1:
        score_to_add += 5

    # 3) امتیاز کارمزد
    score_to_add += calculate_score_from_fee_toman(fee_toman)

    if score_to_add > 0:
        user.total_points = (user.total_points or 0) + score_to_add
        user.save(update_fields=["total_points"])

    # 2-ب) اولین معامله زیرمجموعه => 10 امتیاز برای معرف
    if accepted_count == 1 and user.invited_by and not user.referral_first_trade_rewarded:
        inviter = user.invited_by
        inviter.total_points = (inviter.total_points or 0) + 10
        inviter.save(update_fields=["total_points"])

        user.referral_first_trade_rewarded = True
        user.save(update_fields=["referral_first_trade_rewarded"])

async def offer_accept_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    try:
        offer_id = int(q.data.split(":")[1])
    except Exception:
        await q.answer("❌ دیتای نامعتبر", show_alert=True)
        return

    offer = await get_offer_for_owner(offer_id, q.from_user.id)
    if not offer:
        await q.answer("❌ دسترسی نداری", show_alert=True)
        return

    if offer.status == TradeOffer.Status.ACCEPTED:
        await q.answer("قبلاً تایید شده ✅", show_alert=False)
        return

    await _accept_offer_and_close_request(offer)
    await _apply_scores_for_accepted_offer(offer.id)

    offer_label = (
        f"{format_money(offer.unit_price_irt)} تومان "
        f"در {jalali_with_month_name(offer.created_at)}"
    )
    await sync_to_async(set_offer_status_in_channel)(
        offer.request_id,
        offer.id,
        offer_label,
        "ACCEPTED"
    )

    other_rejected = await get_other_rejected_offers(offer.request_id, offer.id)

    for ro in other_rejected:
        rejected_label = (
            f"{format_money(ro.unit_price_irt)} تومان "
            f"در {jalali_with_month_name(ro.created_at)}"
        )
        await sync_to_async(set_offer_status_in_channel)(
            ro.request_id,
            ro.id,
            rejected_label,
            "REJECTED"
        )

    try:
        req = offer.request
        link = channel_post_link(req)
        ad_text = f'<a href="{link}">مشاهده جزئیات حواله</a>' if link else f"#{req.id}"

        method_value = getattr(req, "deal_method", None)
        method_text = dict(TradeRequest.DealMethod.choices).get(
            method_value, str(method_value)
        ) if method_value else "—"

        amount_val = getattr(req, "amount", None)
        currency_value = getattr(req, "currency", None)
        currency_text = req.get_currency_display() if currency_value else "—"

        if amount_val is not None:
            amount_decimal = Decimal(str(amount_val))
            amount_text = f"{format_money(amount_decimal)} {currency_text}"
        else:
            amount_decimal = None
            amount_text = f"— {currency_text}" if currency_text != "—" else "—"

        price_val = getattr(offer, "unit_price_irt", None)
        price_decimal = Decimal(str(price_val)) if price_val is not None else None
        price_text = format_money(price_decimal)

        created_at = getattr(offer, "created_at", None)
        created_at_text = jalali_with_month_name(created_at) if created_at else "—"

        # کارمزد بر حسب خود ارز
        fee_in_currency = get_trade_fee(currency_value, amount_decimal) if amount_decimal is not None else Decimal("0")

        # تبدیل کارمزد به تومان با نرخ هر واحد
        fee_toman = None
        if price_decimal is not None:
            fee_toman = (fee_in_currency * price_decimal).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # مبلغ پایه معامله به تومان
        base_amount_toman = None
        if price_decimal is not None and amount_decimal is not None:
            base_amount_toman = (amount_decimal * price_decimal).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # مبلغ نهایی = مبلغ پایه + کارمزد تبدیل‌شده به تومان
        final_amount_toman = None
        if base_amount_toman is not None and fee_toman is not None:
            final_amount_toman = (base_amount_toman + fee_toman).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        fee_in_currency_text = format_money(fee_in_currency)
        fee_toman_text = format_money(fee_toman)
        final_amount_text = format_money(final_amount_toman)

        offer_message_text = escape(offer.message) if offer.message else "—"
        method_text_safe = escape(method_text)
        amount_text_safe = escape(amount_text)
        price_text_safe = escape(price_text)
        created_at_text_safe = escape(created_at_text)
        final_amount_text_safe = escape(final_amount_text)
        fee_in_currency_text_safe = escape(fee_in_currency_text)
        fee_toman_text_safe = escape(fee_toman_text)
        currency_text_safe = escape(currency_text)

        await context.bot.send_message(
            chat_id=offer.sender.telegram_id,
            parse_mode="HTML",
            disable_web_page_preview=True,
            text=(
                "✅ <b>توافق جدید ثبت شد</b>\n\n"
                f"📌 {ad_text}\n\n"
                f"⬅ مقدار: {amount_text_safe}\n\n"
                f"⬅ نرخ پیشنهادی: <b>{price_text_safe} تومان</b>\n\n"
                f"⬅ زمان ثبت پیشنهاد: {created_at_text_safe}\n\n"
                f"⬅ روش انجام معامله: {method_text_safe}\n\n"
                f"⬅ توضیحات: {offer_message_text}\n\n"
                "<b>جزئیات تسویه در صورت تأیید معامله:</b>\n"

                f"در صورت پذیرش نرخ ثبت‌شده، با پرداخت مبلغ "
                f"<b>{final_amount_text_safe} تومان</b> (با احتساب کارمزد)، "
                f"مقدار <b>{amount_text_safe}</b> دریافت خواهید کرد.\n\n"
                "⚡این پیام را به ادمین ارسال کنید تا هماهنگی‌های بعدی صورت پذیرد."
            )
        )
    except Exception as e:
        print("SEND ACCEPT MESSAGE ERROR:", type(e), repr(e))

    base_text = q.message.text or q.message.caption or ""
    new_text = "🟩✅ تایید شد\n━━━━━━━━━━━━━━\n" + base_text

    try:
        await q.edit_message_text(
            text=new_text,
            reply_markup=build_offer_after_accept_keyboard(offer.id),
            disable_web_page_preview=True,
        )
    except BadRequest:
        try:
            await q.message.reply_text(
                text=new_text,
                reply_markup=build_offer_after_accept_keyboard(offer.id),
                disable_web_page_preview=True,
            )
        except Exception:
            pass
    except Exception:
        pass


async def offer_reject_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    offer_id = int(q.data.split(":")[1])
    offer = await get_offer_for_owner(offer_id, q.from_user.id)
    if not offer:
        await q.answer("❌ دسترسی نداری", show_alert=True)
        return

    offer.status = TradeOffer.Status.REJECTED
    await sync_to_async(offer.save)(update_fields=["status"])

    offer_label = (
        f"{format_money(offer.unit_price_irt)} تومان "
        f"در {jalali_with_month_name(offer.created_at)}"
    )

    await sync_to_async(set_offer_status_in_channel)(
        offer.request_id,
        offer.id,
        offer_label,
        "REJECTED"
    )

    try:
        await context.bot.send_message(
            chat_id=offer.sender.telegram_id,
            text="❌ متأسفانه پیشنهاد شما رد شد."
        )
    except Exception:
        pass

    try:
        await q.message.delete()
    except Exception:
        pass


async def offer_user_info_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    offer_id = int(q.data.split(":")[1])

    offer = await get_offer_for_owner(offer_id, q.from_user.id)
    if not offer:
        await q.answer("❌", show_alert=True)
        return

    user = offer.sender
    joined = user.date_joined.strftime("%Y/%m/%d")

    await q.answer(
        f"👤 {user.name}\n"
        f"👤 {user.last_name}\n"
        f"\n📅 عضو از: {joined}",
        show_alert=True
    )