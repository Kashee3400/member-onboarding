SENSITIVE_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "authorization",
    "api_key",
    "aadhaar",
    "account_number",
)
REDACTED = "[REDACTED]"


def _redact(value):
    if isinstance(value, dict):
        return {
            key: REDACTED
            if any(part in str(key).lower() for part in SENSITIVE_KEY_PARTS)
            else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [_redact(item) for item in value]
    return value


def redact_sensitive_values(logger, method_name, event_dict):
    return _redact(event_dict)
