import pytest

from apps.applications.models import Status
from apps.core.tenancy import organization_context
from apps.documents.services import set_staff_signature
from apps.organizations.models import Membership

from .test_applications import URL, World, png_bytes

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def world(org_a):
    world = World(org_a)
    with organization_context(org_a.id):
        set_staff_signature(
            Membership.objects.get(user=world.admin), raw=png_bytes(), actor=world.admin
        )
    return world


def detail(world, user, application):
    return world.client(user).get(f"{URL}{application['id']}/").data


def test_the_admin_can_act_on_every_step_at_any_stage(world):
    application = world.submitted()

    steps = detail(world, world.admin, application)["review_steps"]

    assert all(step["can_approve"] for step in steps)
    assert all(step["mine"] for step in steps)


def test_a_stage_checked_ahead_is_passed_by_itself(world):
    application = world.submitted()
    admin = world.client(world.admin)

    ahead = admin.post(
        f"{URL}{application['id']}/decide/",
        {"decision": "approved", "steps": ["member", "address", "nominee"]},
    )
    assert ahead.status_code == 200, ahead.content
    assert ahead.data["status"] == "pending_am"

    world.approve(application, world.manager)

    final = detail(world, world.finance, application)
    assert final["status"] == "pending_finance"
    stages = [item["stage"] for item in final["decisions"] if item["decision"] == "approved"]
    assert stages == ["pending_am", "pending_cs"]


def test_others_see_only_what_is_left_after_the_admin(world):
    application = world.submitted()
    world.client(world.admin).post(
        f"{URL}{application['id']}/decide/", {"decision": "approved", "steps": ["member"]}
    )
    world.approve(application, world.manager)

    steps = detail(world, world.legal, application)["review_steps"]

    assert {step["key"] for step in steps if step["can_approve"]} == {"address", "nominee"}


def test_the_admin_takes_a_form_through_every_stage(world):
    application = world.submitted()
    client = world.client(world.admin)

    # Everything but the fee, which waits for the payment: the form runs to Finance.
    response = client.post(
        f"{URL}{application['id']}/decide/",
        {
            "decision": "approved",
            "steps": ["member", "address", "milk", "bank", "household", "nominee", "village"],
        },
    )
    assert response.status_code == 200, response.content

    assert detail(world, world.admin, application)["status"] == Status.PENDING_FINANCE


def test_the_admin_can_reject_and_mark_any_field(world):
    application = world.submitted()

    response = world.client(world.admin).post(
        f"{URL}{application['id']}/decide/",
        {"decision": "rejected", "reason": "Wrong IFSC", "rejected_fields": ["bank.ifsc"]},
    )

    assert response.status_code == 200, response.content
    assert response.data["rejected_fields"] == ["bank.ifsc"]


def test_the_admin_sees_the_full_numbers(world):
    application = world.submitted()

    response = world.client(world.admin).post(f"{URL}{application['id']}/numbers/")

    assert response.status_code == 200


def test_the_admin_has_a_queue_on_the_home_page(world):
    world.submitted()

    queue = world.client(world.admin).get("/api/v1/home/").data["my_queue"]

    assert queue["waiting"] == 1


def test_other_roles_still_act_only_on_their_own_steps(world):
    application = world.submitted()

    steps = detail(world, world.legal, application)["review_steps"]

    assert not any(step["can_approve"] for step in steps)
