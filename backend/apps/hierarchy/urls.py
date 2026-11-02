from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    BmcViewSet,
    DistrictViewSet,
    HamletViewSet,
    MccAssignmentEndView,
    MccCoverViewSet,
    MccViewSet,
    MppAssignmentEndView,
    MppImportView,
    MppViewSet,
    PlantViewSet,
    RouteViewSet,
    StateViewSet,
    TehsilViewSet,
    VillageViewSet,
)

router = SimpleRouter()
router.register("plants", PlantViewSet, basename="plant")
router.register("mccs", MccViewSet, basename="mcc")
router.register("mcc-covers", MccCoverViewSet, basename="mcc-cover")
router.register("bmcs", BmcViewSet, basename="bmc")
router.register("routes", RouteViewSet, basename="route")
router.register("mpps", MppViewSet, basename="mpp")
router.register("states", StateViewSet, basename="state")
router.register("districts", DistrictViewSet, basename="district")
router.register("tehsils", TehsilViewSet, basename="tehsil")
router.register("villages", VillageViewSet, basename="village")
router.register("hamlets", HamletViewSet, basename="hamlet")

urlpatterns = [
    path("mpps/import/", MppImportView.as_view(), name="mpp-import"),
    path(
        "mccs/<uuid:pk>/area-manager/<uuid:membership>/end/",
        MccAssignmentEndView.as_view(),
        name="mcc-assignment-end",
    ),
    path(
        "mpps/<uuid:pk>/assignments/<slug:responsibility>/",
        MppAssignmentEndView.as_view(),
        name="mpp-assignment-end",
    ),
    path("", include(router.urls)),
]
