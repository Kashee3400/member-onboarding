from io import BytesIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.branding.models import Branding
from apps.core.tenancy import organization_context
from apps.hierarchy.models import Mcc, Mpp, Plant
from apps.rbac.navigation import NAVIGATION, navigation_for

from .conftest import authenticated_client, make_member
from .test_applications import AADHAAR, OTHER_AADHAAR, URL, World

pytestmark = pytest.mark.django_db(transaction=True)

MEMBERS = "/api/v1/members/"
SEARCH = "/api/v1/search/"
BRANDING = "/api/v1/organization/branding/"
PUBLIC = "/api/v1/public/branding/"


@pytest.fixture
def world(org_a):
    return World(org_a)


def image_bytes(kind="PNG", size=(40, 40)):
    buffer = BytesIO()
    Image.new("RGB", size, "skyblue").save(buffer, kind)
    return buffer.getvalue()


def upload(raw=None, name="x.png"):
    return {"file": SimpleUploadedFile(name, raw or image_bytes())}


def test_lists_report_a_total_and_page_links(world):
    world.submitted()
    world.submitted(OTHER_AADHAAR)

    data = world.client(world.manager).get(URL, {"page_size": 1}).data

    assert data["count"] == 2
    assert len(data["results"]) == 1
    assert "page=2" in data["next"]
    assert data["previous"] is None


def test_a_page_past_the_end_is_not_found(world):
    assert world.client(world.manager).get(URL, {"page": 9}).status_code == 404


def test_a_table_can_ask_for_more_than_one_default_page(world, org_a):
    with organization_context(org_a.id):
        for number in range(3):
            Plant.objects.create(code=f"X{number}", name="Spare")

    data = world.client(world.admin).get("/api/v1/hierarchy/plants/", {"page_size": 99999}).data

    assert data["count"] == 4
    assert len(data["results"]) == 4


def test_applications_are_found_by_name_form_mpp_and_code(world):
    done = world.fully_approved()
    client = world.client(world.finance)

    for needle in ("Test Appl", done["form_number"], "Dudwa", "1305", done["tr_code"]):
        assert client.get(URL, {"q": needle}).data["count"] == 1, needle
    assert client.get(URL, {"q": "nobody"}).data["count"] == 0


def test_applications_filter_by_several_statuses(world):
    world.draft()
    world.submitted()
    client = world.client(world.facilitator)

    assert client.get(URL, {"status": "draft,pending_am"}).data["count"] == 2
    assert client.get(URL, {"status": "pending_am"}).data["count"] == 1


def test_applications_sort_by_a_listed_field_only(world):
    first = world.submitted()
    second = world.submitted(OTHER_AADHAAR)
    client = world.client(world.manager)

    rows = client.get(URL, {"ordering": "-form_number"}).data["results"]
    assert [row["id"] for row in rows] == [second["id"], first["id"]]

    # Ignored rather than sorted, so nothing can be learned from a hidden column.
    assert client.get(URL, {"ordering": "aadhaar_index"}).status_code == 200


def test_search_does_not_widen_access(world, org_a):
    world.submitted()
    outsider = world.member("other@a.test", "facilitator")

    assert world.client(outsider).get(URL, {"q": "Test"}).data["count"] == 0


def test_members_search_and_sort(world):
    world.fully_approved()
    world.fully_approved(OTHER_AADHAAR)
    client = world.client(world.finance)

    assert client.get(MEMBERS, {"q": "1305"}).data["count"] == 2
    rows = client.get(MEMBERS, {"ordering": "tr_code"}).data["results"]
    assert [row["tr_code"] for row in rows] == sorted(row["tr_code"] for row in rows)


def test_members_cannot_be_found_by_mobile(world):
    world.fully_approved()

    assert world.client(world.finance).get(MEMBERS, {"q": "9170800000"}).data["count"] == 0


def test_staff_is_a_searchable_sortable_page(world):
    client = world.client(world.admin)

    data = client.get("/api/v1/staff/", {"q": "finance", "ordering": "email"}).data

    assert data["count"] == 1
    assert data["results"][0]["email"] == "finance@a.test"


