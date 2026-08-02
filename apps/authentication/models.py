import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from .managers import UserManager
import secrets
from django.conf import settings
class EmailVerification(models.Model):
    """
    One-time email verification token.
    Created on registration; deleted once the email is verified.
    """
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='email_verification',
    )
    token      = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = 'Email Verification'

    def __str__(self):
        return f'{self.user.email} — verified: {self.user.email_verified}'

    @classmethod
    def generate(cls, user) -> 'EmailVerification':
        token      = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timezone.timedelta(hours=24)
        obj, _     = cls.objects.update_or_create(
            user     = user,
            defaults = {'token': token, 'expires_at': expires_at},
        )
        return obj

    def is_valid(self) -> bool:
        return timezone.now() < self.expires_at


# ── PasswordResetToken model ──────────────────────────────────────────
class PasswordResetToken(models.Model):
    """
    Secure password reset token.
    One active token per user at a time (update_or_create).
    Expires in 1 hour.
    """
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='password_reset_token',
    )
    token      = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used       = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Password Reset Token'

    def __str__(self):
        return f'{self.user.email} — expires: {self.expires_at}'

    @classmethod
    def generate(cls, user) -> 'PasswordResetToken':
        token      = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timezone.timedelta(hours=1)
        obj, _     = cls.objects.update_or_create(
            user     = user,
            defaults = {'token': token, 'expires_at': expires_at, 'used': False},
        )
        return obj

    def is_valid(self) -> bool:
        return not self.used and timezone.now() < self.expires_at


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model using email as the unique identifier
    instead of username.
    """
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email      = models.EmailField(_('email'), unique=True)
    name = models.CharField(_('name'), max_length=150, blank=True)
    last_name  = models.CharField(_('last name'),  max_length=150, blank=True)
    avatar     = models.ImageField(upload_to='avatars/', blank=True, null=True)

    is_active  = models.BooleanField(default=True)
    is_staff   = models.BooleanField(default=False)
    is_verified= models.BooleanField(default=False)

    date_joined = models.DateTimeField(default=timezone.now)
    last_login  = models.DateTimeField(null=True, blank=True)
    email_verified = models.BooleanField(default=False, db_index=True)
    google_id      = models.CharField(max_length=128, blank=True, null=True, unique=True)
    microsoft_id   = models.CharField(max_length=128, blank=True, null=True, unique=True)
    avatar_url     = models.URLField(blank=True)
    objects = UserManager()

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['name']

    class Meta:
        verbose_name        = _('user')
        verbose_name_plural = _('users')
        ordering            = ['-date_joined']
        indexes             = [models.Index(fields=['email'])]

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f'{self.name} {self.last_name}'.strip()

    def get_short_name(self):
        return self.name
