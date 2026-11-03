import pytest
from rest_framework.test import APIClient

from apps.core.tenancy import organization_context
from apps.organizations.models import Membership

from .conftest import authenticated_client, make_member

pytestmark = pytest.mark.django_db(transaction=True)

START = "/api/v1/auth/mobile/start/"
VERIFY = "/api/v1/auth/mobile/verify/"
STAFF = "/api/v1/staff/"
ME = "/api/v1/auth/me/"
MOBILE = "9876543210"


@pytest.fixture
def sent(monkeypatch):
    """The SMS gateway, faked: each code lands here instead of on a phone."""
    codes = []
    monkeypatch.setattr(
        "apps.accounts.mobile_login.send_otp_sms", lambda mobile, code: codes.append((mobile, code))
    )
    return codes


def with_mobile(organization, email, role, mobile=MOBILE):
    user = make_member(organization, email, role)
    with organization_context(organization.id):
        Membership.objects.filter(user=user).update(mobile=mobile)
    return user


def start(mobile=MOBILE):
    return APIClient().post(START, {"mobile": mobile}, format="json")


def verify(challenge, code, organization=""):
    body = {"challenge": challenge, "code": code, "organization": organization}
    return APIClient().post(VERIFY, body, format="json")


def signed_in(response):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    return client.get(ME).data


def test_a_facilitator_signs_in_with_a_code_by_sms(org_a, sent):
    with_mobile(org_a, "field@a.test", "facilitator")

    challenge = start().data["challenge"]
    response = verify(challenge, sent[-1][1])

    assert response.status_code == 200, response.content
    assert response.data["organization"]["slug"] == "org-a"
    assert signed_in(response)["email"] == "field@a.test"
    assert sent[-1][0] == MOBILE


def test_an_unknown_number_looks_the_same_and_gets_no_code(org_a, sent):
    response = start("9123456780")

    assert response.status_code == 200
    assert set(response.data) == {"challenge", "expires_in"}
    assert sent == []
    assert verify(response.data["challenge"], "000000").status_code == 401


def test_a_wrong_code_is_refused_and_tries_run_out(org_a, sent):
    with_mobile(org_a, "field@a.test", "facilitator")
    challenge = start().data["challenge"]
    right = sent[-1][1]
    wrong = "000000" if right != "000000" else "111111"

    for _ in range(5):
        assert verify(challenge, wrong).status_code == 401
    assert verify(challenge, right).status_code == 401


def test_a_code_works_once(org_a, sent):
    with_mobile(org_a, "field@a.test", "facilitator")
    challenge = start().data["challenge"]

    assert verify(challenge, sent[-1][1]).status_code == 200
    assert verify(challenge, sent[-1][1]).status_code == 401


def test_roles_that_need_mfa_cannot_use_a_code(org_a, sent):
    with_mobile(org_a, "admin@a.test", "org_admin")

    challenge = start().data["challenge"]

    assert sent == []
    assert verify(challenge, "123456").status_code == 401


def test_a_number_in_two_organizations_chooses_after_the_code(org_a, org_b, sent):
    with_mobile(org_a, "field@a.test", "facilitator")
    with_mobile(org_b, "field@b.test", "facilitator")
    challenge = start().data["challenge"]
    code = sent[-1][1]

    asked = verify(challenge, code)
    assert {choice["slug"] for choice in asked.data["choose"]} == {"org-a", "org-b"}
    chosen = verify(challenge, code, "org-b")

    assert chosen.data["organization"]["slug"] == "org-b"
    assert signed_in(chosen)["email"] == "field@b.test"


def test_a_second_code_waits_a_little(org_a, sent):
    with_mobile(org_a, "field@a.test", "facilitator")

    assert start().status_code == 200
    assert start().status_code == 409


def test_without_sms_set_up_the_app_says_so(org_a, monkeypatch):
    from apps.notifications.sms import SmsNotConfigured

    def not_set_up(mobile, code):
        raise SmsNotConfigured

    monkeypatch.setattr("apps.accounts.mobile_login.send_otp_sms", not_set_up)
    with_mobile(org_a, "field@a.test", "facilitator")

    assert start().status_code == 409


# Staff with a mobile and no email ------------------------------------------------------


def facilitator_role_id(organization):
    from apps.rbac.models import Role

    with organization_context(organization.id):
        return str(Role.objects.get(code="facilitator").id)


def test_an_admin_adds_a_facilitator_by_mobile_alone(org_a, admin_a, sent):
    client = authenticated_client(org_a, admin_a)

    response = client.post(
        STAFF,
        {"full_name": "Field Person", "mobile": MOBILE, "role_ids": [facilitator_role_id(org_a)]},
        format="json",
    )

    assert response.status_code == 201, response.content
    assert response.data["email"] == ""
    assert response.data["mobile"] == MOBILE
    assert "invite_link" not in response.data
    challenge = start().data["challenge"]
    assert verify(challenge, sent[-1][1]).status_code == 200


def test_a_mobile_is_used_once_per_organization(org_a, admin_a):
    client = authenticated_client(org_a, admin_a)
    body = {"full_name": "One", "mobile": MOBILE, "role_ids": [facilitator_role_id(org_a)]}

    assert client.post(STAFF, body, format="json").status_code == 201
    assert client.post(STAFF, body | {"full_name": "Two"}, format="json").status_code == 409


def test_staff_need_an_email_or_a_mobile(org_a, admin_a):
    client = authenticated_client(org_a, admin_a)

    body = {"full_name": "Nobody", "role_ids": [facilitator_role_id(org_a)]}
    assert client.post(STAFF, body, format="json").status_code == 400