def test_audit_events_are_searchable(world):
    world.draft()

    data = world.client(world.admin).get("/api/v1/audit/events/", {"q": "application.created"}).data

    assert data["count"] == 1


def test_notifications_filter_by_unread(world):
    world.submitted()
    client = world.client(world.manager)

    assert client.get("/api/v1/notifications/", {"read_at__isnull": "true"}).data["count"] == 1
    assert client.get("/api/v1/notifications/", {"read_at__isnull": "false"}).data["count"] == 0


def test_counts_follow_what_the_caller_can_see(world):
    world.draft()
    world.submitted()
    outsider = world.member("other@a.test", "facilitator")

    response = world.client(world.facilitator).get(f"{URL}counts/")

    assert response.data == {"by_status": {"draft": 1, "pending_am": 1}, "total": 2}
    assert world.client(outsider).get(f"{URL}counts/").data == {"by_status": {}, "total": 0}


def test_every_page_in_the_menu_explains_itself():
    def walk(items):
        for item in items:
            assert item.description, item.key
            walk(item.children)

    walk(NAVIGATION)


def test_the_menu_carries_descriptions():
    menu = navigation_for({"dashboard.view"})

    assert menu[0]["description"]


def test_branding_appears_for_those_who_manage_settings():
    keys = [node["key"] for node in navigation_for({"settings.manage"})[0]["children"]]

    assert "administration.branding" in keys


def test_me_names_the_roles(world):
    data = world.client(world.manager).get("/api/v1/auth/me/").data

    assert data["roles"] == ["area_manager"]
    assert data["role_names"] == ["Area Manager"]


def test_search_finds_forms_and_members(world):
    done = world.fully_approved()

    hits = world.client(world.finance).get(SEARCH, {"q": "Test App"}).data

    assert {hit["kind"] for hit in hits} == {"application", "member"}
    application = next(hit for hit in hits if hit["kind"] == "application")
    assert application["title"] == "Test Applicant"
    assert done["form_number"] in application["subtitle"]
    assert application["path"] == f"/applications/{done['id']}"


def test_search_follows_permissions(world):
    world.fully_approved()

    hits = world.client(world.facilitator).get(SEARCH, {"q": "Test App"}).data

    assert {hit["kind"] for hit in hits} == {"application"}


def test_search_stays_within_the_callers_mpps(world):
    world.submitted()
    outsider = world.member("other@a.test", "facilitator")

    assert world.client(outsider).get(SEARCH, {"q": "Test App"}).data == []


def test_search_never_matches_or_shows_identifiers(world):
    world.fully_approved()
    client = world.client(world.finance)

    assert client.get(SEARCH, {"q": AADHAAR}).data == []
    assert AADHAAR not in str(client.get(SEARCH, {"q": "Test"}).data)


def test_search_waits_for_two_letters(world):
    world.submitted()

    assert world.client(world.manager).get(SEARCH, {"q": "T"}).data == []


def test_unknown_and_unbranded_organizations_look_the_same(org_a):
    client = APIClient()

    unknown = client.get(PUBLIC, {"organization": "nobody"})
    unbranded = client.get(PUBLIC, {"organization": org_a.slug})

    assert unknown.status_code == unbranded.status_code == 200
    assert unknown.data == unbranded.data
    assert unknown.data["primary_color"] == "#0284C7"
    assert unknown.data["accent_color"] == "#F59E0B"


def test_branding_is_saved_and_public(world, org_a):
    client = world.client(world.admin)

    response = client.patch(
        BRANDING,
        {"display_name": "Kashee", "tagline": "Staff portal", "primary_color": "#0a7ea4"},
        format="json",
    )

    assert response.status_code == 200
    public = APIClient().get(PUBLIC, {"organization": org_a.slug}).data
    assert public["display_name"] == "Kashee"
    assert public["tagline"] == "Staff portal"
    assert public["primary_color"] == "#0A7EA4"
    with organization_context(org_a.id):
        assert AuditEvent.objects.filter(action="branding.updated").exists()


