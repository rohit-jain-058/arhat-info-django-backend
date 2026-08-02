"""
Authorize.net checkout views.

Endpoints:
  POST /api/subscriptions/checkout/     — create subscription (receives Accept.js nonce)
  POST /api/subscriptions/webhook/      — Authorize.net webhook events
  POST /api/subscriptions/cancel/       — cancel via ARB then update DB
  POST /api/subscriptions/upgrade/      — upgrade plan
  GET  /api/subscriptions/client-key/   — returns public client key for Accept.js
"""
import json
import logging
from datetime import timedelta

from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

from .models import Plan, Subscription, Payment
from .serializers import SubscriptionSerializer
from .authnet_service import (
    create_subscription,
    cancel_subscription,
    update_subscription,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)



# ── CHECKOUT — create subscription ────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def checkout(request):
    """
    POST /api/subscriptions/checkout/
    Body:
    {
      "plan_id":             "<uuid>",
      "interval":            "monthly" | "yearly",
      "opaque_data_descriptor": "COMMON.ACCEPT.INAPP.PAYMENT",
      "opaque_data_value":      "<nonce from Accept.js>"
    }
    """
    plan_id    = request.data.get('plan_id')
    interval   = request.data.get('interval', 'monthly')
    descriptor = request.data.get('opaque_data_descriptor', '')
    nonce      = request.data.get('opaque_data_value', '')

    if not all([plan_id, descriptor, nonce]):
        return Response({'error': 'plan_id, opaque_data_descriptor, and opaque_data_value are required'}, status=400)

    # Validate plan
    try:
        plan = Plan.objects.get(id=plan_id, is_active=True)
    except Plan.DoesNotExist:
        return Response({'error': 'Plan not found'}, status=404)

    if plan.tier == 'free':
        return Response({'error': 'Free plan does not require payment'}, status=400)

    user = request.user

    # Call Authorize.net ARB API
    try:
        result = create_subscription(
            opaque_data_descriptor = descriptor,
            opaque_data_value      = nonce,
            plan                   = plan,
            user                   = user,
            interval               = interval,
        )
    except Exception as e:
        logger.error(f'[Checkout] ARB create failed for {user.email}: {e}')
        return Response({'error': str(e)}, status=402)

    authnet_sub_id = result['subscription_id']

    # Calculate period dates
    now        = timezone.now()
    period_end = now + (timedelta(days=365) if interval == 'yearly' else timedelta(days=30))

    # Update or create subscription in DB
    try:
        sub = user.subscription
        sub.plan                        = plan
        sub.status                      = 'active'
        sub.authnet_subscription_id     = authnet_sub_id
        sub.cancel_at_period_end        = False
        sub.cancelled_at                = None
        sub.current_period_start        = now
        sub.current_period_end          = period_end
        sub.save()
    except Subscription.DoesNotExist:
        sub = Subscription.objects.create(
            user                    = user,
            plan                    = plan,
            status                  = 'active',
            authnet_subscription_id = authnet_sub_id,
            current_period_start    = now,
            current_period_end      = period_end,
        )

    # Record payment
    Payment.objects.create(
        user         = user,
        subscription = sub,
        plan         = plan,
        amount_cents = plan.price_cents,
        currency     = plan.currency,
        status       = 'succeeded',
        description  = f'{plan.name} — {interval}',
        authnet_subscription_id = authnet_sub_id,
    )

    logger.info(f'[Checkout] {user.email} subscribed to {plan.name} (authnet: {authnet_sub_id})')
    return Response({
        'message':             f'Subscribed to {plan.name}',
        'subscription_id':     str(sub.id),
        'authnet_subscription':authnet_sub_id,
        'subscription':        SubscriptionSerializer(sub).data,
    })


# ── CANCEL ────────────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel(request):
    """
    POST /api/subscriptions/cancel/
    Body: { "at_period_end": true }  — true = cancel at end, false = cancel now
    """
    at_period_end = request.data.get('at_period_end', True)

    try:
        sub = request.user.subscription
    except Subscription.DoesNotExist:
        return Response({'error': 'No active subscription'}, status=404)

    if not sub.is_active or sub.plan.tier == 'free':
        return Response({'error': 'No paid subscription to cancel'}, status=400)

    if at_period_end:
        # Don't hit Authorize.net yet — just mark for cancellation
        # A Celery task will cancel at period end
        sub.cancel_at_period_end = True
        sub.save(update_fields=['cancel_at_period_end', 'updated_at'])
        return Response({
            'message': 'Subscription will cancel at end of billing period.',
            'subscription': SubscriptionSerializer(sub).data,
        })
    else:
        # Cancel immediately at Authorize.net
        if sub.authnet_subscription_id:
            try:
                cancel_subscription(sub.authnet_subscription_id)
            except Exception as e:
                logger.error(f'[Cancel] ARB cancel failed: {e}')
                return Response({'error': str(e)}, status=502)

        sub.status       = 'cancelled'
        sub.cancelled_at = timezone.now()
        sub.save()

        # Downgrade to free
        _downgrade_to_free(request.user, sub)

        return Response({
            'message': 'Subscription cancelled.',
            'subscription': SubscriptionSerializer(sub).data,
        })


