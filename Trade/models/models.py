from django.db import models
from Users.models import CustomUser


class TradeRequest(models.Model):

    class Role(models.TextChoices):
        BUYER = "buyer", "خریدار"
        SELLER = "seller", "فروشنده"

    class Currency(models.TextChoices):
        EUR = "EUR", "یورو"
        USD = "USD", "دلار"
        TRY = "TRY", "لیر"
        AED = "AED", "درهم"

    class DealMethod(models.TextChoices):
        PAYPAL = "paypal", "پی‌پال"
        TRANSFER = "transfer", "حواله"
        CASH = "cash", "نقدی"
        CRYPTO = "crypto", "رمزارز"

    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PENDING_ADMIN = "pending_admin", "در انتظار تایید ادمین"
        APPROVED = "approved", "تایید شده"
        POSTED = "posted", "منتشر شده"
        CLOSED = "closed", "بسته شده"

    owner = models.ForeignKey(CustomUser,on_delete=models.CASCADE,related_name="trade_requests")

    role = models.CharField(max_length=10, choices=Role.choices)
    currency = models.CharField(max_length=5, choices=Currency.choices)

    unit_price_irt = models.BigIntegerField()

    deal_method = models.CharField(max_length=20, choices=DealMethod.choices)
    description = models.TextField(blank=True, default="")

    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)

    channel_chat_id = models.BigIntegerField(null=True, blank=True)
    channel_message_id = models.BigIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)



class TradeOffer(models.Model):

    class Status(models.TextChoices):
        PENDING = "pending", "منتظر پاسخ"
        ACCEPTED = "accepted", "تایید شده"
        REJECTED = "rejected", "رد شده"
        CANCELLED = "cancelled", "لغو شده"

    request = models.ForeignKey(TradeRequest,on_delete=models.CASCADE,related_name="offers")

    sender = models.ForeignKey(CustomUser,on_delete=models.CASCADE,related_name="sent_offers")

    unit_price_irt = models.BigIntegerField()
    message = models.TextField(blank=True, default="")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["request", "status"]),
            models.Index(fields=["sender", "created_at"]),
        ]


        constraints = [
        models.UniqueConstraint(fields=["request", "sender"], name="uniq_offer_per_sender_per_request")
        ]
