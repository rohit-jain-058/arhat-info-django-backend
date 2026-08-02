"""
Stripe views — handles both new subscriptions and upgrades/downgrades.

checkout() now detects the user's state and routes correctly:
  - No existing paid sub → Stripe Checkout Session (redirect)
  - Existing paid sub    → inline upgrade via Subscription.modify()
                           with proration, no redirect needed
"""
import json
import logging
from datetime import datetime, timezone

from django.conf import settings
# from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import HttpResponse

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status

from .models import Plan, Subscription, Payment
from .serializers import SubscriptionSerializer
from .stripe_service import (
    create_checkout_session,
    upgrade_subscription,
    create_portal_session,
    cancel_subscription,
    resume_subscription,
    construct_webhook_event,
)

logger = logging.getLogger(__name__)

FRONTEND_URL = getattr(settings, 'FRONTEND_URL', 'https://arhat.info')


def _sub_periods(stripe_sub) -> tuple:
    """Extract period dates from Stripe Subscription, compatible with new API."""
    start_ts = _stripe_val(stripe_sub, 'current_period_start')
    end_ts   = _stripe_val(stripe_sub, 'current_period_end')
    if start_ts is None or end_ts is None:
        items = _stripe_val(stripe_sub, 'items') or {}
        items_data = _stripe_val(items, 'data') or []
        if items_data:
            start_ts = start_ts or _stripe_val(items_data[0], 'current_period_start')
            end_ts   = end_ts   or _stripe_val(items_data[0], 'current_period_end')
    now = datetime.now()
    period_start = datetime.fromtimestamp(start_ts, tz=timezone.utc) if start_ts else now
    period_end   = datetime.fromtimestamp(end_ts,   tz=timezone.utc) if end_ts   else now
    return period_start, period_end


# ── PUBLISHABLE KEY ────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def publishable_key(request):
    return Response({'publishable_key': settings.STRIPE_PUBLISHABLE_KEY})


# ── CHECKOUT / UPGRADE ─────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def checkout(request):
    """
    POST /api/subscriptions/checkout/
    Body: { "plan_id": "<uuid>", "interval": "monthly" | "yearly" }

    Two paths:
    A) User has NO existing paid subscription:
       → Creates Stripe Checkout Session
       → Returns { "checkout_url": "https://checkout.stripe.com/..." }
       → React redirects to that URL

    B) User ALREADY has a paid subscription (upgrading or downgrading):
       → Modifies the existing Stripe subscription in place with proration
       → Returns { "subscription": {...}, "upgraded": true }
       → React stays on the page, refreshes subscription state
       → NO duplicate subscription, NO double charge
    """
    plan_id  = request.data.get('plan_id')
    interval = request.data.get('interval', 'monthly')

    if not plan_id:
        return Response({'error': 'plan_id is required'}, status=400)

    try:
        plan = Plan.objects.get(id=plan_id, is_active=True)
    except Plan.DoesNotExist:
        return Response({'error': 'Plan not found'}, status=404)

    if plan.tier == 'free':
        return Response({'error': 'Free plan does not require checkout'}, status=400)

    if not plan.stripe_price_id:
        return Response({'error': 'This plan is not yet available for purchase.'}, status=400)

    user = request.user

    # ── Check if user already has an active paid subscription ──────────
    existing_sub = None
    try:
        sub = user.subscription
        if sub.is_active and sub.stripe_subscription_id and not sub.is_free:
            existing_sub = sub
    except Subscription.DoesNotExist:
        pass

    # ── PATH B: Existing subscriber — upgrade/downgrade in place ───────
    if existing_sub:
        if existing_sub.plan.id == plan.id:
            return Response({'error': 'You are already on this plan.'}, status=400)

        try:
            stripe_sub = upgrade_subscription(
                stripe_subscription_id = existing_sub.stripe_subscription_id,
                new_plan               = plan,
            )
        except Exception as e:
            logger.error(f'[Upgrade] Failed for {user.email}: {e}', exc_info=True)
            return Response({'error': str(e)}, status=500)

        # Update DB immediately — proration credit already applied at Stripe level
        period_start, period_end = _sub_periods(stripe_sub)
        existing_sub.plan                 = plan
        existing_sub.status               = 'active'
        existing_sub.cancel_at_period_end = False
        existing_sub.current_period_start = period_start
        existing_sub.current_period_end   = period_end
        existing_sub.save()

        # Log the upgrade as a payment event
        Payment.objects.create(
            user         = user,
            subscription = existing_sub,
            plan         = plan,
            amount_cents = 0,   # actual prorated amount is handled by Stripe invoice
            currency     = plan.currency,
            status       = 'succeeded',
            description  = f'Plan change → {plan.name} (prorated)',
        )

        logger.info(f'[Upgrade] {user.email}: {existing_sub.plan.name} → {plan.name} (prorated)')
        return Response({
            'upgraded':     True,
            'subscription': SubscriptionSerializer(existing_sub).data,
            'message':      f'Upgraded to {plan.name}. Unused days credited automatically.',
        })

    # ── PATH A: New subscriber — Stripe Checkout Session ───────────────
    try:
        checkout_url = create_checkout_session(
            user        = user,
            plan        = plan,
            interval    = interval,
            success_url = f'{FRONTEND_URL}/dashboard',
            cancel_url  = f'{FRONTEND_URL}/pricing',
        )
    except Exception as e:
        logger.error(f'[Checkout] Session creation failed: {e}', exc_info=True)
        return Response({'error': str(e)}, status=500)

    return Response({'checkout_url': checkout_url})


