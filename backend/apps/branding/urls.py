from django.urls import path, re_path

from .views import BrandingImageView, BrandingView, PublicBrandingImageView, PublicBrandingView

KIND = r"(?P<kind>logo|login_image)"

urlpatterns = [
    path("public/branding/", PublicBrandingView.as_view(), name="public-branding"),
    re_path(
        rf"^public/branding/(?P<slug>[-a-zA-Z0-9_]+)/{KIND}/$",
        PublicBrandingImageView.as_view(),
        name="public-branding-image",
    ),
    path("organization/branding/", BrandingView.as_view(), name="organization-branding"),
    re_path(
        rf"^organization/branding/{KIND}/$",
        BrandingImageView.as_view(),
        name="organization-branding-image",
    ),
]
