from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from Users.managers import CustomUserManager


# Create your models here.

class Country(models.Model):
    name = models.CharField(max_length=50, null=False, verbose_name='نام')
    is_available = models.BooleanField(default=True, verbose_name='قابل دسترس')

    class Meta:
        verbose_name = "کشور"
        verbose_name_plural = "کشورها"

        indexes = [
            models.Index(fields=['name'], name='country_name_idx')
        ]

    def __str__(self):
        return self.name



class CustomUser(AbstractBaseUser,PermissionsMixin):
    telegram_id = models.BigIntegerField(unique=True, null=True, blank=True, verbose_name='آیدی تلگرام')
    telegram_username = models.CharField(max_length=25, null=True, blank=True, verbose_name='نام کاربری تلگرام')
    username = models.CharField(max_length=50, null=True, blank=True, unique=True, verbose_name='نام کاربری')
    phone = models.CharField(max_length=12, unique=True, null=True, blank=True, verbose_name='شماره تلفن')
    name = models.CharField(max_length=50, null=True, blank=True, verbose_name='نام')
    last_name = models.CharField(max_length=50, null=True, blank=True, verbose_name='نام خانوادگی')
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='کشور')
    total_points = models.PositiveIntegerField(default=0)
    used_points = models.PositiveIntegerField(default=0)


    referral_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    invited_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invited_users"
    )

    referral_signup_rewarded = models.BooleanField(default=False)
    referral_first_trade_rewarded = models.BooleanField(default=False)

    @property
    def available_points(self):
        return max(self.total_points - self.used_points, 0)




    date_joined = models.DateField(auto_now_add=True, verbose_name='تاریخ عضویت')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='به روز رسانی شده در')
    version = models.CharField(default='1.0.0', max_length=20, verbose_name='نسخه')

    is_registered = models.BooleanField(default=False, verbose_name='تایید شده')


    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_superuser = models.BooleanField(default=False)


    class Meta:
        verbose_name = 'کاربر'
        verbose_name_plural = 'کاربران'

        indexes = [
            models.Index(fields=['username'], name='username_idx'),
            models.Index(fields=['phone'], name='phone_idx'),
        ]

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []


    objects = CustomUserManager()


    def __str__(self):
        return self.name


# rewards/models.py

from django.db import models
from django.conf import settings

class PointTransaction(models.Model):
    class Reason(models.TextChoices):
        FIRST_TRADE_BONUS = "first_trade_bonus", "بونوس اولین معامله"
        REFERRAL_INVITE = "referral_invite", "معرفی دوست"
        REFERRAL_FIRST_TRADE = "referral_first_trade", "اولین معامله زیرمجموعه"
        FEE_PAYMENT = "fee_payment", "امتیاز بابت کارمزد"
        DISCOUNT_USAGE = "discount_usage", "مصرف امتیاز برای تخفیف"
        MANUAL = "manual", "ثبت دستی"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="point_logs")
    points = models.IntegerField()  # مثبت یا منفی
    reason = models.CharField(max_length=50, choices=Reason.choices)
    description = models.TextField(blank=True, null=True)

    related_trade_id = models.IntegerField(null=True, blank=True)
    related_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="related_point_logs"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)