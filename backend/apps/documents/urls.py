from django.urls import path

from .views import (
    ApplicationDocumentsView,
    DocumentFileView,
    StaffPhotoView,
    StaffSignatureFileView,
    StaffSignatureView,
)

urlpatterns = [
    path(
        "applications/<uuid:pk>/documents/",
        ApplicationDocumentsView.as_view(),
        name="application-documents",
    ),
    path("documents/<uuid:pk>/file/", DocumentFileView.as_view(), name="document-file"),
    path("staff/<uuid:pk>/photo/", StaffPhotoView.as_view(), name="staff-photo"),
    path("staff/<uuid:pk>/signature/", StaffSignatureView.as_view(), name="staff-signature"),
    path(
        "staff/<uuid:pk>/signature/file/",
        StaffSignatureFileView.as_view(),
        name="staff-signature-file",
    ),
]