# ── BILLING PORTAL ─────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def portal(request):
    try:
        sub = request.user.subscription
        if not sub.stripe_customer_id:
            return Response({'error': 'No billing account found.'}, status=404)
    except Subscription.DoesNotExist:
        return Response({'error': 'No subscription found.'}, status=404)

    try:
        portal_url = create_portal_session(
            user       = request.user,
            return_url = f'{FRONTEND_URL}/dashboard',
        )
    except Exception as e:
        logger.error(f'[Portal] Failed for {request.user.email}: {e}', exc_info=True)
        return Response({'error': str(e)}, status=500)

    return Response({'portal_url': portal_url})


# ── CANCEL ─────────────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel(request):
    at_period_end = request.data.get('at_period_end', True)

    try:
        sub = request.user.subscription
    except Subscription.DoesNotExist:
        return Response({'error': 'No subscription found.'}, status=404)

    if not sub.is_active or sub.is_free:
        return Response({'error': 'No paid subscription to cancel.'}, status=400)

    if not sub.stripe_subscription_id:
        return Response({'error': 'No Stripe subscription found.'}, status=400)

    try:
        cancel_subscription(sub.stripe_subscription_id, at_period_end=at_period_end)
    except Exception as e:
        logger.error(f'[Cancel] Stripe cancel failed for {request.user.email}: {e}', exc_info=True)
        return Response({'error': str(e)}, status=500)

    if at_period_end:
        sub.cancel_at_period_end = True
        sub.save(update_fields=['cancel_at_period_end', 'updated_at'])
        message = 'Subscription will cancel at end of billing period.'
    else:
        sub.status       = 'cancelled'
        sub.cancelled_at = timezone.now()
        sub.save()
        _downgrade_to_free(request.user, sub)
        message = 'Subscription cancelled immediately.'

    return Response({'message': message, 'subscription': SubscriptionSerializer(sub).data})


# ── RESUME ─────────────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def resume(request):
    try:
        sub = request.user.subscription
    except Subscription.DoesNotExist:
        return Response({'error': 'No subscription found.'}, status=404)

    if not sub.cancel_at_period_end:
        return Response({'error': 'Subscription is not scheduled to cancel.'}, status=400)

    try:
        resume_subscription(sub.stripe_subscription_id)
    except Exception as e:
        return Response({'error': str(e)}, status=500)

    sub.cancel_at_period_end = False
    sub.save(update_fields=['cancel_at_period_end', 'updated_at'])
    return Response({'message': 'Subscription resumed.', 'subscription': SubscriptionSerializer(sub).data})


# ── WEBHOOK ────────────────────────────────────────────────────────────
@csrf_exempt
@require_POST
def webhook(request):
    payload    = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        event = construct_webhook_event(payload, sig_header)
    except Exception as e:
        logger.warning(f'[Webhook] Invalid signature: {e}')
        return HttpResponse(status=400)

    event_type = event['type']
    data       = event['data']['object']

    logger.info(f'[Webhook] Event: {event_type}')

    handlers = {
        'checkout.session.completed':    _handle_checkout_complete,
        'customer.subscription.updated': _handle_subscription_updated,
        'customer.subscription.deleted': _handle_subscription_deleted,
        'invoice.payment_succeeded':     _handle_payment_succeeded,
        'invoice.payment_failed':        _handle_payment_failed,
    }

    handler = handlers.get(event_type)
    if handler:
        try:
            handler(data)
        except Exception as e:
            logger.error(
                f'[Webhook] Handler error for {event_type}: {e}',
                exc_info=True,
                extra={'event_type': event_type},
            )

    return HttpResponse(status=200)


