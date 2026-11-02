import pytest

from apps.applications.models import Application
from apps.core.tenancy import organization_context
from apps.hierarchy.imports import COLUMNS
from apps.hierarchy.models import District, Hamlet, Mpp, State, Tehsil, Village

from .conftest import authenticated_client
from .test_applications import URL, World
from .test_reports import IMPORT, workbook_file

pytestmark = pytest.mark.django_db(transaction=True)

API = "/api/v1/hierarchy/"
PLACE_COLUMNS = (
    *COLUMNS,
    "state_code",
    "hamlet_code",
    "state_name",
    "district_code",
    "district_name",
    "tehsil_code",
    "tehsil_name",
    "village_name",
    "hamlet_name",
    "pincode",
    "post_office",
)


@pytest.fixture
def world(org_a):
    return World(org_a)


def place_chain(org, village_code="00209982"):
    with organization_context(org.id):
        state = State.objects.create(code="09", name="Uttar Pradesh", name_hi="उत्तर प्रदेश")
        district = District.objects.create(state=state, code="183", name="Bhadohi")
        tehsil = Tehsil.objects.create(district=district, code="00951", name="Gyanpur")
        village = Village.objects.create(tehsil=tehsil, code=village_code, name="Dudwa Kalan")
        hamlet = Hamlet.objects.create(village=village, code="03", name="Purva")
        return state, district, tehsil, village, hamlet


def placed(world):
    """The World's MPP, linked to its whole place."""
    *_, village, hamlet = place_chain(world.org)
    with organization_context(world.org.id):
        mpp = Mpp.objects.get(pk=world.mpp.pk)
        mpp.village, mpp.hamlet = village, hamlet
        mpp.post_office, mpp.pincode = "Mondh", "221406"
        mpp.save()
    return mpp


def place_row(mpp="2001", village="00300001", district="183", tehsil="00951", **names):
    return (
        "P9",
        "Plant Nine",
        "7",
        "MCC Seven",
        mpp,
        f"9{mpp}",
        "New MPP",
        village,
        "09",
        "01",
        names.get("state_name", "Uttar Pradesh"),
        district,
        names.get("district_name", "Bhadohi"),
        tehsil,
        names.get("tehsil_name", "Gyanpur"),
        names.get("village_name", "Rampur"),
        names.get("hamlet_name", "Purva"),
        names.get("pincode", "221406"),
        names.get("post_office", "Mondh"),
    )


# Masters -----------------------------------------------------------------------------


def test_the_chain_is_read_and_filtered_by_parent(world):
    state, *_ = place_chain(world.org)
    admin = world.client(world.admin)

    listed = admin.get(f"{API}tehsils/", {"district__state": str(state.id)}).data
    hamlet = admin.get(f"{API}hamlets/").data["results"][0]

    assert [item["code"] for item in listed["results"]] == ["00951"]
    assert hamlet["parent_label"] == "00209982 - Dudwa Kalan"
    assert admin.get(f"{API}villages/", {"q": "dud"}).data["count"] == 1
    assert admin.get(f"{API}villages/", {"q": "nowhere"}).data["count"] == 0


def test_locations_come_only_from_the_erp_import(world):
    state, district, tehsil, village, hamlet = place_chain(world.org)
    admin = world.client(world.admin)

    assert admin.post(f"{API}states/", {"code": "10", "name": "Bihar"}).status_code == 405
    assert admin.patch(f"{API}districts/{district.id}/", {"name": "X"}).status_code == 405
    assert admin.patch(f"{API}villages/{village.id}/", {"name": "X"}).status_code == 405
    assert admin.patch(f"{API}hamlets/{hamlet.id}/", {"name": "X"}).status_code == 405
    assert (
        admin.post(
            f"{API}tehsils/", {"district": str(district.id), "code": "1", "name": "X"}
        ).status_code
        == 405
    )


