import smtplib

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_event
from apps.rbac.permissions import require_permission

from .mail import MailNotConfigured, send_mail
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "title", "body", "application", "read_at", "created_at"]


class UnreadCountSerializer(serializers.Serializer):
    unread = serializers.IntegerField()


def _mine(request):
    return Notification.objects.filter(recipient=request.user.active_membership)


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    filterset_fields = {"read_at": ["isnull"]}
    search_fields = ["title", "body"]
    ordering_fields = ["created_at", "read_at"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        return _mine(self.request)


class UnreadCountView(APIView):
    @extend_schema(responses={200: UnreadCountSerializer})
    def get(self, request):
        return Response({"unread": _mine(request).filter(read_at__isnull=True).count()})


class MarkReadView(APIView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request, pk):
        notification = get_object_or_404(_mine(request), pk=pk)
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MarkAllReadView(APIView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        _mine(request).filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)


class MailTestView(APIView):
    """Tries the saved settings by sending to the person who pressed the button."""

    permission_classes = [IsAuthenticated, require_permission("settings.manage")]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        try:
            send_mail(
                request.user.email,
                "Member Onboarding test",
                "Your mail settings work.",
            )
        except MailNotConfigured as exc:
            raise exceptions.ValidationError(
                {"detail": ["Save and enable the mail settings first."]}
            ) from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise exceptions.ValidationError({"detail": [f"Mail failed: {exc}"]}) from exc
        record_event("integration.mail_tested", actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
