from celery import shared_task
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

@shared_task
def expire_trials():
    """Run daily via Celery Beat to expire ended trials."""
    from apps.subscriptions.models import Subscription, Plan

    expired = Subscription.objects.filter(
        is_trial    = True,
        status      = 'trialing',
        trial_ends_at__lte = timezone.now(),
    ).select_related('user', 'plan')

    free_plan = Plan.objects.filter(tier='free', interval='monthly').first()
    if not free_plan:
        logger.error('[Trial] Free plan not found — cannot expire trials')
        return

    count = 0
    for sub in expired:
        sub.plan     = free_plan
        sub.status   = 'active'
        sub.is_trial = False
        sub.save(update_fields=['plan', 'status', 'is_trial', 'updated_at'])
        logger.info(f'[Trial] Expired: {sub.user.email}')
        count += 1

    logger.info(f'[Trial] Expired {count} trials')
    return count