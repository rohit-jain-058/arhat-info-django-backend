"""
Authorize.net ARB (Automated Recurring Billing) service.

Flow:
  1. Frontend uses Accept.js to tokenize card → gets opaqueData (nonce)
  2. Frontend POSTs nonce + plan to /api/subscriptions/checkout/
  3. This service calls ARB API to create the recurring subscription
  4. Authorize.net handles all future billing automatically
  5. Webhooks notify us of payment events

Install:
  pip install authorizenet

.env vars needed:
  AUTHORIZENET_API_LOGIN_ID=your_login_id
  AUTHORIZENET_TRANSACTION_KEY=your_transaction_key
  AUTHORIZENET_ENVIRONMENT=sandbox   # or 'production'
"""
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings

logger = logging.getLogger(__name__)


def _get_controller_base():
    """Return sandbox or production API base URL."""
    env = getattr(settings, 'AUTHORIZENET_ENVIRONMENT', 'sandbox')
    if env == 'production':
        return 'https://api.authorize.net/xml/v1/request.api'
    return 'https://apitest.authorize.net/xml/v1/request.api'


def _merchant_auth():
    return {
        'name':           settings.AUTHORIZENET_API_LOGIN_ID,
        'transactionKey': settings.AUTHORIZENET_TRANSACTION_KEY,
    }


def _post(payload: dict) -> dict:
    """POST to Authorize.net API and return parsed response."""
    import requests, json
    url = _get_controller_base()
    res = requests.post(url, json=payload, timeout=30)
    res.raise_for_status()
    data = res.json()
    logger.debug(f'[AuthNet] Response: {json.dumps(data, indent=2)}')
    return data


# ── CREATE SUBSCRIPTION (ARB) ──────────────────────────────────────────
def create_subscription(
    opaque_data_descriptor: str,
    opaque_data_value: str,
    plan,                          # Plan model instance
    user,                          # User model instance
    interval: str = 'monthly',     # 'monthly' or 'yearly'
) -> dict:
    """
    Create a recurring subscription via Authorize.net ARB.

    Args:
        opaque_data_descriptor: from Accept.js response (e.g. 'COMMON.ACCEPT.INAPP.PAYMENT')
        opaque_data_value:      from Accept.js response (the nonce token)
        plan:                   your Plan model instance
        user:                   your User model instance
        interval:               'monthly' or 'yearly'

    Returns:
        dict with 'subscription_id' on success, raises on failure
    """
    amount       = Decimal(plan.price_cents) / 100
    start_date   = date.today().isoformat()

    # ARB interval
    if interval == 'yearly':
        arb_length = 12
        arb_unit   = 'months'
        total_occurrences = 9999  # indefinite
    else:
        arb_length = 1
        arb_unit   = 'months'
        total_occurrences = 9999

    # Split name safely
    name_parts  = (getattr(user, 'name', '') or user.email).split(' ', 1)
    first_name  = name_parts[0][:50]
    last_name   = name_parts[1][:50] if len(name_parts) > 1 else '.'

    payload = {
        'ARBCreateSubscriptionRequest': {
            'merchantAuthentication': _merchant_auth(),
            'refId': f'user_{user.id}_{plan.tier}',
            'subscription': {
                'name': f'{plan.name} — {user.email}'[:50],
                'paymentSchedule': {
                    'interval': {
                        'length': arb_length,
                        'unit':   arb_unit,
                    },
                    'startDate':         start_date,
                    'totalOccurrences':  str(total_occurrences),
                    'trialOccurrences':  '0',
                },
                'amount':      str(amount),
                'trialAmount': '0.00',
                'payment': {
                    'opaqueData': {
                        'dataDescriptor': opaque_data_descriptor,
                        'dataValue':      opaque_data_value,
                    }
                },
                'billTo': {
                    'firstName': first_name,
                    'lastName':  last_name,
                    'email':     user.email,
                },
            }
        }
    }

    response = _post(payload)
    result   = response.get('ARBCreateSubscriptionResponse', {})
    messages = result.get('messages', {})

    if messages.get('resultCode') == 'Ok':
        sub_id = result.get('subscriptionId')
        logger.info(f'[AuthNet] Subscription created: {sub_id} for {user.email}')
        return {
            'subscription_id': sub_id,
            'ref_id':          result.get('refId', ''),
        }
    else:
        error = messages.get('message', [{}])
        error_msg = error[0].get('text', 'Unknown error') if error else 'Unknown error'
        error_code= error[0].get('code', '') if error else ''
        logger.error(f'[AuthNet] Create failed: {error_code} — {error_msg}')
        raise Exception(f'Payment failed: {error_msg}')