# ── UPGRADE ───────────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upgrade(request):
    """
    POST /api/subscriptions/upgrade/
    Body:
    {
      "plan_id": "<uuid>",
      "interval": "monthly" | "yearly",
      "opaque_data_descriptor": "...",
      "opaque_data_value": "..."
    }

    For upgrade with existing payment on file:
    If user already has authnet_subscription_id, we cancel old + create new.
    """
    plan_id    = request.data.get('plan_id')
    interval   = request.data.get('interval', 'monthly')
    descriptor = request.data.get('opaque_data_descriptor', '')
    nonce      = request.data.get('opaque_data_value', '')

    if not plan_id:
        return Response({'error': 'plan_id is required'}, status=400)

    try:
        plan = Plan.objects.get(id=plan_id, is_active=True)
    except Plan.DoesNotExist:
        return Response({'error': 'Plan not found'}, status=404)

    user = request.user

    try:
        old_sub = user.subscription
    except Subscription.DoesNotExist:
        old_sub = None

    # If upgrading to free — just cancel existing
    if plan.tier == 'free':
        if old_sub and old_sub.authnet_subscription_id:
            try:
                cancel_subscription(old_sub.authnet_subscription_id)
            except Exception as e:
                logger.warning(f'[Upgrade] Could not cancel old sub: {e}')
        if old_sub:
            _downgrade_to_free(user, old_sub)
        return Response({'message': 'Downgraded to free plan.'})

    # Need nonce for paid plan
    if not descriptor or not nonce:
        return Response({'error': 'Payment details required for paid plan'}, status=400)

    # Cancel old ARB subscription if exists
    if old_sub and old_sub.authnet_subscription_id:
        try:
            cancel_subscription(old_sub.authnet_subscription_id)
        except Exception as e:
            logger.warning(f'[Upgrade] Could not cancel old ARB sub: {e}')

    # Create new ARB subscription
    try:
        result = create_subscription(
            opaque_data_descriptor = descriptor,
            opaque_data_value      = nonce,
            plan                   = plan,
            user                   = user,
            interval               = interval,
        )
    except Exception as e:
        return Response({'error': str(e)}, status=402)

    authnet_sub_id = result['subscription_id']
    now            = timezone.now()
    period_end     = now + (timedelta(days=365) if interval == 'yearly' else timedelta(days=30))

    if old_sub:
        old_sub.plan                    = plan
        old_sub.status                  = 'active'
        old_sub.authnet_subscription_id = authnet_sub_id
        old_sub.cancel_at_period_end    = False
        old_sub.cancelled_at            = None
        old_sub.current_period_start    = now
        old_sub.current_period_end      = period_end
        old_sub.save()
        sub = old_sub
    else:
        sub = Subscription.objects.create(
            user                    = user,
            plan                    = plan,
            status                  = 'active',
            authnet_subscription_id = authnet_sub_id,
            current_period_start    = now,
            current_period_end      = period_end,
        )

    Payment.objects.create(
        user         = user,
        subscription = sub,
        plan         = plan,
        amount_cents = plan.price_cents,
        currency     = plan.currency,
        status       = 'succeeded',
        description  = f'{plan.name} — upgrade',
        authnet_subscription_id = authnet_sub_id,
    )

    return Response({
        'message':      f'Upgraded to {plan.name}',
        'subscription': SubscriptionSerializer(sub).data,
    })


# ── WEBHOOK ───────────────────────────────────────────────────────────
@csrf_exempt
@require_POST
def webhook(request):
    """
    POST /api/subscriptions/webhook/

    Authorize.net sends webhooks for:
      net.authorize.payment.authcapture.created — payment succeeded
      net.authorize.payment.capture.created     — payment captured
      net.authorize.payment.void.created        — payment voided
      net.authorize.payment.refund.created      — payment refunded
      net.authorize.payment.fraud.held          — fraud hold
      net.authorize.payment.fraud.approved      — fraud approved
      net.authorize.arb.subscription.cancelled  — subscription cancelled
      net.authorize.arb.subscription.suspended  — subscription suspended

    Set webhook URL in Authorize.net merchant portal:
      https://arhatinfo.com/api/subscriptions/webhook/
    """
    # Verify signature
    print('here')
    signature = request.headers.get('X-ANET-Signature', '')
    print(signature)
    if signature and not verify_webhook_signature(request.body, signature):
        logger.warning('[Webhook] Invalid signature — rejected')
        return HttpResponse(status=401)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    event_type = payload.get('eventType', '')
    event_data = payload.get('payload', {})
    print(f'[Webhook] Received event: {event_type} with data: {event_data}')
    logger.info(f'[Webhook] Event: {event_type}')

    # Route to handler
    handlers = {
        'net.authorize.payment.authcapture.created': _handle_payment_success,
        'net.authorize.payment.capture.created':     _handle_payment_success,
        'net.authorize.payment.void.created':         _handle_payment_void,
        'net.authorize.payment.refund.created':       _handle_payment_refund,
        'net.authorize.arb.subscription.cancelled':   _handle_sub_cancelled,
        'net.authorize.arb.subscription.suspended':   _handle_sub_suspended,
        'net.authorize.arb.subscription.terminated':  _handle_sub_cancelled,
    }

    handler = handlers.get(event_type)
    if handler:
        try:
            handler(event_data)
        except Exception as e:
            logger.error(f'[Webhook] Handler error for {event_type}: {e}')

    return HttpResponse(status=200)


