"""
Subscription serializers.
Match your existing DRF serializer style.
"""
from rest_framework import serializers
from django.utils import timezone
from .models import Plan, Subscription, Payment, APIKey, AIUsageLog


class PlanSerializer(serializers.ModelSerializer):
    price_display = serializers.ReadOnlyField()

    class Meta:
        model  = Plan
        fields = [
            'id', 'name', 'tier', 'interval',
            'price_cents', 'price_display', 'currency',
            'removes_ads', 'allows_ai_tools', 'allows_api_key',
            'ai_requests_per_day',
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan          = PlanSerializer(read_only=True)
    tier          = serializers.ReadOnlyField()
    is_active     = serializers.ReadOnlyField()
    removes_ads   = serializers.ReadOnlyField()
    allows_ai_tools = serializers.ReadOnlyField()
    allows_api_key  = serializers.ReadOnlyField()
    days_remaining  = serializers.SerializerMethodField()

    class Meta:
        model  = Subscription
        fields = [
            'id', 'plan', 'tier', 'status', 'is_active',
            'removes_ads', 'allows_ai_tools', 'allows_api_key',
            'started_at', 'current_period_start', 'current_period_end',
            'cancel_at_period_end', 'cancelled_at', 'trial_end',
            'days_remaining',
        ]

    def get_days_remaining(self, obj):
        return obj.days_remaining()


class PaymentSerializer(serializers.ModelSerializer):
    amount_display = serializers.ReadOnlyField()
    plan_name      = serializers.CharField(source='plan.name', read_only=True)

    class Meta:
        model  = Payment
        fields = [
            'id', 'amount_cents', 'amount_display', 'currency',
            'status', 'description', 'plan_name', 'created_at',
        ]


class APIKeySerializer(serializers.ModelSerializer):
    """Never exposes the full key — only prefix."""
    class Meta:
        model  = APIKey
        fields = [
            'id', 'name', 'key_prefix', 'is_active',
            'last_used', 'requests_today', 'requests_total', 'created_at',
        ]
        read_only_fields = ['key_prefix', 'last_used', 'requests_today', 'requests_total', 'created_at']


class APIKeyCreateSerializer(serializers.ModelSerializer):
    """Used only on key creation — includes the full key once."""
    full_key = serializers.SerializerMethodField()

    class Meta:
        model  = APIKey
        fields = ['id', 'name', 'key_prefix', 'full_key', 'created_at']
        read_only_fields = ['key_prefix', 'created_at']

    def get_full_key(self, obj):
        # full_key is temporarily attached in the view after creation
        return getattr(obj, '_plain_key', None)


class SubscribeDashboardSerializer(serializers.Serializer):
    """
    Full user subscription state for the dashboard.
    Single endpoint returns everything the frontend needs.
    """
    tier            = serializers.CharField()
    subscription    = SubscriptionSerializer(allow_null=True)
    plans           = PlanSerializer(many=True)
    payments        = PaymentSerializer(many=True)
    api_keys        = APIKeySerializer(many=True)
    ai_usage_today  = serializers.IntegerField()
    ai_limit_today  = serializers.IntegerField()


class UpgradeSerializer(serializers.Serializer):
    """Request body for upgrading to a plan."""
    plan_id = serializers.UUIDField()

    def validate_plan_id(self, value):
        try:
            return Plan.objects.get(id=value, is_active=True)
        except Plan.DoesNotExist:
            raise serializers.ValidationError('Plan not found or not active.')


class CancelSerializer(serializers.Serializer):
    """Request body for cancelling a subscription."""
    at_period_end = serializers.BooleanField(default=True)


class CreateAPIKeySerializer(serializers.Serializer):
    """Request body for creating an API key."""
    name = serializers.CharField(max_length=100, default='Default Key')
