import json
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from django.utils import timezone

from apps.configuration.models import IntegrationConfig
from apps.core.tenancy import organization_context
from apps.notifications import sms
from apps.notifications.models import ContactOtp

from .test_applications import URL, World, complete_form

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def world(org_a):
    return World(org_a)


@pytest.fixture
def sent(monkeypatch):
    """Codes that would have gone out, by number or address."""
    codes = {}
    monkeypatch.setattr(
        "apps.notifications.otp.send_otp_sms", lambda mobile, code: codes.update({mobile: code})
    )
    monkeypatch.setattr(
        "apps.notifications.otp.send_mail",
        lambda to, subject, body: codes.update({to: body[26:32]}),
    )
    return codes


def otp_url(application):
    return f"{URL}{application['id']}/contact-otp/"


def send(client, application, channel="mobile"):
    return client.post(otp_url(application), {"channel": channel}, format="json")


def verify(client, application, code, channel="mobile"):
    return client.post(
        f"{otp_url(application)}verify/", {"channel": channel, "code": code}, format="json"
    )


def test_a_right_code_marks_the_mobile_verified(world, sent):
    application = world.filled()
    client = world.client(world.facilitator)

    assert send(client, application).status_code == 201
    mobile = application["data"]["address"]["mobile"]
    response = verify(client, application, sent[mobile])

    assert response.status_code == 200, response.content
    assert response.data["mobile"] is not None
    assert client.get(f"{URL}{application['id']}/").data["contact_verified"]["mobile"] is not None


def test_a_wrong_code_counts_down_and_then_stops(world, sent):
    application = world.filled()
    client = world.client(world.facilitator)
    send(client, application)

    first = verify(client, application, "000000")
    for _ in range(4):
        verify(client, application, "000000")
    last = verify(client, application, "000000")

    assert first.status_code == 400
    assert "4 tries left" in str(first.data)
    assert last.status_code == 409


def test_the_email_is_verified_the_same_way(world, sent):
    application = world.filled()
    client = world.client(world.facilitator)
    data = complete_form()
    data["address"]["email"] = "Member@Example.com"
    client.patch(f"{URL}{application['id']}/", {"data": data}, format="json")

    assert send(client, application, "email").status_code == 201
    assert verify(client, application, sent["member@example.com"], "email").status_code == 200


def test_a_code_cannot_be_resent_at_once(world, sent):
    application = world.filled()
    client = world.client(world.facilitator)
    send(client, application)

    assert send(client, application).status_code == 409


def test_a_code_sent_to_an_old_number_proves_nothing(world, sent):
    application = world.filled()
    client = world.client(world.facilitator)
    send(client, application)
    code = next(iter(sent.values()))
    data = complete_form()
    data["address"]["mobile"] = "9876543210"
    client.patch(f"{URL}{application['id']}/", {"data": data}, format="json")

    assert verify(client, application, code).status_code == 409


def test_an_expired_code_is_refused(world, sent):
    application = world.filled()
    client = world.client(world.facilitator)
    send(client, application)
    with organization_context(world.org.id):
        ContactOtp.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

    assert verify(client, application, next(iter(sent.values()))).status_code == 409


def test_without_sms_settings_it_says_so(world):
    application = world.filled()

    response = send(world.client(world.facilitator), application)

    assert response.status_code == 409
    assert "Integrations" in str(response.data)


def test_a_submitted_form_is_not_verified_any_more(world, sent):
    application = world.submitted()

    assert send(world.client(world.facilitator), application).status_code == 409


def test_the_gateway_gets_the_erp_parameters(world, monkeypatch):
    with organization_context(world.org.id):
        integration = IntegrationConfig(
            organization=world.org,
            kind="sms",
            is_enabled=True,
            config={
                "base_url": "https://sms.example/api",
                "user_id": "kashee",
                "sender_id": "KASHEE",
                "dlt_entity_id": "E1",
                "otp_template_id": "T1",
                "otp_message": "आपका सत्यापन कोड {otp} है -काशी डेयरी",
            },
        )
        integration.set_secrets({"password": "secret"})
        integration.save()

    seen = {}

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"status": "success", "msgid": "42"}).encode()

    def fake_urlopen(request, timeout):
        seen.update(parse_qs(urlparse(request.full_url).query))
        return Reply()

    monkeypatch.setattr(sms, "urlopen", fake_urlopen)
    with organization_context(world.org.id):
        assert sms.send_otp_sms("+919170800000", "654321") == "42"

    assert seen["mobile"] == ["9170800000"]
    assert seen["msg"] == ["आपका सत्यापन कोड 654321 है -काशी डेयरी"]
    assert seen["dltTemplateId"] == ["T1"]
    assert seen["password"] == ["secret"]


def test_the_otp_message_needs_a_place_for_the_code(world):
    response = world.client(world.admin).put(
        "/api/v1/settings/integrations/sms/",
        {"config": {"otp_message": "No code here"}},
        format="json",
    )

    assert response.status_code == 400
