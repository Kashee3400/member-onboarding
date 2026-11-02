import hashlib
import hmac
import secrets
import time
from datetime import timedelta

import pyotp
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken, Token

from apps.audit.services import record_event
from apps.core import crypto
from apps.organizations.models import Membership
from apps.rbac.services import requires_mfa

from .models import MfaDevice, MfaRecoveryCode

TOTP_STEP_SECONDS = 30
ALLOWED_CLOCK_DRIFT_STEPS = 1
RECOVERY_CODE_COUNT = 8
MAX_ATTEMPTS_PER_CHALLENGE = 5
OTP_ISSUER = "Member Onboarding"


class MfaChallengeToken(Token):
    """Proves the password step passed. It is not an access token and opens no API."""

    token_type = "mfa_challenge"  # noqa: S105
    lifetime = timedelta(minutes=5)


def issue_tokens(user, organization, *, mfa: bool) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh["org"] = str(organization.id)
    if mfa:
        refresh["mfa"] = True
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def login_result(user, organization) -> dict:
    """Runs inside the organization's context, after the password was accepted."""
    membership = Membership.objects.get(user=user)
    enrolled = MfaDevice.objects.filter(user=user, confirmed_at__isnull=False).exists()

    if not enrolled and not requires_mfa(membership):
        record_event("auth.login.succeeded", actor=user)
        return issue_tokens(user, organization, mfa=False)

    challenge = MfaChallengeToken.for_user(user)
    challenge["org"] = str(organization.id)
    return {"mfa_status": "verify" if enrolled else "enroll", "mfa_token": str(challenge)}


def consume_attempt(challenge) -> bool:
    """Caps guesses per challenge, on top of the rate limit per caller."""
    key = f"mfa:attempts:{challenge['jti']}"
    cache.add(key, 0, timeout=int(MfaChallengeToken.lifetime.total_seconds()))
    return cache.incr(key) <= MAX_ATTEMPTS_PER_CHALLENGE


def consume_challenge(challenge) -> bool:
    """A challenge opens exactly one session."""
    key = f"mfa:used:{challenge['jti']}"
    return cache.add(key, 1, timeout=int(MfaChallengeToken.lifetime.total_seconds()))


def _encryption_context(user_id) -> str:
    return f"mfa:{user_id}"


def _secret_of(device) -> str:
    return crypto.decrypt(device.encrypted_secret, _encryption_context(device.user_id)).decode()


def start_enrollment(user) -> dict:
    secret = pyotp.random_base32()
    MfaDevice.objects.update_or_create(
        user=user,
        defaults={
            "encrypted_secret": crypto.encrypt(secret.encode(), _encryption_context(user.pk)),
            "confirmed_at": None,
            "last_used_step": 0,
        },
    )
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=OTP_ISSUER)
    return {"secret": secret, "otpauth_uri": uri}


def _matching_step(device, code: str) -> int | None:
    """Returns the time step the code belongs to, refusing any already-used step."""
    totp = pyotp.TOTP(_secret_of(device))
    current = int(time.time()) // TOTP_STEP_SECONDS
    for step in range(current - ALLOWED_CLOCK_DRIFT_STEPS, current + ALLOWED_CLOCK_DRIFT_STEPS + 1):
        expected = totp.at(step * TOTP_STEP_SECONDS)
        if step > device.last_used_step and hmac.compare_digest(expected, code):
            return step
    return None


def verify_code(device, code: str) -> bool:
    step = _matching_step(device, code)
    if step is None:
        return False
    device.last_used_step = step
    device.save(update_fields=["last_used_step", "updated_at"])
    return True


def _hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()


def use_recovery_code(user, code: str) -> bool:
    updated = MfaRecoveryCode.objects.filter(
        user=user, code_hash=_hash_recovery_code(code), used_at__isnull=True
    ).update(used_at=timezone.now())
    return updated == 1


def confirm_enrollment(device, code: str) -> list[str] | None:
    """Returns recovery codes, shown once and stored only as hashes."""
    if not verify_code(device, code):
        return None

    codes = [secrets.token_hex(5) for _ in range(RECOVERY_CODE_COUNT)]
    device.confirmed_at = timezone.now()
    device.save(update_fields=["confirmed_at", "updated_at"])
    MfaRecoveryCode.objects.filter(user=device.user).delete()
    MfaRecoveryCode.objects.bulk_create(
        MfaRecoveryCode(user=device.user, code_hash=_hash_recovery_code(code)) for code in codes
    )
    return codes


@transaction.atomic
def reset_mfa(user) -> None:
    MfaDevice.objects.filter(user=user).delete()
    MfaRecoveryCode.objects.filter(user=user).delete()
