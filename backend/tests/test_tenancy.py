import pytest
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.db import ProgrammingError, connection, transaction

from apps.audit.models import AuditEvent
from apps.configuration.models import IntegrationConfig
from apps.core.tenancy import organization_context
from apps.organizations.models import Membership, OrganizationOwnedModel

from .conftest import authenticated_client

pytestmark = pytest.mark.django_db(transaction=True)


def test_the_suite_runs_as_a_role_that_cannot_bypass_rls():
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        assert cursor.fetchone() == (False, False)


def test_every_organization_owned_table_enforces_rls():
    tables = [AuditEvent._meta.db_table] + [
        model._meta.db_table
        for model in apps.get_models()
        if issubclass(model, OrganizationOwnedModel)
    ]
    assert Membership._meta.db_table in tables
    with connection.cursor() as cursor:
        for table in tables:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s",
                [table],
            )
            assert cursor.fetchone() == (True, True), f"{table} is missing RLS"


def test_rows_are_invisible_without_an_active_organization(org_a, admin_a):
    assert Membership.objects.count() == 0
    with organization_context(org_a.id):
        assert Membership.objects.count() == 1


def test_one_organization_cannot_see_anothers_rows(org_a, org_b, admin_a, admin_b):
    with organization_context(org_a.id):
        assert list(Membership.objects.values_list("user_id", flat=True)) == [admin_a.id]
    with organization_context(org_b.id):
        assert list(Membership.objects.values_list("user_id", flat=True)) == [admin_b.id]


def test_a_write_into_another_organization_is_rejected_by_the_database(org_a, org_b):
    with organization_context(org_a.id):
        with pytest.raises(ProgrammingError), transaction.atomic():
            IntegrationConfig.objects.create(organization=org_b, kind="mail")


def test_organization_context_restores_the_previous_one(org_a, org_b, admin_a, admin_b):
    with organization_context(org_a.id):
        with organization_context(org_b.id):
            assert Membership.objects.get().user_id == admin_b.id
        assert Membership.objects.get().user_id == admin_a.id


def test_organization_context_recovers_after_a_failed_block(org_a, org_b, admin_a):
    with organization_context(org_a.id):
        with pytest.raises(ProgrammingError):
            with organization_context(org_b.id):
                IntegrationConfig.objects.create(organization=org_a, kind="mail")
        assert Membership.objects.get().user_id == admin_a.id


def test_organization_id_is_filled_from_the_active_context(org_a):
    with organization_context(org_a.id):
        integration = IntegrationConfig.objects.create(kind="sms")
        assert integration.organization_id == org_a.id


def test_writing_without_an_organization_fails_loudly(db):
    with pytest.raises(ImproperlyConfigured):
        IntegrationConfig(kind="sms").save()


def test_the_active_organization_does_not_leak_into_the_next_request(org_a, org_b, admin_a):
    authenticated_client(org_a, admin_a).get("/api/v1/auth/me/")
    assert Membership.objects.count() == 0


def test_the_api_only_serves_the_callers_organization(org_a, org_b, admin_a, admin_b):
    client_a = authenticated_client(org_a, admin_a)
    client_b = authenticated_client(org_b, admin_b)

    client_a.put(
        "/api/v1/settings/integrations/mail/",
        {"config": {"host": "smtp.a.test"}},
        format="json",
    )

    assert client_a.get("/api/v1/settings/integrations/mail/").data["config"] == {
        "host": "smtp.a.test"
    }
    assert client_b.get("/api/v1/settings/integrations/mail/").data["config"] == {}
