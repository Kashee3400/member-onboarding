import pytest
from django.db import ProgrammingError, connection, transaction

from apps.audit.models import AuditEvent
from apps.audit.services import record_event
from apps.core.tenancy import organization_context

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def event(org_a):
    with organization_context(org_a.id):
        yield record_event("test.happened")


def test_events_cannot_be_updated(event):
    with pytest.raises(ProgrammingError, match="append-only"), transaction.atomic():
        AuditEvent.objects.filter(pk=event.pk).update(action="tampered")


def test_events_cannot_be_deleted(event):
    with pytest.raises(ProgrammingError, match="append-only"), transaction.atomic():
        AuditEvent.objects.filter(pk=event.pk).delete()


def test_events_capture_the_active_organization(org_a, event):
    assert event.organization_id == org_a.id


def test_the_audit_table_rejects_changes_even_through_raw_sql(event):
    with pytest.raises(ProgrammingError, match="append-only"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("UPDATE audit_event SET action = 'tampered'")


def test_events_from_another_organization_are_hidden(org_a, org_b, event):
    with organization_context(org_b.id):
        assert AuditEvent.objects.count() == 0
