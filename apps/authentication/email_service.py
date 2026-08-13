"""
Email service for authentication emails.
Uses your existing EMAIL_HOST / EMAIL_HOST_USER settings from base.py.
"""
import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)

FRONTEND_URL = getattr(settings, 'FRONTEND_URL', 'https://arhat.info')


def send_verification_email(user, token: str):
    """Send email verification link to new user."""
    verify_url = f'{FRONTEND_URL}/verify-email?token={token}'

    subject = 'Verify your Tylented email address'

    text_body = f"""Hi{' ' + user.name if getattr(user, 'name', '') else ''},

Thanks for signing up for Tylented!

Please verify your email address by clicking the link below:
{verify_url}

This link expires in 24 hours.

If you didn't create an account, you can safely ignore this email.

— The Tylented team
"""

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8"/>
<style>
  body {{ font-family: 'DM Sans', Arial, sans-serif; background: #f4f6fa; margin: 0; padding: 20px; }}
  .card {{ max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,.08); }}
  .header {{ background: #07080c; padding: 28px 32px; text-align: center; }}
  .logo {{ font-size: 22px; font-weight: 800; color: #ffffff; letter-spacing: -.02em; }}
  .logo span {{ color: #00c8f0; }}
  .body {{ padding: 32px; color: #333; line-height: 1.65; }}
  h2 {{ font-size: 18px; color: #07080c; margin: 0 0 12px; }}
  p {{ margin: 0 0 16px; font-size: 14px; color: #555; }}
  .btn {{ display: inline-block; padding: 13px 28px; background: linear-gradient(135deg, #00c8f0, #4d8fff);
          color: #07080c !important; font-weight: 700; text-decoration: none; border-radius: 8px;
          font-size: 14px; margin: 8px 0 20px; }}
  .link {{ word-break: break-all; font-size: 12px; color: #888; }}
  .footer {{ padding: 20px 32px; background: #f8f9fc; font-size: 11px; color: #aaa; text-align: center; }}
</style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="logo">Tylented</div>
    </div>
    <div class="body">
      <h2>Verify your email address</h2>
      <p>Hi{' ' + user.name if getattr(user, 'name', '') else ''},</p>
      <p>Thanks for signing up! Click the button below to verify your email and activate your account.</p>
      <a href="{verify_url}" class="btn">Verify Email Address</a>
      <p>This link expires in <strong>24 hours</strong>.</p>
      <p class="link">Or copy this link: {verify_url}</p>
      <p style="font-size:12px;color:#aaa;">If you didn't create an account, you can safely ignore this email.</p>
    </div>
    <div class="footer">Tylented &mdash; Free everyday tools</div>
  </div>
</body>
</html>
"""

    try:
        send_mail(
            subject      = subject,
            message      = text_body,
            from_email   = settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message = html_body,
            fail_silently= False,
        )
        logger.info(f'[Email] Verification sent to {user.email}')
    except Exception as e:
        logger.error(f'[Email] Failed to send verification to {user.email}: {e}', exc_info=True)
        raise


def send_password_reset_email(user, token: str):
    """Send password reset link."""
    reset_url = f'{FRONTEND_URL}/reset-password?token={token}'

    subject = 'Reset your Tylented password'

    text_body = f"""Hi{' ' + user.name if getattr(user, 'name', '') else ''},

We received a request to reset your password.

Reset your password here:
{reset_url}

This link expires in 1 hour. If you didn't request a password reset, ignore this email — your password won't change.

— The Tylented team
"""

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8"/>
<style>
  body {{ font-family: 'DM Sans', Arial, sans-serif; background: #f4f6fa; margin: 0; padding: 20px; }}
  .card {{ max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,.08); }}
  .header {{ background: #07080c; padding: 28px 32px; text-align: center; }}
  .logo {{ font-size: 22px; font-weight: 800; color: #ffffff; letter-spacing: -.02em; }}
  .logo span {{ color: #00c8f0; }}
  .body {{ padding: 32px; color: #333; line-height: 1.65; }}
  h2 {{ font-size: 18px; color: #07080c; margin: 0 0 12px; }}
  p {{ margin: 0 0 16px; font-size: 14px; color: #555; }}
  .btn {{ display: inline-block; padding: 13px 28px; background: linear-gradient(135deg, #00c8f0, #4d8fff);
          color: #07080c !important; font-weight: 700; text-decoration: none; border-radius: 8px;
          font-size: 14px; margin: 8px 0 20px; }}
  .warning {{ background: #fff8e6; border: 1px solid #ffd04b; border-radius: 7px;
              padding: 10px 14px; font-size: 12px; color: #7a5c00; margin-bottom: 16px; }}
  .link {{ word-break: break-all; font-size: 12px; color: #888; }}
  .footer {{ padding: 20px 32px; background: #f8f9fc; font-size: 11px; color: #aaa; text-align: center; }}
</style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="logo">Tylented</div>
    </div>
    <div class="body">
      <h2>Reset your password</h2>
      <p>Hi{' ' + user.name if getattr(user, 'name', '') else ''},</p>
      <p>We received a request to reset the password for your Tylented account.</p>
      <a href="{reset_url}" class="btn">Reset Password</a>
      <div class="warning">⏱ This link expires in <strong>1 hour</strong>.</div>
      <p style="font-size:12px;color:#aaa;">If you didn't request a password reset, you can safely ignore this email. Your password won't change.</p>
      <p class="link">Or copy this link: {reset_url}</p>
    </div>
    <div class="footer">Tylented &mdash; Free everyday tools</div>
  </div>
</body>
</html>
"""

    try:
        send_mail(
            subject      = subject,
            message      = text_body,
            from_email   = settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message = html_body,
            fail_silently= False,
        )
        logger.info(f'[Email] Password reset sent to {user.email}')
    except Exception as e:
        logger.error(f'[Email] Failed to send password reset to {user.email}: {e}', exc_info=True)
        raise
