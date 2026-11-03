import io
import json
import zipfile
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import timezone

from apps.applications.models import Application, OrganizationProfile, Status
from apps.applications.services import printed_form
from apps.applications.tasks import discard_stale_drafts
from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context
from apps.documents.models import Document

from .test_applications import AADHAAR, URL, World

pytestmark = pytest.mark.django_db(transaction=True)

AUDIT = "/api/v1/audit/events/"


@pytest.fixture
def world(org_a):
    return World(org_a)


def age(world, application_id, days):
    with organization_context(world.org.id):
        Application.objects.filter(pk=application_id).update(
            updated_at=timezone.now() - timedelta(days=days)
        )


# Retention ---------------------------------------------------------------------------


def test_a_draft_left_past_retention_is_discarded_with_its_photos(world):
    draft = world.draft()
    world.attach_documents(world.client(world.facilitator), draft["id"])
    with organization_context(world.org.id):
        paths = list(
            Document.objects.filter(application_id=draft["id"]).values_list(
                "relative_path", flat=True
            )
        )
    age(world, draft["id"], 91)

    assert discard_stale_drafts() == 1

    with organization_context(world.org.id):
        assert Application.objects.get(pk=draft["id"]).status == Status.DISCARDED
        assert not Document.objects.filter(application_id=draft["id"]).exists()
        event = AuditEvent.objects.get(action="application.discarded", target_id=draft["id"])
        assert event.metadata["reason"] == "retention"
    assert paths and not any((Path(settings.MEDIA_ROOT) / path).exists() for path in paths)


def test_recent_drafts_and_submitted_forms_stay(world):
    recent = world.draft()
    submitted = world.submitted()
    age(world, recent["id"], 30)
    age(world, submitted["id"], 400)

    assert discard_stale_drafts() == 0


def test_an_organization_can_keep_drafts(world):
    draft = world.draft()
    age(world, draft["id"], 400)
    with organization_context(world.org.id):
        OrganizationProfile.objects.update_or_create(defaults={"draft_retention_days": 0})

    assert discard_stale_drafts() == 0


# Member data export ------------------------------------------------------------------


def export(client, application_id):
    return client.get(f"{URL}{application_id}/data-export/")


def test_cs_legal_exports_everything_held_about_a_member(world):
    done = world.fully_approved()
    with organization_context(world.org.id):
        printed_form(Application.objects.get(pk=done["id"]), "single")

    response = export(world.client(world.legal), done["id"])

    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    record = json.loads(archive.read("record.json"))
    assert record["numbers"]["aadhaar_number"] == AADHAAR
    assert record["member"]["tr_code"] == done["tr_code"]
    assert {decision["stage"] for decision in record["decisions"]} >= {
        "pending_am",
        "pending_finance",
    }
    names = archive.namelist()
    assert any(name.startswith("documents/aadhaar_front.") for name in names)
    assert "forms/single.pdf" in names
    history = json.loads(archive.read("history.json"))
    assert history[-1]["action"] == "application.data_exported"


def test_the_export_needs_its_own_permission(world):
    done = world.fully_approved()

    assert export(world.client(world.manager), done["id"]).status_code == 403
    assert export(world.client(world.finance), done["id"]).status_code == 403


# Sensitive access ---------------------------------------------------------------------


def test_the_audit_log_filters_to_every_look_at_personal_data(world):
    done = world.fully_approved()
    legal = world.client(world.legal)
    legal.post(f"{URL}{done['id']}/numbers/")
    export(legal, done["id"])

    sensitive = "application.numbers_viewed,application.data_exported,document.viewed"
    rows = (
        world.client(world.admin)
        .get(AUDIT, {"action__in": sensitive, "page_size": 100})
        .data["results"]
    )

    assert {row["action"] for row in rows} == {
        "application.numbers_viewed",
        "application.data_exported",
    }
