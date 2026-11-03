from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from rest_framework import serializers

from apps.rbac.models import Role

from .models import TrustedIssuer

MIN_RSA_KEY_BITS = 2048


class ExchangeRequestSerializer(serializers.Serializer):
    assertion = serializers.CharField(write_only=True)


class ExchangeResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    expires_in = serializers.IntegerField()


class TrustedIssuerSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrustedIssuer
        fields = [
            "id",
            "name",
            "issuer",
            "audience",
            "public_key",
            "default_role_code",
            "syncs_mpp_assignments",
            "is_active",
        ]

    def validate_issuer(self, value):
        organization_id = self.context["request"].user.active_membership.organization_id
        taken = TrustedIssuer.objects.filter(organization_id=organization_id, issuer=value)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError("This app is already connected.")
        return value

    def validate_public_key(self, value):
        try:
            key = serialization.load_pem_public_key(value.encode())
        except ValueError as exc:
            raise serializers.ValidationError("Must be a PEM public key.") from exc
        if not isinstance(key, RSAPublicKey) or key.key_size < MIN_RSA_KEY_BITS:
            raise serializers.ValidationError(f"Must be an RSA key of {MIN_RSA_KEY_BITS}+ bits.")
        return value

    def validate_default_role_code(self, value):
        if not value:
            return value
        role = Role.objects.filter(code=value).first()
        if role is None:
            raise serializers.ValidationError("Unknown role.")
        # A host cannot do MFA here, so it must not mint staff with sensitive access.
        if role.requires_mfa:
            raise serializers.ValidationError("Roles that require MFA cannot be auto-assigned.")
        return value
