"""
Push notifications to staff phones through Firebase Cloud Messaging (HTTP v1).

The host app's Firebase service account lives under Integrations, encrypted, never in
the env: each organization's app can bring its own Firebase project. Sent with the
standard library and PyJWT, like the SMS gateway, so no SDK is needed.
"""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import jwt
import structlog
from django.core.cache import cache

from apps.configuration.models import IntegrationConfig
from apps.core.tenancy import get_current_organization_id

logger = structlog.get_logger(__name__)

TIMEOUT_SECONDS = 10
SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"
CHANNEL = "member_onboarding"
REQUIRED_KEYS = ("project_id", "client_email", "private_key", "token_uri")
# Google's tokens last an hour; a few minutes are kept back so one never expires mid-send.
TOKEN_SECONDS = 3300


class PushNotConfigured(Exception):
    pass


class PushFailed(Exception):
    """Firebase could not be reached or refused the credentials. Safe to show."""


def parse_service_account(text: str) -> dict:
    """The JSON key file as Firebase gives it, or ValueError saying what is wrong."""
    try:
        account = json.loads(text)
    except ValueError as exc:
        raise ValueError("This is not the JSON key file from Firebase.") from exc
    if not isinstance(account, dict) or account.get("type") != "service_account":
        raise ValueError("This is not a service account key file.")
    if missing := [key for key in REQUIRED_KEYS if not account.get(key)]:
        raise ValueError(f"The key file is missing: {', '.join(missing)}.")
    return account


def _account() -> dict:
    integration = IntegrationConfig.objects.filter(kind="push", is_enabled=True).first()
    if integration is None:
        raise PushNotConfigured
    text = integration.get_secrets().get("service_account")
    if not text:
        raise PushNotConfigured
    try:
        return parse_service_account(text)
    except ValueError as exc:
        raise PushNotConfigured from exc


def _post(url: str, body: bytes, headers: dict) -> dict:
    # Only Google's own token and FCM addresses come here.
    request = Request(url, data=body, headers=headers, method="POST")  # noqa: S310
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        return json.loads(response.read() or b"{}")


def access_token(account: dict) -> str:
    """A short-lived OAuth token for FCM, kept in the cache until shortly before it ends."""
    key = f"fcm-token:{get_current_organization_id()}:{account['client_email']}"
    if cached := cache.get(key):
        return cached
    now = int(time.time())
    assertion = jwt.encode(
        {
            "iss": account["client_email"],
            "scope": SCOPE,
            "aud": account["token_uri"],
            "iat": now,
            "exp": now + 3600,
        },
        account["private_key"],
        algorithm="RS256",
    )
    try:
        body = _post(
            account["token_uri"],
            urlencode(
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                }
            ).encode(),
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
    except HTTPError as exc:
        raise PushFailed("Google refused the key file. Make a new key in Firebase.") from exc
    except (URLError, OSError) as exc:
        raise PushFailed("Google could not be reached.") from exc
    token = body.get("access_token")
    if not token:
        raise PushFailed("Google gave no access token.")
    cache.set(key, token, TOKEN_SECONDS)
    return token


def check_credentials() -> None:
    """Proves the saved key works, without sending anything to anyone."""
    account = _account()
    cache.delete(f"fcm-token:{get_current_organization_id()}:{account['client_email']}")
    access_token(account)


def send(tokens: list[str], *, title: str, body: str, data: dict[str, str]) -> list[str]:
    """Sends to each phone. Returns the tokens Firebase says no longer exist."""
    account = _account()
    bearer = access_token(account)
    url = f"https://fcm.googleapis.com/v1/projects/{account['project_id']}/messages:send"
    gone = []
    for token in tokens:
        message = {
            "message": {
                "token": token,
                "notification": {"title": title, "body": body},
                "data": data,
                "android": {
                    "priority": "high",
                    "notification": {"channel_id": "member_onboarding"},
                },
            }
        }
        try:
            _post(
                url,
                json.dumps(message).encode(),
                {"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"},
            )
        except HTTPError as exc:
            # 404 UNREGISTERED, or 400 for a token that was never valid: the phone is gone.
            if exc.code in (400, 404):
                gone.append(token)
            else:
                logger.warning("push_failed", status=exc.code)
        except URLError, OSError:
            logger.warning("push_unreachable")
    return gone
