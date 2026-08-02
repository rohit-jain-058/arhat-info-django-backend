from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    """
    Returns a consistent error envelope:
    {
        "success": false,
        "error": {
            "code":    "validation_error",
            "message": "...",
            "detail":  { ... }
        }
    }
    """
    response = exception_handler(exc, context)

    if response is not None:
        error_detail = response.data

        # Flatten single-string errors
        if isinstance(error_detail, list) and len(error_detail) == 1:
            message = str(error_detail[0])
        elif isinstance(error_detail, dict) and 'detail' in error_detail:
            message = str(error_detail['detail'])
        else:
            message = 'An error occurred.'

        response.data = {
            'success': False,
            'error': {
                'code':    _get_error_code(response.status_code),
                'message': message,
                'detail':  error_detail,
            }
        }

    return response


def _get_error_code(status_code):
    codes = {
        400: 'bad_request',
        401: 'unauthorized',
        403: 'forbidden',
        404: 'not_found',
        405: 'method_not_allowed',
        409: 'conflict',
        422: 'validation_error',
        429: 'too_many_requests',
        500: 'server_error',
    }
    return codes.get(status_code, 'error')
