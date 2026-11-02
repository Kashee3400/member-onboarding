import time
from unittest import mock

import pyotp
import pytest
from rest_framework.test import APIClient

from apps.accounts import mfa
from apps.accounts.models import MfaDevice, MfaRecoveryCode
from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context
from apps.organizations.models import Membership
from apps.rbac.models import Role

from .conftest import PASSWORD, authenticated_client, make_member

pytestmark = pytest.mark.django_db(transaction=True)

LOGIN = "/api/v1/auth/login/"
VERIFY = "/api/v1/auth/mfa/verify/"
ENROLL = "/api/v1/auth/mfa/enroll/"
CONFIRM = "/api/v1/auth/mfa/enroll/confirm/"
ME = "/api/v1/auth/me/"


def password_step(client, org, user):
    response = client.post(
        LOGIN, {"email": user.email, "password": PASSWORD, "organization": org.slug}
    )
    assert response.status_code == 200, response.content
    return response.data


def enroll(client, org, user):
    """Complete first-time setup and return the secret, recovery codes and tokens."""
    token = password_step(client, org, user)["mfa_token"]
    secret = client.post(ENROLL, {"mfa_token": token}).data["secret"]
    response = client.post(CONFIRM, {"mfa_token": token, "code": pyotp.TOTP(secret).now()})
    assert response.status_code == 200, response.content
    return secret, response.data


def next_code(secret):
    """A code one step ahead, valid within drift and unused by the enrollment."""
    return pyotp.TOTP(secret).at(time.time() + 30)


def test_roles_without_mfa_get_tokens_straight_away(api_client, org_a, staff_a):
    assert "access" in password_step(api_client, org_a, staff_a)


@pytest.mark.parametrize("role", ["org_admin", "cs_legal", "finance"])
def test_sensitive_roles_must_set_up_mfa_first(api_client, org_a, role):
    user = make_member(org_a, f"{role}@a.test", role)

    result = password_step(api_client, org_a, user)

    assert result["mfa_status"] == "enroll"
    assert "access" not in result


