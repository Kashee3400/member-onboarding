from rest_framework import serializers

from .schemas import INTEGRATION_SCHEMAS


class IntegrationReadSerializer(serializers.Serializer):
    """Never includes secret values, only the names of those that are set."""

    kind = serializers.CharField()
    is_enabled = serializers.BooleanField()
    config = serializers.JSONField()
    configured_secrets = serializers.ListField(child=serializers.CharField())


class IntegrationWriteSerializer(serializers.Serializer):
    is_enabled = serializers.BooleanField(required=False)
    config = serializers.JSONField(required=False)
    secrets = serializers.DictField(
        child=serializers.CharField(allow_null=True, trim_whitespace=False),
        required=False,
        write_only=True,
        help_text="Merged into stored secrets. Omitted names are kept; null removes one.",
    )

    def validate(self, attrs):
        schema = INTEGRATION_SCHEMAS[self.context["kind"]]
        errors = {}

        config = attrs.get("config")
        if config is not None:
            if not isinstance(config, dict):
                errors["config"] = ["Must be an object."]
            elif unknown := set(config) - schema.config_fields:
                errors["config"] = [f"Unknown fields: {', '.join(sorted(unknown))}"]

        message = (config or {}).get("otp_message") if isinstance(config, dict) else None
        if self.context["kind"] == "sms" and message and "{otp}" not in message:
            errors["config"] = ["The OTP message must contain {otp} where the code goes."]

        if unknown := set(attrs.get("secrets", {})) - schema.secret_fields:
            errors["secrets"] = [f"Unknown fields: {', '.join(sorted(unknown))}"]

        key_file = attrs.get("secrets", {}).get("service_account")
        if self.context["kind"] == "push" and key_file:
            # Imported here: notifications reads integrations, not the other way round.
            from apps.notifications.push import parse_service_account

            try:
                parse_service_account(key_file)
            except ValueError as exc:
                errors["secrets"] = [str(exc)]

        if errors:
            raise serializers.ValidationError(errors)
        return attrs
