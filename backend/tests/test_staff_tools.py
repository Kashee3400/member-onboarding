from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook, load_workbook

from apps.applications.models import Signatory, StaffReviewSteps, Status
from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context
from apps.hierarchy.models import MccAssignment, MppAssignment
from apps.hierarchy.services import assign_mcc
from apps.organizations.models import Membership

from .test_applications import REVIEW_STEPS, URL, World

pytestmark = pytest.mark.django_db(transaction=True)

STAFF = "/api/v1/staff/"
STEPS_URL = "/api/v1/settings/review-steps/"


@pytest.fixture
def world(org_a):
    return World(org_a)


def membership_of(world, user):
    with organization_context(world.org.id):
        return Membership.objects.get(user=user)


def second_manager(world, email="am2@a.test"):
    user = world.member(email, "area_manager")
    with organization_context(world.org.id):
        assign_mcc(mcc=world.mpp.mcc, membership=membership_of(world, user), actor=world.admin)
    return user


# Own review steps ----------------------------------------------------------------------


def steps_url(world, user):
    return f"{STAFF}{membership_of(world, user).id}/review-steps/"


def test_a_person_starts_with_the_steps_of_their_roles(world):
    response = world.client(world.admin).get(steps_url(world, world.manager))
    assert response.status_code == 200
    assert response.data["custom"] is False
    assert response.data["steps"] == ["household", "milk", "village"]


def test_own_steps_narrow_what_one_area_manager_approves(world):
    colleague = second_manager(world)
    client = world.client(world.admin)
    response = client.put(steps_url(world, world.manager), {"steps": ["milk"]}, format="json")
    assert response.status_code == 200, response.content
    assert response.data["custom"] is True

    application = world.submitted()
    steps = world.client(world.manager).get(f"{URL}{application['id']}/").data["review_steps"]
    assert {step["key"] for step in steps if step["can_approve"]} == {"milk"}

    # The other area manager still has every step of the stage.
    steps = world.client(colleague).get(f"{URL}{application['id']}/").data["review_steps"]
    assert {step["key"] for step in steps if step["can_approve"]} == {
        "household",
        "milk",
        "village",
    }


def test_a_step_nobody_else_approves_needs_a_confirm(world):
    client = world.client(world.admin)
    url = steps_url(world, world.manager)
    response = client.put(url, {"steps": ["milk"]}, format="json")
    assert response.status_code == 409
    assert response.data["error"]["code"] == "steps_left_uncovered"
    assert "Household Members" in response.data["error"]["message"]
    with organization_context(world.org.id):
        assert not StaffReviewSteps.objects.exists()

    response = client.put(url, {"steps": ["milk"], "confirm": True}, format="json")
    assert response.status_code == 200


def test_own_steps_stay_within_the_stages_they_approve(world):
    response = world.client(world.admin).put(
        steps_url(world, world.manager), {"steps": ["milk", "bank"]}, format="json"
    )
    assert response.status_code == 400


def test_own_steps_can_go_back_to_the_role(world):
    client = world.client(world.admin)
    url = steps_url(world, world.manager)
    client.put(url, {"steps": ["milk"], "confirm": True}, format="json")
    response = client.put(url, {"steps": None}, format="json")
    assert response.status_code == 200
    assert response.data["custom"] is False
    assert response.data["steps"] == ["household", "milk", "village"]


def test_a_stage_cannot_be_left_without_steps(world):
    steps = {**REVIEW_STEPS, "member": ["cs_legal"], "address": ["cs_legal"]}
    steps.update({"milk": ["cs_legal"], "household": ["cs_legal"], "village": ["cs_legal"]})
    response = world.client(world.admin).put(STEPS_URL, {"steps": steps}, format="json")
    assert response.status_code == 400
    assert "Area Manager" in str(response.data)


# Transfer -------------------------------------------------------------------------------


def transfer(world, source, target):
    return world.client(world.admin).post(
        f"{STAFF}{membership_of(world, source).id}/transfer/",
        {"to": str(membership_of(world, target).id)},
        format="json",
    )


def test_a_transfer_moves_mccs_mpps_and_their_forms(world):
    application = world.submitted()
    newcomer = world.member("am-new@a.test", "area_manager")
    with organization_context(world.org.id):
        assign_mcc(
            mcc=world.mpp.mcc, membership=membership_of(world, world.manager), actor=world.admin
        )

    response = transfer(world, world.manager, newcomer)
    assert response.status_code == 200, response.content
    assert response.data["mccs"] == ["6"]
    assert response.data["mpps"] == ["1305"]

    with organization_context(world.org.id):
        old = membership_of(world, world.manager)
        assert not MccAssignment.objects.filter(membership=old, ended_at__isnull=True).exists()
        assert not MppAssignment.objects.filter(membership=old, ended_at__isnull=True).exists()
        assert AuditEvent.objects.filter(action="staff.work_transferred").exists()
    assert world.client(newcomer).get(f"{URL}{application['id']}/").status_code == 200
    assert world.client(world.manager).get(f"{URL}{application['id']}/").status_code == 404


