import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.applications.models import ReviewStepAccess
from apps.applications.review_steps import STEP_KEYS
from apps.core.tenancy import organization_context

from .test_applications import (
    AADHAAR,
    ACCOUNT,
    PAYMENT,
    REVIEW_STEPS,
    URL,
    World,
    choose_review_steps,
    jpeg_bytes,
)

pytestmark = pytest.mark.django_db(transaction=True)

STEPS_URL = "/api/v1/settings/review-steps/"
DEFAULT = REVIEW_STEPS


@pytest.fixture
def world(org_a):
    return World(org_a)


@pytest.fixture
def application(world):
    return world.submitted()


def detail(world, user, application):
    return world.client(user).get(f"{URL}{application['id']}/").data


def mine(world, user, application):
    return {
        step["key"] for step in detail(world, user, application)["review_steps"] if step["mine"]
    }


def test_each_role_acts_on_the_steps_chosen_for_it(world, application):
    assert mine(world, world.legal, application) == {"member", "address", "nominee"}
    assert mine(world, world.manager, application) == {"milk", "household", "village"}
    assert mine(world, world.finance, application) == {"bank", "fee"}
    # The admin acts on every step, whatever Review Steps says.
    assert mine(world, world.admin, application) == set(STEP_KEYS)


def test_there_are_eight_steps_in_order(world, application):
    steps = detail(world, world.legal, application)["review_steps"]

    assert [step["number"] for step in steps] == list(range(1, 9))


def test_everyone_can_read_every_step(world, application):
    for user in (world.manager, world.legal, world.finance, world.admin):
        data = detail(world, user, application)
        assert {"applicant", "bank", "animals", "nominee"} <= set(data["data"])
        assert data["account_last4"] == ACCOUNT[-4:]
        rows = world.client(user).get(f"{URL}{application['id']}/documents/").data
        assert {"passbook", "aadhaar_front"} <= {row["document_type"] for row in rows}


def test_all_approvers_get_the_full_numbers(world, application):
    for user in (world.manager, world.legal, world.finance):
        response = world.client(user).post(f"{URL}{application['id']}/numbers/")
        assert response.data == {"aadhaar_number": AADHAAR, "account_number": ACCOUNT}


def test_village_details_come_with_the_form(world, application):
    place = detail(world, world.manager, application)["place"]

    assert place["mpp_code"] == "1305"
    assert place["village_code"] == "00209982"
    assert place["mcc_name"] == "Bhadohi"


def test_only_your_own_steps_can_be_marked_when_rejecting(world, application):
    response = world.client(world.manager).post(
        f"{URL}{application['id']}/decide/",
        {"decision": "rejected", "reason": "x", "rejected_fields": ["bank.ifsc"]},
    )

    assert response.status_code == 400
    assert "rejected_fields" in response.data["error"]["details"]


def test_a_rejection_on_your_own_step_goes_through(world, application):
    response = world.client(world.manager).post(
        f"{URL}{application['id']}/decide/",
        {"decision": "rejected", "reason": "x", "rejected_fields": ["animals.production_lpd"]},
    )

    assert response.status_code == 200


def test_an_admin_can_move_a_step_to_another_role(world, application):
    steps = {**DEFAULT, "bank": ["area_manager", "finance"]}

    response = world.client(world.admin).put(STEPS_URL, {"steps": steps})

    assert response.status_code == 200
    assert "bank" in mine(world, world.manager, application)
    assert "bank" in mine(world, world.finance, application)
    row = next(item for item in response.data["steps"] if item["key"] == "bank")
    assert row["roles"] == ["area_manager", "finance"]


def test_a_moved_step_changes_what_can_be_marked(world, application):
    world.client(world.admin).put(STEPS_URL, {"steps": {**DEFAULT, "bank": ["area_manager"]}})

    response = world.client(world.manager).post(
        f"{URL}{application['id']}/decide/",
        {"decision": "rejected", "reason": "x", "rejected_fields": ["bank.ifsc"]},
    )

    assert response.status_code == 200


def test_every_step_needs_a_role(world):
    response = world.client(world.admin).put(STEPS_URL, {"steps": {**DEFAULT, "bank": []}})

    assert response.status_code == 400


def test_a_role_that_cannot_approve_is_refused(world):
    response = world.client(world.admin).put(STEPS_URL, {"steps": {**DEFAULT, "bank": ["pib"]}})

    assert response.status_code == 400


def test_a_partial_save_is_refused(world):
    response = world.client(world.admin).put(STEPS_URL, {"steps": {"bank": ["finance"]}})

    assert response.status_code == 400


def test_changing_steps_needs_the_permission(world):
    assert world.client(world.manager).put(STEPS_URL, {"steps": DEFAULT}).status_code == 403


def test_organizations_keep_their_own_choice(world, org_b):
    world.client(world.admin).put(STEPS_URL, {"steps": DEFAULT})

    with organization_context(org_b.id):
        assert ReviewStepAccess.objects.count() == 0


