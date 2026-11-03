"""
Field staff sign in to the standalone app with their mobile number and a code sent
to it by SMS, so they need no email or password.

Nothing is said about whether a number is registered until the code is right: an
unknown number gets the same answer and simply never receives a code. Roles that
need MFA cannot sign in this way, because a code to a phone is not enough for them.
A number that works in more than one organization chooses one after the code.
"""

import hashlib
import hmac
import secrets
import uuid

from django.conf import settings
from django.core.cache import cache
from rest_framework import exceptions

from apps.audit.services import record_event
from apps.core.exceptions import Conflict
from apps.core.tenancy import organization_context
from apps.notifications.sms import SmsFailed, SmsNotConfigured, normalize_mobile, send_otp_sms
from apps.organizations.models import Membership, Organization
from apps.rbac.services import requires_mfa

from .mfa import issue_tokens

CODE_DIGITS = 6
VALID_SECONDS = 600
RESEND_SECONDS = 30
MAX_TRIES = 5


class CodeRejected(exceptions.APIException):
    """401, also from views without authentication, where DRF would turn
    AuthenticationFailed into a 403."""

    status_code = 401
    default_code = "code_rejected"
    default_detail = "That code is not right, or it has expired. Ask for a new one."


def _hash(challenge: str, code: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(), f"mobile:{challenge}:{code}".encode(), hashlib.sha256
    ).hexdigest()


def _key(challenge: str) -> str:
    return f"mobile_login:{challenge}"


def _who(mobile: str) -> list[tuple[Organization, Membership]]:
    """Every active organization where this number may sign in."""
    found = []
    for organization in Organization.objects.filter(is_active=True).order_by("name"):
        with organization_context(organization.id):
            membership = (
                Membership.objects.select_related("user")
                .filter(mobile=mobile, is_active=True, user__is_active=True)
                .first()
            )
            if membership and not requires_mfa(membership):
                found.append((organization, membership))
    return found


def start(raw_mobile: str) -> dict:
    mobile = normalize_mobile(raw_mobile)
    if len(mobile) != 10:
        raise exceptions.ValidationError({"mobile": ["Enter a 10 digit mobile number."]})
    if not cache.add(f"mobile_login:cooldown:{mobile}", 1, timeout=RESEND_SECONDS):
        raise Conflict(f"Wait {RESEND_SECONDS} seconds before asking for another code.")

    challenge = uuid.uuid4().hex
    matches = _who(mobile)
    code = f"{secrets.randbelow(10**CODE_DIGITS):0{CODE_DIGITS}d}"
    if matches:
        # The first organization that can send SMS sends it.
        sent = False
        for organization, _ in matches:
            with organization_context(organization.id):
                try:
                    send_otp_sms(mobile, code)
                except SmsNotConfigured:
                    continue
                except SmsFailed as exc:
                    cache.delete(f"mobile_login:cooldown:{mobile}")
                    raise Conflict(str(exc)) from exc
                sent = True
                break
        if not sent:
            cache.delete(f"mobile_login:cooldown:{mobile}")
            raise Conflict("Sign-in by SMS is not set up yet. Ask your administrator.")
    cache.set(
        _key(challenge),
        {
            "hash": _hash(challenge, code),
            "tries": 0,
            "memberships": [[str(o.id), str(m.id)] for o, m in matches],
        },
        timeout=VALID_SECONDS,
    )
    return {"challenge": challenge, "expires_in": VALID_SECONDS}


def verify(challenge: str, code: str, organization_slug: str = "") -> dict:
    state = cache.get(_key(challenge))
    if not state:
        raise CodeRejected()
    state["tries"] += 1
    if state["tries"] > MAX_TRIES:
        cache.delete(_key(challenge))
        raise CodeRejected()
    if not state["memberships"] or not hmac.compare_digest(
        state["hash"], _hash(challenge, code.strip())
    ):
        cache.set(_key(challenge), state, timeout=VALID_SECONDS)
        raise CodeRejected()

    organizations = {
        organization.id: organization
        for organization in Organization.objects.filter(
            pk__in=[org for org, _ in state["memberships"]], is_active=True
        )
    }
    choices = [
        (organizations[uuid.UUID(org)], membership)
        for org, membership in state["memberships"]
        if uuid.UUID(org) in organizations
    ]
    if organization_slug:
        choices = [pair for pair in choices if pair[0].slug == organization_slug]
    if len(choices) > 1:
        # The code was right: keep it for the second step, which names the organization.
        cache.set(_key(challenge), state, timeout=VALID_SECONDS)
        return {
            "choose": [{"slug": o.slug, "name": o.name} for o, _ in choices],
        }
    if not choices:
        raise CodeRejected()

    cache.delete(_key(challenge))
    organization, membership_id = choices[0]
    with organization_context(organization.id):
        membership = Membership.objects.select_related("user").get(pk=membership_id)
        if not (membership.is_active and membership.user.is_active) or requires_mfa(membership):
            raise CodeRejected()
        record_event(
            "auth.login.succeeded", actor=membership.user, metadata={"method": "mobile_otp"}
        )
        tokens = issue_tokens(membership.user, organization, mfa=False)
    return tokens | {"organization": {"slug": organization.slug, "name": organization.name}}
