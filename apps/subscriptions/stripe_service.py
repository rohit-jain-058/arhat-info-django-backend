"""
Stripe service — handles both new subscriptions AND upgrades/downgrades.

Key flow difference:
  NEW subscriber (no existing stripe_subscription_id):
    → Stripe Checkout Session → redirect → webhook activates
  EXISTING subscriber upgrading/downgrading:
    → stripe.Subscription.modify() inline with proration
    → NO new checkout session, NO redirect, instant switch
    → Stripe automatically credits unused days and charges the difference

Proration example:
  User on No Ads ($2.99/mo CAD), upgrades to AI Tools ($9.99/mo) after 10 days
  used 10/30 days = 1/3 of billing period = $0.997 used
  credit remaining = $2.99 - $0.997 = $1.993
  charge at upgrade = $9.99 - $1.993 = $7.997 (Stripe handles this automatically)
  next month: full $9.99
"""
import logging
from django.conf import settings
import stripe

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


class StaleSubscriptionError(Exception):
    """
    Raised when upgrade_subscription() is asked to modify a Stripe
    subscription that Stripe already considers canceled/expired.

    This happens when the local Subscription row falls out of sync with
    Stripe — e.g. a webhook was missed, or the subscription was cancelled
    directly in the Stripe dashboard. Stripe rejects Subscription.modify()
    on a canceled subscription with: "A canceled subscription can only
    update its cancellation_details and metadata." Callers should catch
    this, heal the local record (mark it cancelled), and start a fresh
    Checkout Session instead of trying to modify in place.
    """
    def __init__(self, stripe_status: str):
        self.stripe_status = stripe_status
        super().__init__(f'Stripe subscription is already "{stripe_status}" — cannot modify in place.')


# ── NEW SUBSCRIPTION — first-time checkout ─────────────────────────────
def create_checkout_session(user, plan, interval: str, success_url: str, cancel_url: str) -> str:
    """
    Only called for users with NO existing paid subscription.
    Returns Stripe Checkout URL to redirect the user to.
    """
    if not plan.stripe_price_id:
        raise ValueError(f'Plan "{plan.name}" has no stripe_price_id. Run setup_stripe_prices.')

    stripe_customer_id = _get_or_create_customer(user)

    session = stripe.checkout.Session.create(
        customer                   = stripe_customer_id,
        payment_method_types       = ['card'],
        mode                       = 'subscription',
        line_items                 = [{'price': plan.stripe_price_id, 'quantity': 1}],
        success_url                = success_url + '?session_id={CHECKOUT_SESSION_ID}',
        cancel_url                 = cancel_url,
        allow_promotion_codes      = True,
        billing_address_collection = 'auto',
        metadata = {
            'user_id':   str(user.id),
            'plan_id':   str(plan.id),
            'plan_tier': plan.tier,
            'interval':  interval,
        },
        subscription_data = {
            'metadata': {
                'user_id':   str(user.id),
                'plan_id':   str(plan.id),
                'plan_tier': plan.tier,
            }
        },
    )
    logger.info(f'[Stripe] Checkout session created: {session.id} for {user.email}')
    return session.url


