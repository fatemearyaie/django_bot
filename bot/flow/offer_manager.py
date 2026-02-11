from telegram import Update
from telegram.ext import ContextTypes
from asgiref.sync import sync_to_async
from Trade.models.models import TradeOffer
from Trade.services.offers_service import build_offer_after_accept_keyboard
from bot.flow.registration import build_main_menu_keyboard


# ==== helpers ===

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

# ===== Accept =====
async def offer_accept_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    offer_id = int(q.data.split(":")[1])
    offer = await get_offer_for_owner(offer_id, q.from_user.id)

    if not offer:
        await q.answer("❌ دسترسی نداری", show_alert=True)
        return

    if offer.status == TradeOffer.Status.ACCEPTED:
        await q.answer("قبلاً تایید شده ✅", show_alert=False)
        return

    offer.status = TradeOffer.Status.ACCEPTED
    await sync_to_async(offer.save)()

    await context.bot.send_message(
        chat_id=offer.sender.telegram_id,
        text="✅ پیشنهاد شما تایید شد.\nبه‌زودی درخواست‌دهنده با شما تماس می‌گیرد.",
        reply_markup=build_main_menu_keyboard,
    )


    new_text = (
        "🟩✅ *تایید شد*\n"
        "━━━━━━━━━━━━━━\n"
        f"{q.message.text}"
    )

    await q.edit_message_text(
        text=new_text,
        parse_mode="Markdown",
        reply_markup=build_offer_after_accept_keyboard(offer.id),
        disable_web_page_preview=True,
    )


# ===== Reject =====
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

    await context.bot.send_message(
        chat_id=offer.sender.telegram_id,
        text="❌ متأسفانه پیشنهاد شما رد شد.",
        reply_markup=build_main_menu_keyboard,

    )

    await q.message.delete()

# ===== User Data =====
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
        f"👤 {user.name or user.username}\n📅 عضو از: {joined}",
        show_alert=True
    )

