"""
Models for all tool categories:
- Network tools (IP, DNS, WHOIS, etc.)
- Developer tools (JSON, Base64, Hash, JWT, etc.)
- AI tools (prompt gen, email gen, SQL gen, etc.)
- Text tools (word count, case convert, etc.)
- Finance tools (FIRE, mortgage, compound interest, etc.)
- Business tools (invoice, GST, payroll, etc.)
- File tools (image convert, PDF merge, etc.)

Each model logs usage for analytics, rate limiting, and caching.
"""
import uuid
from django.db import models
from django.conf import settings
# ── SHARED BASE ────────────────────────────────────────────────────────
class ToolUsageBase(models.Model):
    """Abstract base for all tool usage logs."""
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ip_address  = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    user_agent  = models.CharField(max_length=512, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)
    duration_ms = models.IntegerField(null=True, blank=True)   # how long it took
    success     = models.BooleanField(default=True)
    error       = models.TextField(blank=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']


# ── NETWORK TOOLS ──────────────────────────────────────────────────────
class IPLookupLog(ToolUsageBase):
    """Logs for IP lookup / My IP tool."""
    TOOL_CHOICES = [
        ('myip',       'My IP'),
        ('iplookup',   'IP Lookup'),
        ('hostname',   'Hostname Lookup'),
        ('whois',      'WHOIS'),
        ('blacklist',  'Blacklist Check'),
        ('portscan',   'Port Scanner'),
        ('traceroute', 'Traceroute'),
        ('dns',        'DNS Lookup'),
        ('useragent',  'User Agent'),
        ('speedtest',  'Speed Test'),
        ('mxrecord',   'MX Record'),
        ('spf',        'SPF Record'),
        ('ssl',        'SSL Checker'),
        ('headers',    'HTTP Headers'),
    ]
    tool          = models.CharField(max_length=20, choices=TOOL_CHOICES, db_index=True)
    query         = models.CharField(max_length=255, blank=True)   # the IP/domain queried
    result_cached = models.BooleanField(default=False)

    class Meta(ToolUsageBase.Meta):
        verbose_name     = 'IP Tool Log'
        verbose_name_plural = 'IP Tool Logs'

    def __str__(self):
        return f'{self.tool}: {self.query}'


class IPCache(models.Model):
    """Cache IP geolocation results to avoid hitting rate limits."""
    ip          = models.GenericIPAddressField(unique=True, db_index=True)
    data        = models.JSONField()
    cached_at   = models.DateTimeField(auto_now=True)
    hits        = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'IP Cache Entry'

    def __str__(self):
        return f'{self.ip} (hits: {self.hits})'


# ── DEVELOPER TOOLS ────────────────────────────────────────────────────
class DevToolLog(ToolUsageBase):
    """Logs for developer tools — JSON, Base64, JWT, UUID, Hash, etc."""
    TOOL_CHOICES = [
        ('json_format',   'JSON Formatter'),
        ('json_validate', 'JSON Validator'),
        ('json_minify',   'JSON Minifier'),
        ('text_diff',     'Text Diff'),
        ('yaml_format',   'YAML Formatter'),
        ('base64_encode', 'Base64 Encode'),
        ('base64_decode', 'Base64 Decode'),
        ('url_encode',    'URL Encode'),
        ('url_decode',    'URL Decode'),
        ('jwt_decode',    'JWT Decode'),
        ('uuid_generate', 'UUID Generate'),
        ('hash_sha256',   'SHA-256 Hash'),
        ('hash_sha512',   'SHA-512 Hash'),
        ('hmac_generate', 'HMAC Generate'),
        ('regex_test',    'Regex Test'),
    ]
    tool         = models.CharField(max_length=20, choices=TOOL_CHOICES, db_index=True)
    input_size   = models.IntegerField(null=True, blank=True)   # bytes
    output_size  = models.IntegerField(null=True, blank=True)

    class Meta(ToolUsageBase.Meta):
        verbose_name     = 'Dev Tool Log'
        verbose_name_plural = 'Dev Tool Logs'

    def __str__(self):
        return f'{self.tool} ({self.input_size or 0}b)'


# ── AI TOOLS ───────────────────────────────────────────────────────────
class AIToolRequest(ToolUsageBase):
    """Logs for all AI-powered tool requests (GPT-4o)."""
    TOOL_CHOICES = [
        ('prompt_gen',   'Prompt Generator'),
        ('email_gen',    'Email Generator'),
        ('linkedin_post','LinkedIn Post'),
        ('cover_letter', 'Cover Letter'),
        ('resume_summary','Resume Summary'),
        ('sql_gen',      'SQL Generator'),
        ('regex_gen',    'Regex Generator'),
        ('api_docs',     'API Docs Generator'),
        ('meeting_notes','Meeting Notes'),
        ('upwork_proposal', 'Upwork Proposal Generator'),
        ('recruiter_reply', 'LinkedIn Recruiter Reply'),
        ('job_matcher',     'Job Description Matcher'),
        ('cron_gen',        'Cron Generator'),
        ('api_tester',      'API Tester')
    ]
    tool             = models.CharField(max_length=20, choices=TOOL_CHOICES, db_index=True)
    prompt_tokens    = models.IntegerField(null=True, blank=True)
    completion_tokens= models.IntegerField(null=True, blank=True)
    total_tokens     = models.IntegerField(null=True, blank=True)
    model_used       = models.CharField(max_length=50, default='gpt-4o')
    # Store the actual inputs and output for debugging (optional)
    input_data       = models.JSONField(null=True, blank=True)
    output_preview   = models.TextField(blank=True)   # first 500 chars
    user = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL, null=True, blank=True,
    related_name='ai_requests')

    class Meta(ToolUsageBase.Meta):
        verbose_name     = 'AI Tool Request'
        verbose_name_plural = 'AI Tool Requests'

    def __str__(self):
        return f'{self.tool} — {self.total_tokens or 0} tokens'


