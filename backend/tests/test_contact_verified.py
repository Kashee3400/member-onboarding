import pytest
from django.utils import timezone

from apps.applications.models import Application
from apps.core.tenancy import organization_context

from .test_applications import URL, World, complete_form

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def world(org_a):
    return World(org_a)


def verified_now(world, application):
    with organization_context(world.org.id):
        Application.objects.filter(pk=application["id"]).update(
            mobile_verified_at=timezone.now(), email_verified_at=timezone.now()
        )


def test_a_new_form_shows_both_as_not_verified(world):
    application = world.submitted()

    data = world.client(world.manager).get(f"{URL}{application['id']}/").data

    assert data["contact_verified"] == {"mobile": None, "email": None}


def test_changing_the_number_drops_its_proof_only(world):
    application = world.filled()
    verified_now(world, application)
    data = complete_form()
    data["address"]["mobile"] = "9876543210"

    client = world.client(world.facilitator)
    client.patch(f"{URL}{application['id']}/", {"data": data})

    shown = client.get(f"{URL}{application['id']}/").data["contact_verified"]
    assert shown["mobile"] is None
    assert shown["email"] is not None


def test_the_form_cannot_mark_itself_verified(world):
    application = world.filled()
    data = complete_form()
    data["address"]["mobile_verified_at"] = "2026-01-01T00:00:00Z"

    client = world.client(world.facilitator)
    client.patch(f"{URL}{application['id']}/", {"data": data})

    assert client.get(f"{URL}{application['id']}/").data["contact_verified"]["mobile"] is None
