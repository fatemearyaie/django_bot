from django.db import models
from django.utils import timezone

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
        CLOSED = "closed", "بسته شده"

    owner = models.ForeignKey(CustomUser,on_delete=models.CASCADE,related_name="trade_requests")

    role = models.CharField(max_length=10, choices=Role.choices)
    currency = models.CharField(max_length=5, choices=Currency.choices)

    amount = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    unit_price_irt = models.BigIntegerField(null=True, blank=True)
    fee_irt = models.BigIntegerField(null=True, blank=True)

    deal_method = models.CharField(max_length=20, choices=DealMethod.choices, default=DealMethod.PAYPAL)
    description = models.TextField(blank=True, default="")

    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)

    channel_chat_id = models.BigIntegerField(null=True, blank=True)
    channel_message_id = models.BigIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    confirmed_at = models.DateTimeField(null=True, blank=True)
    editable_until = models.DateTimeField(null=True, blank=True)

    channel_post_text = models.TextField(null=True, blank=True)

    def can_edit(self) -> bool:
        if not self.editable_until:
            return True
        return timezone.now() <= self.editable_until



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