def test_finance_records_how_it_was_paid(world, application):
    world.approve(application, world.manager)
    world.approve(application, world.legal)
    client = world.client(world.finance)
    client.post(
        f"{URL}{application['id']}/documents/",
        {"document_type": "payment_proof", "file": SimpleUploadedFile("p.jpg", jpeg_bytes())},
        format="multipart",
    )

    response = client.post(f"{URL}{application['id']}/payment/", PAYMENT)

    # The bank is the organization's; the mode and amount are what was collected.
    assert response.data["payment"]["bank_name"] == "Indian Bank"
    assert response.data["payment"]["bank_address"] == "Kashee Vidyapith Road, Varanasi"
    assert response.data["payment"]["mode"] == "cash"
    assert response.data["payment"]["amount"] == 50
    assert "is_shg_member" in response.data["fee"]


def steps_of(world, user, application):
    return detail(world, user, application)["review_steps"]


def approve(world, user, application, steps=None):
    body = {"decision": "approved"}
    if steps is not None:
        body["steps"] = steps
    return world.client(user).post(f"{URL}{application['id']}/decide/", body, format="json")


def test_nothing_is_assumed_until_the_steps_are_chosen(world, application, org_a):
    with organization_context(org_a.id):
        ReviewStepAccess.objects.all().delete()

    response = approve(world, world.manager, application)

    assert response.status_code == 409
    assert mine(world, world.manager, application) == set()


def test_one_step_does_not_move_the_form(world, application):
    response = approve(world, world.manager, application, ["milk"])

    assert response.status_code == 200
    assert response.data["status"] == "pending_am"
    step = next(item for item in response.data["review_steps"] if item["key"] == "milk")
    assert step["approved_by_name"]
    assert step["can_approve"] is False


def test_the_form_moves_when_the_stage_steps_are_all_done(world, application):
    approve(world, world.manager, application, ["milk"])
    approve(world, world.manager, application, ["household"])

    response = approve(world, world.manager, application, ["village"])

    assert response.data["status"] == "pending_cs"


def test_a_step_cannot_be_approved_twice(world, application):
    approve(world, world.manager, application, ["milk"])

    assert approve(world, world.manager, application, ["milk"]).status_code == 400


def test_another_roles_step_cannot_be_approved(world, application):
    assert approve(world, world.manager, application, ["bank"]).status_code == 400


def test_a_step_cannot_be_approved_before_its_stage(world, application):
    assert approve(world, world.legal, application, ["member"]).status_code == 403


def test_every_step_shows_who_approved_it(world, application):
    world.fully_approved_steps = None
    approve(world, world.manager, application)
    approve(world, world.legal, application)

    done = [
        step["key"] for step in steps_of(world, world.finance, application) if step["approved_at"]
    ]

    assert set(done) == {"milk", "household", "village", "member", "address", "nominee"}


def test_a_rejection_starts_all_the_steps_again(world, application):
    approve(world, world.manager, application)
    world.client(world.legal).post(
        f"{URL}{application['id']}/decide/", {"decision": "rejected", "reason": "x"}
    )
    client = world.client(world.facilitator)
    client.post(f"{URL}{application['id']}/submit/")

    steps = steps_of(world, world.manager, application)

    assert [step["approved_at"] for step in steps] == [None] * 8


def test_the_fee_can_move_to_another_role(world, application, org_a):
    with organization_context(org_a.id):
        choose_review_steps({**REVIEW_STEPS, "fee": ["area_manager"]})

    response = world.client(world.manager).post(f"{URL}{application['id']}/payment/", PAYMENT)
    denied = world.client(world.finance).post(f"{URL}{application['id']}/payment/", PAYMENT)

    assert response.status_code == 200
    assert denied.status_code == 403


def test_finance_records_only_the_deposit_date(world, application):
    world.approve(application, world.manager)
    world.approve(application, world.legal)

    # Anything else sent is ignored: it comes from the settings and the form.
    response = world.client(world.finance).post(
        f"{URL}{application['id']}/payment/",
        {**PAYMENT, "share_quantity": 0, "bank_name": "Elsewhere", "amount": 1},
    )

    payment = response.data["payment"]
    assert (payment["bank_name"], payment["amount"], payment["deposited_on"]) == (
        "Indian Bank",
        50,
        "2026-01-15",
    )
    assert response.data["fee"]["share_quantity"] == 5


def test_no_deposit_before_the_collection_bank_is_set(world, application):
    from apps.applications.models import MemberCodeSettings
    from apps.core.tenancy import organization_context

    world.approve(application, world.manager)
    world.approve(application, world.legal)
    with organization_context(world.org.id):
        MemberCodeSettings.objects.update(collection_bank_name="")

    response = world.client(world.finance).post(f"{URL}{application['id']}/payment/", PAYMENT)

    assert response.status_code == 409


def test_the_fee_step_needs_the_payment(world, application):
    world.approve(application, world.manager)
    world.approve(application, world.legal)

    assert approve(world, world.finance, application, ["bank"]).status_code == 200
    assert approve(world, world.finance, application, ["fee"]).status_code == 400


def test_landline_is_optional(world, application):
    data = detail(world, world.manager, application)

    assert "landline" not in data["data"]["address"]