# ── WEBHOOK HANDLERS ───────────────────────────────────────────────────

def _handle_checkout_complete(session):
    """New subscriber — activate their subscription."""
    stripe_sub_id      = _stripe_val(session, 'subscription')
    stripe_customer_id = _stripe_val(session, 'customer')
    metadata           = _stripe_val(session, 'metadata') or {}
    user_id            = _stripe_val(metadata, 'user_id')
    plan_id            = _stripe_val(metadata, 'plan_id')

    if not user_id or not plan_id:
        logger.error('[Webhook] checkout.session.completed missing metadata', extra={'session_id': _stripe_val(session, 'id')})
        return

    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
        plan = Plan.objects.get(id=plan_id)
    except Exception as e:
        logger.error(f'[Webhook] User/Plan not found: {e}', exc_info=True)
        return

    import stripe as stripe_lib
    stripe_lib.api_key = settings.STRIPE_SECRET_KEY
    try:
        stripe_sub = stripe_lib.Subscription.retrieve(stripe_sub_id)
        period_start, period_end = _sub_periods(stripe_sub)
    except Exception:
        period_start = period_end = timezone.now()

    # Update or create — never create a second subscription row
    try:
        sub = user.subscription
    except Subscription.DoesNotExist:
        sub = Subscription(user=user)

    sub.plan                   = plan
    sub.status                 = 'active'
    sub.stripe_subscription_id = stripe_sub_id
    sub.stripe_customer_id     = stripe_customer_id
    sub.cancel_at_period_end   = False
    sub.cancelled_at           = None
    sub.current_period_start   = period_start
    sub.current_period_end     = period_end
    sub.save()

    logger.info(f'[Webhook] New subscription activated: {user.email} → {plan.name}')


def _handle_subscription_updated(stripe_sub):
    """
    Fires on any subscription change — including our own upgrade_subscription() call.
    Update period dates and status. The plan was already updated in the checkout() view
    for in-place upgrades, so we don't re-lookup the plan here to avoid overwriting it
    with stale Stripe metadata on upgrades that happened mid-period.
    """
    try:
        sub = Subscription.objects.get(stripe_subscription_id=stripe_sub['id'])
    except Subscription.DoesNotExist:
        return

    period_start, period_end = _sub_periods(stripe_sub)
    sub.current_period_start = period_start
    sub.current_period_end   = period_end
    sub.cancel_at_period_end = _stripe_val(stripe_sub, 'cancel_at_period_end') or False

    stripe_status = _stripe_val(stripe_sub, 'status')
    status_map = {
        'active':   'active',
        'trialing': 'trialing',
        'past_due': 'past_due',
        'canceled': 'cancelled',
        'unpaid':   'past_due',
    }
    sub.status = status_map.get(stripe_status, sub.status)
    sub.save()

    logger.info(f'[Webhook] Subscription updated: {stripe_sub["id"]} status={stripe_status}')


def _handle_subscription_deleted(stripe_sub):
    """Subscription cancelled at Stripe — downgrade to free."""
    try:
        sub = Subscription.objects.get(stripe_subscription_id=stripe_sub['id'])
    except Subscription.DoesNotExist:
        return

    sub.status       = 'cancelled'
    sub.cancelled_at = timezone.now()
    sub.save()
    _downgrade_to_free(sub.user, sub)
    logger.info(f'[Webhook] Subscription deleted, downgraded to free: {stripe_sub["id"]}')


def _stripe_val(obj, key, default=None):
    """
    Safe field access for Stripe objects in API version 2026-05-27.dahlia.
    Stripe objects no longer support .get() — use bracket access with try/except.
    """
    try:
        v = obj[key]
        return v if v is not None else default
    except (KeyError, TypeError):
        return default


