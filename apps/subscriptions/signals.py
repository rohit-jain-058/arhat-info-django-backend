"""
Signals — auto-create a free subscription when a new user registers.
This ensures every user always has a subscription record.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_free_subscription(sender, instance, created, **kwargs):
    """Give every new user a free subscription automatically."""
    if not created:
        return
    try:
        from .models import Plan, Subscription
        free_plan, _ = Plan.objects.get_or_create(
            tier     = 'free',
            interval = 'monthly',
            defaults = {
                'name':                'Free',
                'price_cents':         0,
                'removes_ads':         False,
                'allows_ai_tools':     False,
                'allows_api_key':      False,
                'ai_requests_per_day': 0,
            }
        )
        Subscription.objects.get_or_create(
            user     = instance,
            defaults = {'plan': free_plan, 'status': 'active'},
        )
        logger.info(f'[Subscription] Free plan created for {instance}')
    except Exception as e:
        logger.error(f'[Subscription] Failed to create free plan for {instance}: {e}')
