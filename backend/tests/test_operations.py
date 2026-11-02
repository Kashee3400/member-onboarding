import re

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.configuration.models import IntegrationConfig
from apps.core.tenancy import organization_context
from apps.notifications.models import Notification
from apps.organizations.models import Membership

from .conftest import PASSWORD, authenticated_client, login, make_member
from .test_applications import PAYMENT, URL, World  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)

NEW_PASSWORD = "A-much-better-password-77"
CHANGE = "/api/v1/auth/password/change/"
FORGOT = "/api/v1/auth/password/forgot/"
RESET = "/api/v1/auth/password/reset/"
ME = "/api/v1/auth/me/"


@pytest.fixture
def world(org_a):
    return World(org_a)


@pytest.fixture(autouse=True)
def memory_mail(settings):
    settings.MAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


def enable_mail(org):
    with organization_context(org.id):
        integration = IntegrationConfig(
            organization=org,
            kind="mail",
            is_enabled=True,
            config={"host": "smtp.test", "port": 25, "from_email": "forms@a.test"},
        )
        integration.set_secrets({"password": "x"})
        integration.save()


# Password change ---------------------------------------------------------------------


def staff_with_temporary_password(org):
    user = make_member(org, "new@a.test", "facilitator")
    User.objects.filter(pk=user.pk).update(must_change_password=True)
    return user


def test_a_new_person_must_change_the_temporary_password_first(org_a):
    client = authenticated_client(org_a, staff_with_temporary_password(org_a))

    response = client.get(ME)

    assert response.status_code == 403
    assert response.data["error"]["code"] == "password_change_required"


def test_changing_the_password_opens_the_account(org_a):
    user = staff_with_temporary_password(org_a)
    client = authenticated_client(org_a, user)

    response = client.post(CHANGE, {"current_password": PASSWORD, "new_password": NEW_PASSWORD})

    assert response.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    assert client.get(ME).status_code == 200
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)


def test_staff_created_in_the_portal_start_with_a_temporary_password(world, org_a):
    from apps.rbac.models import Role

    with organization_context(org_a.id):
        role = str(Role.objects.get(code="pib").id)
    response = world.client(world.admin).post(
        "/api/v1/staff/",
        {
            "email": "temp@a.test",
            "full_name": "Temp",
            "password": PASSWORD,
            "role_ids": [role],
        },
    )
    assert response.status_code == 201
    assert User.objects.get(email="temp@a.test").must_change_password


