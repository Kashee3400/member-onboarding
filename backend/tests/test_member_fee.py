import pytest

from apps.applications.models import FormOption
from apps.core.tenancy import organization_context

from .test_applications import URL, World

pytestmark = pytest.mark.django_db(transaction=True)

FORM = "/api/v1/applications/form/"
LISTS = "/api/v1/settings/form-lists/"


@pytest.fixture
def world(org_a):
    return World(org_a)


def submit_with(world, fee):
    client = world.client(world.facilitator)
    application = world.filled()
    if fee is not None:
        data = {**application["data"], "fee": fee}
        client.patch(f"{URL}{application['id']}/", {"data": data}, format="json")
    return client.post(f"{URL}{application['id']}/submit/", {}, format="json")


def test_the_form_asks_how_the_fee_was_collected_and_only_cash_is_open(world):
    schema = world.client(world.facilitator).get(FORM).data
    fee = next(section for section in schema["sections"] if section["key"] == "fee")
    mode = next(field for field in fee["fields"] if field["key"] == "payment_mode")

    # Online is kept in the list, retired, until a gateway is set up.
    assert [option["value"] for option in mode["options"]] == ["cash"]
    assert [option["value"] for option in mode["retired_options"]] == ["online"]


def test_the_form_does_not_ask_for_an_amount(world):
    schema = world.client(world.facilitator).get(FORM).data
    fee = next(section for section in schema["sections"] if section["key"] == "fee")

    assert [field["key"] for field in fee["fields"]] == ["payment_mode", "transaction_id"]


def test_collecting_the_admission_fee_in_cash_submits(world):
    response = submit_with(world, {"payment_mode": "cash"})

    assert response.status_code == 200, response.content


def test_a_form_without_the_fee_is_not_submitted(world):
    response = submit_with(world, {})

    assert response.status_code == 400
    assert "fee.payment_mode" in response.data["error"]["details"]


def test_online_cannot_be_chosen_until_it_is_switched_on(world):
    client = world.client(world.facilitator)
    application = world.filled()
    data = {**application["data"], "fee": {"payment_mode": "online"}}

    saved = client.patch(f"{URL}{application['id']}/", {"data": data}, format="json").data

    assert saved["data"]["fee"]["payment_mode"] == ""


def test_switching_online_on_needs_its_transaction_id(world):
    world.client(world.admin).get(LISTS)
    with organization_context(world.org.id):
        FormOption.objects.filter(list_key="payment_mode", value="online").update(is_active=True)

    without = submit_with(world, {"payment_mode": "online"})

    assert without.status_code == 400
    assert "fee.transaction_id" in without.data["error"]["details"]