def test_work_moves_only_to_someone_who_approves_the_same(world):
    response = transfer(world, world.manager, world.finance)
    assert response.status_code == 400


def test_a_facilitator_is_moved_in_the_erp(world):
    other = world.member("field2@a.test", "facilitator")
    response = transfer(world, world.facilitator, other)
    assert response.status_code == 400
    assert "ERP" in str(response.data)


# Import and export ------------------------------------------------------------------------

HEADER = [
    "organization",
    "full_name",
    "email",
    "mobile",
    "role",
    "mcc_codes",
    "mpp_codes",
    "signs_as_head",
]


def sheet(*rows):
    book = Workbook()
    book.active.title = "Staff"
    book.active.append(HEADER)
    book.active.append(["org name", "Full name as it should print on the form"])
    for row in rows:
        book.active.append(list(row))
    out = BytesIO()
    book.save(out)
    return SimpleUploadedFile(
        "staff.xlsx",
        out.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


ROWS = (
    ("org-a", "Pradip Gautam", "pradip@a.test", "", "area_manager", "6", "", "yes"),
    ("org-a", "Asha Rai", "asha@a.test", "9876543210", "cs_legal", "", "", "yes"),
    ("org-a", "Field Person", "", "9876500000", "facilitator", "", "", ""),
)


def upload(world, *rows, preview):
    return world.client(world.admin).post(
        f"{STAFF}import/", {"file": sheet(*rows), "preview": preview}, format="multipart"
    )


def test_an_import_preview_changes_nothing(world):
    response = upload(world, *ROWS, preview=True)
    assert response.status_code == 200, response.content
    assert (response.data["create"], response.data["skip"], response.data["problems"]) == (2, 1, 0)
    pradip = response.data["rows"][0]
    assert "only for CS & Legal and Finance" in pradip["notes"][0]
    with organization_context(world.org.id):
        assert not Membership.objects.filter(user__email="pradip@a.test").exists()


def test_an_import_adds_staff_with_one_time_passwords(world):
    response = upload(world, *ROWS, preview=False)
    assert response.status_code == 200, response.content
    credentials = {row["email"]: row for row in response.data["credentials"]}
    assert set(credentials) == {"pradip@a.test", "asha@a.test"}
    assert credentials["asha@a.test"]["temporary_password"]

    with organization_context(world.org.id):
        pradip = Membership.objects.get(user__email="pradip@a.test")
        asha = Membership.objects.get(user__email="asha@a.test")
        assert pradip.user.must_change_password
        assert MccAssignment.objects.filter(membership=pradip, mcc__code="6").exists()
        assert Signatory.objects.get(stage=Status.PENDING_CS).membership == asha

    again = upload(world, *ROWS, preview=False)
    assert again.data["skip"] == 3
    assert again.data["credentials"] == []


def test_an_import_with_a_mistake_changes_nothing(world):
    rows = (*ROWS, ("org-a", "Bad Row", "bad@a.test", "", "area_manager", "99", "", ""))
    response = upload(world, *rows, preview=False)
    assert response.status_code == 200
    assert response.data["problems"] == 1
    assert response.data["credentials"] == []
    with organization_context(world.org.id):
        assert not Membership.objects.filter(user__email="pradip@a.test").exists()


def test_a_row_for_another_organization_is_refused(world):
    response = upload(
        world, ("org-b", "Elsewhere", "x@a.test", "", "finance", "", "", ""), preview=True
    )
    assert response.data["problems"] == 1


def test_export_gives_back_what_import_takes(world):
    response = world.client(world.admin).get(f"{STAFF}export/")
    assert response.status_code == 200
    assert "attachment" in response["Content-Disposition"]
    rows = list(load_workbook(BytesIO(response.content)).active.iter_rows(values_only=True))
    assert list(rows[0]) == HEADER
    by_email = {row[2]: row for row in rows[2:]}
    assert by_email["am@a.test"][4] == "area_manager"
    assert by_email["am@a.test"][6] == "1305"
    assert by_email["cs@a.test"][7] == "yes"

    template = world.client(world.admin).get(f"{STAFF}export/", {"template": "1"})
    assert len(list(load_workbook(BytesIO(template.content)).active.iter_rows())) == 2
