from django.db import connection
from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Health-check endpoint for load balancers and uptime monitors.
    Returns 200 if DB and Redis are reachable, 503 otherwise.
    """
    checks = {}

    # Database
    try:
        connection.ensure_connection()
        checks['database'] = 'ok'
    except Exception as e:
        checks['database'] = f'error: {e}'

    # Redis / cache
    try:
        cache.set('health_check', 'ok', timeout=5)
        val = cache.get('health_check')
        checks['redis'] = 'ok' if val == 'ok' else 'error'
    except Exception as e:
        checks['redis'] = f'error: {e}'

    healthy = all(v == 'ok' for v in checks.values())
    return Response(
        {'status': 'healthy' if healthy else 'unhealthy', 'checks': checks},
        status=200 if healthy else 503,
    )
