import pytest

from .test_applications import URL, World


@pytest.fixture
def world(org_a):
    return World(org_a)


def test_a_list_row_says_who_the_form_is_for(world):
    application = world.submitted()

    row = world.client(world.facilitator).get(URL, {"mine": "true"}).data["results"][0]

    assert row["id"] == application["id"]
    assert row["aadhaar_last4"] == application["aadhaar_last4"]
    assert row["mobile"] == application["data"]["address"]["mobile"]
    assert row["photo_id"]


def test_a_fresh_submission_waits_at_the_area_manager(world):
    application = world.submitted()

    stages = world.client(world.facilitator).get(f"{URL}{application['id']}/").data["stages"]

    assert [stage["state"] for stage in stages] == ["pending", "waiting", "waiting"]
    assert stages[0]["label"] == "Area Manager"
    assert stages[0]["since"]


def test_an_approved_stage_names_who_approved_it(world):
    application = world.submitted()
    world.approve(application, world.manager)

    stages = world.client(world.facilitator).get(f"{URL}{application['id']}/").data["stages"]

    assert [stage["state"] for stage in stages] == ["approved", "pending", "waiting"]
    assert stages[0]["by"]
    assert stages[0]["at"]


def test_a_rejection_shows_where_and_why(world):
    application = world.submitted()
    world.client(world.manager).post(
        f"{URL}{application['id']}/decide/",
        {"decision": "rejected", "reason": "Photo unclear"},
    )

    stages = world.client(world.facilitator).get(f"{URL}{application['id']}/").data["stages"]

    assert stages[0]["state"] == "rejected"
    assert stages[0]["reason"] == "Photo unclear"


def test_the_form_says_what_the_member_pays(world):
    fee = world.client(world.facilitator).get(f"{URL}form/").data["fee"]

    assert fee["total"] == fee["admission_fee"] + fee["share_count"] * fee["share_price"]
    assert fee["admission_fee"] > 0