# ── UPGRADE / DOWNGRADE — existing subscriber ──────────────────────────
def upgrade_subscription(stripe_subscription_id: str, new_plan) -> dict:
    """
    Modify an existing Stripe subscription to a new price IN PLACE.

    This is the correct way to handle plan changes. It:
    - Keeps ONE subscription (no duplicates)
    - Automatically calculates proration (credits unused days)
    - Charges only the difference immediately
    - No new checkout session needed — user is already a customer

    Args:
        stripe_subscription_id: the existing sub_xxx ID
        new_plan: your Plan model instance with stripe_price_id set

    Returns: updated Stripe Subscription object
    """
    if not new_plan.stripe_price_id:
        raise ValueError(f'Plan "{new_plan.name}" has no stripe_price_id.')

    # Get current subscription to find the subscription item ID
    # (Stripe requires the item ID to change the price on it)
    current_sub = stripe.Subscription.retrieve(stripe_subscription_id)

    # Stripe rejects .modify() on a subscription it already considers
    # canceled/expired — surface that as a specific error so the caller
    # can heal the local record and fall back to a fresh checkout instead
    # of a raw 500 from Stripe's own error message.
    if current_sub['status'] in ('canceled', 'incomplete_expired'):
        raise StaleSubscriptionError(current_sub['status'])

    item_id = current_sub['items']['data'][0]['id']

    updated_sub = stripe.Subscription.modify(
        stripe_subscription_id,
        items = [{
            'id':    item_id,
            'price': new_plan.stripe_price_id,
        }],
        proration_behavior = 'create_prorations',  # credit unused days immediately
        metadata = {
            'plan_id':   str(new_plan.id),
            'plan_tier': new_plan.tier,
        },
    )

    logger.info(
        f'[Stripe] Subscription upgraded: {stripe_subscription_id} '
        f'→ {new_plan.name} (proration applied)'
    )
    return updated_sub


# ── CREATE BILLING PORTAL SESSION ─────────────────────────────────────
def create_portal_session(user, return_url: str) -> str:
    stripe_customer_id = _get_or_create_customer(user)
    session = stripe.billing_portal.Session.create(
        customer   = stripe_customer_id,
        return_url = return_url,
    )
    logger.info(f'[Stripe] Portal session created for {user.email}')
    return session.url


# ── CANCEL ─────────────────────────────────────────────────────────────
def cancel_subscription(stripe_subscription_id: str, at_period_end: bool = True) -> dict:
    if at_period_end:
        sub = stripe.Subscription.modify(
            stripe_subscription_id,
            cancel_at_period_end=True,
        )
    else:
        sub = stripe.Subscription.cancel(stripe_subscription_id)
    logger.info(f'[Stripe] Subscription cancelled: {stripe_subscription_id} (at_period_end={at_period_end})')
    return sub


# ── RESUME ─────────────────────────────────────────────────────────────
def resume_subscription(stripe_subscription_id: str) -> dict:
    sub = stripe.Subscription.modify(
        stripe_subscription_id,
        cancel_at_period_end=False,
    )
    logger.info(f'[Stripe] Subscription resumed: {stripe_subscription_id}')
    return sub


# ── WEBHOOK VERIFICATION ───────────────────────────────────────────────
def construct_webhook_event(payload: bytes, sig_header: str):
    return stripe.Webhook.construct_event(
        payload    = payload,
        sig_header = sig_header,
        secret     = settings.STRIPE_WEBHOOK_SECRET,
    )


# ── CREATE STRIPE PRICES (one-time setup command) ─────────────────────
def create_stripe_prices(plan) -> dict:
    product = stripe.Product.create(
        name     = plan.name,
        metadata = {'tier': plan.tier, 'interval': plan.interval},
    )
    price = stripe.Price.create(
        product    = product.id,
        unit_amount= plan.price_cents,
        currency   = plan.currency.lower(),
        recurring  = {'interval': 'month' if plan.interval == 'monthly' else 'year'},
        metadata   = {'plan_id': str(plan.id)},
    )
    logger.info(f'[Stripe] Created price {price.id} for {plan.name}')
    return {'product_id': product.id, 'price_id': price.id}


# ── HELPERS ────────────────────────────────────────────────────────────
def _get_or_create_customer(user) -> str:
    try:
        sub = user.subscription
        if sub.stripe_customer_id:
            return sub.stripe_customer_id
    except Exception:
        pass

    customer = stripe.Customer.create(
        email    = user.email,
        name     = getattr(user, 'name', '') or user.email,
        metadata = {'user_id': str(user.id)},
    )

    try:
        sub = user.subscription
        sub.stripe_customer_id = customer.id
        sub.save(update_fields=['stripe_customer_id', 'updated_at'])
    except Exception:
        pass

    logger.info(f'[Stripe] Customer created: {customer.id} for {user.email}')
    return customer.id
