import os
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.db import transaction

from asgiref.sync import async_to_sync
from telegram import Bot
from telegram.error import TelegramError

from Users.models import CustomUser


@receiver(pre_save, sender=CustomUser)
def cache_old_is_registered(sender, instance: CustomUser, **kwargs):
    if not instance.pk:
        instance._old_is_registered = None
        return

    try:
        old = CustomUser.objects.only("is_registered").get(pk=instance.pk)
        instance._old_is_registered = old.is_registered
    except CustomUser.DoesNotExist:
        instance._old_is_registered = None


@receiver(post_save, sender=CustomUser)
def notify_user_when_registered(sender, instance: CustomUser, created: bool, **kwargs):
    old_value = getattr(instance, "_old_is_registered", None)

    if old_value is True:
        return
    if not instance.is_registered:
        return
    if not instance.telegram_id:
        return

    def _send():
        try:
            token = os.environ.get("API_TOKEN")
            if not token:
                print("TELEGRAM ERROR: API_TOKEN is empty")
                return

            bot = Bot(token=token)
            async_to_sync(bot.send_message)(
                chat_id=instance.telegram_id,
                text="✅ حساب شما توسط ادمین تایید شد! حالا می‌تونی از امکانات ربات استفاده کنی."
            )
        except TelegramError as e:
            print("TELEGRAM ERROR:", repr(e))
        except Exception as e:
            print("UNKNOWN ERROR:", repr(e))

    transaction.on_commit(_send)
