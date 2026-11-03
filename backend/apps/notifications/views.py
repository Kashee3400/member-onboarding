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
from .models import ContactOtp, Notification, Preference, PushDevice
from .otp import RESEND_AFTER, send_code, verify_code
from .push import PushFailed, PushNotConfigured, check_credentials
from .sms import SmsFailed, SmsNotConfigured, send_otp_sms


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


class PreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Preference
        fields = ["morning_summary"]


class PreferenceView(APIView):
    """Each person's own choices, for the organization they are signed in to."""

    def _mine(self, request):
        membership = request.user.active_membership
        return Preference.objects.filter(membership=membership).first() or Preference(
            membership=membership, organization_id=membership.organization_id
        )

    @extend_schema(responses={200: PreferenceSerializer})
    def get(self, request):
        return Response(PreferenceSerializer(self._mine(request)).data)

    @extend_schema(request=PreferenceSerializer, responses={200: PreferenceSerializer})
    def patch(self, request):
        serializer = PreferenceSerializer(self._mine(request), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class MailTestView(APIView):
    """Tries the saved settings by sending to the person who pressed the button."""

    permission_classes = [IsAuthenticated, require_permission("settings.integrations")]

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


def _editable_form(request, pk):
    from apps.applications.services import visible_applications

    user = request.user
    forms = visible_applications(user.active_membership, user.active_permissions)
    return get_object_or_404(forms.select_for_update(of=("self",)), pk=pk)


class ContactOtpRequestSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=ContactOtp.Channel.choices)


class ContactOtpVerifySerializer(ContactOtpRequestSerializer):
    code = serializers.RegexField(r"^\d{6}$", error_messages={"invalid": "Enter the 6-digit code."})


class ContactOtpSentSerializer(serializers.Serializer):
    channel = serializers.CharField()
    expires_at = serializers.DateTimeField()
    resend_after_seconds = serializers.IntegerField()


class ContactVerifiedSerializer(serializers.Serializer):
    mobile = serializers.DateTimeField(allow_null=True)
    email = serializers.DateTimeField(allow_null=True)


class ContactOtpSendView(APIView):
    """Sends a code to the form's mobile number or email, for the member to read out."""

    permission_classes = [IsAuthenticated, require_permission("applications.edit")]

    @extend_schema(request=ContactOtpRequestSerializer, responses={201: ContactOtpSentSerializer})
    def post(self, request, pk):
        serializer = ContactOtpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp = send_code(
            _editable_form(request, pk), serializer.validated_data["channel"], user=request.user
        )
        return Response(
            {
                "channel": otp.channel,
                "expires_at": otp.expires_at,
                "resend_after_seconds": int(RESEND_AFTER.total_seconds()),
            },
            status=status.HTTP_201_CREATED,
        )


class ContactOtpVerifyView(APIView):
    permission_classes = [IsAuthenticated, require_permission("applications.edit")]

    @extend_schema(request=ContactOtpVerifySerializer, responses={200: ContactVerifiedSerializer})
    def post(self, request, pk):
        serializer = ContactOtpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        application = _editable_form(request, pk)
        wrong = verify_code(application, data["channel"], data["code"], user=request.user)
        if wrong:
            # A response, not an exception, so the counted try is kept.
            return Response(
                {"error": {"code": "wrong_code", "message": wrong, "details": {"code": [wrong]}}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"mobile": application.mobile_verified_at, "email": application.email_verified_at}
        )


class SmsTestSerializer(serializers.Serializer):
    mobile = serializers.RegexField(
        r"^(\+?91)?[6-9]\d{9}$", error_messages={"invalid": "Enter a 10-digit mobile number."}
    )


class PushDeviceSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)
    platform = serializers.CharField(max_length=20, required=False, allow_blank=True)


class PushDeviceView(APIView):
    """A phone says where to send this person's push notifications, or stops them."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=PushDeviceSerializer, responses={204: None})
    def post(self, request):
        serializer = PushDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership = request.user.active_membership
        # A phone handed to someone else follows its new user.
        PushDevice.objects.update_or_create(
            organization=membership.organization,
            token=data["token"],
            defaults={
                "membership": membership,
                "platform": data.get("platform", ""),
                "is_active": True,
                "last_seen_at": timezone.now(),
            },
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=PushDeviceSerializer, responses={204: None})
    def delete(self, request):
        serializer = PushDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PushDevice.objects.filter(
            membership=request.user.active_membership, token=serializer.validated_data["token"]
        ).update(is_active=False)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PushTestView(APIView):
    """Checks the saved Firebase key with Google, without sending anything to anyone."""

    permission_classes = [IsAuthenticated, require_permission("settings.integrations")]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        try:
            check_credentials()
        except PushNotConfigured as exc:
            raise exceptions.ValidationError(
                {"detail": ["Paste the Firebase key file, turn push on, and save first."]}
            ) from exc
        except PushFailed as exc:
            raise exceptions.ValidationError({"detail": [str(exc)]}) from exc
        record_event("integration.push_tested", actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SmsTestView(APIView):
    """Sends the OTP template with a sample code, to check the saved gateway settings."""

    permission_classes = [IsAuthenticated, require_permission("settings.integrations")]

    @extend_schema(request=SmsTestSerializer, responses={204: None})
    def post(self, request):
        serializer = SmsTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            send_otp_sms(serializer.validated_data["mobile"], "123456")
        except SmsNotConfigured as exc:
            raise exceptions.ValidationError(
                {"detail": ["Save and enable the SMS settings, with every field filled, first."]}
            ) from exc
        except SmsFailed as exc:
            raise exceptions.ValidationError({"detail": [f"SMS failed: {exc}"]}) from exc
        record_event("integration.sms_tested", actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