def test_a_tehsil_name_can_be_set_but_not_its_code(world):
    mpp = placed(world)
    admin = world.client(world.admin)
    tehsil = mpp.village.tehsil

    response = admin.patch(
        f"{API}tehsils/{tehsil.id}/",
        {"name": "Gyanpur Sadar", "name_hi": "ज्ञानपुर सदर", "code": "99999"},
    )

    assert response.status_code == 200, response.content
    with organization_context(world.org.id):
        tehsil.refresh_from_db()
    assert (tehsil.name, tehsil.code) == ("Gyanpur Sadar", "00951")
    assert world.client(world.facilitator).get(f"{API}mpps/").data["results"][0]["place"][
        "tehsil"
    ] == ("Gyanpur Sadar")


def test_only_hierarchy_managers_name_tehsils(world):
    *_, tehsil, _, _ = place_chain(world.org)
    facilitator = world.client(world.facilitator)
    assert facilitator.patch(f"{API}tehsils/{tehsil.id}/", {"name": "X"}).status_code == 403


def test_another_organization_sees_none_of_them(world, org_b, admin_b):
    place_chain(world.org)
    other = authenticated_client(org_b, admin_b)
    for kind in ("states", "districts", "tehsils", "villages", "hamlets"):
        assert other.get(f"{API}{kind}/").data["count"] == 0


# An MPP's place -----------------------------------------------------------------------


def test_an_mpps_place_cannot_be_typed_in(world):
    *_, village, hamlet = place_chain(world.org, village_code="00400004")

    response = world.client(world.admin).patch(
        f"{API}mpps/{world.mpp.id}/",
        {"village": str(village.id), "hamlet": str(hamlet.id), "pincode": "221406"},
    )

    assert response.status_code == 200, response.content
    assert response.data["village"] is None
    assert response.data["pincode"] == ""


def test_the_app_gets_each_mpps_place_with_its_mpps(world):
    placed(world)
    mpps = world.client(world.facilitator).get(f"{API}mpps/").data["results"]

    place = next(item for item in mpps if item["id"] == str(world.mpp.id))["place"]
    assert place == {
        "pooling_point_code": "1305",
        "village_name": "Dudwa Kalan",
        "village_code": "00209982",
        "hamlet_name": "Purva",
        "hamlet_code": "03",
        "post_office": "Mondh",
        "tehsil": "Gyanpur",
        "tehsil_code": "00951",
        "district": "Bhadohi",
        "district_code": "183",
        "state": "Uttar Pradesh",
        "state_code": "09",
        "pincode": "221406",
    }


# The form ------------------------------------------------------------------------------


def test_the_schema_marks_the_place_fields_locked(world):
    schema = world.client(world.facilitator).get(f"{URL}form/").data
    address = next(section for section in schema["sections"] if section["key"] == "address")
    locked = {field["key"] for field in address["fields"] if field.get("locked")}

    assert locked == {
        "pooling_point_code",
        "village_name",
        "village_code",
        "hamlet_name",
        "hamlet_code",
        "post_office",
        "tehsil",
        "district",
        "state",
        "pincode",
    }
    assert {field.get("source") for field in address["fields"] if field.get("locked")} == {"mpp"}


def test_a_new_draft_already_has_the_mpps_place(world):
    placed(world)
    address = world.draft()["data"]["address"]

    assert address["tehsil"] == "Gyanpur"
    assert address["district"] == "Bhadohi"
    assert address["state"] == "Uttar Pradesh"
    assert address["pincode"] == "221406"
    assert address["hamlet_name"] == "Purva"
    assert address["pooling_point_code"] == "1305"


def test_the_phone_cannot_change_the_place(world):
    placed(world)
    client = world.client(world.facilitator)
    draft = world.draft(client)
    sent = {"tehsil": "Elsewhere", "pincode": "110001", "house_number": "12", "mobile": "9"}

    saved = client.patch(f"{URL}{draft['id']}/", {"data": {"address": sent}}).data

    assert saved["data"]["address"]["tehsil"] == "Gyanpur"
    assert saved["data"]["address"]["pincode"] == "221406"
    assert saved["data"]["address"]["house_number"] == "12"


