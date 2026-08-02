"""
AI history endpoint — lets a logged-in user see their own past AI tool
requests (what they asked, which tool, when, token cost).

Add to apps/tools/urls.py:
  path('ai/history/', history_views.ai_history, name='ai_history'),
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import AIToolRequest
from .ai_usage import get_daily_usage, get_daily_limit


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ai_history(request):
    """
    GET /api/tools/ai/history/?limit=50
    Returns the requesting user's own AI tool request history.
    Users can only ever see their own data — filtered by request.user.
    """
    limit = min(int(request.GET.get('limit', 50)), 200)

    qs = AIToolRequest.objects.filter(user=request.user).order_by('-created_at')[:limit]

    history = [{
        'id':          str(r.id),
        'tool':        r.tool,
        'tool_label':  r.get_tool_display(),
        'input':       r.input_data,
        'output_preview': r.output_preview,
        'tokens':      r.total_tokens,
        'model':       r.model_used,
        'success':     r.success,
        'error':       r.error,
        'created_at':  r.created_at,
    } for r in qs]

    return Response({
        'history':      history,
        'usage_today':  get_daily_usage(request.user),
        'limit_today':  get_daily_limit(request.user),   # 0 = unlimited
    })
