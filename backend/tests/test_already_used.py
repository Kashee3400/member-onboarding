import csv

import pytest

from apps.applications.legacy import import_legacy_members
from apps.core.tenancy import organization_context

from .test_applications import AADHAAR, OTHER_AADHAAR, URL, World, complete_form

pytestmark = pytest.mark.django_db(transaction=True)

COLUMNS = [
    "member_tr_code",
    "member_code",
    "member_name",
    "mpp_code",
    "mobile_no",
    "is_active",
    "is_default",
    "application_no",
    "aadhar_no",
]
TAKEN_MOBILE = "9876543210"


@pytest.fixture
def world(org_a):
    return World(org_a)


def load(org, tmp_path, *, active, mobile=TAKEN_MOBILE, aadhaar=""):
    path = tmp_path / "members.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerow(["0900209982010025", "M1", "Old", "", mobile, active, "True", "", aadhaar])
    with organization_context(org.id):
        import_legacy_members(path, organization_id=org.id, form_prefix="A")


def submit_with(world, aadhaar, **address):
    client = world.client(world.facilitator)
    application = world.filled(aadhaar)
    data = complete_form()
    data["address"].update({"mobile": f"9{aadhaar[-9:]}", **address})
    client.patch(f"{URL}{application['id']}/", {"data": data})
    return client.post(f"{URL}{application['id']}/submit/")


def test_a_mobile_on_another_form_is_refused(world):
    world.submitted(AADHAAR)

    response = submit_with(world, OTHER_AADHAAR, mobile=f"9{AADHAAR[-9:]}")

    assert response.status_code == 400
    assert response.data["error"]["details"]["address.mobile"] == (
        "Another form already uses this mobile number."
    )


def test_a_mobile_of_a_member_is_refused_with_their_code(world):
    member = world.fully_approved(AADHAAR)

    response = submit_with(world, OTHER_AADHAAR, mobile=f"9{AADHAAR[-9:]}")

    assert member["tr_code"] in response.data["error"]["details"]["address.mobile"]


def test_a_mobile_of_an_existing_member_is_refused(world, org_a, tmp_path):
    load(org_a, tmp_path, active="True")

    response = submit_with(world, AADHAAR, mobile=TAKEN_MOBILE)

    assert "0900209982010025" in response.data["error"]["details"]["address.mobile"]


def test_a_former_members_mobile_is_free(world, org_a, tmp_path):
    load(org_a, tmp_path, active="False")

    assert submit_with(world, AADHAAR, mobile=TAKEN_MOBILE).status_code == 200


def test_an_email_on_another_form_is_refused(world):
    first = submit_with(world, AADHAAR, email="Sunita@Example.com")
    assert first.status_code == 200

    response = submit_with(world, OTHER_AADHAAR, email="sunita@example.com")

    assert response.data["error"]["details"]["address.email"] == (
        "Another form already uses this email."
    )


def test_an_active_members_aadhaar_is_refused_with_their_code(world, org_a, tmp_path):
    load(org_a, tmp_path, active="True", aadhaar=AADHAAR)
    client = world.client(world.facilitator)
    application = world.draft(client)

    response = client.patch(f"{URL}{application['id']}/", {"aadhaar_number": AADHAAR})

    assert response.status_code == 409
    assert "0900209982010025" in response.data["error"]["message"]


def test_a_member_who_became_active_after_the_draft_is_caught_at_submit(world, org_a, tmp_path):
    application = world.filled(AADHAAR)
    load(org_a, tmp_path, active="True", aadhaar=AADHAAR, mobile="")

    response = world.client(world.facilitator).post(f"{URL}{application['id']}/submit/")

    assert "applicant.aadhaar_number" in response.data["error"]["details"]
