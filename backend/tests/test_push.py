import json
from io import BytesIO
from urllib.error import HTTPError

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache

from apps.configuration.models import IntegrationConfig
from apps.core.tenancy import organization_context
from apps.notifications import push
from apps.notifications.models import PushDevice

from .test_applications import URL, World

pytestmark = pytest.mark.django_db(transaction=True)

DEVICES = "/api/v1/notifications/push-devices/"


@pytest.fixture
def world(org_a):
    return World(org_a)


def key_file() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return json.dumps(
        {
            "type": "service_account",
            "project_id": "kashee-facilitator",
            "client_email": "push@kashee-facilitator.iam.gserviceaccount.com",
            "private_key": pem,
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )


@pytest.fixture
def firebase(world, monkeypatch):
    """Push turned on, and Google answered by this list instead of the network."""
    with organization_context(world.org.id):
        integration = IntegrationConfig(organization=world.org, kind="push", is_enabled=True)
        integration.set_secrets({"service_account": key_file()})
        integration.save()
    cache.clear()
    sent = []

    def fake_post(url, body, headers):
        if url.endswith("/token"):
            return {"access_token": "google-token"}
        message = json.loads(body)["message"]
        if message["token"] == "gone-token":
            raise HTTPError(url, 404, "UNREGISTERED", {}, BytesIO(b"{}"))
        sent.append(message)
        return {"name": "projects/x/messages/1"}

    monkeypatch.setattr(push, "_post", fake_post)
    return sent


def register(world, token, user=None):
    return world.client(user or world.facilitator).post(
        DEVICES, {"token": token, "platform": "android"}, format="json"
    )


def reject(world, application, reason="Photo unclear"):
    return world.client(world.manager).post(
        f"{URL}{application['id']}/decide/", {"decision": "rejected", "reason": reason}
    )


def test_a_phone_registers_once_and_follows_a_new_user(world):
    assert register(world, "phone-1").status_code == 204
    assert register(world, "phone-1").status_code == 204
    assert register(world, "phone-1", user=world.manager).status_code == 204

    with organization_context(world.org.id):
        device = PushDevice.objects.get(token="phone-1")
        assert PushDevice.objects.count() == 1
        assert device.membership.user == world.manager


def test_a_form_sent_back_reaches_the_facilitators_phone(world, firebase):
    register(world, "phone-1")
    application = world.submitted()

    assert reject(world, application).status_code == 200

    assert len(firebase) == 1
    message = firebase[0]
    assert message["token"] == "phone-1"
    assert message["data"] == {
        "source": "member_onboarding",
        "type": "application_rejected",
        "application_id": application["id"],
    }
    assert "Photo unclear" in message["notification"]["body"]


def test_a_phone_that_no_longer_exists_is_dropped(world, firebase):
    register(world, "gone-token")
    application = world.submitted()

    reject(world, application)

    with organization_context(world.org.id):
        assert not PushDevice.objects.get(token="gone-token").is_active


def test_without_push_set_up_a_rejection_still_works(world):
    register(world, "phone-1")
    application = world.submitted()

    assert reject(world, application).status_code == 200


def test_a_wrong_key_file_is_refused_on_save(world):
    response = world.client(world.admin).put(
        "/api/v1/settings/integrations/push/",
        {"is_enabled": True, "secrets": {"service_account": '{"type": "user"}'}},
        format="json",
    )

    assert response.status_code == 400


def test_the_key_is_checked_with_google(world, firebase):
    response = world.client(world.admin).post("/api/v1/settings/integrations/push/test/")

    assert response.status_code == 204
