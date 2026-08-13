# apps/subscriptions/management/commands/update_plans.py
# Usage: python manage.py update_plans
# Usage (dry run): python manage.py update_plans --dry-run
#
# Non-destructive: upserts each plan below by (tier, interval) instead of
# deleting all Plan rows first. Any Subscription sitting on a legacy tier
# that no longer exists in this list (e.g. no_ads, form_tools, form_ai,
# no_ads_form_ai, api_full) gets reassigned to the Free plan before that
# legacy Plan row is removed — this avoids the ProtectedError you get from
# Subscription.plan (on_delete=PROTECT) when a Plan is still referenced.

from django.core.management.base import BaseCommand
from django.db import transaction


NEW_PLANS = [
    # ── Free ──────────────────────────────────────────────────────
    {
        'name':                    'Free',
        'tier':                    'free',
        'interval':                'monthly',
        'price_cents':             0,
        'currency':                'CAD',
        'is_active':               True,
        'removes_ads':             False,
        'allows_ai_tools':         False,
        'allows_form_tools':       False,
        'allows_api_key':          False,
        'allows_chrome_extension': False,
        'ai_requests_per_day':     0,
    },

    # ── AI Tool — Monthly ────────────────────────────────────────
    {
        'name':                    'AI Tool',
        'tier':                    'ai_tools',
        'interval':                'monthly',
        'price_cents':             799,
        'currency':                'CAD',
        'is_active':               True,
        'removes_ads':             True,
        'allows_ai_tools':         True,
        'allows_form_tools':       False,
        'allows_api_key':          False,
        'allows_chrome_extension': False,
        'ai_requests_per_day':     20,
    },

    # ── AI Tool — Yearly ─────────────────────────────────────────
    {
        'name':                    'AI Tool — Yearly',
        'tier':                    'ai_tools',
        'interval':                'yearly',
        'price_cents':             7190,
        'currency':                'CAD',
        'is_active':               True,
        'removes_ads':             True,
        'allows_ai_tools':         True,
        'allows_form_tools':       False,
        'allows_api_key':          False,
        'allows_chrome_extension': False,
        'ai_requests_per_day':     20,
    },

    # ── AI + Chrome Extension — Monthly ───────────────────────────
    {
        'name':                    'AI + Chrome Extension',
        'tier':                    'ai_tools_plus',
        'interval':                'monthly',
        'price_cents':             1099,
        'currency':                'CAD',
        'is_active':               True,
        'removes_ads':             True,
        'allows_ai_tools':         True,
        'allows_form_tools':       False,
        'allows_api_key':          False,
        'allows_chrome_extension': True,
        'ai_requests_per_day':     30,
    },

    # ── AI + Chrome Extension — Yearly ────────────────────────────
    {
        'name':                    'AI + Chrome Extension — Yearly',
        'tier':                    'ai_tools_plus',
        'interval':                'yearly',
        'price_cents':             9890,
        'currency':                'CAD',
        'is_active':               True,
        'removes_ads':             True,
        'allows_ai_tools':         True,
        'allows_form_tools':       False,
        'allows_api_key':          False,
        'allows_chrome_extension': True,
        'ai_requests_per_day':     30,
    },

    # ── AI Premium — Monthly ──────────────────────────────────────
    {
        'name':                    'AI Premium',
        'tier':                    'ai_premium',
        'interval':                'monthly',
        'price_cents':             1399,
        'currency':                'CAD',
        'is_active':               True,
        'removes_ads':             True,
        'allows_ai_tools':         True,
        'allows_form_tools':       False,
        'allows_api_key':          False,
        'allows_chrome_extension': True,
        'ai_requests_per_day':     50,
    },

    # ── AI Premium — Yearly ───────────────────────────────────────
    {
        'name':                    'AI Premium — Yearly',
        'tier':                    'ai_premium',
        'interval':                'yearly',
        'price_cents':             12590,
        'currency':                'CAD',
        'is_active':               True,
        'removes_ads':             True,
        'allows_ai_tools':         True,
        'allows_form_tools':       False,
        'allows_api_key':          False,
        'allows_chrome_extension': True,
        'ai_requests_per_day':     50,
    },
]

NEW_TIER_CODES = {p['tier'] for p in NEW_PLANS}