def test_a_bad_colour_is_refused(world):
    response = world.client(world.admin).patch(BRANDING, {"accent_color": "red"}, format="json")

    assert response.status_code == 400


def test_branding_needs_the_settings_permission(world):
    client = world.client(world.manager)

    assert client.get(BRANDING).status_code == 403
    assert client.post(f"{BRANDING}logo/", upload(), format="multipart").status_code == 403


def test_a_logo_is_served_to_anyone_and_cached(world, org_a):
    response = world.client(world.admin).post(f"{BRANDING}logo/", upload(), format="multipart")

    assert response.status_code == 200
    url = response.data["logo_url"]
    image = APIClient().get(url)
    assert image.status_code == 200
    assert image["Content-Type"] == "image/png"
    assert "immutable" in image["Cache-Control"]
    assert APIClient().get(PUBLIC, {"organization": org_a.slug}).data["logo_url"] == url


def test_a_login_image_becomes_webp_at_a_sensible_size(world):
    raw = image_bytes("JPEG", (3000, 1500))

    response = world.client(world.admin).post(
        f"{BRANDING}login_image/", upload(raw, "x.jpg"), format="multipart"
    )

    image = APIClient().get(response.data["login_image_url"])
    assert image["Content-Type"] == "image/webp"
    assert Image.open(BytesIO(image.content)).size == (2560, 1280)


def test_webp_is_accepted(world):
    response = world.client(world.admin).post(
        f"{BRANDING}logo/", upload(image_bytes("WEBP"), "x.webp"), format="multipart"
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("kind", "raw"),
    [
        ("logo", b"not an image"),
        ("logo", image_bytes("GIF")),
        ("logo", b"x" * (2 * 1024 * 1024 + 1)),
        ("login_image", b"x" * (10 * 1024 * 1024 + 1)),
    ],
)
def test_unsuitable_images_are_refused(world, kind, raw):
    response = world.client(world.admin).post(f"{BRANDING}{kind}/", upload(raw), format="multipart")

    assert response.status_code == 400


def test_replacing_a_logo_removes_the_old_file(world, org_a):
    client = world.client(world.admin)
    client.post(f"{BRANDING}logo/", upload(), format="multipart")
    with organization_context(org_a.id):
        old = Path(settings.MEDIA_ROOT) / Branding.objects.get().logo_path
    assert old.exists()

    client.post(f"{BRANDING}logo/", upload(), format="multipart")

    assert not old.exists()


def test_removing_an_image_stops_serving_it(world):
    client = world.client(world.admin)
    url = client.post(f"{BRANDING}logo/", upload(), format="multipart").data["logo_url"]

    response = client.delete(f"{BRANDING}logo/")

    assert response.status_code == 200
    assert response.data["logo_url"] is None
    assert APIClient().get(url).status_code == 404


def test_images_of_unknown_organizations_are_not_found(db):
    assert APIClient().get(f"{PUBLIC}nobody/logo/").status_code == 404


def test_one_organizations_branding_stays_its_own(org_a, org_b):
    admin_a = make_member(org_a, "admin@a.test", "org_admin")
    admin_b = make_member(org_b, "admin@b.test", "org_admin")
    authenticated_client(org_a, admin_a).patch(BRANDING, {"display_name": "First"}, format="json")

    data = authenticated_client(org_b, admin_b).get(BRANDING).data

    assert data["display_name"] == org_b.name
    assert APIClient().get(PUBLIC, {"organization": org_b.slug}).data["display_name"] != "First"


def test_mpps_are_found_by_name_and_village_code(org_a):
    with organization_context(org_a.id):
        plant = Plant.objects.create(code="P9", name="Plant")
        mcc = Mcc.objects.create(plant=plant, code="9", name="Hub")
        Mpp.objects.create(mcc=mcc, code="7777", name="Tilthi", village_code="00211673")
    admin = make_member(org_a, "admin2@a.test", "org_admin")
    client = authenticated_client(org_a, admin)

    assert client.get("/api/v1/hierarchy/mpps/", {"q": "Tilthi"}).data["count"] == 1
    assert client.get("/api/v1/hierarchy/mpps/", {"q": "00211673"}).data["count"] == 1
