import uuid
from django.db import models


class ChatSession(models.Model):
    """One anonymous chat session identified by session_id."""
    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_id       = models.CharField(max_length=255, unique=True, db_index=True)
    phase            = models.CharField(max_length=30, default="requirements")
    pipeline_context = models.JSONField(default=dict)  # full PipelineContext stored here
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Session {self.session_id[:12]} [{self.phase}]"


class ChatMessage(models.Model):
    """Individual message in a session."""
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant')]

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session    = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role       = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content    = models.TextField()
    agent      = models.CharField(max_length=50, blank=True, null=True)  # which agent produced it
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:60]}"
