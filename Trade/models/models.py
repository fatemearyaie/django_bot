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
        AED = "AED", "درهم"

    class DealMethod(models.TextChoices):
        PAYPAL = "paypal", "انتقال آنی پی‌پال"
        TRANSFER = "transfer", "حواله بانکی"
        MASTER = "master card", "مستر کارت"
        OTHER = "other", "سایر"

    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PENDING_ADMIN = "pending_admin", "در انتظار تایید ادمین"
        APPROVED = "approved", "تایید شده"
        CLOSED = "closed", "بسته شده"

    owner = models.ForeignKey(CustomUser,on_delete=models.CASCADE,related_name="trade_requests", verbose_name='درخواست دهنده')

    role = models.CharField(max_length=10, choices=Role.choices, verbose_name='نقش')
    currency = models.CharField(max_length=5, choices=Currency.choices, verbose_name='ارز')

    amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True, verbose_name='مقدار')
    unit_price_irt = models.BigIntegerField(null=True, blank=True, verbose_name='قیمت هر واحد')
    fee_irt = models.BigIntegerField(null=True, blank=True,verbose_name='کارمزد')

    deal_method = models.CharField(max_length=20, choices=DealMethod.choices, default=DealMethod.PAYPAL, verbose_name='شیوه معامله')
    description = models.TextField(blank=True, default="", verbose_name='توضیحات')

    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT, verbose_name='وضعیت')

    channel_chat_id = models.BigIntegerField(null=True, blank=True, verbose_name='آیدی چت')
    channel_message_id = models.BigIntegerField(null=True, blank=True, verbose_name='آیدی مسیج در کانال')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاریخ آپدیت')

    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name='تاریخ تایید')
    editable_until = models.DateTimeField(null=True, blank=True, verbose_name='قابل تغییر')

    channel_post_text = models.TextField(null=True, blank=True, verbose_name='متن پیام کانال')

    def can_edit(self) -> bool:
        if not self.editable_until:
            return True
        return timezone.now() <= self.editable_until

    class Meta:
        verbose_name = 'درخواست'
        verbose_name_plural = 'درخواست ها'

    def __str__(self):
        role = dict(self.Role.choices).get(self.role, self.role)
        currency = self.currency or "-"
        amount = self.amount if self.amount is not None else "?"
        return f"Request #{self.id} | {role} | {amount} {currency}"


class TradeOffer(models.Model):

    class Status(models.TextChoices):
        PENDING = "pending", "منتظر پاسخ"
        ACCEPTED = "accepted", "تایید شده"
        REJECTED = "rejected", "رد شده"
        CANCELLED = "cancelled", "لغو شده"

    request = models.ForeignKey(TradeRequest,on_delete=models.CASCADE,related_name="offers", verbose_name='درخواست')

    sender = models.ForeignKey(CustomUser,on_delete=models.CASCADE,related_name="sent_offers", verbose_name='پیشنهاد دهنده')

    unit_price_irt = models.BigIntegerField(verbose_name='قیمت هر واحد')
    message = models.TextField(blank=True, default="", verbose_name='پیام')

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name='وضعیت')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='ایجاد شده در')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='به روز رسانی شده در')

    class Meta:

        verbose_name = 'پیشنهاد'
        verbose_name_plural = 'پیشنهادها'
        indexes = [
            models.Index(fields=["request", "status"]),
            models.Index(fields=["sender", "created_at"]),
        ]


        constraints = []

    def __str__(self):
        price = self.unit_price_irt if self.unit_price_irt is not None else "?"
        return f"Offer #{self.id} | Request #{self.request_id} | {price} IRT"


