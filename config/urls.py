from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("admin/", admin.site.urls),

    # Auth
    path("api/v1/auth/", include("apps.accounts.urls")),

    # Domain apps
    path("api/v1/inventory/", include("apps.inventory.urls")),
    path("api/v1/suppliers/", include("apps.suppliers.urls")),
    path("api/v1/alerts/", include("apps.alerts.urls")),
    path("api/v1/assistant/", include("apps.chatbot.urls")),

    # API schema / docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),

    # Server-rendered dashboard (HTMX/templates)
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
