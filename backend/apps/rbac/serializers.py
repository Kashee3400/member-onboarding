from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.organizations.models import Membership

from .catalog import PERMISSIONS
from .models import Role


class PermissionSerializer(serializers.Serializer):
    code = serializers.CharField()
    description = serializers.CharField()


class NavigationItemSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    icon = serializers.CharField()
    path = serializers.CharField(allow_null=True)
    description = serializers.CharField(allow_blank=True)
    children = serializers.ListField(child=serializers.DictField())


class LockedPagesSerializer(serializers.Serializer):
    paths = serializers.ListField(child=serializers.CharField())


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(PERMISSIONS)), allow_empty=True
    )

    class Meta:
        model = Role
        fields = ["id", "code", "name", "is_system", "requires_mfa", "permissions"]
        read_only_fields = ["id", "is_system"]

    def validate_code(self, value):
        queryset = Role.objects.filter(code=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("A role with this code already exists.")
        return value


class StaffRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "code", "name"]


class TemporaryPasswordSerializer(serializers.Serializer):
    temporary_password = serializers.CharField()


class InvitationLinkSerializer(serializers.Serializer):
    invite_link = serializers.CharField()


class InvitationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField()
    organization = serializers.CharField()


class AcceptInvitationSerializer(serializers.Serializer):
    organization = serializers.SlugField()
    token = serializers.CharField()
    full_name = serializers.CharField(max_length=200)
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class StaffSerializer(serializers.ModelSerializer):
    email = serializers.SerializerMethodField()
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    photo_url = serializers.ReadOnlyField()
    status = serializers.SerializerMethodField()
    has_signature = serializers.SerializerMethodField()
    needs_signature = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = [
            "id",
            "email",
            "mobile",
            "full_name",
            "is_active",
            "status",
            "has_signature",
            "needs_signature",
            "photo_url",
            "roles",
            "created_at",
        ]
        read_only_fields = fields

    @staticmethod
    def get_email(membership) -> str:
        email = membership.user.email
        return "" if email.endswith(NO_EMAIL_DOMAIN) else email

    @staticmethod
    def get_status(membership) -> str:
        if not membership.is_active:
            return "inactive"
        return "active" if membership.user.has_usable_password() else "invited"

    @staticmethod
    def get_has_signature(membership) -> bool:
        return bool(getattr(membership, "signature_on_file", False))

    @staticmethod
    def get_needs_signature(membership) -> bool:
        """Facilitators and Area Managers sign forms, and so do the heads chosen to."""
        held = {code for link in membership.role_links.all() for code in link.role.permissions}
        return bool(
            {"applications.submit", "applications.approve_am"} & held
            or getattr(membership, "is_signatory", False)
        )

    @staticmethod
    def get_roles(membership) -> list[dict]:
        roles = [link.role for link in membership.role_links.all()]
        return StaffRoleSerializer(roles, many=True).data


MOBILE = r"^[6-9]\d{9}$"
# Field staff who sign in only by SMS have no address; this stands in for one.
NO_EMAIL_DOMAIN = "@mobile.invalid"


class StaffCreateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    mobile = serializers.RegexField(
        MOBILE, required=False, help_text="Signs in to the app with a code by SMS."
    )
    full_name = serializers.CharField(max_length=200)
    # Without a password the person is invited by email and chooses their own.
    password = serializers.CharField(write_only=True, trim_whitespace=False, required=False)
    role_ids = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(), many=True, allow_empty=False
    )

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        if not attrs.get("email") and not attrs.get("mobile"):
            raise serializers.ValidationError({"email": ["Enter an email, a mobile, or both."]})
        return attrs


class StaffUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(required=False, allow_blank=False, max_length=200)
    email = serializers.EmailField(required=False)
    mobile = serializers.RegexField(MOBILE, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    role_ids = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(), many=True, required=False
    )
