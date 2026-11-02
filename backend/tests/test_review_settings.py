import pytest

from apps.applications.review_settings import DEFAULT_REASONS
from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context

from .conftest import authenticated_client
from .test_applications import World
from .test_overdue import row_of, submitted_days_ago

pytestmark = pytest.mark.django_db(transaction=True)

SETTINGS_URL = "/api/v1/settings/review/"
REASONS_URL = "/api/v1/applications/reject-reasons/"

NAME = {"text": "Name is misspelt", "section": "applicant", "fields": ["applicant.full_name"]}
BANK = {"text": "Wrong IFSC", "section": "bank", "fields": ["bank.ifsc"]}


@pytest.fixture
def world(org_a):
    return World(org_a)


def save(world, **body):
    return world.client(world.admin).put(
        SETTINGS_URL, {"overdue_days": 2, "reject_reasons": [], **body}, format="json"
    )


def test_reviewers_get_the_usual_reasons_at_first(world):
    reasons = world.client(world.legal).get(REASONS_URL).data

    assert len(reasons) == len(DEFAULT_REASONS)
    assert reasons[0] == {
        "text": "Name does not match the Aadhaar card",
        "section": "applicant",
        "fields": ["applicant.full_name"],
    }


def test_every_default_reason_passes_validation(world):
    defaults = world.client(world.admin).get(SETTINGS_URL).data["reject_reasons"]

    assert save(world, reject_reasons=defaults).status_code == 200


def test_an_admin_sees_the_settings_and_the_sections(world):
    data = world.client(world.admin).get(SETTINGS_URL).data

    assert data["overdue_days"] == 2
    sections = {section["key"]: section for section in data["sections"]}
    assert {"applicant", "address", "animals", "bank", "family", "nominee", "payment"} <= set(
        sections
    )
    nominee_fields = {field["path"] for field in sections["nominee"]["fields"]}
    assert {"nominee.name", "declaration.accepted_terms"} <= nominee_fields


def test_only_admins_change_the_settings(world):
    for user in (world.legal, world.finance, world.facilitator):
        client = world.client(user)
        assert client.get(SETTINGS_URL).status_code == 403
        assert client.put(SETTINGS_URL, {}, format="json").status_code == 403


def test_saved_reasons_replace_the_list_in_their_order(world, org_a):
    response = save(world, overdue_days=4, reject_reasons=[BANK, NAME])

    assert response.status_code == 200, response.content
    assert response.data["overdue_days"] == 4
    assert world.client(world.finance).get(REASONS_URL).data == [BANK, NAME]
    with organization_context(org_a.id):
        event = AuditEvent.objects.get(action="review_settings.updated")
    assert event.metadata == {"overdue_days": 4, "reject_reasons": 2}


def test_an_emptied_list_stays_empty(world):
    assert save(world).status_code == 200
    assert world.client(world.legal).get(REASONS_URL).data == []


@pytest.mark.parametrize(
    "reason",
    [
        {"text": "x", "section": "applicant", "fields": ["applicant.shoe_size"]},
        {"text": "x", "section": "applicant", "fields": ["bank.ifsc"]},
        {"text": "x", "section": "kitchen", "fields": []},
        {"text": "", "section": "applicant", "fields": []},
    ],
)
def test_a_reason_must_fit_the_form(world, reason):
    assert save(world, reject_reasons=[reason]).status_code == 400


def test_a_reason_may_mark_any_field_of_its_own_step(world):
    reason = {
        "text": "Terms not read",
        "section": "nominee",
        "fields": ["declaration.accepted_terms"],
    }
    assert save(world, reject_reasons=[reason]).status_code == 200


def test_reasons_must_differ(world):
    assert save(world, reject_reasons=[NAME, {**BANK, "text": NAME["text"]}]).status_code == 400


@pytest.mark.parametrize("days", [0, 61])
def test_the_late_threshold_has_limits(world, days):
    assert save(world, overdue_days=days).status_code == 400


def test_the_late_threshold_is_the_organizations_own(world):
    application = submitted_days_ago(world, 3)
    assert row_of(world, world.manager, application)["is_overdue"] is True

    assert save(world, overdue_days=5).status_code == 200

    assert row_of(world, world.manager, application)["is_overdue"] is False
    queue = world.client(world.manager).get("/api/v1/home/").data["my_queue"]
    assert queue["overdue"] == 0
    assert queue["overdue_days"] == 5


def test_each_organization_keeps_its_own_settings(world, org_b, admin_b):
    save(world, overdue_days=7, reject_reasons=[NAME])

    data = authenticated_client(org_b, admin_b).get(SETTINGS_URL).data

    assert data["overdue_days"] == 2
    assert len(data["reject_reasons"]) == len(DEFAULT_REASONS)