# ── TEXT TOOLS ─────────────────────────────────────────────────────────
class TextToolLog(ToolUsageBase):
    """Logs for text tools — word count, case convert, etc."""
    TOOL_CHOICES = [
        ('word_count',  'Word Counter'),
        ('case_convert','Case Converter'),
        ('dedupe',      'Remove Duplicates'),
        ('lorem_ipsum', 'Lorem Ipsum'),
        ('markdown',    'Markdown Preview'),
        ('html_encode', 'HTML Encoder'),
        ('html_decode', 'HTML Decoder'),
        ('html_to_md',  'HTML to Markdown'),
    ]
    tool       = models.CharField(max_length=20, choices=TOOL_CHOICES, db_index=True)
    input_size = models.IntegerField(null=True, blank=True)

    class Meta(ToolUsageBase.Meta):
        verbose_name     = 'Text Tool Log'
        verbose_name_plural = 'Text Tool Logs'


# ── FINANCE TOOLS ──────────────────────────────────────────────────────
class FinanceCalculation(ToolUsageBase):
    """Logs for all finance calculator usage."""
    TOOL_CHOICES = [
        # FIRE
        ('fire',         'FIRE Calculator'),
        ('coast_fire',   'Coast FIRE'),
        ('fat_fire',     'Fat FIRE'),
        ('barista_fire', 'Barista FIRE'),
        ('windfall',     'Windfall Impact'),
        ('purchase',     'Purchase Impact'),
        # Investing
        ('compound',     'Compound Interest'),
        ('loan',         'Loan Payment'),
        ('mortgage',     '15v30 Mortgage'),
        ('portfolio',    'Portfolio Rebalance'),
        ('rental',       'Rental Property'),
        ('house_hack',   'House Hacking'),
        ('cap_rate',     'Cap Rate'),
        ('cash_on_cash', 'Cash-on-Cash'),
        # Saving
        ('savings_rate', 'Savings Rate'),
        ('emergency',    'Emergency Fund'),
        ('hsa',          'HSA Growth'),
        ('inflation',    'Inflation Calc'),
        ('upwork_fee',   'Upwork Fee'),
        ('ev_savings',   'EV Savings'),
        # Canada
        ('sip',          'SIP Calculator'),
        ('retirement',   'Retirement Calc'),
        ('rrsp',         'RRSP Contribution'),
        ('tfsa',         'TFSA Growth'),
        ('dividend',     'Dividend Yield'),
        ('currency',     'Currency Converter'),
    ]
    tool     = models.CharField(max_length=20, choices=TOOL_CHOICES, db_index=True)
    currency = models.CharField(max_length=3, default='USD')
    # Store input params for analytics
    inputs   = models.JSONField(null=True, blank=True)
    result   = models.JSONField(null=True, blank=True)

    class Meta(ToolUsageBase.Meta):
        verbose_name     = 'Finance Calculation'
        verbose_name_plural = 'Finance Calculations'

    def __str__(self):
        return f'{self.tool} ({self.currency})'


# ── BUSINESS TOOLS ─────────────────────────────────────────────────────
class BusinessToolLog(ToolUsageBase):
    """Logs for business tools — invoice, GST, payroll, etc."""
    TOOL_CHOICES = [
        ('invoice',  'Invoice Generator'),
        ('gst',      'GST/VAT Calculator'),
        ('margin',   'Profit Margin'),
        ('markup',   'Markup Calculator'),
        ('rate',     'Freelance Rate'),
        ('payroll',  'Payroll Calculator'),
    ]
    tool     = models.CharField(max_length=20, choices=TOOL_CHOICES, db_index=True)
    currency = models.CharField(max_length=3, default='USD')

    class Meta(ToolUsageBase.Meta):
        verbose_name     = 'Business Tool Log'
        verbose_name_plural = 'Business Tool Logs'


# ── FILE TOOLS ─────────────────────────────────────────────────────────
class FileToolLog(ToolUsageBase):
    """Logs for file tools — image convert, PDF merge, PDF compress."""
    TOOL_CHOICES = [
        ('image_convert', 'Image Converter'),
        ('pdf_merge',     'PDF Merger'),
        ('pdf_minify',    'PDF Compressor'),
    ]
    tool         = models.CharField(max_length=20, choices=TOOL_CHOICES, db_index=True)
    file_count   = models.IntegerField(default=1)
    input_size   = models.IntegerField(null=True, blank=True)   # bytes
    output_size  = models.IntegerField(null=True, blank=True)
    savings_pct  = models.FloatField(null=True, blank=True)     # compression savings

    class Meta(ToolUsageBase.Meta):
        verbose_name     = 'File Tool Log'
        verbose_name_plural = 'File Tool Logs'

    def __str__(self):
        return f'{self.tool}: {self.file_count} file(s)'


# ── ANALYTICS ─────────────────────────────────────────────────────────
class ToolAnalytics(models.Model):
    """Daily aggregated analytics per tool."""
    date       = models.DateField(db_index=True)
    tool_name  = models.CharField(max_length=50, db_index=True)
    category   = models.CharField(max_length=20)   # network, dev, ai, text, finance, business, file
    total_uses = models.IntegerField(default=0)
    unique_ips = models.IntegerField(default=0)
    errors     = models.IntegerField(default=0)

    class Meta:
        unique_together = ('date', 'tool_name')
        ordering        = ['-date', '-total_uses']
        verbose_name    = 'Tool Analytics'

    def __str__(self):
        return f'{self.date} | {self.tool_name}: {self.total_uses} uses'
