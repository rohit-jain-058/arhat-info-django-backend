"""
Internal admin dashboard views — staff-only (request.user.is_staff).

Not to be confused with Django's /admin/ (that's still there for raw CRUD).
These are read-only aggregation endpoints that back the React admin
dashboard at /admin, giving a business-level view: revenue, active
subscribers, and which users need billing follow-up this month.

Endpoints:
  GET /api/subscriptions/admin/overview/  — MRR, subscriber counts, churn, failed $
  GET /api/subscriptions/admin/users/     — paginated user list + this month's payment status
  GET /api/subscriptions/admin/alerts/    — users needing follow-up (past_due / failed payment)
"""
import logging
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from .models import Plan, Subscription, Payment

logger = logging.getLogger(__name__)
User = get_user_model()


# ── HELPERS ───────────────────────────────────────────────────────────
def _month_start(now=None):
    now = now or timezone.now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _monthly_value_cents(plan) -> int:
    """Normalize any plan's price to a monthly value for MRR math."""
    if not plan or plan.tier == 'free':
        return 0
    if plan.interval == 'yearly':
        return round(plan.price_cents / 12)
    return plan.price_cents


def _payment_status_map(user_ids, month_start) -> dict:
    """
    {user_id: latest payment status this month}. Bulk query — avoids
    an N+1 lookup per user when building the admin user list.
    """
    payments = (
        Payment.objects
        .filter(user_id__in=user_ids, created_at__gte=month_start)
        .order_by('user_id', '-created_at')
        .values('user_id', 'status')
    )
    status_map = {}
    for p in payments:
        uid = p['user_id']
        if uid not in status_map:          # first row per user_id = most recent (order_by above)
            status_map[uid] = p['status']
    return status_map


def _this_month_status(sub, latest_payment_status) -> str:
    """
    Single source of truth for "this month's payment status" — used by
    both the user list and the alerts view so they never disagree.
    """
    if sub.plan.tier == 'free':
        return 'free'
    if latest_payment_status == 'succeeded':
        return 'paid'
    if sub.status == 'past_due':
        return 'past_due'
    if latest_payment_status == 'failed':
        return 'failed'
    if sub.status == 'trialing':
        return 'trialing'
    if sub.status == 'cancelled':
        return 'cancelled'
    return 'pending'  # paid tier, no payment recorded yet this month (renewal not due)


# ── OVERVIEW ─────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_overview(request):
    """
    GET /api/subscriptions/admin/overview/
    Revenue + subscriber snapshot for the current calendar month.
    """
    month_start = _month_start()

    active_subs = (
        Subscription.objects
        .filter(status__in=['active', 'trialing'])
        .exclude(plan__tier='free')
        .select_related('plan')
    )
    active_list = list(active_subs)
    mrr_cents   = sum(_monthly_value_cents(s.plan) for s in active_list)

    tier_counts = defaultdict(int)
    for s in active_list:
        tier_counts[s.plan.tier] += 1

    new_this_month = (
        Subscription.objects
        .filter(created_at__gte=month_start)
        .exclude(plan__tier='free')
        .count()
    )

    cancelled_this_month = Subscription.objects.filter(cancelled_at__gte=month_start).count()
    past_due_count       = Subscription.objects.filter(status='past_due').count()

    failed_payments      = Payment.objects.filter(status='failed', created_at__gte=month_start)
    failed_count         = failed_payments.count()
    failed_amount_cents  = sum(p.amount_cents for p in failed_payments)

    succeeded_payments   = Payment.objects.filter(status='succeeded', created_at__gte=month_start)
    collected_cents      = sum(p.amount_cents for p in succeeded_payments)

    return Response({
        'month_label':                    month_start.strftime('%B %Y'),
        'mrr_cents':                      mrr_cents,
        'mrr_display':                    f'${mrr_cents / 100:,.2f}',
        'active_subscribers':             len(active_list),
        'total_users':                    User.objects.count(),
        'tier_breakdown':                 dict(tier_counts),
        'new_subscribers_this_month':     new_this_month,
        'cancelled_this_month':           cancelled_this_month,
        'past_due_count':                 past_due_count,
        'failed_payments_this_month':     failed_count,
        'failed_amount_cents':            failed_amount_cents,
        'failed_amount_display':          f'${failed_amount_cents / 100:,.2f}',
        'collected_this_month_cents':     collected_cents,
        'collected_this_month_display':   f'${collected_cents / 100:,.2f}',
    })