def test_the_current_password_is_required(org_a, staff_a):
    response = authenticated_client(org_a, staff_a).post(
        CHANGE, {"current_password": "wrong", "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 400


def test_weak_new_passwords_are_refused(org_a, staff_a):
    response = authenticated_client(org_a, staff_a).post(
        CHANGE, {"current_password": PASSWORD, "new_password": "12345"}
    )
    assert response.status_code == 400


def test_changing_the_password_ends_other_sessions(org_a, staff_a):
    elsewhere = login(APIClient(), org_a, staff_a)
    client = authenticated_client(org_a, staff_a)

    client.post(CHANGE, {"current_password": PASSWORD, "new_password": NEW_PASSWORD})

    refreshed = APIClient().post("/api/v1/auth/refresh/", {"refresh": elsewhere["refresh"]})
    assert refreshed.status_code == 401


def test_mfa_stays_satisfied_after_a_password_change(org_a, admin_a):
    client = authenticated_client(org_a, admin_a)
    response = client.post(CHANGE, {"current_password": PASSWORD, "new_password": NEW_PASSWORD})

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    assert client.get(ME).status_code == 200


# Password reset ----------------------------------------------------------------------


def reset_link():
    return re.search(r"uid=([^&]+)&token=(\S+)", mail.outbox[-1].body).groups()


def test_a_reset_mail_opens_a_new_password(org_a, staff_a, api_client):
    enable_mail(org_a)

    response = api_client.post(FORGOT, {"email": staff_a.email, "organization": org_a.slug})

    assert response.status_code == 202
    uid, token = reset_link()
    assert (
        api_client.post(
            RESET, {"uid": uid, "token": token, "new_password": NEW_PASSWORD}
        ).status_code
        == 204
    )
    staff_a.refresh_from_db()
    assert staff_a.check_password(NEW_PASSWORD)


def test_a_reset_link_works_once(org_a, staff_a, api_client):
    enable_mail(org_a)
    api_client.post(FORGOT, {"email": staff_a.email, "organization": org_a.slug})
    uid, token = reset_link()
    body = {"uid": uid, "token": token, "new_password": NEW_PASSWORD}
    api_client.post(RESET, body)

    assert api_client.post(RESET, body | {"new_password": "Yet-another-pass-88"}).status_code == 400


def test_unknown_people_get_the_same_answer_and_no_mail(org_a, api_client):
    enable_mail(org_a)

    response = api_client.post(FORGOT, {"email": "nobody@a.test", "organization": org_a.slug})

    assert response.status_code == 202
    assert mail.outbox == []


def test_a_forged_reset_is_refused(staff_a, api_client):
    body = {"uid": "bad", "token": "bad", "new_password": NEW_PASSWORD}
    assert api_client.post(RESET, body).status_code == 400


# Notifications -----------------------------------------------------------------------


def titles(world, user):
    results = world.client(user).get("/api/v1/notifications/").data["results"]
    return [item["title"] for item in results]


def test_the_area_manager_hears_about_a_new_form(world):
    world.submitted()
    assert titles(world, world.manager)[0].startswith("Application waiting")


def test_each_stage_tells_the_next_one(world):
    application = world.submitted()
    world.approve(application, world.manager)
    assert titles(world, world.legal)
    assert not titles(world, world.finance)

    world.approve(application, world.legal)
    assert titles(world, world.finance)


def test_a_rejection_reaches_the_facilitator_with_the_reason(world):
    application = world.submitted()
    world.client(world.manager).post(
        f"{URL}{application['id']}/decide/", {"decision": "rejected", "reason": "Wrong IFSC"}
    )

    item = world.client(world.facilitator).get("/api/v1/notifications/").data["results"][0]
    assert "Wrong IFSC" in item["body"]


def test_the_facilitator_gets_the_member_code(world):
    final = world.fully_approved()
    item = world.client(world.facilitator).get("/api/v1/notifications/").data["results"][0]
    assert final["tr_code"] in item["body"]


def test_notifications_are_private(world):
    world.submitted()
    other = world.member("am2@a.test", "area_manager")
    assert titles(world, other) == []


def test_reading_lowers_the_unread_count(world):
    world.submitted()
    client = world.client(world.manager)
    assert client.get("/api/v1/notifications/unread/").data == {"unread": 1}

    item = client.get("/api/v1/notifications/").data["results"][0]
    assert client.post(f"/api/v1/notifications/{item['id']}/read/").status_code == 204

    assert client.get("/api/v1/notifications/unread/").data == {"unread": 0}


def test_all_can_be_marked_read(world):
    world.submitted()
    client = world.client(world.manager)
    client.post("/api/v1/notifications/read-all/")
    assert client.get("/api/v1/notifications/unread/").data == {"unread": 0}


def test_someone_elses_notification_cannot_be_touched(world):
    world.submitted()
    item = world.client(world.manager).get("/api/v1/notifications/").data["results"][0]
    other = world.client(world.facilitator)
    assert other.post(f"/api/v1/notifications/{item['id']}/read/").status_code == 404


def test_notifications_are_emailed_when_mail_is_set_up(world, org_a):
    enable_mail(org_a)
    world.submitted()

    assert mail.outbox[-1].to == ["am@a.test"]
    assert "Application waiting" in mail.outbox[-1].subject
    with organization_context(org_a.id):
        assert Notification.objects.exclude(emailed_at=None).exists()


def test_without_mail_the_portal_copy_still_arrives(world, org_a):
    world.submitted()

    assert mail.outbox == []
    assert titles(world, world.manager)


def test_host_app_users_are_not_emailed(world, org_a):
    enable_mail(org_a)
    User.objects.filter(pk=world.manager.pk).update(email="ext-1@external.invalid")

    world.submitted()

    assert mail.outbox == []


def test_a_mail_outage_does_not_break_the_form(world, org_a, settings):
    enable_mail(org_a)
    settings.MAIL_BACKEND = "tests.test_operations.BrokenBackend"

    assert world.submitted()["status"] == "pending_am"


class BrokenBackend:
    def __init__(self, *args, **kwargs):
        pass

    def send_messages(self, messages):
        raise OSError("no route to host")


# Mail test ---------------------------------------------------------------------------


def test_the_mail_button_sends_to_the_person_pressing_it(world, org_a):
    enable_mail(org_a)
    response = world.client(world.admin).post("/api/v1/settings/integrations/mail/test/")

    assert response.status_code == 204
    assert mail.outbox[-1].to == ["admin@a.test"]


def test_the_mail_button_explains_missing_settings(world):
    response = world.client(world.admin).post("/api/v1/settings/integrations/mail/test/")
    assert response.status_code == 400


def test_the_mail_button_reports_a_failure(world, org_a, settings):
    enable_mail(org_a)
    settings.MAIL_BACKEND = "tests.test_operations.BrokenBackend"
    response = world.client(world.admin).post("/api/v1/settings/integrations/mail/test/")
    assert response.status_code == 400


def test_the_mail_button_needs_permission(world):
    response = world.client(world.manager).post("/api/v1/settings/integrations/mail/test/")
    assert response.status_code == 403


# Dashboard and handover --------------------------------------------------------------


def test_the_dashboard_counts_what_the_person_can_see(world):
    world.submitted()
    data = world.client(world.manager).get("/api/v1/applications/dashboard/").data

    assert data["by_status"]["pending_am"] == 1
    assert data["waiting_for_me"] == 1


def test_nothing_waits_for_someone_else_at_another_stage(world):
    world.submitted()
    data = world.client(world.finance).get("/api/v1/applications/dashboard/").data
    assert data["waiting_for_me"] == 0


def test_the_dashboard_needs_its_permission(world):
    response = world.client(world.facilitator).get("/api/v1/applications/dashboard/")
    assert response.status_code == 403


def test_a_handover_warns_about_open_work(world):
    draft = world.filled()
    response = world.client(world.admin).get(f"/api/v1/hierarchy/mpps/{world.mpp.id}/open-work/")

    assert response.status_code == 200
    assert [item["id"] for item in response.data["drafts"]] == [draft["id"]]
    assert response.data["drafts"][0]["last_edited_by_name"] == "field@a.test"


def test_handover_details_need_the_assign_permission(world):
    response = world.client(world.manager).get(f"/api/v1/hierarchy/mpps/{world.mpp.id}/open-work/")
    assert response.status_code == 403


def test_memberships_survive_notifications(world, org_a):
    world.submitted()
    with organization_context(org_a.id):
        assert Membership.objects.count() >= 5
