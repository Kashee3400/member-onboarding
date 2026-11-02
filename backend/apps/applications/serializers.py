from datetime import datetime, timedelta

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.hierarchy.models import Mpp
from apps.hierarchy.services import mpp_place

from . import form, place, review_settings, review_steps, services
from .models import (
    Application,
    ApplicationDecision,
    ApplicationRevision,
    Decision,
    LegacyMember,
    Member,
    MemberCodeSettings,
    OrganizationProfile,
)


class ApplicationListSerializer(serializers.ModelSerializer):
    mpp_code = serializers.CharField(source="mpp.code", read_only=True)
    mpp_name = serializers.CharField(source="mpp.name", read_only=True)
    applicant_name = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    waiting_since = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    tr_code = serializers.SerializerMethodField()
    approved_at = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            "id",
            "form_number",
            "status",
            "status_label",
            "mpp",
            "mpp_code",
            "mpp_name",
            "applicant_name",
            "created_by_name",
            "created_at",
            "submitted_at",
            "waiting_since",
            "is_overdue",
            "tr_code",
            "approved_at",
            "updated_at",
        ]

    @staticmethod
    def get_applicant_name(application) -> str:
        return application.data.get("applicant", {}).get("full_name", "")

    @staticmethod
    def get_waiting_since(application) -> datetime | None:
        """When it reached its current stage. Only lists and the form page carry it."""
        since = getattr(application, "waiting_since", None)
        return serializers.DateTimeField().to_representation(since) if since else None

    @staticmethod
    def get_tr_code(application) -> str:
        member = getattr(application, "member", None) if application.status == "approved" else None
        return member.tr_code if member else ""

    @staticmethod
    def get_approved_at(application) -> datetime | None:
        member = getattr(application, "member", None) if application.status == "approved" else None
        return serializers.DateTimeField().to_representation(member.joined_at) if member else None

    def get_is_overdue(self, application) -> bool:
        since = getattr(application, "waiting_since", None)
        if not since or application.status not in services.STAGES:
            return False
        # Read once per response: the context is shared by every row of a list.
        if "overdue_days" not in self.context:
            self.context["overdue_days"] = review_settings.overdue_days()
        return timezone.now() - since > timedelta(days=self.context["overdue_days"])


class DecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationDecision
        fields = [
            "id",
            "revision",
            "stage",
            "decision",
            "reason",
            "rejected_fields",
            "decided_by_name",
            "decided_at",
        ]


class RevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationRevision
        fields = [
            "number",
            "data",
            "aadhaar_last4",
            "account_last4",
            "submitted_by_name",
            "submitted_at",
        ]


class ApplicationDetailSerializer(ApplicationListSerializer):
    """Sensitive numbers appear only as their last four digits."""

    computed = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()
    tr_code = serializers.SerializerMethodField()
    fee = serializers.SerializerMethodField()
    place = serializers.SerializerMethodField()
    mpp_place = serializers.SerializerMethodField()
    review_steps = serializers.SerializerMethodField()
    contact_verified = serializers.SerializerMethodField()
    decisions = DecisionSerializer(many=True, read_only=True)
    revisions = RevisionSerializer(many=True, read_only=True)

    class Meta(ApplicationListSerializer.Meta):
        fields = [
            *ApplicationListSerializer.Meta.fields,
            "client_id",
            "form_version",
            "version",
            "revision",
            "data",
            "aadhaar_last4",
            "account_last4",
            "last_edited_by_name",
            "rejection_reason",
            "rejected_fields",
            "payment",
            "computed",
            "warnings",
            "tr_code",
            "fee",
            "place",
            "mpp_place",
            "review_steps",
            "contact_verified",
            "decisions",
            "revisions",
        ]

    @staticmethod
    def get_contact_verified(application) -> dict:
        """When the mobile number and email were confirmed by OTP, or null."""
        stamp = serializers.DateTimeField().to_representation
        return {
            "mobile": stamp(application.mobile_verified_at)
            if application.mobile_verified_at
            else None,
            "email": stamp(application.email_verified_at)
            if application.email_verified_at
            else None,
        }

    def get_review_steps(self, application) -> list[dict]:
        request = self.context.get("request")
        membership = request.user.active_membership if request else None
        return review_steps.steps_for(membership, application)

    @staticmethod
    def get_place(application) -> dict:
        """The form's own copy of the place first: it is what was submitted and signed."""
        mpp = application.mpp
        address = application.data.get("address", {})
        route = mpp.route
        known = mpp_place(mpp)

        def value(key):
            return address.get(key) or known[key]

        return {
            "mcc_code": mpp.mcc.code,
            "mcc_name": mpp.mcc.name,
            "bmc_name": route.bmc.name if route else "",
            "route_name": route.name if route else "",
            "mpp_code": mpp.code,
            "mpp_name": mpp.name,
            "village_name": value("village_name") or mpp.name,
            "village_code": mpp.village_code,
            "as_on_date": application.submitted_at,
            "hamlet_name": value("hamlet_name"),
            "hamlet_code": value("hamlet_code"),
            "post_office": value("post_office"),
            "tehsil": value("tehsil"),
            "district": value("district"),
            "state": value("state"),
            "pincode": value("pincode"),
        }

    @staticmethod
    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_mpp_place(application) -> dict:
        """The address fields the MPP fills and locks, so the app shows them read-only."""
        return place.locked_values(application.mpp)

    @staticmethod
    def get_fee(application) -> dict:
        settings = services.code_settings()
        return {
            "admission_fee": settings.entry_fee,
            "share_quantity": application.payment.get("share_quantity", settings.share_count),
            "share_price": settings.share_price,
            "is_shg_member": application.data.get("applicant", {}).get("is_shg_member"),
        }

    @staticmethod
    def get_computed(application) -> dict:
        return form.computed_totals(application.data)

    @staticmethod
    def get_warnings(application) -> list[str]:
        return form.name_warnings(application.data)

    @staticmethod
    def get_tr_code(application) -> str | None:
        member = getattr(application, "member", None)
        return member.tr_code if member else None


