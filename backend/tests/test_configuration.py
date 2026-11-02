import pytest
from django.db import connection

from apps.audit.models import AuditEvent
from apps.configuration.models import IntegrationConfig
from apps.core import crypto
from apps.core.tenancy import organization_context

from .conftest import authenticated_client

pytestmark = pytest.mark.django_db(transaction=True)

URL = "/api/v1/settings/integrations/mail/"
SECRET = "smtp-password-value"


@pytest.fixture
def client(org_a, admin_a):
    return authenticated_client(org_a, admin_a)


def test_saved_secrets_are_encrypted_at_rest_and_never_returned(client, org_a):
    response = client.put(
        URL,
        {"is_enabled": True, "config": {"host": "smtp.test"}, "secrets": {"password": SECRET}},
    )

    assert response.status_code == 200
    assert response.data["configured_secrets"] == ["password"]
    assert SECRET not in response.content.decode()
    assert SECRET not in client.get(URL).content.decode()

    with organization_context(org_a.id):
        with connection.cursor() as cursor:
            cursor.execute("SELECT encrypted_secrets FROM integration_config")
            stored = cursor.fetchone()[0]
        assert SECRET not in stored
        assert IntegrationConfig.objects.get(kind="mail").get_secrets() == {"password": SECRET}


def test_secrets_are_merged_and_null_removes_one(client):
    client.put(URL, {"secrets": {"password": "a"}})
    assert client.put(URL, {"secrets": {"password": None}}).data["configured_secrets"] == []


def test_changing_config_keeps_existing_secrets(client):
    client.put(URL, {"secrets": {"password": SECRET}})
    response = client.put(URL, {"config": {"host": "new.test"}})
    assert response.data["configured_secrets"] == ["password"]


def test_a_secret_cannot_be_saved_as_plain_config(client):
    response = client.put(URL, {"config": {"password": SECRET}})
    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"


def test_unknown_secret_names_are_rejected(client):
    assert client.put(URL, {"secrets": {"nope": "x"}}).status_code == 400


def test_unknown_integration_kind_is_not_found(client):
    assert client.get("/api/v1/settings/integrations/nope/").status_code == 404


def test_non_admins_cannot_read_or_change_integrations(org_a, staff_a):
    client = authenticated_client(org_a, staff_a)
    assert client.get(URL).status_code == 403
    assert client.put(URL, {"is_enabled": True}).status_code == 403


def test_anonymous_callers_are_rejected(api_client, org_a):
    assert api_client.get(URL).status_code == 401


def test_changes_are_audited_without_secret_values(client, org_a):
    client.put(URL, {"secrets": {"password": SECRET}})

    with organization_context(org_a.id):
        event = AuditEvent.objects.get(action="integration.updated")
    assert event.metadata["secrets"] == ["password"]
    assert SECRET not in str(event.metadata)


def test_ciphertext_copied_to_another_organization_cannot_be_decrypted(org_a, org_b):
    with organization_context(org_a.id):
        original = IntegrationConfig(organization=org_a, kind="mail")
        original.set_secrets({"password": SECRET})
        original.save()

    copy = IntegrationConfig(
        organization=org_b, kind="mail", encrypted_secrets=original.encrypted_secrets
    )
    with pytest.raises(crypto.DecryptionError):
        copy.get_secrets()
