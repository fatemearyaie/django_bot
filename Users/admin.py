from django.contrib import admin
from unfold.admin import ModelAdmin

from Users.models import CustomUser, Country


# Register your models here.

@admin.register(CustomUser)
class CustomUserAdmin(ModelAdmin):
    list_display = ['username', 'phone','date_joined', 'name', 'last_name', 'country', 'city']
    search_fields = ['username', 'phone', ]
    fields = ['username','phone', 'name', 'last_name', 'country',
              'city', 'telegram_username', 'telegram_id']


@admin.register(Country)
class CountryAdmin(ModelAdmin):
    list_display = ['name', 'is_available']
    search_fields = ['name',]
    list_filter = ['name', 'is_available']


