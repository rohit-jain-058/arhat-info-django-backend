from django.contrib import admin
from django.utils.html import format_html
from .models import Plan, Subscription, Payment, APIKey, AIUsageLog


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display  = ('name', 'tier', 'interval', 'price_display', 'removes_ads', 'allows_ai_tools', 'allows_api_key', 'is_active')
    list_filter   = ('tier', 'interval', 'is_active')
    list_editable = ('is_active',)
    fieldsets = (
        ('Plan Details', {'fields': ('name', 'tier', 'interval', 'price_cents', 'currency', 'is_active')}),
        ('Features',     {'fields': ('removes_ads', 'allows_ai_tools', 'allows_api_key', 'ai_requests_per_day')}),
        ('Payment IDs',  {'fields': ('stripe_price_id', 'paypal_plan_id'), 'classes': ('collapse',)}),
    )


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display  = ('user', 'plan', 'status', 'current_period_end', 'cancel_at_period_end', 'created_at')
    list_filter   = ('status', 'plan__tier', 'cancel_at_period_end')
    search_fields = ('user__email', 'stripe_subscription_id')
    readonly_fields = ('id', 'created_at', 'updated_at')
    raw_id_fields = ('user',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'plan')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display  = ('user', 'amount_display', 'status', 'plan', 'created_at')
    list_filter   = ('status', 'currency')
    search_fields = ('user__email', 'stripe_payment_intent_id')
    readonly_fields = ('id', 'created_at', 'updated_at')
    raw_id_fields   = ('user',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'plan')


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display  = ('user', 'name', 'key_prefix_display', 'is_active', 'requests_total', 'last_used', 'created_at')
    list_filter   = ('is_active',)
    search_fields = ('user__email', 'key_prefix')
    readonly_fields = ('id', 'key_prefix', 'key_hash', 'last_used', 'requests_today', 'requests_total', 'created_at')
    raw_id_fields = ('user',)

    def key_prefix_display(self, obj):
        return format_html('<code>{}...</code>', obj.key_prefix)
    key_prefix_display.short_description = 'Key Prefix'

    def has_add_permission(self, request):
        return False  # Keys must be created through the API


@admin.register(AIUsageLog)
class AIUsageLogAdmin(admin.ModelAdmin):
    list_display  = ('user', 'date', 'tool', 'requests_count', 'tokens_used')
    list_filter   = ('date', 'tool')
    search_fields = ('user__email',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    raw_id_fields = ('user',)
