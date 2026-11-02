from django.urls import path

from .views import IntegrationDetailView, IntegrationListView

urlpatterns = [
    path("integrations/", IntegrationListView.as_view(), name="integration-list"),
    path("integrations/<slug:kind>/", IntegrationDetailView.as_view(), name="integration-detail"),
]
