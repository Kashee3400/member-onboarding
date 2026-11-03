from django.urls import path

from .views import ConsoleOrganizationsView, ConsoleOrganizationView

urlpatterns = [
    path("organizations/", ConsoleOrganizationsView.as_view(), name="console-organizations"),
    path(
        "organizations/<uuid:pk>/", ConsoleOrganizationView.as_view(), name="console-organization"
    ),
]
