"""
UPDATE apps/subscriptions/permissions.py

Replaces IsNoAdsSubscriber / IsAIToolsSubscriber / IsFullBundle with logic
that checks the actual feature flag on the user's plan, rather than
assuming tier order. This is necessary now because tiers no longer form
a strict ladder — e.g. 'ai_tools' does NOT remove ads, but 'no_ads' does
not include AI. Each permission class checks ITS OWN flag only.
"""
from rest_framework.permissions import BasePermission, IsAuthenticated


def _get_subscription(user):
    from django.utils import timezone
    try:
        sub = user.subscription

        # Expire trial if past end date
        if sub.is_trial and sub.trial_ends_at and timezone.now() >= sub.trial_ends_at:
            if sub.status == 'trialing':
                from apps.subscriptions.models import Plan
                free_plan = Plan.objects.filter(tier='free').first()
                if free_plan:
                    sub.plan             = free_plan
                    sub.status           = 'active'
                    sub.is_trial         = False
                    sub.save(update_fields=['plan','status','is_trial','updated_at'])
            return user.subscription  # now returns free plan

        return sub if sub.is_active else None
    except Exception:
        return None


def _get_tier(user) -> str:
    if not user or not user.is_authenticated:
        return 'free'
    sub = _get_subscription(user)
    return sub.tier if sub else 'free'


# ── FEATURE-FLAG-BASED PERMISSIONS ─────────────────────────────────────
# Each class checks ONE flag on the plan. A user can match multiple
# classes at once if their plan has multiple flags set — e.g. 'api_full'
# passes IsNoAdsSubscriber, IsAIToolsSubscriber, AND IsFullBundle.

class IsNoAdsSubscriber(IsAuthenticated):
    """True only if the plan's removes_ads flag is set."""
    message = 'A plan that removes ads is required.'

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        sub = _get_subscription(request.user)
        return bool(sub and sub.removes_ads)


class IsAIToolsSubscriber(IsAuthenticated):
    """True only if the plan's allows_ai_tools flag is set."""
    message = 'A plan with AI Tools access is required.'

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        sub = _get_subscription(request.user)
        return bool(sub and sub.allows_ai_tools)


class IsFormToolsSubscriber(IsAuthenticated):
    """
    True only if the plan's allows_form_tools flag is set.
    RESERVED — Form Tools has no feature behind this yet. Wire this up
    to actual Form Tools views when that product ships; the flag and
    plan data already exist so no further model work is needed then.
    """
    message = 'A plan with Form Tools access is required.'

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        sub = _get_subscription(request.user)
        return bool(sub and sub.allows_form_tools)


class IsFullBundle(IsAuthenticated):
    """True only if the plan's allows_api_key flag is set (API Access tier)."""
    message = 'The API Access plan is required.'

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        sub = _get_subscription(request.user)
        return bool(sub and sub.allows_api_key)


# ── API KEY AUTH — unchanged ────────────────────────────────────────────
class HasValidAPIKey(BasePermission):
    """
    Authenticate via API key in Authorization header.
    Header format: Authorization: Api-Key arhat_xxxx...
    """
    message = 'Valid API key required. Format: Authorization: Api-Key <your-key>'

    def has_permission(self, request, view):
        from apps.subscriptions.models import APIKey

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Api-Key '):
            return False

        raw_key = auth_header[len('Api-Key '):]
        api_key = APIKey.verify(raw_key)
        if not api_key:
            return False

        request.api_key  = api_key
        request.api_user = api_key.user
        api_key.record_use()
        return True


# ── HELPER ────────────────────────────────────────────────────────────
def get_user_tier(request) -> str:
    """Returns the raw tier code: 'free' | 'no_ads' | 'ai_tools' |
    'form_tools' | 'form_ai' | 'no_ads_form_ai' | 'api_full'."""
    if not request.user or not request.user.is_authenticated:
        return 'free'
    return _get_tier(request.user)


def get_user_features(request) -> dict:
    """
    Returns all 4 feature flags at once — convenient for a single
    /api/subscriptions/me/ response instead of 4 separate checks.
    """
    sub = _get_subscription(request.user) if request.user.is_authenticated else None
    return {
        'tier':              sub.tier if sub else 'free',
        'removes_ads':       bool(sub and sub.removes_ads),
        'allows_ai_tools':   bool(sub and sub.allows_ai_tools),
        'allows_form_tools': bool(sub and sub.allows_form_tools),   # reserved
        'allows_api_key':    bool(sub and sub.allows_api_key),
    }
