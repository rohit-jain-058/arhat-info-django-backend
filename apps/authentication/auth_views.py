"""
New authentication views to ADD to apps/authentication/views.py

Adds:
  POST /api/auth/register/              — register + send verification email
  POST /api/auth/verify-email/          — verify email with token
  POST /api/auth/resend-verification/   — resend verification email
  POST /api/auth/forgot-password/       — send password reset email
  POST /api/auth/reset-password/        — set new password using token
  POST /api/auth/social/google/         — sign in with Google ID token
  POST /api/auth/social/microsoft/      — sign in with Microsoft ID token
  GET  /api/auth/me/                    — current user info (add email_verified, avatar_url)
"""
import logging
import requests as http_requests

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from .models import EmailVerification, PasswordResetToken
from .email_service import send_verification_email, send_password_reset_email

User   = get_user_model()
logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────
def _make_tokens(user) -> dict:
    """Generate JWT access + refresh token pair for a user."""
    refresh = RefreshToken.for_user(user)
    return {
        'access':  str(refresh.access_token),
        'refresh': str(refresh),
    }

def _user_data(user) -> dict:
    return {
        'id':             str(user.id),
        'email':          user.email,
        'name':           getattr(user, 'name', '') or '',
        'email_verified': getattr(user, 'email_verified', False),
        'avatar_url':     getattr(user, 'avatar_url', '') or '',
    }


