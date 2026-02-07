from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from Users.managers import CustomUserManager


# Create your models here.

class Country(models.Model):
    name = models.CharField(max_length=50, null=False)
    is_available = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Country"
        verbose_name_plural = "Countries"

        indexes = [
            models.Index(fields=['name'], name='country_name_idx')
        ]

    def __str__(self):
        return self.name



class CustomUser(AbstractBaseUser,PermissionsMixin):
    telegram_id = models.IntegerField(unique=True, null=True, blank=True)
    telegram_username = models.CharField(max_length=25, null=True, blank=True)
    username = models.CharField(max_length=50, null=True, blank=True, unique=True)
    phone = models.CharField(max_length=12, unique=True, null=True, blank=True)
    name = models.CharField(max_length=50, null=True, blank=True)
    last_name = models.CharField(max_length=50, null=True, blank=True)
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True)





    date_joined = models.DateField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.CharField(default='1.0.0', max_length=20)

    is_registered = models.BooleanField(default=False)


    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_superuser = models.BooleanField(default=False)


    class Meta:
        verbose_name = 'CustomUser'
        verbose_name_plural = 'CustomUsers'

        indexes = [
            models.Index(fields=['username'], name='username_idx'),
            models.Index(fields=['phone'], name='phone_idx'),
        ]

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []


    objects = CustomUserManager()


    def __str__(self):
        return self.username