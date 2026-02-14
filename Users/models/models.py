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