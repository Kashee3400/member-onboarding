from rest_framework import serializers


class LoginRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)
    organization = serializers.SlugField()


class LoginResponseSerializer(serializers.Serializer):
    """Either tokens, or an MFA step to finish first."""

    access = serializers.CharField(required=False)
    refresh = serializers.CharField(required=False)
    mfa_status = serializers.ChoiceField(choices=["verify", "enroll"], required=False)
    mfa_token = serializers.CharField(required=False)


class MfaVerifySerializer(serializers.Serializer):
    mfa_token = serializers.CharField()
    code = serializers.CharField(required=False, max_length=6)
    recovery_code = serializers.CharField(required=False, max_length=20)

    def validate(self, attrs):
        if bool(attrs.get("code")) == bool(attrs.get("recovery_code")):
            raise serializers.ValidationError("Provide either code or recovery_code.")
        return attrs


class MfaEnrollSerializer(serializers.Serializer):
    mfa_token = serializers.CharField()


class MfaEnrollResponseSerializer(serializers.Serializer):
    secret = serializers.CharField()
    otpauth_uri = serializers.CharField()


class MfaConfirmSerializer(serializers.Serializer):
    mfa_token = serializers.CharField()
    code = serializers.CharField(max_length=6)


class MfaConfirmResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    recovery_codes = serializers.ListField(child=serializers.CharField())


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class RefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)


class LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)


class CurrentOrganizationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.SlugField()


class CurrentUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    full_name = serializers.CharField()
    organization = CurrentOrganizationSerializer()
    roles = serializers.ListField(child=serializers.CharField())
    role_names = serializers.ListField(child=serializers.CharField())
    membership_id = serializers.UUIDField()
    photo_url = serializers.CharField(allow_null=True)
    has_signature = serializers.BooleanField()
    needs_signature = serializers.BooleanField()
    permissions = serializers.ListField(child=serializers.CharField())