def _handle_payment_succeeded(invoice):
    """
    Recurring payment succeeded — log it and extend period.
    Also acts as fallback activation if checkout.session.completed was missed.
    """
    # Use bracket access — Stripe objects in the new API don't support .get()
    parent  = _stripe_val(invoice, 'parent') or {}
    sub_det = _stripe_val(parent,  'subscription_details') or {}

    stripe_sub_id  = _stripe_val(invoice, 'subscription') or _stripe_val(sub_det, 'subscription')
    amount_cents   = _stripe_val(invoice, 'amount_paid') or 0
    stripe_cust_id = _stripe_val(invoice, 'customer')

    if not stripe_sub_id:
        return

    sub = None
    try:
        sub = Subscription.objects.get(stripe_subscription_id=stripe_sub_id)
    except Subscription.DoesNotExist:
        pass

    # Fallback activation if checkout.session.completed wasn't processed
    if sub is None:
        lines      = _stripe_val(invoice, 'lines') or {}
        lines_data = _stripe_val(lines, 'data') or []
        line0      = lines_data[0] if lines_data else {}

        metadata = (
            _stripe_val(sub_det, 'metadata')
            or _stripe_val(line0, 'metadata')
            or _stripe_val(invoice, 'metadata')
            or {}
        )
        user_id = _stripe_val(metadata, 'user_id')
        plan_id = _stripe_val(metadata, 'plan_id')

        if not user_id or not plan_id:
            logger.warning(f'[Webhook] No subscription found for {stripe_sub_id} and no metadata to recover')
            return

        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(id=user_id)
            plan = Plan.objects.get(id=plan_id)
        except Exception as e:
            logger.error(f'[Webhook] Recovery failed — user/plan not found: {e}', exc_info=True)
            return

        import stripe as stripe_lib
        stripe_lib.api_key = settings.STRIPE_SECRET_KEY
        try:
            stripe_sub = stripe_lib.Subscription.retrieve(stripe_sub_id)
            period_start, period_end = _sub_periods(stripe_sub)
        except Exception:
            period_start = period_end = timezone.now()

        try:
            sub = user.subscription
        except Subscription.DoesNotExist:
            sub = Subscription(user=user)

        sub.plan                   = plan
        sub.status                 = 'active'
        sub.stripe_subscription_id = stripe_sub_id
        sub.stripe_customer_id     = stripe_cust_id
        sub.cancel_at_period_end   = False
        sub.cancelled_at           = None
        sub.current_period_start   = period_start
        sub.current_period_end     = period_end
        sub.save()
        logger.info(f'[Webhook] Subscription activated via invoice fallback: {sub.user.email} → {sub.plan.name}')

    # Log the payment (dedupe by invoice id)
    if amount_cents > 0:
        Payment.objects.get_or_create(
            stripe_invoice_id = _stripe_val(invoice, 'id') or '',
            defaults = dict(
                user                     = sub.user,
                subscription             = sub,
                plan                     = sub.plan,
                amount_cents             = amount_cents,
                currency                 = (_stripe_val(invoice, 'currency') or 'cad').upper(),
                status                   = 'succeeded',
                description              = f'{sub.plan.name} — payment',
                stripe_payment_intent_id = _stripe_val(invoice, 'payment_intent') or '',
            )
        )
    logger.info(f'[Webhook] Payment succeeded: ${amount_cents/100:.2f} for {sub.user.email}')


def _handle_payment_failed(invoice):
    """Recurring payment failed — mark past_due."""
    parent  = _stripe_val(invoice, 'parent') or {}
    sub_det = _stripe_val(parent, 'subscription_details') or {}
    stripe_sub_id = _stripe_val(invoice, 'subscription') or _stripe_val(sub_det, 'subscription')
    amount_cents  = _stripe_val(invoice, 'amount_due') or 0

    try:
        sub = Subscription.objects.get(stripe_subscription_id=stripe_sub_id)
    except Subscription.DoesNotExist:
        return

    sub.status = 'past_due'
    sub.save(update_fields=['status', 'updated_at'])

    Payment.objects.create(
        user              = sub.user,
        subscription      = sub,
        plan              = sub.plan,
        amount_cents      = amount_cents,
        currency          = (_stripe_val(invoice, 'currency') or 'cad').upper(),
        status            = 'failed',
        description       = f'Failed payment — {sub.plan.name}',
        stripe_invoice_id = _stripe_val(invoice, 'id') or '',
    )
    logger.warning(f'[Webhook] Payment FAILED: ${amount_cents/100:.2f} for {sub.user.email}')


# ── HELPER ─────────────────────────────────────────────────────────────
def _downgrade_to_free(user, sub):
    try:
        free_plan = Plan.objects.get(tier='free', interval='monthly')
        sub.plan                   = free_plan
        sub.status                 = 'active'
        sub.stripe_subscription_id = ''
        sub.cancel_at_period_end   = False
        sub.save()
    except Plan.DoesNotExist:
        logger.error('[Stripe] Free plan not found — run loaddata fixtures')
