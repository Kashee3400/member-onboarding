import pytest

from apps.applications import form
from apps.applications.models import Application, FormOption
from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context

from .conftest import authenticated_client
from .test_applications import URL, World, complete_form

pytestmark = pytest.mark.django_db(transaction=True)

LISTS_URL = "/api/v1/settings/form-lists/"


@pytest.fixture
def world(org_a):
    return World(org_a)


def schema(world, user=None):
    return world.client(user or world.facilitator).get(f"{URL}form/").data


def field(schema, path):
    section, key = path.split(".")
    section = next(item for item in schema["sections"] if item["key"] == section)
    return next(item for item in section["fields"] if item["key"] == key)


def options_of(world, key):
    lists = world.client(world.admin).get(LISTS_URL).data["lists"]
    return next(item for item in lists if item["key"] == key)["options"]


def save_list(world, key, options):
    return world.client(world.admin).put(f"{LISTS_URL}{key}/", {"options": options}, format="json")


def as_sent(options):
    return [
        {
            "value": o["value"],
            "label": o["label"],
            "label_hi": o["label_hi"],
            "is_active": o["active"],
        }
        for o in options
    ]


def retire(world, key, value):
    options = as_sent(options_of(world, key))
    for option in options:
        if option["value"] == value:
            option["is_active"] = False
    response = save_list(world, key, options)
    assert response.status_code == 200, response.content


def test_an_organization_starts_with_the_usual_lists(world, org_a):
    data = schema(world)

    education = field(data, "applicant.education")
    assert [o["value"] for o in education["options"]] == [o["value"] for o in form.EDUCATION]
    assert education["option_list"] == "education"
    assert education["retired_options"] == []
    assert education["options"][0]["label_hi"] == "कोई नहीं"
    assert [o["value"] for o in data["family"]["relations"]] == [
        o["value"] for o in form.FAMILY_RELATIONS
    ]
    with organization_context(org_a.id):
        seeded = FormOption.objects.count()
    # Read again: nothing is seeded twice.
    schema(world)
    with organization_context(org_a.id):
        assert FormOption.objects.count() == seeded


def test_the_nominee_relation_is_a_list(world):
    relation = field(schema(world), "nominee.relation")

    assert relation["type"] == "choice"
    assert relation["option_list"] == "nominee_relation"
    assert {"husband", "son", "daughter"} <= {o["value"] for o in relation["options"]}


def test_an_admin_renames_reorders_and_adds(world):
    options = as_sent(options_of(world, "education"))
    options[0]["label"], options[0]["label_hi"] = "Illiterate", "निरक्षर"
    options.reverse()
    options.append({"label": "Diploma (ITI)", "label_hi": "डिप्लोमा", "is_active": True})

    response = save_list(world, "education", options)

    assert response.status_code == 200, response.content
    offered = field(schema(world), "applicant.education")["options"]
    assert offered[0]["value"] == "postgraduate"
    assert offered[-2] == {"value": "none", "label": "Illiterate", "label_hi": "निरक्षर"}
    assert offered[-1]["value"] == "diploma_iti"
    with organization_context(world.org.id):
        event = AuditEvent.objects.get(action="form_list.updated")
    assert event.metadata == {"list": "education", "options": 8, "retired": 0}


def test_a_value_cannot_be_removed(world):
    options = as_sent(options_of(world, "category"))[1:]

    response = save_list(world, "category", options)

    assert response.status_code == 400
    assert "Retire" in str(response.data)


@pytest.mark.parametrize(
    "change",
    [
        lambda options: options.append({**options[0], "value": "", "label": options[1]["label"]}),
        lambda options: [option.update(is_active=False) for option in options],
        lambda options: options.append({**options[0], "value": "unknown"}),
        lambda options: options.append({"label": "No Hindi", "label_hi": "", "is_active": True}),
    ],
)
def test_a_list_must_make_sense(world, change):
    options = as_sent(options_of(world, "category"))
    change(options)

    assert save_list(world, "category", options).status_code == 400


def test_female_stays_while_members_are_women_only(world):
    options = as_sent(options_of(world, "gender"))
    for option in options:
        option["is_active"] = option["value"] != "female"

    assert save_list(world, "gender", options).status_code == 400


def test_only_admins_edit_the_lists(world):
    client = world.client(world.facilitator)

    assert client.get(LISTS_URL).status_code == 403
    assert client.put(f"{LISTS_URL}education/", {"options": []}, format="json").status_code == 403
    assert save_list(world, "shoe_size", [{"label": "x", "label_hi": "x"}]).status_code == 404


def test_a_retired_value_is_shown_but_not_offered(world):
    retire(world, "category", "st")

    category = field(schema(world), "applicant.category")

    assert "st" not in {o["value"] for o in category["options"]}
    assert category["retired_options"] == [
        {"value": "st", "label": "ST", "label_hi": "अनुसूचित जनजाति (ST)"}
    ]


def test_a_retired_value_cannot_be_chosen_for_a_new_form(world):
    retire(world, "category", "st")
    retire(world, "family_relation", "brother")
    client = world.client(world.facilitator)
    application = world.filled()
    data = complete_form()
    data["applicant"]["category"] = "st"
    data["family"][0]["relation"] = "brother"

    saved = client.patch(f"{URL}{application['id']}/", {"data": data}, format="json")

    assert saved.status_code == 200, saved.content
    assert saved.data["data"]["applicant"]["category"] == ""
    assert saved.data["data"]["family"][0]["relation"] == ""
    response = client.post(f"{URL}{application['id']}/submit/")
    assert response.status_code == 400
    assert "applicant.category" in response.data["error"]["details"]
    assert "family.0.relation" in response.data["error"]["details"]


def test_a_form_that_already_held_a_retired_value_keeps_it(world, org_a):
    application = world.submitted()
    with organization_context(org_a.id):
        Application.objects.filter(pk=application["id"]).update(status="rejected")
    retire(world, "education", "12th")
    client = world.client(world.facilitator)

    data = complete_form()
    data["address"] = application["data"]["address"]
    saved = client.patch(f"{URL}{application['id']}/", {"data": data}, format="json")

    assert saved.data["data"]["applicant"]["education"] == "12th"
    response = client.post(f"{URL}{application['id']}/submit/")
    assert response.status_code == 200, response.content


def test_an_old_typed_nominee_relation_still_reads(world, org_a):
    application = world.filled()
    with organization_context(org_a.id):
        row = Application.objects.get(pk=application["id"])
        row.data["nominee"]["relation"] = "Grandson"
        row.save()

    response = world.client(world.facilitator).post(f"{URL}{application['id']}/submit/")

    assert response.status_code == 400
    assert "nominee.relation" in response.data["error"]["details"]
    detail = world.client(world.facilitator).get(f"{URL}{application['id']}/").data
    assert detail["data"]["nominee"]["relation"] == "Grandson"


def test_each_organization_keeps_its_own_lists(world, org_b, admin_b):
    retire(world, "category", "st")

    other = authenticated_client(org_b, admin_b).get(f"{URL}form/").data

    assert "st" in {o["value"] for o in field(other, "applicant.category")["options"]}
