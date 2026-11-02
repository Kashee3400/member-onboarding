from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    ApplicationViewSet,
    DashboardView,
    FormSchemaView,
    GlobalSearchView,
    HomeBreakdownView,
    HomeView,
    LegacyMemberViewSet,
    MemberCodeSettingsView,
    MemberViewSet,
    MppOpenWorkView,
    OrganizationProfileView,
    ReviewStepAccessView,
    SignatoriesView,
)

router = SimpleRouter()
router.register("applications", ApplicationViewSet, basename="application")
router.register("members", MemberViewSet, basename="member")
router.register("legacy-members", LegacyMemberViewSet, basename="legacy-member")

urlpatterns = [
    path("search/", GlobalSearchView.as_view(), name="global-search"),
    path("applications/form/", FormSchemaView.as_view(), name="application-form"),
    path("applications/dashboard/", DashboardView.as_view(), name="application-dashboard"),
    path(
        "hierarchy/mpps/<uuid:pk>/open-work/",
        MppOpenWorkView.as_view(),
        name="mpp-open-work",
    ),
    path("settings/signatories/", SignatoriesView.as_view(), name="signatories"),
    path("home/", HomeView.as_view(), name="home"),
    path("home/breakdown/", HomeBreakdownView.as_view(), name="home-breakdown"),
    path("settings/review-steps/", ReviewStepAccessView.as_view(), name="review-steps"),
    path("settings/member-code/", MemberCodeSettingsView.as_view(), name="member-code-settings"),
    path(
        "settings/organization-profile/",
        OrganizationProfileView.as_view(),
        name="organization-profile",
    ),
    path("", include(router.urls)),
]
