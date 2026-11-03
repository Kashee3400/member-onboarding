from django.urls import path

from .views import (
    ContactOtpSendView,
    ContactOtpVerifyView,
    MailTestView,
    MarkAllReadView,
    MarkReadView,
    NotificationListView,
    PreferenceView,
    PushDeviceView,
    PushTestView,
    SmsTestView,
    UnreadCountView,
)

urlpatterns = [
    path("notifications/", NotificationListView.as_view(), name="notification-list"),
    path("notifications/preferences/", PreferenceView.as_view(), name="notification-preferences"),
    path("notifications/unread/", UnreadCountView.as_view(), name="notification-unread"),
    path("notifications/read-all/", MarkAllReadView.as_view(), name="notification-read-all"),
    path("notifications/<uuid:pk>/read/", MarkReadView.as_view(), name="notification-read"),
    path("settings/integrations/mail/test/", MailTestView.as_view(), name="mail-test"),
    path("settings/integrations/sms/test/", SmsTestView.as_view(), name="sms-test"),
    path("settings/integrations/push/test/", PushTestView.as_view(), name="push-test"),
    path("notifications/push-devices/", PushDeviceView.as_view(), name="push-devices"),
    path(
        "applications/<uuid:pk>/contact-otp/", ContactOtpSendView.as_view(), name="contact-otp-send"
    ),
    path(
        "applications/<uuid:pk>/contact-otp/verify/",
        ContactOtpVerifyView.as_view(),
        name="contact-otp-verify",
    ),
]
