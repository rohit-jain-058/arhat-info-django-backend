"""
Subscription models.

Tiers:
  free       — all tools, ads shown
  no_ads     — all tools, no ads
  ai_tools   — all tools + AI tools, no ads
  full       — everything + API key access

Plugs into your existing authentication.User model.
"""
import uuid
import secrets
import hashlib
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


# ── PLAN DEFINITION ───────────────────────────────────────────────────
class Plan(models.Model):
    """
    Defines a subscription plan.
    Create these once via admin or fixture.
    """
    TIER_CHOICES = [
        ('free',            'Free'),
        ('no_ads',          'No Ads'),
        ('ai_tools',        'AI Tools'),
        ('form_tools',      'Form Tools'),                      # reserved, future product
        ('form_ai',         'Form Tools + AI Tools'),
        ('no_ads_form_ai',  'No Ads + Form Tools + AI Tools'),
        ('api_full',        'API Access (Full Bundle)'),
    ]
    INTERVAL_CHOICES = [
        ('monthly', 'Monthly'),
        ('yearly',  'Yearly'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name            = models.CharField(max_length=100)          # "Full Bundle — Monthly"
    tier            = models.CharField(max_length=20, choices=TIER_CHOICES, db_index=True)
    interval        = models.CharField(max_length=10, choices=INTERVAL_CHOICES, default='monthly')
    price_cents     = models.PositiveIntegerField(default=0)    # e.g. 999 = $9.99
    currency        = models.CharField(max_length=3, default='USD')
    is_active       = models.BooleanField(default=True)

    # Payment provider IDs — populate when you add Stripe/PayPal
    stripe_price_id = models.CharField(max_length=100, blank=True)
    paypal_plan_id  = models.CharField(max_length=100, blank=True)

    # What this plan unlocks
    removes_ads     = models.BooleanField(default=False)
    allows_ai_tools = models.BooleanField(default=False)
    allows_form_tools = models.BooleanField(default=False)
    allows_api_key  = models.BooleanField(default=False)
    ai_requests_per_day = models.PositiveIntegerField(default=0)  # 0 = unlimited
    allows_chrome_extension = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering        = ['price_cents']
        unique_together = ('tier', 'interval')

    def __str__(self):
        price = f'${self.price_cents/100:.2f}/{self.interval}' if self.price_cents else 'Free'
        return f'{self.name} ({price})'

    @property
    def price_display(self):
        if self.price_cents == 0:
            return 'Free'
        return f'${self.price_cents / 100:.2f}'


# ── USER SUBSCRIPTION ─────────────────────────────────────────────────
class Subscription(models.Model):
    """
    One active subscription per user.
    Update status when payment succeeds/fails/cancels.
    """
    STATUS_CHOICES = [
        ('active',    'Active'),
        ('cancelled', 'Cancelled'),
        ('expired',   'Expired'),
        ('past_due',  'Past Due'),
        ('trialing',  'Trialing'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user            = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription',
    )
    plan            = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='subscriptions')
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)

    # Dates
    started_at      = models.DateTimeField(default=timezone.now)
    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end   = models.DateTimeField(null=True, blank=True)
    cancelled_at    = models.DateTimeField(null=True, blank=True)
    trial_end       = models.DateTimeField(null=True, blank=True)

    # Payment provider refs — populate when you add Stripe/PayPal
    stripe_subscription_id  = models.CharField(max_length=100, blank=True, db_index=True)
    stripe_customer_id      = models.CharField(max_length=100, blank=True, db_index=True)
    paypal_subscription_id  = models.CharField(max_length=100, blank=True, db_index=True)

    # Metadata
    cancel_at_period_end    = models.BooleanField(default=False)
    created_at              = models.DateTimeField(auto_now_add=True)
    updated_at              = models.DateTimeField(auto_now=True)

    authnet_subscription_id     = models.CharField(max_length=50, blank=True, db_index=True)
    authnet_customer_profile_id = models.CharField(max_length=50, blank=True)
    is_trial         = models.BooleanField(default=False, db_index=True)
    trial_started_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} — {self.plan.name} ({self.status})'

    # ── Convenience props ──────────────────────────────────────────

    @property
    def is_trial_active(self) -> bool:
        if not self.is_trial or not self.trial_ends_at:
            return False
        return timezone.now() < self.trial_ends_at

    @property
    def trial_days_remaining(self) -> int:
        if not self.is_trial_active:
            return 0
        delta = self.trial_ends_at - timezone.now()
        return max(0, delta.days)
    @property
    def is_active(self) -> bool:
        return self.status in ('active', 'trialing')

    @property
    def is_free(self) -> bool:
        return self.plan.tier == 'free'

    @property
    def removes_ads(self) -> bool:
        return self.is_active and self.plan.removes_ads

    @property
    def allows_ai_tools(self) -> bool:
        return self.is_active and self.plan.allows_ai_tools

    @property
    def allows_api_key(self) -> bool:
        return self.is_active and self.plan.allows_api_key
    @property
    def allows_form_tools(self) -> bool:          # ← NEW — reserved, returns flag only
        return self.is_active and self.plan.allows_form_tools
    @property
    def tier(self) -> str:
        return self.plan.tier if self.is_active else 'free'

    def days_remaining(self) -> int | None:
        if self.current_period_end:
            delta = self.current_period_end - timezone.now()
            return max(0, delta.days)
        return None

    def cancel(self, at_period_end: bool = True):
        """Cancel subscription — immediately or at end of billing period."""
        if at_period_end:
            self.cancel_at_period_end = True
        else:
            self.status       = 'cancelled'
            self.cancelled_at = timezone.now()
        self.save()


