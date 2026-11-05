from datetime import datetime, timedelta

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.hierarchy.models import Mpp
from apps.hierarchy.services import mpp_place

from . import (
    aadhaar_check,
    banks,
    form,
    place,
    review_checks,
    review_settings,
    review_steps,
    services,
    warnings,
)
from .models import (
    Application,
    ApplicationDecision,
    ApplicationRevision,
    Bank,
    BankBranch,
    Decision,
    LegacyMember,
    Member,
    MemberCodeSettings,
    OrganizationProfile,
    Status,
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
    mobile = serializers.SerializerMethodField()
    photo_id = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            "id",
            "form_number",
            "aadhaar_last4",
            "mobile",
            "photo_id",
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
    def get_mobile(application) -> str:
        return str(application.data.get("address", {}).get("mobile") or "")

    @staticmethod
    def get_photo_id(application) -> str | None:
        """The member's photo, for a list to show; only lists and the form page carry it."""
        photo = getattr(application, "photo_id", None)
        return str(photo) if photo else None

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
            "field_notes",
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


class AadhaarFieldSerializer(serializers.Serializer):
    field = serializers.CharField()
    label = serializers.CharField()
    form = serializers.CharField(allow_blank=True)
    aadhaar = serializers.CharField(allow_blank=True)
    match = serializers.BooleanField(allow_null=True)


class AadhaarCheckSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["verified", "unsigned", "invalid"])
    source = serializers.ChoiceField(choices=["scan", "photo"])
    certificate = serializers.CharField(allow_blank=True)
    checked_at = serializers.DateTimeField()
    checked_by_name = serializers.CharField(allow_blank=True)
    consent = serializers.BooleanField()
    has_photo = serializers.BooleanField()
    fields = AadhaarFieldSerializer(many=True)
    full_match = serializers.BooleanField()


