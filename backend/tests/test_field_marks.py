import pytest

from apps.applications.models import Application
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


def marks_url(application):
    return f"{URL}{application['id']}/marks/"


def mark(world, user, application, path, reason="Does not match the photo"):
    return world.client(user).put(
        marks_url(application), {"path": path, "reason": reason}, format="json"
    )


def marks_of(world, user, application):
    return world.client(user).get(marks_url(application)).data


def reject(world, user, application, **body):
    return world.client(user).post(
        f"{URL}{application['id']}/decide/", {"decision": "rejected", **body}, format="json"
    )


def test_a_reviewer_marks_a_field_with_a_reason(world, application):
    response = mark(world, world.manager, application, "animals.production_lpd", "Too high")

    assert response.status_code == 200, response.content
    [row] = response.data
    assert row["path"] == "animals.production_lpd"
    assert row["reason"] == "Too high"
    assert row["label"] == "Milk production (litres per day)"
    assert row["mine"] is True
    assert row["can_remove"] is True


def test_marks_are_kept_and_seen_by_others_on_the_stage(world, application):
    mark(world, world.manager, application, "animals.production_lpd")

    # Others reviewing the form see the mark, but it stays the marker's own.
    [row] = marks_of(world, world.legal, application)

    assert row["marked_by_name"]
    assert row["mine"] is False
    assert row["can_remove"] is False


def test_marking_again_changes_the_reason(world, application):
    mark(world, world.manager, application, "animals.production_lpd", "Too high")

    response = mark(world, world.manager, application, "animals.production_lpd", "Too low")

    assert [row["reason"] for row in response.data] == ["Too low"]


def test_only_your_own_sections_can_be_marked(world, application):
    response = mark(world, world.manager, application, "bank.ifsc")

    assert response.status_code == 400
    assert "path" in response.data["error"]["details"]


def test_the_admin_can_mark_any_field(world, application):
    assert mark(world, world.admin, application, "bank.ifsc").status_code == 200


def test_the_sealed_numbers_and_the_household_can_be_marked(world, application):
    assert mark(world, world.manager, application, "family").status_code == 200
    assert mark(world, world.admin, application, "applicant.aadhaar_number").status_code == 200


def test_an_unknown_field_cannot_be_marked(world, application):
    assert mark(world, world.admin, application, "applicant.shoe_size").status_code == 400


def test_a_mark_needs_a_reason(world, application):
    assert mark(world, world.manager, application, "family", "  ").status_code == 400


def test_the_facilitator_does_not_see_the_marks(world, application):
    mark(world, world.manager, application, "family")

    response = world.client(world.facilitator).get(marks_url(application))

    assert response.status_code == 403


def test_marks_are_removed_by_whoever_made_them(world, application):
    [row] = mark(world, world.manager, application, "family").data
    url = f"{marks_url(application)}{row['id']}/"

    assert world.client(world.legal).delete(url).status_code == 403
    response = world.client(world.manager).delete(url)

    assert response.status_code == 200
    assert response.data == []


def test_the_admin_can_remove_anyones_mark(world, application):
    [row] = mark(world, world.manager, application, "family").data

    response = world.client(world.admin).delete(f"{marks_url(application)}{row['id']}/")

    assert response.status_code == 200
    assert response.data == []


def test_marking_is_audited(world, application, org_a):
    mark(world, world.manager, application, "family")

    with organization_context(org_a.id):
        assert AuditEvent.objects.filter(action="application.field_marked").exists()


def test_a_rejection_carries_each_fields_reason(world, application):
    response = reject(
        world,
        world.manager,
        application,
        reason="Please correct",
        rejected_fields=["animals.consumption_lpd"],
        field_notes={"animals.production_lpd": "Too high for two buffaloes", "family": ""},
    )

    assert response.status_code == 200, response.content
    assert response.data["rejected_fields"] == [
        "animals.consumption_lpd",
        "animals.production_lpd",
        "family",
    ]
    assert response.data["rejected_field_notes"] == {
        "animals.production_lpd": "Too high for two buffaloes"
    }
    decision = response.data["decisions"][-1]
    assert decision["field_notes"] == {"animals.production_lpd": "Too high for two buffaloes"}
    assert response.data["rejection_reason"] == "Please correct"


def test_marks_alone_are_a_reason_to_reject(world, application):
    response = reject(world, world.manager, application, field_notes={"family": "Husband missing"})

    assert response.status_code == 200, response.content
    assert response.data["rejection_reason"] == "Household members: Husband missing"


def test_notes_follow_the_own_sections_rule(world, application):
    response = reject(world, world.manager, application, field_notes={"bank.ifsc": "Wrong"})

    assert response.status_code == 400


def test_a_resubmission_starts_without_marks(world, application, org_a):
    mark(world, world.manager, application, "family")
    reject(world, world.manager, application, field_notes={"family": "Husband missing"})

    response = world.client(world.facilitator).post(f"{URL}{application['id']}/submit/")

    assert response.status_code == 200, response.content
    assert response.data["rejected_field_notes"] == {}
    assert marks_of(world, world.manager, application) == []
    with organization_context(org_a.id):
        assert Application.objects.get(pk=application["id"]).decisions.last().field_notes


def test_fields_are_not_marked_on_a_returned_form(world, application):
    reject(world, world.manager, application, reason="x")

    assert mark(world, world.manager, application, "family").status_code == 409
