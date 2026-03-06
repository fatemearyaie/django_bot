from telegram import Update
from telegram.ext import ContextTypes
from asgiref.sync import sync_to_async
from telegram.error import BadRequest
from decouple import config
from django.db import transaction

from Trade.models.models import TradeOffer, TradeRequest
from Trade.services.offers_service import (
    set_offer_status_in_channel,
    build_offer_after_accept_keyboard,
    channel_post_link,
)
from bot.flow.offer import jalali_with_month_name

FEE = config("TRADE_REQUEST_FEE")

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

    # ✅ accept + close
    await _accept_offer_and_close_request(offer)

    offer_label = (
        f"{offer.unit_price_irt:,} تومان "
        f"در {jalali_with_month_name(offer.created_at)}"
    )
    await sync_to_async(set_offer_status_in_channel)(
        offer.request.id,
        offer.id,
        offer_label,
        "ACCEPTED"
    )
    other_rejected = await get_other_rejected_offers(offer.request.id, offer.id)

    for ro in other_rejected:
        rejected_label = (
            f"{ro.unit_price_irt:,} تومان "
            f"در {jalali_with_month_name(ro.created_at)}"
        )
        await sync_to_async(set_offer_status_in_channel)(
            ro.request.id,
            ro.id,
            rejected_label,
            "REJECTED"
        )

    try:
        req = offer.request
        link = channel_post_link(req)
        ad_text = f"[مشاهده جزئیات حواله]({link})" if link else f"#{req.id}"

        method_value = getattr(req, "deal_method", None)
        method_text = dict(TradeRequest.DealMethod.choices).get(method_value,str(method_value)) if method_value else "—"



        amount_text = getattr(req, "amount", None)
        amount_text = str(amount_text) if amount_text is not None else "—"

        price_val = getattr(offer, "unit_price_irt", None)
        price_text = f"{int(price_val):,}" if isinstance(price_val, (int, float)) else "—"

        created_at = getattr(offer, "created_at", None)
        created_at_text = created_at.strftime("%Y/%m/%d %H:%M") if created_at else "—"

        # ✅ اضافه شد: مقدار عددی amount برای محاسبه
        amount_val = getattr(req, "amount", None)

        # ✅ اضافه شد: FEE اگر تعریف نشده/None بود کرش نکنه
        try:
            fee_val = int(FEE)
        except Exception:
            fee_val = 0

        # ✅ اضافه شد: محاسبه امن مبلغ نهایی
        final_amount = None
        try:
            if price_val is not None and amount_val is not None:
                # اگر amount Decimal باشه هم کار می‌کنه
                final_amount = int(price_val * float(amount_val)) + fee_val
        except Exception:
            final_amount = None

        # ✅ اضافه شد: متن نمایشی مبلغ نهایی
        final_amount_text = f"{final_amount:,}" if isinstance(final_amount, int) else "—"
        # ✅ اضافه شد: کارمزد با جداکننده
        fee_text = f"{fee_val:,}"

        await context.bot.send_message(
            chat_id=offer.sender.telegram_id,
            parse_mode="Markdown",
            text=(
                "✅ *توافق جدید ثبت شد*\n\n"
                f" مشاهده جزئیات حواله {ad_text}\n"
                f"📦 مقدار: {amount_text}\n"
                f"💰 مبلغ/نرخ پیشنهاد: {price_text} تومان\n"
                f"🕒 زمان ثبت پیشنهاد: {created_at_text}\n"
                f"🔁 روش معامله: `{method_text}`\n"
                f"📝 توضیحات: {offer.message if offer.message else '—'}\n\n"
                f"شما در ازای پرداخت مبلغ {final_amount_text} ارز تومان با لحاظ مقدار کارمزد تعداد {amount_text} معامله خواهید کرد\n\n"
                
                "این پیام را برای ادمین بفرستید تا ارتباط بین شما و درخواست دهنده را برقرار کنند\n"                
                f" 💸 کارمزد: {fee_text} تومان\n"
            )
        )
    except Exception:
        pass

    # ✅ آپدیت پیام مالک
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
        f"{offer.unit_price_irt:,} تومان "
        f"در {jalali_with_month_name(offer.created_at)}"
    )

    await sync_to_async(set_offer_status_in_channel)(
        offer.request.id,
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