# ── PAYMENT HISTORY ────────────────────────────────────────────────────
class Payment(models.Model):
    """
    Records every payment attempt.
    Create one on each webhook event from your payment provider.
    """
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('succeeded', 'Succeeded'),
        ('failed',    'Failed'),
        ('refunded',  'Refunded'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user            = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    subscription    = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    plan            = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, blank=True)

    amount_cents    = models.PositiveIntegerField()
    currency        = models.CharField(max_length=3, default='USD')
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    description     = models.CharField(max_length=255, blank=True)

    # Provider refs
    stripe_payment_intent_id = models.CharField(max_length=100, blank=True, db_index=True)
    stripe_invoice_id        = models.CharField(max_length=100, blank=True)
    paypal_order_id          = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    authnet_subscription_id = models.CharField(max_length=50, blank=True, db_index=True)
    authnet_transaction_id  = models.CharField(max_length=50, blank=True)
    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} — ${self.amount_cents/100:.2f} ({self.status})'

    @property
    def amount_display(self):
        return f'${self.amount_cents / 100:.2f} {self.currency}'


# ── API KEY ───────────────────────────────────────────────────────────
class APIKey(models.Model):
    """
    API key for Full Bundle subscribers.
    Key is hashed in the DB — never stored in plain text.
    """
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='api_keys')
    name        = models.CharField(max_length=100, default='Default Key')
    key_prefix  = models.CharField(max_length=8, db_index=True)     # first 8 chars for display
    key_hash    = models.CharField(max_length=64, unique=True)       # SHA-256 hash
    is_active   = models.BooleanField(default=True, db_index=True)
    last_used   = models.DateTimeField(null=True, blank=True)
    requests_today    = models.PositiveIntegerField(default=0)
    requests_total    = models.PositiveIntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} — {self.key_prefix}... ({self.name})'

    @classmethod
    def generate(cls, user, name='Default Key') -> tuple:
        """
        Generate a new API key.
        Returns (APIKey instance, plain_text_key).
        The plain text key is shown ONCE and never stored.
        """
        raw_key    = f'arhat_{secrets.token_urlsafe(32)}'
        key_hash   = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:8]
        api_key    = cls.objects.create(
            user       = user,
            name       = name,
            key_prefix = key_prefix,
            key_hash   = key_hash,
        )
        return api_key, raw_key

    @classmethod
    def verify(cls, raw_key: str):
        """Verify a raw key. Returns APIKey or None."""
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        try:
            return cls.objects.select_related('user').get(key_hash=key_hash, is_active=True)
        except cls.DoesNotExist:
            return None

    def record_use(self):
        self.last_used = timezone.now()
        self.requests_today += 1
        self.requests_total += 1
        self.save(update_fields=['last_used', 'requests_today', 'requests_total'])


# ── AI USAGE TRACKER ──────────────────────────────────────────────────
class AIUsageLog(models.Model):
    """
    Track daily AI tool usage per user for rate limiting.
    Reset requests_today via Celery beat task daily.
    """
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user            = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_usage')
    date            = models.DateField(db_index=True)
    tool            = models.CharField(max_length=30)
    requests_count  = models.PositiveIntegerField(default=0)
    tokens_used     = models.PositiveIntegerField(default=0)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'date', 'tool')
        ordering        = ['-date']

    def __str__(self):
        return f'{self.user} — {self.tool} on {self.date} ({self.requests_count} reqs)'