def _handle_payment_success(data: dict):
    """ARB generated a successful recurring payment."""
    authnet_sub_id = str(data.get('id', ''))
    amount_cents   = int(float(data.get('authAmount', 0)) * 100)

    try:
        sub = Subscription.objects.get(authnet_subscription_id=authnet_sub_id)
    except Subscription.DoesNotExist:
        logger.warning(f'[Webhook] No subscription found for authnet id: {authnet_sub_id}')
        return

    # Extend period
    sub.status               = 'active'
    sub.current_period_start = timezone.now()
    sub.current_period_end   = timezone.now() + (
        timedelta(days=365) if sub.plan.interval == 'yearly' else timedelta(days=30)
    )
    sub.save()

    # Log the payment
    Payment.objects.create(
        user                    = sub.user,
        subscription            = sub,
        plan                    = sub.plan,
        amount_cents            = amount_cents,
        currency                = sub.plan.currency,
        status                  = 'succeeded',
        description             = f'Recurring — {sub.plan.name}',
        authnet_subscription_id = authnet_sub_id,
    )
    logger.info(f'[Webhook] Recurring payment succeeded: {authnet_sub_id} (${amount_cents/100:.2f})')


def _handle_payment_void(data: dict):
    """Payment was voided."""
    authnet_sub_id = str(data.get('id', ''))
    try:
        sub = Subscription.objects.get(authnet_subscription_id=authnet_sub_id)
        Payment.objects.filter(
            subscription=sub, status='succeeded'
        ).order_by('-created_at').first()
        Payment.objects.create(
            user=sub.user, subscription=sub, plan=sub.plan,
            amount_cents=0, currency=sub.plan.currency,
            status='refunded', description='Payment voided',
            authnet_subscription_id=authnet_sub_id,
        )
    except Subscription.DoesNotExist:
        pass


def _handle_payment_refund(data: dict):
    """Payment was refunded."""
    authnet_sub_id = str(data.get('id', ''))
    amount_cents   = int(float(data.get('authAmount', 0)) * 100)
    try:
        sub = Subscription.objects.get(authnet_subscription_id=authnet_sub_id)
        Payment.objects.create(
            user=sub.user, subscription=sub, plan=sub.plan,
            amount_cents=amount_cents, currency=sub.plan.currency,
            status='refunded', description='Refund',
            authnet_subscription_id=authnet_sub_id,
        )
    except Subscription.DoesNotExist:
        pass


def _handle_sub_cancelled(data: dict):
    """Authorize.net cancelled or terminated the subscription."""
    authnet_sub_id = str(data.get('id', ''))
    try:
        sub = Subscription.objects.get(authnet_subscription_id=authnet_sub_id)
        sub.status       = 'cancelled'
        sub.cancelled_at = timezone.now()
        sub.save()
        _downgrade_to_free(sub.user, sub)
        logger.info(f'[Webhook] Subscription cancelled: {authnet_sub_id}')
    except Subscription.DoesNotExist:
        logger.warning(f'[Webhook] Cancelled sub not found: {authnet_sub_id}')


def _handle_sub_suspended(data: dict):
    """Subscription suspended (payment failed repeatedly)."""
    authnet_sub_id = str(data.get('id', ''))
    try:
        sub = Subscription.objects.get(authnet_subscription_id=authnet_sub_id)
        sub.status = 'past_due'
        sub.save()
        logger.info(f'[Webhook] Subscription suspended: {authnet_sub_id}')
    except Subscription.DoesNotExist:
        pass


def _downgrade_to_free(user, sub):
    """Switch user to free plan after cancellation."""
    from .models import Plan
    try:
        free_plan = Plan.objects.get(tier='free', interval='monthly')
        sub.plan                    = free_plan
        sub.status                  = 'active'
        sub.authnet_subscription_id = ''
        sub.cancel_at_period_end    = False
        sub.save()
    except Plan.DoesNotExist:
        pass