# ── CANCEL SUBSCRIPTION ────────────────────────────────────────────────
def cancel_subscription(authnet_subscription_id: str) -> bool:
    """
    Cancel a subscription immediately at Authorize.net.
    Returns True on success, raises on failure.
    """
    payload = {
        'ARBCancelSubscriptionRequest': {
            'merchantAuthentication': _merchant_auth(),
            'subscriptionId':         authnet_subscription_id,
        }
    }
    response = _post(payload)
    result   = response.get('ARBCancelSubscriptionResponse', {})
    messages = result.get('messages', {})

    if messages.get('resultCode') == 'Ok':
        logger.info(f'[AuthNet] Subscription cancelled: {authnet_subscription_id}')
        return True
    else:
        error = messages.get('message', [{}])
        error_msg = error[0].get('text', 'Unknown error') if error else 'Unknown error'
        logger.error(f'[AuthNet] Cancel failed: {error_msg}')
        raise Exception(f'Cancel failed: {error_msg}')


# ── GET SUBSCRIPTION STATUS ────────────────────────────────────────────
def get_subscription_status(authnet_subscription_id: str) -> dict:
    """
    Fetch subscription details from Authorize.net.
    Use to verify status or sync with your DB.
    """
    payload = {
        'ARBGetSubscriptionStatusRequest': {
            'merchantAuthentication': _merchant_auth(),
            'subscriptionId':         authnet_subscription_id,
        }
    }
    response = _post(payload)
    result   = response.get('ARBGetSubscriptionStatusResponse', {})
    messages = result.get('messages', {})

    if messages.get('resultCode') == 'Ok':
        return {
            'status':    result.get('status'),
            'raw':       result,
        }
    else:
        error = messages.get('message', [{}])
        error_msg = error[0].get('text', 'Unknown') if error else 'Unknown'
        raise Exception(f'Status check failed: {error_msg}')


# ── UPDATE SUBSCRIPTION AMOUNT ─────────────────────────────────────────
def update_subscription(authnet_subscription_id: str, new_amount: Decimal) -> bool:
    """
    Update amount on an existing subscription (e.g. plan change).
    For plan upgrades/downgrades — easier than cancel + recreate.
    """
    payload = {
        'ARBUpdateSubscriptionRequest': {
            'merchantAuthentication': _merchant_auth(),
            'subscriptionId':         authnet_subscription_id,
            'subscription': {
                'amount': str(new_amount),
            }
        }
    }
    response = _post(payload)
    result   = response.get('ARBUpdateSubscriptionResponse', {})
    messages = result.get('messages', {})

    if messages.get('resultCode') == 'Ok':
        logger.info(f'[AuthNet] Subscription updated: {authnet_subscription_id}')
        return True
    else:
        error = messages.get('message', [{}])
        error_msg = error[0].get('text', 'Unknown') if error else 'Unknown'
        raise Exception(f'Update failed: {error_msg}')


# ── VERIFY WEBHOOK SIGNATURE ───────────────────────────────────────────
def verify_webhook_signature(payload_body: bytes, signature_header: str) -> bool:
    """
    Verify Authorize.net webhook authenticity using HMAC-SHA512.
    Signature header: X-ANET-Signature
    """
    import hmac, hashlib
    signature_key = getattr(settings, 'AUTHORIZENET_SIGNATURE_KEY', '')
    if not signature_key:
        logger.warning('[AuthNet] No AUTHORIZENET_SIGNATURE_KEY set — skipping verification')
        return True

    # Header format: "sha512=<hex_digest>"
    if '=' in signature_header:
        _, received_sig = signature_header.split('=', 1)
    else:
        received_sig = signature_header

    expected_sig = hmac.new(
        signature_key.encode('utf-8'),
        payload_body,
        hashlib.sha512,
    ).hexdigest().upper()

    return hmac.compare_digest(expected_sig, received_sig.upper())