# ── REGISTER ──────────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """
    POST /api/auth/register/
    Body: { "email", "password", "name"? }

    Creates user, sends verification email, returns JWT tokens.
    User can log in immediately but email_verified will be False
    until they click the link.
    """
    email    = request.data.get('email', '').strip().lower()
    password = request.data.get('password', '')
    name     = request.data.get('name', '').strip()

    if not email or not password:
        return Response({'error': 'Email and password are required.'}, status=400)

    if len(password) < 8:
        return Response({'error': 'Password must be at least 8 characters.'}, status=400)

    if User.objects.filter(email=email).exists():
        return Response({'error': 'An account with this email already exists.'}, status=400)

    try:
        user = User.objects.create_user(
            email    = email,
            password = password,
        )
        if name and hasattr(user, 'name'):
            user.name = name
        if hasattr(user, 'email_verified'):
            user.email_verified = False
        user.save()
    except Exception as e:
        logger.error(f'[Auth] Register failed for {email}: {e}', exc_info=True)
        return Response({'error': 'Could not create account.'}, status=500)


    # Start 7-day trial
    try:
        from apps.subscriptions.models import Plan, Subscription
        from django.utils import timezone
        from datetime import timedelta

        # Get or create the AI Tools plan (trial mirrors ai_tools tier)
        ai_plan, _ = Plan.objects.get_or_create(
            tier='ai_tools', interval='monthly',
            defaults={
                'name':                'AI Tools — Monthly',
                'price_cents':         999,
                'removes_ads':         False,
                'allows_ai_tools':     True,
                'allows_form_tools':   False,
                'allows_api_key':      False,
                'ai_requests_per_day': 5,   # trial limit
            }
        )

        now = timezone.now()
        Subscription.objects.update_or_create(
            user     = user,
            defaults = {
                'plan':             ai_plan,
                'status':           'trialing',
                'is_trial':         True,
                'trial_started_at': now,
                'trial_ends_at':    now + timedelta(days=7),
                'current_period_start': now,
                'current_period_end':   now + timedelta(days=7),
            }
        )
        logger.info(f'[Auth] 7-day trial started for {email}')
    except Exception as e:
        logger.warning(f'[Auth] Trial setup failed for {email}: {e}')
    # Send verification email (non-blocking — don't fail registration if email fails)
    try:
        ev    = EmailVerification.generate(user)
        send_verification_email(user, ev.token)
    except Exception as e:
        logger.warning(f'[Auth] Verification email failed for {email}: {e}')

    tokens = _make_tokens(user)
    logger.info(f'[Auth] Registered: {email}')
    return Response({
        **tokens,
        'user':    _user_data(user),
        'message': 'Account created. Check your email to verify your address.',
    }, status=status.HTTP_201_CREATED)


# ── VERIFY EMAIL ───────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([AllowAny])
def verify_email(request):
    """
    POST /api/auth/verify-email/
    Body: { "token": "..." }
    """
    token = request.data.get('token', '').strip()
    if not token:
        return Response({'error': 'Token is required.'}, status=400)

    try:
        ev = EmailVerification.objects.select_related('user').get(token=token)
    except EmailVerification.DoesNotExist:
        return Response({'error': 'Invalid or expired verification link.'}, status=400)

    if not ev.is_valid():
        ev.delete()
        return Response({'error': 'This verification link has expired. Request a new one.'}, status=400)

    user = ev.user
    if hasattr(user, 'email_verified'):
        user.email_verified = True
        user.save(update_fields=['email_verified'])

    ev.delete()   # token is single-use

    logger.info(f'[Auth] Email verified: {user.email}')
    return Response({
        'message': 'Email verified successfully.',
        'user':    _user_data(user),
    })


# ── RESEND VERIFICATION EMAIL ──────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def resend_verification(request):
    """
    POST /api/auth/resend-verification/
    Resends the verification email to the authenticated user.
    """
    user = request.user

    if getattr(user, 'email_verified', True):
        return Response({'message': 'Your email is already verified.'})

    try:
        ev = EmailVerification.generate(user)
        send_verification_email(user, ev.token)
        logger.info(f'[Auth] Verification resent: {user.email}')
        return Response({'message': 'Verification email sent. Check your inbox.'})
    except Exception as e:
        logger.error(f'[Auth] Resend failed for {user.email}: {e}', exc_info=True)
        return Response({'error': 'Could not send email. Please try again.'}, status=500)


# ── FORGOT PASSWORD ────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_password(request):
    """
    POST /api/auth/forgot-password/
    Body: { "email": "..." }

    Always returns 200 regardless of whether the email exists
    (prevents email enumeration attacks).
    """
    email = request.data.get('email', '').strip().lower()
    if not email:
        return Response({'error': 'Email is required.'}, status=400)

    try:
        user = User.objects.get(email=email)
        prt  = PasswordResetToken.generate(user)
        send_password_reset_email(user, prt.token)
        logger.info(f'[Auth] Password reset sent: {email}')
    except User.DoesNotExist:
        # Don't reveal whether the email exists
        logger.info(f'[Auth] Password reset requested for non-existent: {email}')
    except Exception as e:
        logger.error(f'[Auth] Password reset email failed for {email}: {e}', exc_info=True)
        # Still return 200 — don't leak info

    return Response({
        'message': 'If an account exists with that email, a password reset link has been sent.'
    })


# ── RESET PASSWORD ─────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password(request):
    """
    POST /api/auth/reset-password/
    Body: { "token": "...", "password": "..." }
    """
    token    = request.data.get('token', '').strip()
    password = request.data.get('password', '')

    if not token or not password:
        return Response({'error': 'Token and new password are required.'}, status=400)

    if len(password) < 8:
        return Response({'error': 'Password must be at least 8 characters.'}, status=400)

    try:
        prt = PasswordResetToken.objects.select_related('user').get(token=token)
    except PasswordResetToken.DoesNotExist:
        return Response({'error': 'Invalid or expired reset link.'}, status=400)

    if not prt.is_valid():
        prt.delete()
        return Response({'error': 'This reset link has expired. Request a new one.'}, status=400)

    user = prt.user
    user.set_password(password)
    user.save()

    # Mark token as used and clean up
    prt.used = True
    prt.save(update_fields=['used'])

    # Invalidate all existing JWT refresh tokens for security
    try:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
        for t in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=t)
    except Exception:
        pass

    logger.info(f'[Auth] Password reset complete: {user.email}')
    return Response({'message': 'Password updated successfully. You can now log in.'})


# ── SOCIAL AUTH — GOOGLE ───────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([AllowAny])
def social_google(request):
    """
    POST /api/auth/social/google/
    Body: { "id_token": "<Google ID token from frontend>" }

    Flow:
    1. Frontend uses Google Sign-In → gets id_token
    2. Posts id_token here
    3. Django verifies with Google's tokeninfo endpoint
    4. Creates or retrieves user
    5. Returns JWT tokens

    Frontend setup (see INTEGRATION.md):
    - Add Google Sign-In button
    - On success: send credential (id_token) to this endpoint
    """
    id_token = request.data.get('id_token', '').strip()
    if not id_token:
        return Response({'error': 'id_token is required.'}, status=400)

    # Verify token with Google
    try:
        google_resp = http_requests.get(
            'https://oauth2.googleapis.com/tokeninfo',
            params = {'id_token': id_token},
            timeout= 10,
        )
        if not google_resp.ok:
            return Response({'error': 'Invalid Google token.'}, status=401)

        info = google_resp.json()
    except Exception as e:
        logger.error(f'[Auth] Google token verification failed: {e}', exc_info=True)
        return Response({'error': 'Could not verify Google token.'}, status=500)

    # Validate audience (must be your Google Client ID)
    from django.conf import settings
    google_client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
    if google_client_id and info.get('aud') != google_client_id:
        return Response({'error': 'Token audience mismatch.'}, status=401)

    google_id = info.get('sub')
    email     = info.get('email', '').lower()
    name      = info.get('name', '')
    avatar    = info.get('picture', '')

    if not google_id or not email:
        return Response({'error': 'Could not retrieve account info from Google.'}, status=400)

    # Get or create user
    user = _get_or_create_social_user(
        email      = email,
        name       = name,
        avatar_url = avatar,
        provider   = 'google',
        provider_id= google_id,
    )

    tokens = _make_tokens(user)
    logger.info(f'[Auth] Google sign-in: {email} ({"new" if user._created else "existing"})')
    return Response({
        **tokens,
        'user': _user_data(user),
    })


# ── SOCIAL AUTH — MICROSOFT ────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([AllowAny])
def social_microsoft(request):
    """
    POST /api/auth/social/microsoft/
    Body: { "access_token": "<Microsoft access token from frontend>" }

    Flow:
    1. Frontend uses MSAL.js → gets access token
    2. Posts access token here
    3. Django calls Microsoft Graph to get user profile
    4. Creates or retrieves user
    5. Returns JWT tokens

    Frontend setup (see INTEGRATION.md):
    - Install @azure/msal-browser
    - On sign-in: send the access token to this endpoint
    """
    access_token = request.data.get('access_token', '').strip()
    if not access_token:
        return Response({'error': 'access_token is required.'}, status=400)

    # Fetch user profile from Microsoft Graph
    try:
        ms_resp = http_requests.get(
            'https://graph.microsoft.com/v1.0/me',
            headers = {'Authorization': f'Bearer {access_token}'},
            timeout = 10,
        )
        if not ms_resp.ok:
            return Response({'error': 'Invalid Microsoft token.'}, status=401)

        info = ms_resp.json()
    except Exception as e:
        logger.error(f'[Auth] Microsoft token verification failed: {e}', exc_info=True)
        return Response({'error': 'Could not verify Microsoft token.'}, status=500)

    ms_id  = info.get('id')
    email  = (info.get('mail') or info.get('userPrincipalName') or '').lower()
    name   = info.get('displayName', '')

    if not ms_id or not email:
        return Response({'error': 'Could not retrieve account info from Microsoft.'}, status=400)

    user = _get_or_create_social_user(
        email       = email,
        name        = name,
        avatar_url  = '',
        provider    = 'microsoft',
        provider_id = ms_id,
    )

    tokens = _make_tokens(user)
    logger.info(f'[Auth] Microsoft sign-in: {email} ({"new" if user._created else "existing"})')
    return Response({
        **tokens,
        'user': _user_data(user),
    })


# ── UPDATED ME ENDPOINT ────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    """
    GET /api/auth/me/
    Returns current user info including email_verified and avatar_url.
    Add/replace your existing me() view with this.
    """
    return Response(_user_data(request.user))


# ── HELPERS ────────────────────────────────────────────────────────────
def _get_or_create_social_user(email, name, avatar_url, provider, provider_id):
    """
    Find existing user by provider ID or email, or create new one.
    Marks email as verified for social sign-ins (provider already verified it).
    Attaches user._created flag for logging.
    """
    id_field = f'{provider}_id'
    created  = False

    # 1. Try find by provider ID
    try:
        user = User.objects.get(**{id_field: provider_id})
        user._created = False
        return user
    except User.DoesNotExist:
        pass

    # 2. Try find by email — link this provider to existing account
    try:
        user = User.objects.get(email=email)
        setattr(user, id_field, provider_id)
        if avatar_url and hasattr(user, 'avatar_url') and not user.avatar_url:
            user.avatar_url = avatar_url
        if hasattr(user, 'email_verified'):
            user.email_verified = True
        user.save()
        user._created = False
        return user
    except User.DoesNotExist:
        pass

    # 3. Create new user
    user = User(email=email)
    if hasattr(user, 'name') and name:
        user.name = name
    if hasattr(user, 'avatar_url'):
        user.avatar_url = avatar_url
    if hasattr(user, 'email_verified'):
        user.email_verified = True   # social providers already verify email
    setattr(user, id_field, provider_id)
    user.set_unusable_password()    # can't log in with password until they set one
    user.save()

    # Auto-create free subscription
    try:
        from apps.subscriptions.models import Plan, Subscription
        free_plan, _ = Plan.objects.get_or_create(
            tier='free', interval='monthly',
            defaults={'name':'Free','price_cents':0,'removes_ads':False,
                      'allows_ai_tools':False,'allows_form_tools':False,
                      'allows_api_key':False,'ai_requests_per_day':0},
        )
        Subscription.objects.get_or_create(user=user, defaults={'plan':free_plan,'status':'active'})
    except Exception:
        pass

    user._created = True
    return user