class ApplicationDetailSerializer(ApplicationListSerializer):
    """Sensitive numbers appear only as their last four digits."""

    computed = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()
    field_warnings = serializers.SerializerMethodField()
    tr_code = serializers.SerializerMethodField()
    fee = serializers.SerializerMethodField()
    place = serializers.SerializerMethodField()
    mpp_place = serializers.SerializerMethodField()
    review_steps = serializers.SerializerMethodField()
    contact_verified = serializers.SerializerMethodField()
    duplicate_fields = serializers.SerializerMethodField()
    decisions = DecisionSerializer(many=True, read_only=True)
    revisions = RevisionSerializer(many=True, read_only=True)
    stages = serializers.SerializerMethodField()
    aadhaar_check = serializers.SerializerMethodField()

    class Meta(ApplicationListSerializer.Meta):
        fields = [
            *ApplicationListSerializer.Meta.fields,
            "stages",
            "aadhaar_check",
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
            "rejected_field_notes",
            "payment",
            "computed",
            "warnings",
            "field_warnings",
            "tr_code",
            "fee",
            "place",
            "mpp_place",
            "review_steps",
            "contact_verified",
            "duplicate_fields",
            "decisions",
            "revisions",
        ]

    @staticmethod
    @extend_schema_field(AadhaarCheckSerializer(allow_null=True))
    def get_aadhaar_check(application):
        return aadhaar_check.comparison(application)

    @staticmethod
    def get_duplicate_fields(application) -> dict[str, str]:
        """Set only by a save: what was not kept because another form or member has it."""
        return getattr(application, "duplicate_fields", {})

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
        steps = review_steps.steps_for(membership, application)
        return review_checks.with_checks(steps, application, request.user if request else None)

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
    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_stages(application) -> list[dict]:
        """
        Where the current submission stands at each approval stage, for the facilitator:
        approved (by whom, when), rejected (why), pending (since when), or not reached yet.
        """
        stamp = serializers.DateTimeField().to_representation
        decisions = {
            decision.stage: decision
            for decision in sorted(application.decisions.all(), key=lambda item: item.decided_at)
            if decision.revision == application.revision
        }
        stages = []
        for stage in services.STAGES:
            decision = decisions.get(stage)
            if decision:
                state = decision.decision
            elif application.status == stage:
                state = "pending"
            else:
                state = "waiting"
            since = getattr(application, "waiting_since", None) if state == "pending" else None
            stages.append(
                {
                    "stage": stage,
                    "label": Status(stage).label.removeprefix("Pending "),
                    "state": state,
                    "by": decision.decided_by_name if decision else "",
                    "at": stamp(decision.decided_at) if decision else None,
                    "since": stamp(since) if since else None,
                    "reason": decision.reason if decision else "",
                }
            )
        return stages

    @staticmethod
    def get_fee(application) -> dict:
        settings = services.code_settings()
        return {
            "admission_fee": settings.entry_fee,
            "share_quantity": application.payment.get("share_quantity", settings.share_count),
            "share_price": settings.share_price,
            "is_shg_member": application.data.get("applicant", {}).get("is_shg_member"),
            # Where the fee is deposited, shown to Finance before they record it.
            "collection_bank": {
                "bank_name": settings.collection_bank_name,
                "branch_name": settings.collection_branch_name,
                "bank_address": settings.collection_bank_address,
            },
        }

    @staticmethod
    def get_computed(application) -> dict:
        return form.computed_totals(application.data)

    def _field_warnings(self, application) -> dict[str, str]:
        """Worked out once per form, for both the list and the per-field view."""
        cache = self.context.setdefault("field_warnings", {})
        if application.pk not in cache:
            request = self.context.get("request")
            user = getattr(request, "user", None)
            cache[application.pk] = warnings.field_warnings(
                application,
                getattr(user, "active_membership", None),
                getattr(user, "active_permissions", ()),
            )
        return cache[application.pk]

    def get_warnings(self, application) -> list[str]:
        """Worth an approver's attention, but not grounds to block a submission."""
        return list(self._field_warnings(application).values())

    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_field_warnings(self, application) -> dict:
        """The same warnings, keyed by the field they concern, as "section.field"."""
        return self._field_warnings(application)

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
    aadhaar_qr = serializers.CharField(
        required=False,
        write_only=True,
        max_length=20000,
        help_text="The Aadhaar QR as scanned. Checked against UIDAI's signature, then dropped.",
    )
    aadhaar_qr_consent = serializers.BooleanField(required=False, default=False)

    def validate_data(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be an object.")
        return value

    def validate(self, attrs):
        if attrs.get("aadhaar_qr") and not attrs.get("aadhaar_qr_consent"):
            raise serializers.ValidationError(
                {"aadhaar_qr_consent": ["The member must agree to her Aadhaar QR being read."]}
            )
        return attrs


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


class ReviewChecksField(serializers.DictField):
    """Each step's checklist, in order. A step left out, or emptied, has none."""

    child = serializers.ListField(
        child=serializers.CharField(max_length=200), max_length=review_checks.MAX_CHECKS
    )

    def to_internal_value(self, data):
        checks = super().to_internal_value(data)
        errors = {}
        for step, texts in checks.items():
            if step not in review_steps.STEP_KEYS:
                errors[step] = ["This is not a review step."]
                continue
            lowered = [text.lower() for text in texts]
            if len(lowered) != len(set(lowered)):
                errors[step] = ["Each check must be different."]
        if errors:
            raise serializers.ValidationError(errors)
        return checks


class ReviewSettingsSerializer(serializers.Serializer):
    """The reasons and checklists are sent whole, in the order they are offered."""

    overdue_days = serializers.IntegerField(min_value=1, max_value=60)
    reject_reasons = RejectReasonSerializer(many=True)
    checks = ReviewChecksField(required=False)

    def validate_reject_reasons(self, value):
        texts = [reason["text"].strip().lower() for reason in value]
        if len(texts) != len(set(texts)):
            raise serializers.ValidationError("Each reason must be different.")
        return value


class StepTickSerializer(serializers.Serializer):
    step = serializers.ChoiceField(choices=review_steps.STEP_KEYS)
    text = serializers.CharField(max_length=200)
    ticked = serializers.BooleanField()


class StepTicksSerializer(serializers.Serializer):
    step = serializers.CharField()
    ticked = serializers.ListField(child=serializers.CharField())


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
    field_notes = serializers.DictField(
        child=serializers.CharField(max_length=300, allow_blank=True),
        required=False,
        help_text="Each marked field with the reviewer's reason for it.",
    )


class FieldMarkSerializer(serializers.Serializer):
    """A field marked wrong. Sent with a path and a reason; returned with who marked it."""

    id = serializers.UUIDField(read_only=True)
    path = serializers.CharField(max_length=100)
    label = serializers.CharField(read_only=True)
    reason = serializers.CharField(max_length=300)
    marked_by_name = serializers.CharField(read_only=True)
    marked_at = serializers.DateTimeField(read_only=True)
    mine = serializers.BooleanField(read_only=True)
    can_remove = serializers.BooleanField(read_only=True)


class PaymentSerializer(serializers.Serializer):
    """
    The deposit, as Finance records it. Everything else is known already: the bank is
    the organization's collection account, and the amount and mode are what the
    facilitator collected.
    """

    deposited_on = serializers.DateField()


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
            "collection_bank_name",
            "collection_branch_name",
            "collection_bank_address",
            "collection_account_number",
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


class FormOptionSerializer(serializers.Serializer):
    """Without a value, the option is new and the server gives it one."""

    value = serializers.CharField(max_length=40, required=False, allow_blank=True)
    label = serializers.CharField(max_length=100)
    label_hi = serializers.CharField(max_length=100)
    is_active = serializers.BooleanField(default=True)


class FormListSerializer(serializers.Serializer):
    options = FormOptionSerializer(many=True, allow_empty=False)


class BankBranchSerializer(serializers.ModelSerializer):
    bank_name = serializers.CharField(source="bank.name", max_length=200)
    branch_name = serializers.CharField(source="name", max_length=200)
    bank_is_active = serializers.BooleanField(source="bank.is_active", read_only=True)

    class Meta:
        model = BankBranch
        fields = [
            "id",
            "ifsc",
            "bank_name",
            "branch_name",
            "address",
            "district",
            "is_active",
            "bank_is_active",
            "updated_at",
        ]
        read_only_fields = ["id", "updated_at"]

    def validate_ifsc(self, value):
        value = value.strip().upper()
        if not banks.IFSC.match(value):
            raise serializers.ValidationError("Enter a valid IFSC.")
        taken = BankBranch.objects.filter(ifsc=value)
        if self.instance:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError("Another branch has this IFSC.")
        return value

    def _bank(self, validated_data):
        name = " ".join(validated_data.pop("bank")["name"].split())
        existing = {bank.name.lower(): bank for bank in Bank.objects.filter(name__iexact=name)}
        return banks.bank_named(name, existing)

    def create(self, validated_data):
        bank = self._bank(validated_data)
        return BankBranch.objects.create(bank=bank, **validated_data)

    def update(self, instance, validated_data):
        if "bank" in validated_data:
            instance.bank = self._bank(validated_data)
        return super().update(instance, validated_data)


class BankBranchLookupSerializer(serializers.Serializer):
    ifsc = serializers.CharField()
    bank_name = serializers.CharField(source="bank.name")
    branch_name = serializers.CharField(source="name")
    address = serializers.CharField()
    district = serializers.CharField()


class BankImportSerializer(serializers.Serializer):
    file = serializers.FileField()


class BankImportProblemSerializer(serializers.Serializer):
    row = serializers.IntegerField()
    problem = serializers.CharField()


class BankImportResultSerializer(serializers.Serializer):
    created = serializers.IntegerField()
    updated = serializers.IntegerField()
    skipped = serializers.IntegerField()
    repeated = serializers.IntegerField()
    problems = BankImportProblemSerializer(many=True)
