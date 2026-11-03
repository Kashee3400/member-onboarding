"""
Text messages through the gateway Kashee's ERP already uses (DLT-registered templates,
sent as one GET request). Its details live under Integrations, never in the env.
"""

import json
import re
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import structlog

from apps.configuration.models import IntegrationConfig

from .failures import record_failure

logger = structlog.get_logger(__name__)

TIMEOUT_SECONDS = 10
OTP_PLACEHOLDER = "{otp}"
REQUIRED = ("base_url", "user_id", "sender_id", "dlt_entity_id", "otp_template_id", "otp_message")

# The gateway takes the password in the query string, so it must never reach a log.
_SECRET_PARAM = re.compile(r"((?:password|mobile|msg)=)[^&\s'\"]*", re.IGNORECASE)


class SmsNotConfigured(Exception):
    pass


class SmsFailed(Exception):
    """The gateway could not be reached or refused the message. Safe to show."""


def _redact(text: str) -> str:
    return _SECRET_PARAM.sub(r"\1***", text)


def normalize_mobile(mobile: str) -> str:
    digits = "".join(filter(str.isdigit, str(mobile)))
    return digits[2:] if digits.startswith("91") and len(digits) == 12 else digits


def _settings():
    integration = IntegrationConfig.objects.filter(kind="sms", is_enabled=True).first()
    if integration is None:
        raise SmsNotConfigured
    config = integration.config
    password = integration.get_secrets().get("password")
    if not password or any(not config.get(name) for name in REQUIRED):
        raise SmsNotConfigured
    return config, password


def send_otp_sms(mobile: str, code: str) -> str:
    """Sends the OTP template with this code. Returns the gateway's message id."""
    config, password = _settings()
    params = {
        "userid": config["user_id"],
        "output": "json",
        "password": password,
        "sendMethod": "quick",
        "mobile": normalize_mobile(mobile),
        "msg": config["otp_message"].replace(OTP_PLACEHOLDER, code),
        "senderid": config["sender_id"],
        "msgType": "unicode",
        "dltEntityId": config["dlt_entity_id"],
        "dltTemplateId": config["otp_template_id"],
        "duplicatecheck": "true",
    }
    url = f"{config['base_url']}?{urlencode(params)}"
    try:
        with urlopen(Request(url, method="GET"), timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8") or "{}")
    except (URLError, OSError, ValueError) as exc:
        logger.error("sms_gateway_unreachable", error=_redact(f"{type(exc).__name__}: {exc}"))
        record_failure("sms", "The SMS gateway could not be reached.")
        raise SmsFailed("Could not reach the SMS gateway. Try again in a few minutes.") from None

    status = str(data.get("status", "")).lower()
    if status == "success" or str(data.get("errorCode", "")).strip() == "000":
        return str(data.get("msgid") or data.get("requestId") or "")
    reason = str(data.get("reason") or data.get("message") or "The gateway refused the message.")
    logger.error("sms_gateway_refused", reason=_redact(reason)[:200])
    record_failure("sms", _redact(reason))
    raise SmsFailed(_redact(reason)[:200])
