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
    "sms": IntegrationSchema(
        config_fields=frozenset({"provider", "base_url", "sender_id"}),
        secret_fields=frozenset({"api_key"}),
    ),
    "whatsapp": IntegrationSchema(
        config_fields=frozenset({"provider", "base_url", "phone_number_id"}),
        secret_fields=frozenset({"api_key"}),
    ),
}
