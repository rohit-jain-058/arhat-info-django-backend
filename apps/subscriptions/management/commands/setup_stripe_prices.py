"""
Management command to create Stripe Products and Prices for all plans.
Run this ONCE after setting up your Stripe account.

Usage:
  python manage.py setup_stripe_prices
  python manage.py setup_stripe_prices --live   # use live mode keys
"""
from django.core.management.base import BaseCommand
from apps.subscriptions.models import Plan
from apps.subscriptions.stripe_service import create_stripe_prices


class Command(BaseCommand):
    help = 'Create Stripe Products and Prices for all plans'

    def add_arguments(self, parser):
        parser.add_argument('--live', action='store_true', help='Use live Stripe keys')
        parser.add_argument('--tier', type=str, help='Only create for this tier (e.g. ai_tools)')

    def handle(self, *args, **options):
        plans = Plan.objects.filter(is_active=True, price_cents__gt=0)

        if options.get('tier'):
            plans = plans.filter(tier=options['tier'])

        if not plans.exists():
            self.stdout.write(self.style.WARNING('No paid plans found. Run loaddata first.'))
            return

        self.stdout.write(f'\nCreating Stripe prices for {plans.count()} plans...\n')

        for plan in plans:
            if plan.stripe_price_id:
                self.stdout.write(
                    self.style.WARNING(f'  SKIP  {plan.name} — already has price_id: {plan.stripe_price_id}')
                )
                continue

            try:
                result = create_stripe_prices(plan)
                plan.stripe_price_id = result['price_id']
                plan.save(update_fields=['stripe_price_id'])
                self.stdout.write(
                    self.style.SUCCESS(f'  OK    {plan.name} → {result["price_id"]}')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'  FAIL  {plan.name} → {e}')
                )

        self.stdout.write('\nDone. Stripe price IDs saved to database.\n')
        self.stdout.write('Next step: set your webhook endpoint in the Stripe Dashboard.\n')
        self.stdout.write('  URL: https://arhat.info/api/subscriptions/webhook/\n')
        self.stdout.write('  Events: checkout.session.completed, customer.subscription.updated,\n')
        self.stdout.write('          customer.subscription.deleted, invoice.payment_succeeded,\n')
        self.stdout.write('          invoice.payment_failed\n')