# ── USER LIST ──────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_users(request):
    """
    GET /api/subscriptions/admin/users/?search=&status=&page=&page_size=

    `status` filters on the derived this_month_status
    (free | paid | pending | failed | past_due | trialing | cancelled).
    """
    search        = request.query_params.get('search', '').strip()
    status_filter = request.query_params.get('status', '').strip()

    try:
        page      = max(1, int(request.query_params.get('page', 1)))
        page_size = min(100, max(1, int(request.query_params.get('page_size', 25))))
    except ValueError:
        page, page_size = 1, 25

    qs = Subscription.objects.select_related('user', 'plan').order_by('-created_at')

    if search:
        qs = qs.filter(Q(user__email__icontains=search) | Q(user__name__icontains=search))

    month_start = _month_start()
    all_subs    = list(qs)
    status_map  = _payment_status_map([s.user_id for s in all_subs], month_start)

    rows = []
    for s in all_subs:
        this_month_status = _this_month_status(s, status_map.get(s.user_id))
        if status_filter and this_month_status != status_filter:
            continue
        rows.append({
            'user_id':              str(s.user_id),
            'email':                s.user.email,
            'name':                 s.user.name,
            'date_joined':          s.user.date_joined,
            'plan_name':            s.plan.name,
            'tier':                 s.plan.tier,
            'interval':             s.plan.interval,
            'price_display':        s.plan.price_display,
            'subscription_status':  s.status,
            'this_month_status':    this_month_status,
            'current_period_end':   s.current_period_end,
            'cancel_at_period_end': s.cancel_at_period_end,
        })

    total = len(rows)
    start = (page - 1) * page_size
    end   = start + page_size

    return Response({
        'results':   rows[start:end],
        'count':     total,
        'page':      page,
        'page_size': page_size,
        'num_pages': max(1, (total + page_size - 1) // page_size),
    })


# ── ALERTS ───────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_alerts(request):
    """
    GET /api/subscriptions/admin/alerts/
    Users needing follow-up: past_due status, or a failed payment this month.
    One row per user (past_due takes priority if both apply).
    """
    month_start = _month_start()

    past_due_subs = (
        Subscription.objects
        .filter(status='past_due')
        .select_related('user', 'plan')
        .order_by('-updated_at')
    )

    failed_payments = (
        Payment.objects
        .filter(status='failed', created_at__gte=month_start)
        .select_related('user', 'plan')
        .order_by('-created_at')
    )

    seen   = set()
    alerts = []

    for s in past_due_subs:
        seen.add(s.user_id)
        alerts.append({
            'user_id':        str(s.user_id),
            'email':          s.user.email,
            'name':           s.user.name,
            'plan_name':      s.plan.name,
            'reason':         'past_due',
            'amount_display': s.plan.price_display,
            'detail':         'Subscription marked past due — renewal payment failed to collect.',
            'date':           s.updated_at,
        })

    for p in failed_payments:
        if p.user_id in seen:
            continue
        seen.add(p.user_id)
        alerts.append({
            'user_id':        str(p.user_id),
            'email':          p.user.email,
            'name':           p.user.name,
            'plan_name':      p.plan.name if p.plan else '',
            'reason':         'failed_payment',
            'amount_display': p.amount_display,
            'detail':         p.description or 'Payment failed',
            'date':           p.created_at,
        })

    alerts.sort(key=lambda a: a['date'], reverse=True)

    return Response({'results': alerts, 'count': len(alerts)})


# ── USER DETAIL / EDIT ────────────────────────────────────────────────
def _user_detail_payload(target) -> dict:
    try:
        sub = target.subscription
        sub_data = {
            'id':                    str(sub.id),
            'plan_id':               str(sub.plan_id),
            'plan_name':             sub.plan.name,
            'tier':                  sub.plan.tier,
            'interval':              sub.plan.interval,
            'status':                sub.status,
            'current_period_start':  sub.current_period_start,
            'current_period_end':    sub.current_period_end,
            'cancel_at_period_end':  sub.cancel_at_period_end,
            'cancelled_at':          sub.cancelled_at,
            'is_trial':              sub.is_trial,
            'trial_ends_at':         sub.trial_ends_at,
            'stripe_subscription_id': sub.stripe_subscription_id,
            'stripe_customer_id':    sub.stripe_customer_id,
        }
    except Subscription.DoesNotExist:
        sub_data = None

    payments = Payment.objects.filter(user=target).select_related('plan').order_by('-created_at')[:50]
    payments_data = [{
        'id':              str(p.id),
        'amount_display':  p.amount_display,
        'status':          p.status,
        'description':     p.description,
        'plan_name':       p.plan.name if p.plan else '',
        'created_at':      p.created_at,
    } for p in payments]

    return {
        'id':             str(target.id),
        'email':          target.email,
        'name':           target.name,
        'last_name':      target.last_name,
        'is_active':      target.is_active,
        'is_staff':       target.is_staff,
        'is_verified':    target.is_verified,
        'email_verified': target.email_verified,
        'date_joined':    target.date_joined,
        'last_login':     target.last_login,
        'subscription':   sub_data,
        'payments':       payments_data,
    }


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_user_detail(request, user_id):
    """
    GET   /api/subscriptions/admin/users/<user_id>/
    PATCH /api/subscriptions/admin/users/<user_id>/
      Body (all optional): { name, last_name, email, is_active, is_staff,
                              is_verified, email_verified }

    Profile edits only — subscription changes go through
    admin_user_subscription() below so the two concerns (identity vs.
    billing state) stay auditable separately.
    """
    target = get_object_or_404(User, id=user_id)

    if request.method == 'PATCH':
        data    = request.data
        changed = []

        if 'email' in data:
            new_email = (data['email'] or '').strip().lower()
            if not new_email:
                return Response({'error': 'Email cannot be empty.'}, status=400)
            if User.objects.exclude(id=target.id).filter(email=new_email).exists():
                return Response({'error': 'Another user already has that email.'}, status=400)
            target.email = new_email
            changed.append('email')

        for field in ('name', 'last_name'):
            if field in data:
                setattr(target, field, data[field] or '')
                changed.append(field)

        for field in ('is_active', 'is_staff', 'is_verified', 'email_verified'):
            if field in data:
                # Guard: an admin can't strip their own staff access or
                # deactivate their own account through this panel — that's
                # how you get permanently locked out of the panel that
                # would undo it. Do it from Django admin/shell instead.
                if target.id == request.user.id and field in ('is_staff', 'is_active') and not data[field]:
                    return Response(
                        {'error': f'You cannot remove your own {field.replace("_", " ")} through this panel.'},
                        status=400,
                    )
                setattr(target, field, bool(data[field]))
                changed.append(field)

        target.save()
        logger.info(f'[Admin] {request.user.email} updated user {target.email}: {changed}')

    return Response(_user_detail_payload(target))


# ── SUBSCRIPTION OVERRIDE ───────────────────────────────────────────────
@api_view(['PATCH'])
@permission_classes([IsAuthenticated, IsAdminUser])
def admin_user_subscription(request, user_id):
    """
    PATCH /api/subscriptions/admin/users/<user_id>/subscription/
    Body (all optional): { plan_id, status, current_period_end, cancel_at_period_end }

    Manually overrides a user's LOCAL subscription record — for support,
    comps, or fixing a record that drifted from Stripe. Does NOT call
    Stripe. If the user has a live Stripe subscription, the next webhook
    event (renewal, cancellation, etc.) can overwrite fields set here —
    this is a local override, not a Stripe action. For anything that
    should also change what Stripe charges, use the Stripe dashboard or
    the existing /checkout /cancel endpoints instead.
    """
    target = get_object_or_404(User, id=user_id)
    try:
        sub = target.subscription
    except Subscription.DoesNotExist:
        return Response({'error': 'User has no subscription record.'}, status=404)

    data    = request.data
    changed = []

    if 'plan_id' in data:
        try:
            plan = Plan.objects.get(id=data['plan_id'], is_active=True)
        except Plan.DoesNotExist:
            return Response({'error': 'Plan not found.'}, status=400)
        sub.plan = plan
        changed.append('plan')

    if 'status' in data:
        valid_statuses = dict(Subscription.STATUS_CHOICES)
        if data['status'] not in valid_statuses:
            return Response({'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}, status=400)
        sub.status = data['status']
        changed.append('status')

    if 'current_period_end' in data:
        raw = data['current_period_end']
        sub.current_period_end = parse_datetime(raw) if raw else None
        changed.append('current_period_end')

    if 'cancel_at_period_end' in data:
        sub.cancel_at_period_end = bool(data['cancel_at_period_end'])
        changed.append('cancel_at_period_end')

    if not changed:
        return Response({'error': 'No recognized fields in request body.'}, status=400)

    sub.save()
    logger.info(f'[Admin] {request.user.email} manually edited subscription for {target.email}: {changed}')

    return Response(_user_detail_payload(target))
