# from django.urls import path
# from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
# from .views import (
#     CustomTokenObtainPairView,
#     RegisterView,
#     LogoutView,
#     UserProfileView,
#     ChangePasswordView,
# )

# urlpatterns = [
#     # ── JWT ──────────────────────────────────────────────────────────
#     path('token/',          CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
#     path('token/refresh/',  TokenRefreshView.as_view(),          name='token_refresh'),
#     path('token/verify/',   TokenVerifyView.as_view(),           name='token_verify'),

#     # ── Registration & session ────────────────────────────────────────
#     path('register/',       RegisterView.as_view(),              name='register'),
#     path('logout/',         LogoutView.as_view(),                name='logout'),

#     # ── Profile ───────────────────────────────────────────────────────
#     path('me/',             UserProfileView.as_view(),           name='user_profile'),
#     path('me/password/',    ChangePasswordView.as_view(),        name='change_password'),
# ]

"""
ADD THESE to your apps/authentication/urls.py
(or create it if it doesn't exist and include it in config/urls.py)
"""
from django.urls import path
from . import auth_views
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenBlacklistView

urlpatterns = [
    # JWT
    path('token/',           TokenObtainPairView.as_view(),  name='token_obtain_pair'),
    path('token/refresh/',   TokenRefreshView.as_view(),     name='token_refresh'),
    path('token/blacklist/', TokenBlacklistView.as_view(),   name='token_blacklist'),

    # Registration + email verification
    path('register/',            auth_views.register,           name='auth_register'),
    path('verify-email/',        auth_views.verify_email,       name='auth_verify_email'),
    path('resend-verification/', auth_views.resend_verification,name='auth_resend_verification'),

    # Password reset
    path('forgot-password/',     auth_views.forgot_password,    name='auth_forgot_password'),
    path('reset-password/',      auth_views.reset_password,     name='auth_reset_password'),

    # Social auth
    path('social/google/',       auth_views.social_google,      name='auth_social_google'),
    path('social/microsoft/',    auth_views.social_microsoft,   name='auth_social_microsoft'),

    # Current user
    path('me/',                  auth_views.me,                 name='auth_me'),
]

# In config/urls.py add:
# path('api/auth/', include('apps.authentication.urls')),
