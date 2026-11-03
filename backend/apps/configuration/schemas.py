from dataclasses import dataclass


@dataclass(frozen=True)
class IntegrationSchema:
    config_fields: frozenset[str]
    secret_fields: frozenset[str]


INTEGRATION_SCHEMAS = {
    "mail": IntegrationSchema(
        config_fields=frozenset({"host", "port", "username", "use_tls", "from_email"}),
        secret_fields=frozenset({"password"}),
    ),
    # The gateway Kashee's ERP sends its OTPs through, with DLT-registered templates.
    "sms": IntegrationSchema(
        config_fields=frozenset(
            {
                "provider",
                "base_url",
                "user_id",
                "sender_id",
                "dlt_entity_id",
                "otp_template_id",
                "otp_message",
            }
        ),
        secret_fields=frozenset({"password"}),
    ),
    # Firebase Cloud Messaging for the host app's phones: the service account key file.
    "push": IntegrationSchema(
        config_fields=frozenset(),
        secret_fields=frozenset({"service_account"}),
    ),
    "whatsapp": IntegrationSchema(
        config_fields=frozenset({"provider", "base_url", "phone_number_id"}),
        secret_fields=frozenset({"api_key"}),
    ),
}
