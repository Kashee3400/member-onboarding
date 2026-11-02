from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import ExchangeView, TrustedIssuerViewSet

router = SimpleRouter()
router.register("trusted-issuers", TrustedIssuerViewSet, basename="trusted-issuer")

urlpatterns = [
    path("exchange/", ExchangeView.as_view(), name="auth-exchange"),
    path("", include(router.urls)),
]
