"""
Shared AI usage gate — combines subscription tier check + per-plan daily
limit enforcement + logging to both AIToolRequest (full history, per user)
and AIUsageLog (fast daily counters for rate limiting).

Use in every AI tool view via the `@ai_tool_endpoint` decorator below —
it replaces having to repeat permission_classes + manual logging in each
of the 9 AI views.

Plan field used: Plan.ai_requests_per_day
  0  → unlimited requests for that plan
  N  → max N AI requests per rolling 24h (any tool, combined) for that plan

Set per-plan limits via Django admin or fixture, e.g.:
  ai_tools plan  → ai_requests_per_day = 50
  full plan      → ai_requests_per_day = 200   (0 = unlimited if you prefer)
"""
import logging
from functools import wraps

from django.utils import timezone
from rest_framework.response import Response
from rest_framework import status

from apps.subscriptions.permissions import IsAIToolsSubscriber
from apps.subscriptions.models import AIUsageLog
from apps.tools.models import AIToolRequest

logger = logging.getLogger(__name__)


def _get_ip(request) -> str:
    for h in ['HTTP_CF_CONNECTING_IP', 'HTTP_X_REAL_IP', 'HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR']:
        v = request.META.get(h, '').split(',')[0].strip()
        if v:
            return v
    return ''


def get_daily_usage(user) -> int:
    """Total AI requests made by user today across all tools."""
    today = timezone.now().date()
    from django.db.models import Sum
    total = AIUsageLog.objects.filter(user=user, date=today).aggregate(
        total=Sum('requests_count')
    )['total']
    return total or 0


def get_daily_limit(user) -> int:
    """0 = unlimited. Returns the user's plan ai_requests_per_day."""
    try:
        sub = user.subscription
        if sub.is_active:
            return sub.plan.ai_requests_per_day
    except Exception:
        pass
    return 0


def check_ai_quota(user) -> tuple:
    """
    Returns (allowed: bool, used: int, limit: int).
    limit == 0 means unlimited.
    """
    limit = get_daily_limit(user)
    if limit == 0:
        return True, get_daily_usage(user), 0
    used = get_daily_usage(user)
    return used < limit, used, limit


def record_ai_usage(user, tool: str, tokens_used: int = 0):
    """Increment today's usage counter for this user + tool."""
    today = timezone.now().date()
    row, _ = AIUsageLog.objects.get_or_create(
        user=user, date=today, tool=tool,
        defaults={'requests_count': 0, 'tokens_used': 0},
    )
    row.requests_count += 1
    row.tokens_used    += tokens_used
    row.save(update_fields=['requests_count', 'tokens_used', 'updated_at'])


def log_ai_request(request, tool: str, result: dict = None, input_data: dict = None,
                    success: bool = True, error: str = ''):
    """
    Single entry point for logging an AI tool call.
    Writes to AIToolRequest (full record, tied to user) and bumps
    AIUsageLog (daily counter) when successful.
    """
    user = request.user if request.user.is_authenticated else None
    result = result or {}

    try:
        AIToolRequest.objects.create(
            user              = user,
            tool              = tool,
            ip_address        = _get_ip(request),
            user_agent        = request.META.get('HTTP_USER_AGENT', '')[:512],
            prompt_tokens     = result.get('prompt_tokens'),
            completion_tokens = result.get('completion_tokens'),
            total_tokens      = result.get('total_tokens'),
            model_used        = result.get('model', 'gpt-4o'),
            duration_ms       = result.get('duration_ms'),
            input_data        = input_data,
            output_preview    = (result.get('text') or '')[:500],
            success           = success,
            error             = error,
        )
    except Exception as e:
        logger.warning(f'[AIToolRequest] log failed: {e}')

    if success and user is not None:
        record_ai_usage(user, tool, tokens_used=result.get('total_tokens') or 0)


def ai_tool_endpoint(tool_name: str):
    """
    Decorator for AI tool views. Handles:
      1. Subscription tier check (IsAIToolsSubscriber — must be ai_tools or full)
      2. Daily quota check based on the user's plan
      3. Automatic logging of success/failure via log_ai_request()

    The wrapped view must:
      - Return a dict with at least {'text': ..., 'total_tokens': ..., ...}
        on success (same shape gpt_service.gpt_generate returns)
      - Raise an Exception on failure (caught and logged here)
      - Accept (request) and return that result dict — this decorator
        handles building the final Response.

    Usage:
        @api_view(['POST'])
        @permission_classes([IsAIToolsSubscriber])
        @ai_tool_endpoint('prompt_gen')
        def prompt_generator(request):
            goal = request.data.get('goal', '').strip()
            if not goal:
                raise ValueError('goal is required')
            inputs = {'goal': goal}
            result = generate_prompt(goal, ...)
            return result, inputs   # (gpt result dict, input_data dict to log)
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            # 1. Quota check (permission_classes already enforced tier)
            allowed, used, limit = check_ai_quota(request.user)
            if not allowed:
                log_ai_request(
                    request, tool_name, success=False,
                    error=f'Daily limit reached ({used}/{limit})',
                )
                return Response({
                    'error':      f'Daily AI request limit reached ({used}/{limit}). Resets at midnight UTC, or upgrade your plan for a higher limit.',
                    'used':       used,
                    'limit':      limit,
                }, status=status.HTTP_429_TOO_MANY_REQUESTS)

            # 2. Run the actual tool logic
            try:
                result, inputs = view_func(request, *args, **kwargs)
            except ValueError as e:
                # Bad input — 400, not logged as a failed AI call (no API cost incurred)
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                log_ai_request(request, tool_name, success=False, error=str(e))
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # 3. Log success + usage
            log_ai_request(request, tool_name, result=result, input_data=inputs, success=True)

            return Response({
                'text':   result['text'],
                'tokens': result.get('total_tokens'),
                'usage':  {'used': used + 1, 'limit': limit},
            })
        return wrapped
    return decorator
