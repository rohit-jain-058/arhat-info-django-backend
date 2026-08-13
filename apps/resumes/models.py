# apps/resumes/models.py
from django.db import models
from django.conf import settings


class Resume(models.Model):
    user             = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='resumes')
    name             = models.CharField(max_length=100)
    file             = models.FileField(upload_to='resumes/%Y/%m/', null=True, blank=True)
    raw_text         = models.TextField(blank=True)

    # AI extracted
    skills           = models.JSONField(default=list)
    experience       = models.JSONField(default=list)
    achievements     = models.JSONField(default=list)
    years_experience = models.FloatField(null=True, blank=True)
    career_goal      = models.TextField(blank=True)
    summary          = models.TextField(blank=True)

    ai_processed     = models.BooleanField(default=False)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} — {self.name}"
