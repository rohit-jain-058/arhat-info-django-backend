"""
SubscriptionMiddleware — attaches tier info to every request.

Add to MIDDLEWARE in base.py AFTER AuthenticationMiddleware:
  'apps.subscriptions.middleware.SubscriptionMiddleware',

After adding this, any view can do:
  request.tier            → 'free' | 'ai_tools' | 'ai_tools_plus' | 'ai_premium'
  request.removes_ads     → True/False
  request.allows_ai_tools → True/False
  request.allows_api_key  → True/False
"""
import logging

logger = logging.getLogger(__name__)


class SubscriptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Attach defaults — overwritten below if user is authenticated
        request.tier            = 'free'
        request.removes_ads     = False
        request.allows_ai_tools = False
        request.allows_api_key  = False

        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                sub = request.user.subscription
                if sub.is_active:
                    request.tier            = sub.tier
                    request.removes_ads     = sub.removes_ads
                    request.allows_ai_tools = sub.allows_ai_tools
                    request.allows_api_key  = sub.allows_api_key
            except Exception:
                pass  # No subscription — defaults stay as 'free'

        return self.get_response(request)
