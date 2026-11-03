import uuid
from dataclasses import dataclass

import jwt
import structlog
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction

from apps.audit.services import record_event
from apps.core.tenancy import organization_context
from apps.hierarchy.models import Mpp, MppAssignment, Responsibility
from apps.hierarchy.services import assign_mpp, end_assignment
from apps.organizations.models import Membership
from apps.rbac.services import grant_role

from .models import ExternalIdentity, TrustedIssuer

logger = structlog.get_logger(__name__)

ALLOWED_ALGORITHM = "RS256"
MAX_ASSERTION_LIFETIME_SECONDS = 300
CLOCK_LEEWAY_SECONDS = 30
REQUIRED_CLAIMS = ["iss", "aud", "sub", "exp", "iat", "jti"]


class AssertionRejected(Exception):
    """The reason is for logs only. Callers always get the same response."""


@dataclass(frozen=True)
class VerifiedAssertion:
    issuer: TrustedIssuer
    subject: str
    name: str
    mpp_codes: tuple[str, ...]


def verify_assertion(token: str) -> VerifiedAssertion:
    try:
        issuer_name = jwt.decode(token, options={"verify_signature": False}).get("iss")
    except jwt.InvalidTokenError as exc:
        raise AssertionRejected("malformed") from exc

    candidates = list(
        TrustedIssuer.objects.select_related("organization")
        .filter(issuer=issuer_name, is_active=True, organization__is_active=True)
        .order_by("created_at")
    )
    if not candidates:
        raise AssertionRejected("unknown_issuer")

    # Only an organization whose own key and audience accept the token is in the
    # running, so one organization's key can never sign someone into another.
    verified, failure, claims = [], None, None
    for candidate in candidates:
        try:
            claims = jwt.decode(
                token,
                candidate.public_key,
                # Pinned, so a forged token cannot choose a weaker algorithm for itself.
                algorithms=[ALLOWED_ALGORITHM],
                audience=candidate.audience,
                issuer=candidate.issuer,
                leeway=CLOCK_LEEWAY_SECONDS,
                options={"require": REQUIRED_CLAIMS},
            )
        except jwt.InvalidTokenError as exc:
            failure = exc
            continue
        verified.append(candidate)
    if not verified:
        raise AssertionRejected(type(failure).__name__) from failure

    if claims["exp"] - claims["iat"] > MAX_ASSERTION_LIFETIME_SECONDS:
        raise AssertionRejected("lifetime_too_long")

    # Keyed by the host, not the organization, so one token is used once in all.
    replay_window = MAX_ASSERTION_LIFETIME_SECONDS + CLOCK_LEEWAY_SECONDS
    if not cache.add(f"assertion:{issuer_name}:{claims['jti']}", 1, timeout=replay_window):
        raise AssertionRejected("replayed")

    mpps = claims.get("mpps", [])
    if not isinstance(mpps, list) or not all(isinstance(code, str) for code in mpps):
        raise AssertionRejected("invalid_mpps")

    issuer = _organization_for(verified, mpps)

    return VerifiedAssertion(
        issuer=issuer,
        subject=str(claims["sub"]),
        name=str(claims.get("name", ""))[:200],
        mpp_codes=tuple(mpps),
    )


def _organization_for(verified: list[TrustedIssuer], mpps: list[str]) -> TrustedIssuer:
    """
    The one organization this person works for. With a single organization trusting
    the host there is nothing to choose; otherwise it is whoever owns their MPPs.
    """
    if len(verified) == 1:
        return verified[0]
    owners = []
    for candidate in verified:
        with organization_context(candidate.organization_id):
            if Mpp.objects.filter(source_code__in=mpps, is_active=True).exists():
                owners.append(candidate)
    if not owners:
        raise AssertionRejected("no_organization_owns_the_mpps")
    if len(owners) > 1:
        # Someone with MPPs in two companies: refused rather than guessed.
        raise AssertionRejected("mpps_in_several_organizations")
    return owners[0]


def _provision(assertion: VerifiedAssertion) -> Membership:
    """First sign-in. The email is synthetic, so no host can claim a local account."""
    issuer = assertion.issuer
    user = get_user_model().objects.create_user(
        f"ext-{uuid.uuid4().hex}@external.invalid", None, full_name=assertion.name
    )
    membership = Membership.objects.create(organization=issuer.organization, user=user)
    if issuer.default_role_code:
        grant_role(membership, issuer.default_role_code)
    ExternalIdentity.objects.create(issuer=issuer, subject=assertion.subject, membership=membership)
    record_event("federation.user_provisioned", actor=user, target=membership)
    return membership


def resolve_membership(assertion: VerifiedAssertion) -> Membership | None:
    """Runs inside the issuer's organization. Returns None for a disabled account."""
    identity = (
        ExternalIdentity.objects.select_related("membership__user")
        .filter(issuer=assertion.issuer, subject=assertion.subject)
        .first()
    )
    if identity is None:
        return _provision(assertion)

    membership = identity.membership
    user = membership.user
    if not membership.is_active or not user.is_active:
        return None

    if assertion.name and assertion.name != user.full_name:
        user.full_name = assertion.name
        user.save(update_fields=["full_name", "updated_at"])
    return membership


@transaction.atomic
def sync_mpp_assignments(membership, codes, *, actor) -> None:
    """Make the host's list true here, including handing over MPPs that moved."""
    wanted = {
        mpp.source_code: mpp for mpp in Mpp.objects.filter(source_code__in=codes, is_active=True)
    }

    if unknown := set(codes) - set(wanted):
        logger.warning("federation_unknown_mpps", mpps=sorted(unknown))

    current = MppAssignment.objects.filter(
        membership=membership,
        responsibility=Responsibility.FACILITATOR,
        ended_at__isnull=True,
    ).select_related("mpp")

    for assignment in current:
        if assignment.mpp.source_code not in wanted:
            end_assignment(
                mpp=assignment.mpp, responsibility=Responsibility.FACILITATOR, actor=actor
            )

    for mpp in wanted.values():
        assign_mpp(
            mpp=mpp,
            membership=membership,
            responsibility=Responsibility.FACILITATOR,
            actor=actor,
        )
