"""
Subscription views.

All views use:
- @api_view + @permission_classes (matches your existing pattern)
- DRF Response (not JsonResponse)
- request.user from JWT (your existing auth)
- apps.core.exceptions raises handled by your custom_exception_handler

Endpoints:
  GET  /api/subscriptions/dashboard/     — full user state
  GET  /api/subscriptions/plans/         — all available plans (public)
  POST /api/subscriptions/upgrade/       — upgrade to a plan
  POST /api/subscriptions/cancel/        — cancel subscription
  POST /api/subscriptions/resume/        — resume a cancelled subscription
  GET  /api/subscriptions/payments/      — payment history
  GET  /api/subscriptions/api-keys/      — list API keys
  POST /api/subscriptions/api-keys/      — create API key
  DELETE /api/subscriptions/api-keys/<id>/ — revoke API key
  GET  /api/subscriptions/me/            — quick tier check
"""
import logging
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from .models import Plan, Subscription, Payment, APIKey, AIUsageLog
from .serializers import (
    PlanSerializer, SubscriptionSerializer, PaymentSerializer,
    APIKeySerializer, APIKeyCreateSerializer, UpgradeSerializer,
    CancelSerializer, CreateAPIKeySerializer,
)
from .permissions import IsFullBundle, get_user_tier
from apps.subscriptions.permissions import IsAIToolsSubscriber
from .permissions import get_user_features

logger = logging.getLogger(__name__)


# ── HELPERS ───────────────────────────────────────────────────────────
def _get_or_create_free_subscription(user) -> Subscription:
    """
    Every user gets a free subscription by default.
    Called when a user has no subscription record yet.
    """
    free_plan, _ = Plan.objects.get_or_create(
        tier     = 'free',
        interval = 'monthly',
        defaults = {
            'name':              'Free',
            'price_cents':       0,
            'removes_ads':       False,
            'allows_ai_tools':   False,
            'allows_api_key':    False,
            'ai_requests_per_day': 0,
        }
    )
    sub, _ = Subscription.objects.get_or_create(
        user     = user,
        defaults = {'plan': free_plan, 'status': 'active'},
    )
    return sub


def _get_ai_usage_today(user) -> int:
    """Total AI requests made by user today."""
    today = timezone.now().date()
    return AIUsageLog.objects.filter(
        user = user,
        date = today,
    ).aggregate(
        total = __import__('django.db.models', fromlist=['Sum']).Sum('requests_count')
    )['total'] or 0


# ── PLANS — public ────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def plan_list(request):
    """
    GET /api/subscriptions/plans/
    Returns all active plans. Public — no auth required.
    Used to render the pricing page.
    """
    plans = Plan.objects.filter(is_active=True).order_by('price_cents')
    return Response(PlanSerializer(plans, many=True).data)


# ── DASHBOARD ─────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard(request):
    """
    GET /api/subscriptions/dashboard/
    Returns everything the subscription dashboard needs in one call:
    - current plan + tier
    - subscription details
    - payment history
    - API keys
    - AI usage today vs limit
    """
    user = request.user

    # Get or create free subscription
    try:
        sub = user.subscription
        if not sub.is_active:
            sub = _get_or_create_free_subscription(user)
    except Subscription.DoesNotExist:
        sub = _get_or_create_free_subscription(user)

    plans       = Plan.objects.filter(is_active=True).order_by('price_cents')
    payments    = Payment.objects.filter(user=user).order_by('-created_at')[:20]
    api_keys    = APIKey.objects.filter(user=user, is_active=True)
    usage_today = _get_ai_usage_today(user)
    ai_limit    = sub.plan.ai_requests_per_day  # 0 = unlimited

    return Response({
        'tier':          sub.tier,
        'subscription':  SubscriptionSerializer(sub).data,
        'plans':         PlanSerializer(plans, many=True).data,
        'payments':      PaymentSerializer(payments, many=True).data,
        'api_keys':      APIKeySerializer(api_keys, many=True).data,
        'ai_usage_today':usage_today,
        'ai_limit_today':ai_limit,
    })


# ── QUICK TIER CHECK ──────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    user = request.user
    try:
        sub = user.subscription
        if not sub.is_active:
            sub = _get_or_create_free_subscription(user)
    except Subscription.DoesNotExist:
        sub = _get_or_create_free_subscription(user)

    features = get_user_features(request)

    return Response({
        **features,                      # tier, removes_ads, allows_ai_tools,
                                          # allows_form_tools, allows_api_key
        'status':     sub.status,
        'plan_name':  sub.plan.name,
        'period_end': sub.current_period_end,
    })


