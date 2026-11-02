import pytest

from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context
from apps.organizations.models import Membership

from .conftest import PASSWORD, authenticated_client, login

pytestmark = pytest.mark.django_db(transaction=True)

LOGIN_URL = "/api/v1/auth/login/"
ME_URL = "/api/v1/auth/me/"


def test_me_returns_the_active_organization(org_a, admin_a):
    response = authenticated_client(org_a, admin_a).get(ME_URL)

    assert response.status_code == 200
    assert response.data["email"] == admin_a.email
    assert response.data["organization"]["slug"] == org_a.slug
    assert response.data["roles"] == ["org_admin"]
    assert "settings.manage" in response.data["permissions"]


def test_login_is_case_insensitive_on_email(api_client, org_a, admin_a):
    response = api_client.post(
        LOGIN_URL,
        {"email": "ADMIN@A.test", "password": PASSWORD, "organization": org_a.slug},
    )
    assert response.status_code == 200


def test_every_login_failure_looks_the_same(api_client, org_a, org_b, admin_a):
    attempts = [
        {"email": admin_a.email, "password": "wrong", "organization": org_a.slug},
        {"email": "nobody@a.test", "password": PASSWORD, "organization": org_a.slug},
        {"email": admin_a.email, "password": PASSWORD, "organization": org_b.slug},
        {"email": admin_a.email, "password": PASSWORD, "organization": "missing"},
    ]
    for attempt in attempts:
        response = api_client.post(LOGIN_URL, attempt)
        assert response.status_code == 401
        assert response.data["error"]["code"] == "invalid_credentials"


def test_failed_logins_are_kept_in_the_audit_log(api_client, org_a, admin_a):
    api_client.post(
        LOGIN_URL, {"email": admin_a.email, "password": "wrong", "organization": org_a.slug}
    )
    with organization_context(org_a.id):
        assert AuditEvent.objects.filter(action="auth.login.failed").count() == 1


def test_login_is_rate_limited(api_client, org_a, admin_a):
    attempt = {"email": admin_a.email, "password": "wrong", "organization": org_a.slug}
    statuses = [api_client.post(LOGIN_URL, attempt).status_code for _ in range(6)]
    assert statuses == [401, 401, 401, 401, 401, 429]


def test_removing_a_member_revokes_access_immediately(org_a, admin_a):
    client = authenticated_client(org_a, admin_a)
    assert client.get(ME_URL).status_code == 200

    with organization_context(org_a.id):
        Membership.objects.filter(user=admin_a).update(is_active=False)

    assert client.get(ME_URL).status_code == 401


def test_deactivating_an_organization_revokes_access_immediately(org_a, admin_a):
    client = authenticated_client(org_a, admin_a)

    org_a.is_active = False
    org_a.save()

    assert client.get(ME_URL).status_code == 401


def test_deactivating_a_user_revokes_access_immediately(org_a, admin_a):
    client = authenticated_client(org_a, admin_a)

    admin_a.is_active = False
    admin_a.save()

    assert client.get(ME_URL).status_code == 401


def test_refresh_rotates_and_the_old_token_stops_working(api_client, org_a, staff_a):
    tokens = login(api_client, org_a, staff_a)

    rotated = api_client.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]})
    assert rotated.status_code == 200
    assert rotated.data["refresh"] != tokens["refresh"]

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {rotated.data['access']}")
    assert api_client.get(ME_URL).data["organization"]["slug"] == org_a.slug

    replay = api_client.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]})
    assert replay.status_code == 401


def test_logout_invalidates_the_refresh_token(api_client, org_a, staff_a):
    tokens = login(api_client, org_a, staff_a)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    assert (
        api_client.post("/api/v1/auth/logout/", {"refresh": tokens["refresh"]}).status_code == 204
    )

    api_client.credentials()
    assert (
        api_client.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}).status_code == 401
    )


def test_rate_limits_count_each_person_behind_the_portal_separately(api_client, settings, org_a):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}
    attempt = {"email": "x@a.test", "password": "wrong", "organization": org_a.slug}

    for _ in range(5):
        api_client.post(LOGIN_URL, attempt, headers={"X-Forwarded-For": "10.0.0.1"})

    blocked = api_client.post(LOGIN_URL, attempt, headers={"X-Forwarded-For": "10.0.0.1"})
    other = api_client.post(LOGIN_URL, attempt, headers={"X-Forwarded-For": "10.0.0.2"})

    assert blocked.status_code == 429
    assert other.status_code == 401


def test_the_audit_log_records_the_real_address_behind_the_portal(api_client, settings, org_a):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}
    api_client.post(
        LOGIN_URL,
        {"email": "x@a.test", "password": "wrong", "organization": org_a.slug},
        headers={"X-Forwarded-For": "10.0.0.9"},
    )

    with organization_context(org_a.id):
        assert AuditEvent.objects.get(action="auth.login.failed").ip_address == "10.0.0.9"


def test_a_forged_address_is_ignored_when_no_proxy_is_configured(api_client, org_a):
    api_client.post(
        LOGIN_URL,
        {"email": "x@a.test", "password": "wrong", "organization": org_a.slug},
        headers={"X-Forwarded-For": "10.0.0.9"},
    )

    with organization_context(org_a.id):
        assert AuditEvent.objects.get(action="auth.login.failed").ip_address != "10.0.0.9"
