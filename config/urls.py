from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

api_v1 = [
    path('auth/',   include('apps.authentication.urls')),
    path('core/',   include('apps.core.urls')),
]

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # API v1
    path('api/', include(api_v1)),
    path('api/tools/', include('apps.tools.urls')),   # ← add this

    # API schema & docs
    path('api/schema/',   SpectacularAPIView.as_view(),       name='schema'),
    path('api/docs/',     SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/',    SpectacularRedocView.as_view(url_name='schema'),   name='redoc'),
    path('api/chatbot/', include('apps.chatbot.urls')),
    path('api/subscriptions/', include('apps.subscriptions.urls')),
    path('api/tools/', include('apps.tools.urls')),
    path('api/resumes/', include('apps.resumes.urls')),

]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [path('__debug__/', include(debug_toolbar.urls))] + urlpatterns
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
