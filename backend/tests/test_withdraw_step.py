import pytest

from apps.audit.models import AuditEvent
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


@pytest.fixture
def application(world):
    return world.submitted()


def approve(world, user, application, steps):
    response = world.client(user).post(
        f"{URL}{application['id']}/decide/",
        {"decision": "approved", "steps": steps},
        format="json",
    )
    assert response.status_code == 200, response.content
    return response.data


def withdraw(world, user, application, step):
    return world.client(user).post(f"{URL}{application['id']}/steps/{step}/withdraw/")


def step_of(data, key):
    return next(step for step in data["review_steps"] if step["key"] == key)


def detail(world, user, application):
    return world.client(user).get(f"{URL}{application['id']}/").data


def test_a_step_approved_by_mistake_is_taken_back(world, application, org_a):
    approved = approve(world, world.manager, application, ["milk"])
    assert step_of(approved, "milk")["can_withdraw"] is True

    response = withdraw(world, world.manager, application, "milk")

    assert response.status_code == 200, response.content
    step = step_of(response.data, "milk")
    assert step["approved_at"] is None
    assert step["can_approve"] is True
    assert step["can_withdraw"] is False
    with organization_context(org_a.id):
        event = AuditEvent.objects.get(action="application.step_withdrawn")
    assert event.metadata["step"] == "milk"


def test_it_can_be_approved_again_and_the_form_moves_on(world, application):
    approve(world, world.manager, application, ["milk", "household"])
    withdraw(world, world.manager, application, "milk")

    data = approve(world, world.manager, application, ["milk", "village"])

    assert data["status"] == "pending_cs"


def test_only_the_approver_sees_the_withdraw(world, application):
    approve(world, world.manager, application, ["milk"])

    assert step_of(detail(world, world.legal, application), "milk")["can_withdraw"] is False
    assert step_of(detail(world, world.admin, application), "milk")["can_withdraw"] is True


def test_someone_elses_approval_cannot_be_withdrawn(world, application):
    approve(world, world.manager, application, ["milk"])

    assert withdraw(world, world.legal, application, "milk").status_code == 403


def test_nothing_is_withdrawn_once_the_form_moved_on(world, application):
    approve(world, world.manager, application, ["milk", "household", "village"])

    response = withdraw(world, world.manager, application, "milk")

    assert response.status_code == 409
    assert step_of(detail(world, world.manager, application), "milk")["approved_at"]


def test_the_admin_withdraws_anyones_approval_at_the_stage(world, application):
    approve(world, world.manager, application, ["milk"])

    response = withdraw(world, world.admin, application, "milk")

    assert response.status_code == 200, response.content
    assert step_of(response.data, "milk")["approved_at"] is None


def test_a_step_approved_ahead_is_withdrawn_before_its_stage(world, application):
    approve(world, world.admin, application, ["member"])

    response = withdraw(world, world.admin, application, "member")

    assert response.status_code == 200, response.content
    assert response.data["status"] == "pending_am"
    assert step_of(response.data, "member")["approved_at"] is None


def test_a_step_approved_ahead_stays_once_its_stage_is_reached(world, application):
    approve(world, world.admin, application, ["member"])
    approve(world, world.manager, application, ["milk", "household", "village"])

    assert step_of(detail(world, world.admin, application), "member")["can_withdraw"] is False
    assert withdraw(world, world.admin, application, "member").status_code == 409


def test_steps_approved_at_the_new_stage_can_be_withdrawn(world, application):
    approve(world, world.manager, application, ["milk", "household", "village"])
    approve(world, world.legal, application, ["member"])

    assert withdraw(world, world.legal, application, "member").status_code == 200


def test_a_step_not_approved_cannot_be_withdrawn(world, application):
    assert withdraw(world, world.manager, application, "milk").status_code == 409


def test_an_unknown_step_is_not_found(world, application):
    assert withdraw(world, world.manager, application, "shoes").status_code == 404


def test_the_facilitator_cannot_withdraw(world, application):
    approve(world, world.manager, application, ["milk"])

    assert withdraw(world, world.facilitator, application, "milk").status_code == 403
