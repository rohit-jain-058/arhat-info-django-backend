"""
Structured error logging helper — Cloud Run / Cloud Logging version.

Same call signature as the file-based version from before, but now the
`extra` dict and stack trace flow into Cloud Logging's jsonPayload via
the CloudLoggingJSONFormatter, rather than being flattened into a plain
text string for a log file. This is what makes fields individually
filterable in Logs Explorer.

Usage — identical to before, same call sites in stripe_views.py,
ai_usage.py, network_views.py:

    from apps.core.log_helpers import log_exception

    except Exception as e:
        log_exception(logger, 'Webhook handler failed', e,
                       request=request, extra={'event_type': event_type})

In Cloud Console Logs Explorer you can then filter with:
    jsonPayload.context="Webhook handler failed"
    jsonPayload.event_type="invoice.payment_succeeded"
    severity>=ERROR
"""
import logging
import sys


def log_exception(logger: logging.Logger, context: str, exc: Exception,
                   request=None, extra: dict = None):
    """
    Drop-in replacement for `logger.error(f'...: {e}')`.
    Passes structured fields via `extra=` so they land in Cloud Logging's
    jsonPayload as individually filterable fields, and includes exc_info
    so the full stack trace is captured — this is what triggers automatic
    pickup by Cloud Run's Error Reporting.
    """
    fields = {'context': context}

    if request is not None:
        try:
            user = getattr(request, 'user', None)
            if user and getattr(user, 'is_authenticated', False):
                fields['user_email'] = user.email
                fields['user_id']    = str(user.id)
            ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
            if ip:
                fields['ip_address'] = ip.split(',')[0].strip()
            fields['path']   = request.path
            fields['method'] = request.method
        except Exception:
            pass

    if extra:
        fields.update(extra)

    # exc_info=True attaches the real traceback object so the formatter's
    # record.exc_info branch fires and Error Reporting can group on it
    logger.error(f'{context}: {exc}', exc_info=True, extra=fields)


def log_warning(logger: logging.Logger, message: str, request=None, extra: dict = None):
    """Same idea for non-exception warnings — quota hits, suspicious activity, etc."""
    fields = extra.copy() if extra else {}
    if request is not None:
        try:
            user = getattr(request, 'user', None)
            if user and getattr(user, 'is_authenticated', False):
                fields['user_email'] = user.email
        except Exception:
            pass
    logger.warning(message, extra=fields)
