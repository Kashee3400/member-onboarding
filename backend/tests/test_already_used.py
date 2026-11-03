import csv

import pytest

from apps.applications.legacy import import_legacy_members
from apps.applications.models import Application
from apps.core.tenancy import organization_context

from .test_applications import AADHAAR, ACCOUNT, OTHER_AADHAAR, URL, World, complete_form

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
    world.verify_contacts(application["id"])
    return client.post(f"{URL}{application['id']}/submit/")


def save_with(world, aadhaar, **address):
    client = world.client(world.facilitator)
    application = world.filled(aadhaar)
    data = complete_form()
    data["address"].update({"mobile": f"9{aadhaar[-9:]}", **address})
    return client.patch(f"{URL}{application['id']}/", {"data": data})


def test_a_mobile_on_another_form_is_refused(world):
    world.submitted(AADHAAR)

    response = save_with(world, OTHER_AADHAAR, mobile=f"9{AADHAAR[-9:]}")

    assert response.data["duplicate_fields"]["address.mobile"] == (
        "Another form already uses this mobile number."
    )


def test_a_mobile_of_a_member_is_refused_with_their_code(world):
    member = world.fully_approved(AADHAAR)

    response = save_with(world, OTHER_AADHAAR, mobile=f"9{AADHAAR[-9:]}")

    assert member["tr_code"] in response.data["duplicate_fields"]["address.mobile"]


def test_a_mobile_of_an_existing_member_is_refused(world, org_a, tmp_path):
    load(org_a, tmp_path, active="True")

    response = save_with(world, AADHAAR, mobile=TAKEN_MOBILE)

    assert "0900209982010025" in response.data["duplicate_fields"]["address.mobile"]


def test_a_former_members_mobile_is_free(world, org_a, tmp_path):
    load(org_a, tmp_path, active="False")

    assert submit_with(world, AADHAAR, mobile=TAKEN_MOBILE).status_code == 200


def test_an_email_on_another_form_is_refused(world):
    first = submit_with(world, AADHAAR, email="Sunita@Example.com")
    assert first.status_code == 200

    response = save_with(world, OTHER_AADHAAR, email="sunita@example.com")

    assert response.data["duplicate_fields"]["address.email"] == (
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


# Refused as they are typed, not at submit ----------------------------------------------


def save(world, application, **data):
    return world.client(world.facilitator).patch(f"{URL}{application['id']}/", data, format="json")


def test_a_taken_mobile_is_not_kept_and_the_rest_is(world):
    first = world.submitted()
    later = world.draft()

    response = save(
        world,
        later,
        data={"address": {"mobile": first["data"]["address"]["mobile"], "tehsil": "Gyanpur"}},
    )

    assert response.status_code == 200, response.content
    assert "address.mobile" in response.data["duplicate_fields"]
    assert response.data["data"]["address"]["mobile"] == ""
    assert response.data["data"]["address"]["tehsil"] == "Gyanpur"


def test_a_taken_email_is_not_kept(world):
    first = world.filled()
    data = complete_form()
    data["address"]["email"] = "member@example.com"
    save(world, first, data=data)
    later = world.draft()

    response = save(world, later, data={"address": {"email": "Member@Example.com"}})

    assert response.data["duplicate_fields"]["address.email"]
    assert response.data["data"]["address"]["email"] == ""


def test_a_taken_bank_account_is_not_kept(world):
    world.submitted()
    later = world.draft()

    response = save(world, later, account_number=ACCOUNT)

    assert response.data["duplicate_fields"]["bank.account_number"]
    assert response.data["account_last4"] == ""


def test_a_new_number_saves_with_nothing_flagged(world):
    later = world.draft()

    response = save(
        world, later, account_number="123456789012", data={"address": {"mobile": "9123456780"}}
    )

    assert response.data["duplicate_fields"] == {}
    assert response.data["account_last4"] == "9012"


def test_a_taken_account_still_stops_the_submit(world, org_a):
    world.submitted()
    second = world.filled(OTHER_AADHAAR)
    with organization_context(org_a.id):
        first_index = (
            Application.objects.exclude(pk=second["id"])
            .values_list("account_index", flat=True)
            .first()
        )
        Application.objects.filter(pk=second["id"]).update(account_index=first_index)

    response = world.client(world.facilitator).post(f"{URL}{second['id']}/submit/")

    assert response.status_code == 400
    assert "bank.account_number" in response.data["error"]["details"]
