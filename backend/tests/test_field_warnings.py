from datetime import date

import pytest

from apps.applications import warnings
from apps.applications.models import Application
from apps.core.tenancy import organization_context

from .test_applications import OTHER_AADHAAR, URL, World, complete_form

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def world(org_a):
    return World(org_a)


def detail(world, application, user=None):
    response = world.client(user or world.manager).get(f"{URL}{application['id']}/")
    assert response.status_code == 200, response.content
    return response.data


# The server's own rules, which the app now checks while typing --------------------------


@pytest.mark.parametrize(
    ("change", "path"),
    [
        (lambda d: d["applicant"].update(date_of_birth="1900-01-01"), "applicant.date_of_birth"),
        (lambda d: d["address"].update(email="not-an-email"), "address.email"),
        (lambda d: d["animals"].update(production_lpd="twelve"), "animals.production_lpd"),
        (lambda d: d["animals"].update(consumption_lpd=-1), "animals.consumption_lpd"),
    ],
)
def test_more_policies_are_enforced(world, change, path):
    client = world.client(world.facilitator)
    application = world.filled()
    data = complete_form()
    change(data)
    client.patch(f"{URL}{application['id']}/", {"data": data})

    response = client.post(f"{URL}{application['id']}/submit/")

    assert response.status_code == 400
    assert path in response.data["error"]["details"]


def test_the_form_serves_the_rules_the_app_checks(world):
    schema = world.client(world.facilitator).get(f"{URL}form/").data
    fields = {
        f"{section['key']}.{field['key']}": field
        for section in schema["sections"]
        for field in section["fields"]
    }
    assert fields["address.mobile"]["pattern"] == r"^[6-9]\d{9}$"
    assert fields["bank.ifsc"]["pattern"]
    assert fields["address.email"]["pattern"]
    assert fields["applicant.date_of_birth"]["min_age"] == 18
    assert fields["applicant.date_of_birth"]["max_age"] == 100
    assert fields["nominee.date_of_birth"]["adult_age"] == 18


# Warnings from the form's own answers ----------------------------------------------------


def answers(**animals):
    data = complete_form()
    data["animals"].update(animals)
    return data


def test_age_outside_the_usual_range_is_pointed_out():
    data = complete_form()
    data["applicant"]["date_of_birth"] = "1940-06-01"
    found = warnings.data_warnings(data, on=date(2026, 11, 3))
    assert found["applicant.date_of_birth"].startswith("The applicant was 86")

    data["applicant"]["date_of_birth"] = "2010-06-01"
    assert "16" in warnings.data_warnings(data, on=date(2026, 11, 3))["applicant.date_of_birth"]

    data["applicant"]["date_of_birth"] = "1984-01-15"
    assert "applicant.date_of_birth" not in warnings.data_warnings(data, on=date(2026, 11, 3))


def test_implausible_milk_figures_are_pointed_out():
    on = date(2026, 11, 3)
    assert "animals.consumption_lpd" in warnings.data_warnings(
        answers(production_lpd=4, consumption_lpd=6), on=on
    )
    # Two buffaloes in milk: 40 litres is the ceiling.
    assert "animals.production_lpd" in warnings.data_warnings(answers(production_lpd=41), on=on)
    assert "animals.production_lpd" not in warnings.data_warnings(answers(production_lpd=40), on=on)
    assert "animals.production_lpd" in warnings.data_warnings(
        answers(buffalo_in_milk=0, production_lpd=5), on=on
    )


def test_a_plain_form_has_no_warnings(world):
    found = detail(world, world.submitted())
    assert found["field_warnings"] == {}
    assert found["warnings"] == []


def test_the_name_mismatch_is_tied_to_the_holder_field(world):
    client = world.client(world.facilitator)
    application = world.filled()
    data = complete_form()
    data["bank"]["holder_name"] = "Someone Else"
    response = client.patch(f"{URL}{application['id']}/", {"data": data})

    assert "bank.holder_name" in response.data["field_warnings"]
    assert response.data["warnings"] == [response.data["field_warnings"]["bank.holder_name"]]


# Warnings from other forms ---------------------------------------------------------------


def test_a_shared_bank_account_names_the_other_form(world):
    first = world.submitted()
    second = world.submitted(OTHER_AADHAAR)  # The helper gives every form the same account.

    found = detail(world, second)["field_warnings"]

    assert found["bank.account_number"] == (
        f"This bank account is on another form ({first['form_number']})."
    )
    assert found["bank.account_number"] in detail(world, second)["warnings"]


def test_another_form_outside_the_reviewers_mpps_is_not_named(world, org_a):
    first = world.submitted()
    second = world.submitted(OTHER_AADHAAR)
    with organization_context(org_a.id):
        Application.objects.filter(pk=first["id"]).update(mpp=world.other_mpp)

    found = detail(world, second)["field_warnings"]

    assert found["bank.account_number"] == "This bank account is on another form."
    assert first["form_number"] not in str(detail(world, second))


def test_a_mobile_number_on_another_form_is_pointed_out(world):
    first = world.submitted()
    client = world.client(world.facilitator)
    later = world.draft(client)
    client.patch(
        f"{URL}{later['id']}/",
        {"data": {"address": {"mobile": first["data"]["address"]["mobile"]}}},
    )

    found = detail(world, first)["field_warnings"]

    assert found["address.mobile"] == "This mobile number is on another form."


def place_drafts(world, *positions):
    client = world.client(world.facilitator)
    for latitude, longitude in positions:
        draft = world.draft(client)
        location = {"location": {"latitude": latitude, "longitude": longitude}}
        assert client.patch(f"{URL}{draft['id']}/", {"data": location}).status_code == 200


USUAL = [(25.41, 82.51), (25.42, 82.52), (25.415, 82.515)]


def test_a_form_filled_far_from_the_mpp_is_pointed_out(world):
    place_drafts(world, *USUAL)
    client = world.client(world.facilitator)
    application = world.filled()
    data = complete_form()
    data["location"] = {"latitude": 25.9, "longitude": 82.51}  # About 54 km north.
    client.patch(f"{URL}{application['id']}/", {"data": data})
    client.post(f"{URL}{application['id']}/submit/")

    message = detail(world, application)["field_warnings"]["location.latitude"]

    assert message.startswith("Filled 5")
    assert "km from where this MPP's other forms were filled" in message


def test_a_form_filled_nearby_is_not_pointed_out(world):
    place_drafts(world, *USUAL)
    found = detail(world, world.submitted())["field_warnings"]
    assert "location.latitude" not in found


def test_too_few_earlier_forms_say_nothing_about_the_place(world):
    place_drafts(world, *USUAL[:1], (27.0, 80.0))
    found = detail(world, world.submitted())["field_warnings"]
    assert "location.latitude" not in found


def test_drafts_skip_the_checks_against_other_forms(world):
    world.submitted()
    second = world.filled(OTHER_AADHAAR)
    assert "bank.account_number" not in second["field_warnings"]