# ── UPGRADE ───────────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upgrade(request):
    """
    POST /api/subscriptions/upgrade/
    Body: { "plan_id": "<uuid>" }

    Currently creates the subscription directly (no payment).
    When you add Stripe/PayPal: create a checkout session here
    and return the checkout URL instead of activating immediately.
    """
    serializer = UpgradeSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    plan = serializer.validated_data['plan_id']  # Plan instance after validation
    user = request.user

    try:
        sub = user.subscription
    except Subscription.DoesNotExist:
        sub = None

    if sub:
        # Update existing subscription
        sub.plan                  = plan
        sub.status                = 'active'
        sub.cancel_at_period_end  = False
        sub.cancelled_at          = None
        sub.current_period_start  = timezone.now()
        sub.current_period_end    = timezone.now() + (
            __import__('datetime').timedelta(days=365)
            if plan.interval == 'yearly'
            else __import__('datetime').timedelta(days=30)
        )
        sub.save()
    else:
        from datetime import timedelta
        sub = Subscription.objects.create(
            user                 = user,
            plan                 = plan,
            status               = 'active',
            current_period_start = timezone.now(),
            current_period_end   = timezone.now() + (
                timedelta(days=365) if plan.interval == 'yearly' else timedelta(days=30)
            ),
        )

    # Create payment record (pending until payment confirmed)
    Payment.objects.create(
        user         = user,
        subscription = sub,
        plan         = plan,
        amount_cents = plan.price_cents,
        currency     = plan.currency,
        status       = 'pending' if plan.price_cents > 0 else 'succeeded',
        description  = f'Subscription — {plan.name}',
    )

    logger.info(f'[Subscription] {user} upgraded to {plan.name}')
    return Response({
        'message':      f'Upgraded to {plan.name}',
        'subscription': SubscriptionSerializer(sub).data,
        # When Stripe is added, return: 'checkout_url': session.url
    }, status=status.HTTP_200_OK)


# ── CANCEL ────────────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel(request):
    """
    POST /api/subscriptions/cancel/
    Body: { "at_period_end": true }
    """
    serializer = CancelSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        sub = request.user.subscription
    except Subscription.DoesNotExist:
        return Response({'error': 'No active subscription found.'}, status=status.HTTP_404_NOT_FOUND)

    if not sub.is_active:
        return Response({'error': 'Subscription is not active.'}, status=status.HTTP_400_BAD_REQUEST)

    at_period_end = serializer.validated_data['at_period_end']
    sub.cancel(at_period_end=at_period_end)

    logger.info(f'[Subscription] {request.user} cancelled (at_period_end={at_period_end})')
    return Response({
        'message':      'Subscription cancelled.' if not at_period_end else 'Subscription will cancel at end of billing period.',
        'subscription': SubscriptionSerializer(sub).data,
    })


# ── RESUME ────────────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def resume(request):
    """
    POST /api/subscriptions/resume/
    Reactivates a subscription that was set to cancel at period end.
    """
    try:
        sub = request.user.subscription
    except Subscription.DoesNotExist:
        return Response({'error': 'No subscription found.'}, status=status.HTTP_404_NOT_FOUND)

    if not sub.cancel_at_period_end:
        return Response({'error': 'Subscription is not set to cancel.'}, status=status.HTTP_400_BAD_REQUEST)

    sub.cancel_at_period_end = False
    sub.save(update_fields=['cancel_at_period_end', 'updated_at'])

    return Response({
        'message':      'Subscription resumed.',
        'subscription': SubscriptionSerializer(sub).data,
    })


# ── PAYMENT HISTORY ───────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_history(request):
    """GET /api/subscriptions/payments/"""
    payments = Payment.objects.filter(user=request.user).order_by('-created_at')
    return Response(PaymentSerializer(payments, many=True).data)


# ── API KEYS ──────────────────────────────────────────────────────────
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_keys(request):
    """
    GET  /api/subscriptions/api-keys/ — list keys
    POST /api/subscriptions/api-keys/ — create new key (Full Bundle only)
    """
    if request.method == 'GET':
        keys = APIKey.objects.filter(user=request.user, is_active=True)
        return Response(APIKeySerializer(keys, many=True).data)

    # POST — create
    try:
        sub = request.user.subscription
        if not sub.allows_api_key:
            return Response(
                {'error': 'API key access requires a Full Bundle subscription.'},
                status=status.HTTP_403_FORBIDDEN,
            )
    except Subscription.DoesNotExist:
        return Response(
            {'error': 'API key access requires a Full Bundle subscription.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Max 5 keys per user
    if APIKey.objects.filter(user=request.user, is_active=True).count() >= 5:
        return Response(
            {'error': 'Maximum 5 API keys allowed per account.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = CreateAPIKeySerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    api_key, plain_key = APIKey.generate(
        user = request.user,
        name = serializer.validated_data.get('name', 'Default Key'),
    )
    api_key._plain_key = plain_key  # attached temporarily for serializer

    logger.info(f'[APIKey] {request.user} created key: {api_key.key_prefix}...')
    return Response({
        'message':  'API key created. Save this key — it will not be shown again.',
        'api_key':  APIKeyCreateSerializer(api_key).data,
    }, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def revoke_api_key(request, key_id):
    """DELETE /api/subscriptions/api-keys/<key_id>/"""
    try:
        api_key = APIKey.objects.get(id=key_id, user=request.user, is_active=True)
    except APIKey.DoesNotExist:
        return Response({'error': 'API key not found.'}, status=status.HTTP_404_NOT_FOUND)

    api_key.is_active = False
    api_key.save(update_fields=['is_active'])
    logger.info(f'[APIKey] {request.user} revoked key: {api_key.key_prefix}...')
    return Response({'message': 'API key revoked.'})
