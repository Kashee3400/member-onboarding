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


def test_the_admin_can_act_on_each_open_step(world):
    application = world.submitted()

    steps = detail(world, world.admin, application)["review_steps"]

    open_now = {step["key"] for step in steps if step["can_approve"]}
    assert open_now == {"milk", "household", "village"}  # the Area Manager's steps
    assert all(step["mine"] for step in steps)


def test_the_admin_takes_a_form_through_every_stage(world):
    application = world.submitted()
    client = world.client(world.admin)

    for stage in ("pending_am", "pending_cs"):
        assert detail(world, world.admin, application)["status"] == stage
        response = client.post(f"{URL}{application['id']}/decide/", {"decision": "approved"})
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
