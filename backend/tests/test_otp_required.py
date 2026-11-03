import pytest

from apps.applications.models import Application
from apps.core.tenancy import organization_context

from .test_applications import URL, World


@pytest.fixture
def world(org_a):
    return World(org_a)


def unverify(world, application_id, **fields):
    with organization_context(world.org.id):
        Application.objects.filter(pk=application_id).update(**fields)


def submit(world, application):
    return world.client(world.facilitator).post(f"{URL}{application['id']}/submit/")


def test_an_unverified_mobile_stops_the_submit(world):
    application = world.filled()
    unverify(world, application["id"], mobile_verified_at=None)

    response = submit(world, application)

    assert response.status_code == 400
    assert "address.mobile" in response.data["error"]["details"]


def test_an_unverified_email_stops_the_submit(world):
    application = world.filled()
    client = world.client(world.facilitator)
    client.patch(
        f"{URL}{application['id']}/",
        {"data": {"address": {"email": "new@example.com"}}},
        format="json",
    )

    response = submit(world, application)

    assert response.status_code == 400
    assert "address.email" in response.data["error"]["details"]


def test_no_email_needs_no_email_otp(world):
    application = world.filled()
    unverify(world, application["id"], email_verified_at=None)

    assert submit(world, application).status_code == 200
