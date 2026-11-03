from django.urls import path

from apps.rbac.views import LockedPagesView, NavigationView

from .mfa_views import MfaConfirmView, MfaEnrollView, MfaVerifyView
from .mobile_views import MobileStartView, MobileVerifyView
from .password_views import PasswordChangeView, PasswordForgotView, PasswordResetView
from .views import LoginView, LogoutView, MeView, RefreshView

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("mobile/start/", MobileStartView.as_view(), name="auth-mobile-start"),
    path("mobile/verify/", MobileVerifyView.as_view(), name="auth-mobile-verify"),
    path("mfa/verify/", MfaVerifyView.as_view(), name="auth-mfa-verify"),
    path("mfa/enroll/", MfaEnrollView.as_view(), name="auth-mfa-enroll"),
    path("mfa/enroll/confirm/", MfaConfirmView.as_view(), name="auth-mfa-confirm"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("password/change/", PasswordChangeView.as_view(), name="auth-password-change"),
    path("password/forgot/", PasswordForgotView.as_view(), name="auth-password-forgot"),
    path("password/reset/", PasswordResetView.as_view(), name="auth-password-reset"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("me/navigation/", NavigationView.as_view(), name="auth-navigation"),
    path("me/locked-pages/", LockedPagesView.as_view(), name="auth-locked-pages"),
]