def test_a_challenge_token_opens_no_api(api_client, org_a, admin_a):
    token = password_step(api_client, org_a, admin_a)["mfa_token"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert api_client.get(ME).status_code == 401


def test_a_challenge_token_cannot_be_refreshed(api_client, org_a, admin_a):
    token = password_step(api_client, org_a, admin_a)["mfa_token"]
    assert api_client.post("/api/v1/auth/refresh/", {"refresh": token}).status_code == 401


def test_enrollment_gives_access_and_recovery_codes(api_client, org_a, admin_a):
    _, result = enroll(api_client, org_a, admin_a)

    assert len(result["recovery_codes"]) == mfa.RECOVERY_CODE_COUNT
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {result['access']}")
    assert api_client.get(ME).status_code == 200


def test_secrets_and_recovery_codes_are_not_stored_in_clear(api_client, org_a, admin_a):
    secret, result = enroll(api_client, org_a, admin_a)

    assert secret not in MfaDevice.objects.get(user=admin_a).encrypted_secret
    stored = set(MfaRecoveryCode.objects.values_list("code_hash", flat=True))
    assert not stored & set(result["recovery_codes"])


def test_a_wrong_enrollment_code_is_rejected(api_client, org_a, admin_a):
    token = password_step(api_client, org_a, admin_a)["mfa_token"]
    api_client.post(ENROLL, {"mfa_token": token})

    assert api_client.post(CONFIRM, {"mfa_token": token, "code": "000000"}).status_code == 401
    assert not MfaDevice.objects.filter(user=admin_a, confirmed_at__isnull=False).exists()


def test_a_stolen_password_cannot_replace_an_existing_authenticator(api_client, org_a, admin_a):
    enroll(api_client, org_a, admin_a)
    token = password_step(api_client, org_a, admin_a)["mfa_token"]

    assert api_client.post(ENROLL, {"mfa_token": token}).status_code == 409


def test_later_logins_ask_for_a_code(api_client, org_a, admin_a):
    secret, _ = enroll(api_client, org_a, admin_a)

    challenge = password_step(api_client, org_a, admin_a)
    assert challenge["mfa_status"] == "verify"

    response = api_client.post(
        VERIFY, {"mfa_token": challenge["mfa_token"], "code": next_code(secret)}
    )
    assert response.status_code == 200
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    assert api_client.get(ME).status_code == 200


def test_a_code_cannot_be_used_twice(api_client, org_a, admin_a):
    secret, _ = enroll(api_client, org_a, admin_a)
    code = next_code(secret)

    first = password_step(api_client, org_a, admin_a)["mfa_token"]
    assert api_client.post(VERIFY, {"mfa_token": first, "code": code}).status_code == 200

    second = password_step(api_client, org_a, admin_a)["mfa_token"]
    assert api_client.post(VERIFY, {"mfa_token": second, "code": code}).status_code == 401


def test_a_challenge_opens_only_one_session(api_client, org_a, admin_a):
    secret, _ = enroll(api_client, org_a, admin_a)
    token = password_step(api_client, org_a, admin_a)["mfa_token"]

    assert (
        api_client.post(VERIFY, {"mfa_token": token, "code": next_code(secret)}).status_code == 200
    )

    later = pyotp.TOTP(secret).at(time.time() + 60)
    with mock.patch("apps.accounts.mfa.time.time", return_value=time.time() + 60):
        assert api_client.post(VERIFY, {"mfa_token": token, "code": later}).status_code == 401


def test_wrong_guesses_burn_the_challenge(api_client, org_a, admin_a):
    secret, _ = enroll(api_client, org_a, admin_a)
    token = password_step(api_client, org_a, admin_a)["mfa_token"]

    with mock.patch(
        "rest_framework.throttling.ScopedRateThrottle.allow_request", return_value=True
    ):
        for _ in range(mfa.MAX_ATTEMPTS_PER_CHALLENGE):
            assert (
                api_client.post(VERIFY, {"mfa_token": token, "code": "000000"}).status_code == 401
            )

        correct = api_client.post(VERIFY, {"mfa_token": token, "code": next_code(secret)})

    assert correct.status_code == 401


def test_failed_codes_are_audited(api_client, org_a, admin_a):
    enroll(api_client, org_a, admin_a)
    token = password_step(api_client, org_a, admin_a)["mfa_token"]

    api_client.post(VERIFY, {"mfa_token": token, "code": "000000"})

    with organization_context(org_a.id):
        assert AuditEvent.objects.filter(action="auth.mfa.failed").count() == 1


def test_a_recovery_code_works_once(api_client, org_a, admin_a):
    _, result = enroll(api_client, org_a, admin_a)
    code = result["recovery_codes"][0]

    first = password_step(api_client, org_a, admin_a)["mfa_token"]
    assert api_client.post(VERIFY, {"mfa_token": first, "recovery_code": code}).status_code == 200

    second = password_step(api_client, org_a, admin_a)["mfa_token"]
    assert api_client.post(VERIFY, {"mfa_token": second, "recovery_code": code}).status_code == 401


def test_verify_needs_exactly_one_factor(api_client, org_a, admin_a):
    token = password_step(api_client, org_a, admin_a)["mfa_token"]
    assert api_client.post(VERIFY, {"mfa_token": token}).status_code == 400


def test_a_session_without_mfa_loses_access_when_the_role_starts_requiring_it(
    api_client, org_a, staff_a
):
    tokens = password_step(api_client, org_a, staff_a)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert api_client.get(ME).status_code == 200

    with organization_context(org_a.id):
        Role.objects.filter(code="facilitator").update(requires_mfa=True)

    response = api_client.get(ME)
    assert response.status_code == 401
    assert response.data["error"]["code"] == "mfa_required"


def test_an_admin_can_reset_someones_mfa(org_a, admin_a):
    finance = make_member(org_a, "finance@a.test", "finance")
    secret_client = APIClient()
    enroll(secret_client, org_a, finance)
    with organization_context(org_a.id):
        membership = Membership.objects.get(user=finance)

    response = authenticated_client(org_a, admin_a).post(
        f"/api/v1/staff/{membership.id}/mfa-reset/"
    )

    assert response.status_code == 204
    assert not MfaDevice.objects.filter(user=finance).exists()
    assert password_step(secret_client, org_a, finance)["mfa_status"] == "enroll"


def test_nobody_can_reset_their_own_mfa(org_a, admin_a):
    with organization_context(org_a.id):
        membership = Membership.objects.get(user=admin_a)

    response = authenticated_client(org_a, admin_a).post(
        f"/api/v1/staff/{membership.id}/mfa-reset/"
    )

    assert response.status_code == 403


def test_mfa_cannot_be_reset_without_permission(org_a, admin_a, staff_a):
    with organization_context(org_a.id):
        membership = Membership.objects.get(user=admin_a)

    response = authenticated_client(org_a, staff_a).post(
        f"/api/v1/staff/{membership.id}/mfa-reset/"
    )

    assert response.status_code == 403
