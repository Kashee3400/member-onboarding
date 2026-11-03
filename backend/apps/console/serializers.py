from rest_framework import serializers

from apps.branding.serializers import DOMAIN


class FailuresSerializer(serializers.Serializer):
    mail = serializers.IntegerField()
    sms = serializers.IntegerField()
    push = serializers.IntegerField()


class SetupSerializer(serializers.Serializer):
    branding = serializers.BooleanField()
    email_domain = serializers.BooleanField()
    mail = serializers.BooleanField()
    sms = serializers.BooleanField()
    push = serializers.BooleanField()
    review_steps = serializers.BooleanField()
    signatories = serializers.IntegerField()
    connected_apps = serializers.IntegerField()
    mpps = serializers.IntegerField()


class HealthSerializer(serializers.Serializer):
    forms_total = serializers.IntegerField()
    forms_this_week = serializers.IntegerField()
    pending = serializers.IntegerField()
    late = serializers.IntegerField()
    sent_back = serializers.IntegerField()
    members = serializers.IntegerField()
    staff = serializers.IntegerField()
    last_activity = serializers.DateTimeField(allow_null=True)
    failures_this_week = FailuresSerializer()
    storage_bytes = serializers.IntegerField()
    setup = SetupSerializer()


class ConsoleOrganizationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    is_active = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    health = HealthSerializer()


class OrganizationCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    slug = serializers.SlugField(max_length=60, help_text="Short name used at sign-in.")
    admin_name = serializers.CharField(max_length=200)
    admin_email = serializers.EmailField()
    email_domain = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate_slug(self, value):
        return value.lower()

    def validate_admin_email(self, value):
        return value.strip().lower()

    def validate_email_domain(self, value):
        domain = value.strip().lower().lstrip("@")
        if domain and not DOMAIN.fullmatch(domain):
            raise serializers.ValidationError("Enter a domain like kasheemilk.com.")
        return domain


class OrganizationCreatedSerializer(serializers.Serializer):
    organization = ConsoleOrganizationSerializer()
    invitation_link = serializers.CharField(allow_null=True)


class OrganizationUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()