def test_what_the_mpp_does_not_know_is_still_typed(world):
    """The World's MPP has no place yet, so the facilitator's answers stand."""
    application = world.submitted()

    assert application["data"]["address"]["tehsil"] == "Bhadohi"
    assert application["data"]["address"]["village_code"] == "00209982"
    assert application["data"]["address"]["pooling_point_code"] == "1305"
    assert "tehsil" not in application["mpp_place"]


def test_a_submitted_form_carries_the_mpps_place(world):
    placed(world)
    application = world.submitted()

    address = application["data"]["address"]
    assert (address["tehsil"], address["district"]) == ("Gyanpur", "Bhadohi")
    assert application["place"]["hamlet_name"] == "Purva"
    assert application["place"]["state"] == "Uttar Pradesh"
    assert application["mpp_place"]["tehsil"] == "Gyanpur"


def test_a_draft_follows_a_change_to_the_mpp_on_submit(world):
    mpp = placed(world)
    application = world.filled()
    with organization_context(world.org.id):
        mpp.post_office = "Gopiganj"
        mpp.save()

    response = world.client(world.facilitator).post(f"{URL}{application['id']}/submit/")

    assert response.status_code == 200, response.content
    assert response.data["data"]["address"]["post_office"] == "Gopiganj"


def test_the_member_code_still_uses_the_mpps_codes(world):
    placed(world)
    approved = world.fully_approved()

    assert approved["tr_code"].startswith("09" + "00209982" + "03")
    with organization_context(world.org.id):
        assert Application.objects.get(pk=approved["id"]).data["address"]["hamlet_code"] == "03"


# Import -------------------------------------------------------------------------------


def upload(world, rows, columns=PLACE_COLUMNS):
    return world.client(world.admin).post(
        IMPORT, {"file": workbook_file(rows, columns)}, format="multipart"
    )


def test_a_file_loads_each_mpps_place(world):
    response = upload(world, [place_row(), place_row(mpp="2002", village="00300002")])

    assert response.status_code == 200, response.content
    assert response.data["problems"] == []
    with organization_context(world.org.id):
        mpp = Mpp.objects.select_related("village__tehsil__district__state", "hamlet").get(
            code="2001"
        )
        assert mpp.village.name == "Rampur"
        assert mpp.village.tehsil.name == "Gyanpur"
        assert mpp.village.tehsil.district.state.code == "09"
        assert mpp.hamlet.name == "Purva"
        assert (mpp.pincode, mpp.post_office) == ("221406", "Mondh")
        assert Tehsil.objects.count() == 1
        assert Village.objects.count() == 2


def test_blank_names_keep_what_is_there(world):
    upload(world, [place_row()])
    response = upload(world, [place_row(tehsil_name="", pincode="")])

    assert response.data["problems"] == []
    with organization_context(world.org.id):
        assert Tehsil.objects.get(code="00951").name == "Gyanpur"
        assert Mpp.objects.get(code="2001").pincode == "221406"


def test_a_half_filled_place_is_refused(world):
    response = upload(world, [place_row(tehsil="")])

    assert response.data["created"] == 0
    assert "tehsil_code is empty" in response.data["problems"][0]["problem"]


def test_a_district_cannot_sit_under_two_parents_in_one_file(world):
    first = place_row()
    second = list(place_row(mpp="2002", village="00300002", tehsil="00952"))
    second[COLUMNS.index("village_code") + 1] = "10"  # Another state.

    response = upload(world, [first, tuple(second)])

    assert response.data["created"] == 0
    assert "district 183" in response.data["problems"][0]["problem"]


def test_a_file_without_place_columns_links_to_known_villages(world):
    place_chain(world.org, village_code="00300001")
    response = upload(world, [place_row()[:10]], columns=(*COLUMNS, "state_code", "hamlet_code"))

    assert response.data["problems"] == []
    with organization_context(world.org.id):
        assert Mpp.objects.get(code="2001").village.code == "00300001"
