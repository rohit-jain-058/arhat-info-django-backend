"""
ONE-TIME data migration — only needed if you already have live Plan/
Subscription rows using the OLD tier codes: 'free', 'no_ads', 'ai_tools',
'full'. Maps them onto the new codes so existing subscribers keep working.

Mapping:
  old 'full'  ->  new 'api_full'   (same meaning: everything + API key)
  old 'free', 'no_ads', 'ai_tools' -> unchanged, codes are identical

Run as a Django management command:
  python manage.py migrate_old_tiers
"""
from django.core.management.base import BaseCommand
from apps.subscriptions.models import Plan, Subscription


class Command(BaseCommand):
    help = 'Remap old tier code "full" to new "api_full" across Plan and Subscription rows'

    def handle(self, *args, **options):
        old_plans = Plan.objects.filter(tier='full')
        count = old_plans.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS('No plans with old tier "full" found — nothing to migrate.'))
            return

        self.stdout.write(f'Found {count} Plan rows with tier="full". Remapping to "api_full"...')

        for plan in old_plans:
            plan.tier = 'api_full'
            plan.allows_form_tools = True   # api_full includes form tools per the new matrix
            plan.save(update_fields=['tier', 'allows_form_tools'])
            self.stdout.write(f'  Plan "{plan.name}" -> tier=api_full')

        # Subscriptions reference Plan by FK, not by tier string directly,
        # so no Subscription rows need updating — they'll pick up the new
        # tier automatically via sub.plan.tier.

        affected_subs = Subscription.objects.filter(plan__tier='api_full').count()
        self.stdout.write(self.style.SUCCESS(
            f'\nDone. {count} plans remapped. {affected_subs} active subscriptions now resolve to tier=api_full.'
        ))
