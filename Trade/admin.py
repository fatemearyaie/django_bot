from unfold.admin import ModelAdmin, TabularInline
from django.db.models import Count
from django.contrib import admin
from .models import TradeRequest, TradeOffer


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
        "offers_count",
        "channel_message_id",
        "created_at",
    )
    list_filter = ("status", "role", "currency", "deal_method", "created_at")
    search_fields = ("id", "owner__username", "owner__telegram_username", "description")
    autocomplete_fields = ("owner",)
    ordering = ("-created_at",)

    readonly_fields = ("created_at", "updated_at", "offers_count")
    fieldsets = (
        ("Owner", {"fields": ("owner",)}),
        ("Request Info", {"fields": ("role", "currency", "unit_price_irt", "deal_method", "description")}),
        ("Workflow", {"fields": ("status",)}),
        ("Channel Message", {"fields": ("channel_chat_id", "channel_message_id")}),
        ("Meta", {"fields": ("offers_count", "created_at", "updated_at")}),
    )

    actions = ("action_approve_requests", "action_mark_posted", "action_close_requests")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_offers_count=Count("offers"))

    @admin.display(description="Offers", ordering="_offers_count")
    def offers_count(self, obj: TradeRequest) -> int:
        return getattr(obj, "_offers_count", 0)

    @admin.action(description="✅ تایید درخواست‌ها (pending_admin → approved)")
    def action_approve_requests(self, request, queryset):
        updated = queryset.filter(status="pending_admin").update(status="approved")
        self.message_user(request, f"{updated} درخواست تایید شد.")

    @admin.action(description="📣 علامت‌گذاری به عنوان منتشر شده (approved → posted)")
    def action_mark_posted(self, request, queryset):
        updated = queryset.filter(status="approved").update(status="posted")
        self.message_user(request, f"{updated} درخواست posted شد.")

    @admin.action(description="🔒 بستن درخواست‌ها (→ closed)")
    def action_close_requests(self, request, queryset):
        updated = queryset.exclude(status="closed").update(status="closed")
        self.message_user(request, f"{updated} درخواست بسته شد.")


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

    actions = ("action_accept_offers", "action_reject_offers", "action_cancel_offers")

    @admin.action(description="✅ تایید پیشنهادها (→ accepted)")
    def action_accept_offers(self, request, queryset):
        updated = queryset.exclude(status="accepted").update(status="accepted")
        self.message_user(request, f"{updated} پیشنهاد accepted شد.")

    @admin.action(description="❌ رد پیشنهادها (→ rejected)")
    def action_reject_offers(self, request, queryset):
        updated = queryset.exclude(status="rejected").update(status="rejected")
        self.message_user(request, f"{updated} پیشنهاد rejected شد.")

    @admin.action(description="🚫 لغو پیشنهادها (→ cancelled)")
    def action_cancel_offers(self, request, queryset):
        updated = queryset.exclude(status="cancelled").update(status="cancelled")
        self.message_user(request, f"{updated} پیشنهاد cancelled شد.")