class ApplicationCreateSerializer(serializers.Serializer):
    client_id = serializers.CharField(max_length=100)
    mpp = serializers.PrimaryKeyRelatedField(queryset=Mpp.objects.filter(is_active=True))


class ApplicationSaveSerializer(serializers.Serializer):
    version = serializers.IntegerField(required=False)
    data = serializers.JSONField(required=False)
    aadhaar_number = serializers.CharField(required=False, write_only=True, max_length=12)
    account_number = serializers.CharField(required=False, write_only=True, max_length=18)

    def validate_data(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be an object.")
        return value


class SubmitSerializer(serializers.Serializer):
    version = serializers.IntegerField(required=False)


class ReviewStepAccessSerializer(serializers.Serializer):
    steps = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))


class RejectReasonSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=200)
    section = serializers.ChoiceField(choices=review_settings.SECTIONS)
    fields = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, default=list
    )

    def validate(self, attrs):
        errors = review_settings.field_errors(attrs["section"], attrs["fields"])
        if errors:
            raise serializers.ValidationError({"fields": errors})
        return attrs


class ReviewSettingsSerializer(serializers.Serializer):
    """The reasons are sent whole, in the order they are offered."""

    overdue_days = serializers.IntegerField(min_value=1, max_value=60)
    reject_reasons = RejectReasonSerializer(many=True)

    def validate_reject_reasons(self, value):
        texts = [reason["text"].strip().lower() for reason in value]
        if len(texts) != len(set(texts)):
            raise serializers.ValidationError("Each reason must be different.")
        return value


class SensitiveNumbersSerializer(serializers.Serializer):
    aadhaar_number = serializers.CharField(allow_blank=True)
    account_number = serializers.CharField(allow_blank=True)


class DecideSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=Decision.choices)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    rejected_fields = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False
    )
    steps = serializers.ListField(
        child=serializers.CharField(max_length=20), required=False, allow_empty=True
    )


class PaymentSerializer(serializers.Serializer):
    """The form's "office use" block. Some deposits have no slip or UTR number."""

    bank_name = serializers.CharField(max_length=200)
    branch_name = serializers.CharField(max_length=200)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    amount = serializers.IntegerField(min_value=1)
    deposited_on = serializers.DateField()
    mode = serializers.ChoiceField(choices=["cash", "dd", "online"], default="cash")
    bank_address = serializers.CharField(max_length=300, required=False, allow_blank=True)
    share_quantity = serializers.IntegerField(min_value=0, required=False)


class LegacyMemberSerializer(serializers.ModelSerializer):
    mpp_code = serializers.CharField(source="mpp.code", read_only=True, default="")
    mpp_name = serializers.CharField(source="mpp.name", read_only=True, default="")

    class Meta:
        model = LegacyMember
        fields = ["id", "tr_code", "full_name", "mpp", "mpp_code", "mpp_name", "is_active"]


class MemberSerializer(serializers.ModelSerializer):
    mpp_code = serializers.CharField(source="mpp.code", read_only=True)

    class Meta:
        model = Member
        fields = [
            "id",
            "tr_code",
            "full_name",
            "mobile",
            "mpp",
            "mpp_code",
            "aadhaar_last4",
            "joined_at",
        ]


class OrganizationProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationProfile
        exclude = ["id", "organization", "created_at", "updated_at"]


class MemberCodeSettingsSerializer(serializers.ModelSerializer):
    state_code = serializers.RegexField(r"^\d{2}$")
    hamlet_code = serializers.RegexField(r"^\d{2}$")

    class Meta:
        model = MemberCodeSettings
        fields = [
            "state_code",
            "hamlet_code",
            "form_prefix",
            "entry_fee",
            "share_price",
            "share_count",
        ]


class StatusCountsSerializer(serializers.Serializer):
    by_status = serializers.DictField(child=serializers.IntegerField())
    total = serializers.IntegerField()


class SearchHitSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["application", "member"])
    id = serializers.UUIDField()
    title = serializers.CharField()
    subtitle = serializers.CharField()
    path = serializers.CharField()
