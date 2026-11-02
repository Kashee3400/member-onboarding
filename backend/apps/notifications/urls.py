from django.urls import path

from .views import (
    MailTestView,
    MarkAllReadView,
    MarkReadView,
    NotificationListView,
    UnreadCountView,
)

urlpatterns = [
    path("notifications/", NotificationListView.as_view(), name="notification-list"),
    path("notifications/unread/", UnreadCountView.as_view(), name="notification-unread"),
    path("notifications/read-all/", MarkAllReadView.as_view(), name="notification-read-all"),
    path("notifications/<uuid:pk>/read/", MarkReadView.as_view(), name="notification-read"),
    path("settings/integrations/mail/test/", MailTestView.as_view(), name="mail-test"),
]
