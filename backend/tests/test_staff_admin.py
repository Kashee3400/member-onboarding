import pytest

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.core.tenancy import organization_context
from apps.organizations.models import Membership

from .conftest import PASSWORD, authenticated_client, make_member

pytestmark = pytest.mark.django_db(transaction=True)

STAFF_URL = "/api/v1/staff/"


def membership_of(org, user):
    with organization_context(org.id):
        return Membership.objects.get(user=user)


def reset_url(org, user):
    return f"{STAFF_URL}{membership_of(org, user).id}/password-reset/"


def test_admin_corrects_a_name(org_a, admin_a, staff_a):
    client = authenticated_client(org_a, admin_a)

    response = client.patch(
        f"{STAFF_URL}{membership_of(org_a, staff_a).id}/",
        {"full_name": " Sunita Rai "},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["full_name"] == "Sunita Rai"


def test_a_blank_name_is_refused(org_a, admin_a, staff_a):
    client = authenticated_client(org_a, admin_a)

    response = client.patch(
        f"{STAFF_URL}{membership_of(org_a, staff_a).id}/", {"full_name": ""}, format="json"
    )

    assert response.status_code == 400


def patch_staff(org, admin, staff, body):
    return authenticated_client(org, admin).patch(
        f"{STAFF_URL}{membership_of(org, staff).id}/", body, format="json"
    )


def test_admin_corrects_an_email(org_a, admin_a, staff_a, api_client):
    response = patch_staff(org_a, admin_a, staff_a, {"email": " Sunita.Rai@Example.com "})

    assert response.status_code == 200, response.content
    assert response.data["email"] == "sunita.rai@example.com"
    login = api_client.post(
        "/api/v1/auth/login/",
        {"email": "sunita.rai@example.com", "password": PASSWORD, "organization": org_a.slug},
        format="json",
    )
    assert login.status_code == 200, login.content
    with organization_context(org_a.id):
        event = AuditEvent.objects.filter(action="staff.updated").latest("occurred_at")
    assert event.metadata["email_to"] == "sunita.rai@example.com"


def test_an_email_another_account_has_is_refused(org_a, admin_a, staff_a):
    response = patch_staff(org_a, admin_a, staff_a, {"email": admin_a.email.upper()})

    assert response.status_code == 409
    staff_a.refresh_from_db()
    assert staff_a.email != admin_a.email


def test_an_email_shared_with_another_organization_is_left_alone(org_a, org_b, admin_a, staff_a):
    with organization_context(org_b.id):
        Membership.objects.create(organization=org_b, user=staff_a)

    response = patch_staff(org_a, admin_a, staff_a, {"email": "new@example.com"})

    assert response.status_code == 409


def test_reset_gives_a_one_time_password(org_a, admin_a, staff_a, api_client):
    response = authenticated_client(org_a, admin_a).post(reset_url(org_a, staff_a))

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    password = response.data["temporary_password"]
    staff_a.refresh_from_db()
    assert staff_a.must_change_password
    assert staff_a.check_password(password)
    assert not staff_a.check_password(PASSWORD)


def test_reset_is_audited_without_the_password(org_a, admin_a, staff_a):
    password = (
        authenticated_client(org_a, admin_a)
        .post(reset_url(org_a, staff_a))
        .data["temporary_password"]
    )

    with organization_context(org_a.id):
        event = AuditEvent.objects.get(action="staff.password_reset")
    assert event.actor_id == admin_a.pk
    assert password not in str(event.metadata)


def test_reset_needs_staff_manage(org_a, staff_a):
    other = make_member(org_a, "other@a.test", "facilitator")

    assert authenticated_client(org_a, other).post(reset_url(org_a, staff_a)).status_code == 403


def test_nobody_resets_their_own(org_a, admin_a):
    assert authenticated_client(org_a, admin_a).post(reset_url(org_a, admin_a)).status_code == 403


def test_a_connected_app_account_has_no_password_here(org_a, admin_a):
    user = User.objects.create_user("field@a.test", None)
    with organization_context(org_a.id):
        Membership.objects.create(organization=org_a, user=user)

    assert authenticated_client(org_a, admin_a).post(reset_url(org_a, user)).status_code == 409


def test_an_account_shared_with_another_organization_is_left_alone(org_a, org_b, admin_a, staff_a):
    with organization_context(org_b.id):
        Membership.objects.create(organization=org_b, user=staff_a)
    client = authenticated_client(org_a, admin_a)

    assert client.post(reset_url(org_a, staff_a)).status_code == 409
    response = client.patch(
        f"{STAFF_URL}{membership_of(org_a, staff_a).id}/", {"full_name": "Changed"}, format="json"
    )
    assert response.status_code == 409
    staff_a.refresh_from_db()
    assert staff_a.check_password(PASSWORD)
    assert staff_a.full_name != "Changed"


def test_another_organizations_staff_cannot_be_reset(org_a, org_b, admin_a, admin_b):
    assert authenticated_client(org_b, admin_b).post(reset_url(org_a, admin_a)).status_code == 404


def test_audit_shows_who_acted(org_a, admin_a):
    admin_a.full_name = "Asha Admin"
    admin_a.save()
    with organization_context(org_a.id):
        record_event("something.done", actor=admin_a)
        record_event("something.automatic")

    rows = authenticated_client(org_a, admin_a).get("/api/v1/audit/events/").data["results"]

    names = {row["action"]: row["actor_name"] for row in rows}
    assert names["something.done"] == "Asha Admin"
    assert names["something.automatic"] == ""
