from django.conf import settings
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

handler404 = "apps.core.views.not_found"
handler500 = "apps.core.views.server_error"

urlpatterns = [
    path("health/", include("apps.core.urls")),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/auth/", include("apps.federation.urls")),
    path("api/v1/settings/", include("apps.configuration.urls")),
    path("api/v1/", include("apps.rbac.urls")),
    path("api/v1/hierarchy/", include("apps.hierarchy.urls")),
    path("api/v1/", include("apps.documents.urls")),
    path("api/v1/", include("apps.applications.urls")),
    path("api/v1/audit/", include("apps.audit.urls")),
    path("api/v1/reports/", include("apps.reports.urls")),
    path("api/v1/", include("apps.notifications.urls")),
    path("api/v1/", include("apps.branding.urls")),
]

if settings.EXPOSE_API_DOCS:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    ]
