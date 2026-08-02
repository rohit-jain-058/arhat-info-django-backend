import uuid
from django.db import models


class ChatUser(models.Model):
    """Anonymous or registered user identified by session_id."""
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_id = models.CharField(max_length=255, unique=True, db_index=True)
    email      = models.EmailField(blank=True, null=True)
    name       = models.CharField(max_length=255, blank=True, null=True)
    company    = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Chat User'

    def __str__(self):
        return self.session_id


class Conversation(models.Model):
    """One conversation session."""
    STATUS_CHOICES = [
        ('active',    'Active'),
        ('completed', 'Completed'),
        ('escalated', 'Escalated'),
    ]
    PHASE_CHOICES = [
        ('discovery',    'Discovery'),
        ('requirements', 'Requirements'),
        ('architecture', 'Architecture'),
        ('proposal',     'Proposal'),
    ]

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.ForeignKey(ChatUser, on_delete=models.CASCADE, related_name='conversations')
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    phase      = models.CharField(max_length=20, choices=PHASE_CHOICES, default='discovery')
    intent     = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Conv {self.id} [{self.phase}]"


class Message(models.Model):
    """Individual message inside a conversation."""
    ROLE_CHOICES = [
        ('user',      'User'),
        ('assistant', 'Assistant'),
        ('system',    'System'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation    = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role            = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content         = models.TextField()
    structured_data = models.JSONField(null=True, blank=True)  # extracted requirements etc.
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:60]}"


class Project(models.Model):
    """Project extracted from a conversation."""
    COMPLEXITY_CHOICES = [
        ('small',   'Small'),
        ('medium',  'Medium'),
        ('large',   'Large'),
        ('complex', 'Complex'),
    ]
    STATUS_CHOICES = [
        ('draft',    'Draft'),
        ('analyzed', 'Analyzed'),
        ('proposed', 'Proposed'),
        ('approved', 'Approved'),
    ]

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation   = models.OneToOneField(Conversation, on_delete=models.CASCADE, related_name='project')
    name           = models.CharField(max_length=255, blank=True, null=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    project_type   = models.CharField(max_length=100, blank=True, null=True)
    features       = models.JSONField(default=list)
    modules        = models.JSONField(default=list)
    tech_stack     = models.JSONField(default=dict)
    complexity     = models.CharField(max_length=20, choices=COMPLEXITY_CHOICES, blank=True, null=True)
    timeline_weeks = models.IntegerField(null=True, blank=True)
    estimated_cost = models.JSONField(default=dict)    # {min, max, currency}
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name or str(self.id)


class ProjectAnalysis(models.Model):
    """Full structured analysis of a project."""
    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project          = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='analysis')
    feasibility      = models.CharField(max_length=20, blank=True, null=True)  # high/medium/low
    architecture     = models.JSONField(default=dict)
    risks            = models.JSONField(default=list)
    missing_info     = models.JSONField(default=list)
    structured_reqs  = models.JSONField(default=dict)
    proposal_text    = models.TextField(blank=True, null=True)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Analysis for {self.project}"