class Command(BaseCommand):
    help = (
        'Upsert plans to the new pricing structure (Free, AI Tool, '
        'AI + Chrome Extension, AI Premium). Non-destructive — legacy '
        'tiers (no_ads, form_tools, form_ai, no_ads_form_ai, api_full) '
        'have any subscribers reassigned to Free before being removed.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without writing to the database',
        )
        parser.add_argument(
            '--orphan-tier',
            type=str,
            default='free',
            help=(
                "Tier code to reassign subscribers from dropped legacy "
                "tiers onto (must exist in NEW_PLANS). Default: free"
            ),
        )

    def handle(self, *args, **options):
        from apps.subscriptions.models import Plan, Subscription

        dry_run     = options['dry_run']
        orphan_tier = options['orphan_tier']

        if orphan_tier not in NEW_TIER_CODES:
            self.stdout.write(self.style.ERROR(
                f'--orphan-tier "{orphan_tier}" is not one of the new tiers: {sorted(NEW_TIER_CODES)}'
            ))
            return

        self.stdout.write('\n' + '─' * 50)
        self.stdout.write(self.style.HTTP_INFO('  Plan Migration — Free + 3-Tier Update (non-destructive)'))
        self.stdout.write('─' * 50)

        if dry_run:
            self.stdout.write(self.style.WARNING('\n  DRY RUN — no changes will be made\n'))

        # ── Show existing plans ───────────────────────────────────
        existing = Plan.objects.all().order_by('tier', 'interval')
        self.stdout.write(f'\nExisting plans ({existing.count()}):')
        for p in existing:
            self.stdout.write(
                f'  {p.tier:<20} {p.interval:<10} '
                f'CA${p.price_cents/100:>6.2f}  '
                f'stripe={"set" if p.stripe_price_id else "empty"}'
            )

        # ── Find subscriptions sitting on tiers that won't exist anymore ──
        orphan_subs = list(
            Subscription.objects.select_related('user', 'plan')
            .exclude(plan__tier__in=NEW_TIER_CODES)
        )
        if orphan_subs:
            self.stdout.write(f'\n{len(orphan_subs)} subscription(s) on legacy tiers will move to "{orphan_tier}":')
            for sub in orphan_subs:
                self.stdout.write(f'  {sub.user} — {sub.plan.name} ({sub.plan.tier}) → {orphan_tier}')

        if dry_run:
            self.stdout.write('\nPlans that would be created/updated:')
            for plan in NEW_PLANS:
                exists = Plan.objects.filter(tier=plan['tier'], interval=plan['interval']).exists()
                self.stdout.write(
                    f'  {"UPDATE" if exists else "CREATE":<7} {plan["name"]:<28} '
                    f'{plan["interval"]:<10} '
                    f'CA${plan["price_cents"]/100:>6.2f}  '
                    f'{plan["ai_requests_per_day"]} req/day  '
                    f'ext={"✓" if plan["allows_chrome_extension"] else "✗"}'
                )
            orphan_plans = Plan.objects.exclude(tier__in=NEW_TIER_CODES)
            if orphan_plans.exists():
                self.stdout.write('\nLegacy plans that would be removed once subscribers are reassigned:')
                for p in orphan_plans:
                    self.stdout.write(f'  REMOVE  {p.name} ({p.tier} / {p.interval})')
            self.stdout.write(self.style.WARNING('\nDry run complete — no changes made'))
            return

        # ── Run inside transaction ────────────────────────────────
        try:
            with transaction.atomic():
                # 1. Upsert each new plan by (tier, interval) — preserves id
                #    and stripe_price_id for anything that already matches,
                #    so existing subscriptions on e.g. 'ai_tools' just pick
                #    up the new price/limits in place.
                plan_by_key = {}
                created_count = 0
                updated_count = 0
                for data in NEW_PLANS:
                    tier, interval = data['tier'], data['interval']
                    defaults = {k: v for k, v in data.items() if k not in ('tier', 'interval')}
                    obj, created = Plan.objects.update_or_create(
                        tier=tier, interval=interval, defaults=defaults,
                    )
                    plan_by_key[(tier, interval)] = obj
                    created_count += created
                    updated_count += not created
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  {"CREATED" if created else "UPDATED":<8} {data["name"]:<28} '
                            f'{data["interval"]:<10} CA${data["price_cents"]/100:>6.2f}  '
                            f'{data["ai_requests_per_day"]} req/day  '
                            f'ext={"✓" if data["allows_chrome_extension"] else "✗"}'
                        )
                    )

                # 2. Reassign subscriptions on legacy tiers to the orphan target
                target_plan = plan_by_key.get((orphan_tier, 'monthly'))
                reassigned = 0
                if orphan_subs and target_plan:
                    for sub in Subscription.objects.exclude(plan__tier__in=NEW_TIER_CODES):
                        old_name = sub.plan.name
                        sub.plan = target_plan
                        sub.save(update_fields=['plan', 'updated_at'])
                        reassigned += 1
                        self.stdout.write(f'  MOVED   {sub.user} — {old_name} → {target_plan.name}')

                # 3. Now safe to remove legacy plan rows (no more references)
                removed, _ = Plan.objects.exclude(tier__in=NEW_TIER_CODES).delete()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\nMigration failed — rolled back: {e}'))
            raise

        # ── Summary ───────────────────────────────────────────────
        self.stdout.write('\n' + '─' * 50)
        self.stdout.write(self.style.SUCCESS(
            f'  Done — {created_count} created, {updated_count} updated, '
            f'{reassigned} subscription(s) reassigned, {removed} legacy plan row(s) removed'
        ))
        self.stdout.write('─' * 50)
        self.stdout.write('\nFinal plan table:')
        self.stdout.write(f'  {"Name":<28} {"Interval":<10} {"Price":>8}  {"Req/day":>8}  {"Ext":>5}  {"Stripe":>10}')
        self.stdout.write('  ' + '-' * 75)
        for p in Plan.objects.all().order_by('price_cents', 'interval'):
            self.stdout.write(
                f'  {p.name:<28} {p.interval:<10} '
                f'CA${p.price_cents/100:>6.2f}  '
                f'{p.ai_requests_per_day:>8}  '
                f'{"✓" if p.allows_chrome_extension else "✗":>5}  '
                f'{"set" if p.stripe_price_id else "empty":>10}'
            )

        self.stdout.write(
            '\n' + self.style.WARNING(
                'Next step: run setup_stripe_prices to create Stripe products/prices '
                'for any plan still showing stripe=empty'
            )
        )
