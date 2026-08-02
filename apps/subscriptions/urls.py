"""
Updated urls.py — replaces Authorize.net endpoints with Stripe.
Copy this to apps/subscriptions/urls.py
"""
from django.urls import path
from . import views
from . import stripe_views

urlpatterns = [

    # ── Existing endpoints (unchanged) ─────────────────────────────
    path('plans/',              views.plan_list,       name='subscription_plans'),
    path('me/',                 views.me,              name='subscription_me'),
    path('dashboard/',          views.dashboard,       name='subscription_dashboard'),
    path('payments/',           views.payment_history, name='subscription_payments'),
    path('api-keys/',           views.api_keys,        name='subscription_api_keys'),
    path('api-keys/<uuid:key_id>/', views.revoke_api_key, name='subscription_revoke_key'),

    # ── Stripe endpoints ────────────────────────────────────────────
    path('publishable-key/',    stripe_views.publishable_key, name='stripe_publishable_key'),
    path('checkout/',           stripe_views.checkout,        name='stripe_checkout'),
    path('portal/',             stripe_views.portal,          name='stripe_portal'),
    path('cancel/',             stripe_views.cancel,          name='stripe_cancel'),
    path('resume/',             stripe_views.resume,          name='stripe_resume'),

    # No CSRF, no auth — Stripe calls this directly
    path('webhook/',            stripe_views.webhook,         name='stripe_webhook'),
]
