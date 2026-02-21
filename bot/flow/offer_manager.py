from telegram import Update
from telegram.ext import ContextTypes
from asgiref.sync import sync_to_async
from telegram.error import BadRequest
from Trade.services.offers_service import set_offer_status_in_channel

from Trade.models.models import TradeOffer
from Trade.services.offers_service import build_offer_after_accept_keyboard


@sync_to_async
def get_offer_for_owner(offer_id: int, owner_tg_id: int):
    return (
        TradeOffer.objects
        .select_related("sender", "request")
        .filter(
            id=offer_id,
            request__owner__telegram_id=owner_tg_id
        )
        .first()
    )


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


    offer.status = TradeOffer.Status.ACCEPTED
    await sync_to_async(offer.save)()

    offer_name = offer.sender.name or offer.sender.username or ""
    await sync_to_async(set_offer_status_in_channel)(
        offer.request.id,
        offer.id,
        offer_name,
        "ACCEPTED"
    )

    try:

        await context.bot.send_message(
            chat_id=offer.sender.telegram_id,
            text="✅ پیشنهاد شما تایید شد."
                 f"\nبه‌زودی درخواست‌دهنده با شما تماس می‌گیرد. {offer.request.id}"
        )
    except Exception:
        pass

    base_text = q.message.text or q.message.caption or ""
    new_text = (
        "🟩✅ تایید شد\n"
        "━━━━━━━━━━━━━━\n"
        f"{base_text}"
    )

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
    await sync_to_async(offer.save)()

    offer_name = offer.sender.name or offer.sender.username or ""
    await sync_to_async(set_offer_status_in_channel)(
        offer.request.id,
        offer.id,
        offer_name,
        "REJECTED"
    )

    await context.bot.send_message(
        chat_id=offer.sender.telegram_id,
        text="❌ متأسفانه پیشنهاد شما رد شد."
    )

    await q.message.delete()


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
        f"👤{user.last_name}\n"
        f"\n📅 عضو از: {joined}",
        show_alert=True
    )
