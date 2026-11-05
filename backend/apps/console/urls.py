from django.urls import path

from .views import ConsoleApplicationDeleteView, ConsoleOrganizationsView, ConsoleOrganizationView

urlpatterns = [
    path(
        "applications/<uuid:pk>/delete/",
        ConsoleApplicationDeleteView.as_view(),
        name="console-application-delete",
    ),
    path("organizations/", ConsoleOrganizationsView.as_view(), name="console-organizations"),
    path(
        "organizations/<uuid:pk>/", ConsoleOrganizationView.as_view(), name="console-organization"
    ),
]
