import os
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.db import transaction

from asgiref.sync import async_to_sync
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError

from Trade.models.models import TradeRequest

CHANNEL = "@testmestplat"
BOT_USERNAME = 'thisisatestforplattkar_bot'

def build_channel_post_text(req: TradeRequest) -> str:
    role = "خریدار" if req.role == TradeRequest.Role.BUYER else "فروشنده"
    return (
        "📌 *درخواست جدید*\n\n"
        f"🆔 شناسه: `{req.id}`\n"
        f"👤 نقش: {role}\n"
        f"💱 ارز: {req.currency}\n"
        f"💰 قیمت هر واحد (تومان): {req.unit_price_irt}\n"
        f"💳 روش معامله: {req.deal_method}\n"
        f"📝 توضیحات: {req.description or '—'}\n"
        f"💸 کارمزد (تومان): {req.fee_irt}\n"
    )

def build_channel_keyboard(req_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 پیشنهاد بده", url=f"https://t.me/{BOT_USERNAME}?start=offer_{req_id}")]
    ])

@receiver(pre_save, sender=TradeRequest)
def cache_old_status(sender, instance: TradeRequest, **kwargs):
    if not instance.pk:
        instance._old_status = None
        return
    try:
        old = TradeRequest.objects.only("status").get(pk=instance.pk)
        instance._old_status = old.status
    except TradeRequest.DoesNotExist:
        instance._old_status = None

@receiver(post_save, sender=TradeRequest)
def on_request_approved(sender, instance: TradeRequest, created: bool, **kwargs):

    old = getattr(instance, "_old_status", None)
    if old == instance.status:
        return

    if instance.status != TradeRequest.Status.APPROVED:
        return

    def _do():
        token = os.environ.get("API_TOKEN")
        if not token:
            print("API_TOKEN not set")
            return

        bot = Bot(token=token)

        if instance.owner and instance.owner.telegram_id:
            try:
                async_to_sync(bot.send_message)(
                    chat_id=instance.owner.telegram_id,
                    text=f"✅ درخواست شما (#{instance.id}) توسط ادمین تایید شد و در کانال منتشر می‌شود."
                )
            except TelegramError as e:
                print("TELEGRAM user notify ERROR:", repr(e))

        try:
            msg = async_to_sync(bot.send_message)(
                chat_id=CHANNEL,
                text=build_channel_post_text(instance),
                parse_mode="Markdown",
                reply_markup=build_channel_keyboard(instance.id),
                disable_web_page_preview=True,
            )

            TradeRequest.objects.filter(pk=instance.pk).update(
                status=TradeRequest.Status.POSTED,
                channel_chat_id=getattr(msg.chat, "id", None),
                channel_message_id=getattr(msg, "message_id", None),
            )
        except TelegramError as e:
            print("TELEGRAM channel post ERROR:", repr(e))

    transaction.on_commit(_do)
