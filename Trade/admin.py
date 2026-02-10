from unfold.admin import ModelAdmin, TabularInline
from django.db.models import Count
from django.contrib import admin
from .models import TradeRequest, TradeOffer
from .services.request_services import publish_trade_request_to_channel


# ---------- Inline offers inside request ----------
class TradeOfferInline(TabularInline):
    model = TradeOffer
    extra = 0
    fields = ("id", "sender", "unit_price_irt", "status", "created_at")
    readonly_fields = ("id", "created_at")
    show_change_link = True
    autocomplete_fields = ("sender",)
    ordering = ("-created_at",)


# ---------- TradeRequest Admin ----------
@admin.register(TradeRequest)
class TradeRequestAdmin(ModelAdmin):

    inlines = [TradeOfferInline]

    list_display = (
        "id",
        "owner",
        "role",
        "currency",
        "unit_price_irt",
        "deal_method",
        "status",
        "channel_message_id",
        "created_at",
    )
    list_filter = ("status", "role", "currency", "deal_method", "created_at")
    search_fields = ("id", "owner__username", "owner__telegram_username", "description")
    autocomplete_fields = ("owner",)
    ordering = ("-created_at",)

    readonly_fields = ("created_at", "updated_at",)

    def save_model(self, request, obj, form, change):
        old_status = None
        if obj.pk:
            old_status = TradeRequest.objects.get(pk=obj.pk).status

        super().save_model(request, obj, form, change)

        if (
            old_status != TradeRequest.Status.APPROVED
            and obj.status == TradeRequest.Status.APPROVED
            and not obj.channel_message_id
        ):
            publish_trade_request_to_channel(obj.pk)

# ---------- TradeOffer Admin ----------
@admin.register(TradeOffer)
class TradeOfferAdmin(ModelAdmin):
    list_display = (
        "id",
        "request",
        "sender",
        "unit_price_irt",
        "status",
        "created_at",
    )
    list_filter = ("status", "created_at", "request__currency", "request__role")
    search_fields = ("id", "request__id", "sender__username", "sender__telegram_username")
    autocomplete_fields = ("request", "sender")
    ordering = ("-created_at",)

    readonly_fields = ("created_at",)
