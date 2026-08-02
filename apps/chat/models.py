import uuid
from django.db import models


class ChatUser(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_id = models.CharField(max_length=255, unique=True, db_index=True)
    email      = models.EmailField(blank=True, null=True)
    name       = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.session_id


class Conversation(models.Model):
    PHASE_CHOICES = [
        ('requirements', 'Requirements'),
        ('architecture', 'Architecture'),
        ('feasibility',  'Feasibility'),
        ('proposal',     'Proposal'),
        ('complete',     'Complete'),
        ('escalated',    'Escalated'),
    ]

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user             = models.ForeignKey(ChatUser, on_delete=models.CASCADE, related_name='conversations')
    phase            = models.CharField(max_length=20, choices=PHASE_CHOICES, default='requirements')
    pipeline_context = models.JSONField(default=dict)   # stores full PipelineContext
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self): return f"Conv {self.id} [{self.phase}]"


class Message(models.Model):
    ROLE_CHOICES = [
        ('user',      'User'),
        ('assistant', 'Assistant'),
        ('system',    'System'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation    = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role            = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content         = models.TextField()
    structured_data = models.JSONField(null=True, blank=True)
    agent_name      = models.CharField(max_length=50, blank=True, null=True)  # which agent produced this
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self): return f"{self.role}: {self.content[:60]}"
