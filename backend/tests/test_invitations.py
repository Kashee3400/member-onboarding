from datetime import timedelta
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageDraw

from apps.core.tenancy import organization_context
from apps.organizations.models import Membership
from apps.rbac.models import Role, StaffInvitation

from .conftest import PASSWORD, authenticated_client, make_member
from .test_applications import World

pytestmark = pytest.mark.django_db(transaction=True)

STAFF_URL = "/api/v1/staff/"
PUBLIC_URL = "/api/v1/public/invitations/"


@pytest.fixture
def world(org_a):
    return World(org_a)


def invite(world, email="new@a.test", role="area_manager"):
    with organization_context(world.org.id):
        role_id = str(Role.objects.get(code=role).id)
    response = world.client(world.admin).post(
        STAFF_URL, {"email": email, "full_name": "New Person", "role_ids": [role_id]}
    )
    assert response.status_code == 201, response.content
    return response.data


def token_of(link):
    return parse_qs(urlparse(link).query)["token"][0]


def accept(client, org, token, password="A-new-long-password!", name="Official Name"):  # noqa: S107
    return client.post(
        PUBLIC_URL,
        {"organization": org.slug, "token": token, "full_name": name, "password": password},
    )


def test_an_invited_person_sets_their_own_password(world, org_a, api_client):
    staff = invite(world)
    token = token_of(staff["invite_link"])

    shown = api_client.get(PUBLIC_URL, {"organization": org_a.slug, "token": token})
    done = accept(api_client, org_a, token)
    login = api_client.post(
        "/api/v1/auth/login/",
        {"email": "new@a.test", "password": "A-new-long-password!", "organization": org_a.slug},
    )

    assert staff["status"] == "invited"
    assert shown.data["email"] == "new@a.test"
    assert done.status_code == 204
    assert login.status_code == 200


def test_a_link_works_once(world, org_a, api_client):
    token = token_of(invite(world)["invite_link"])
    accept(api_client, org_a, token)

    assert accept(api_client, org_a, token).status_code == 404


def test_a_new_link_ends_the_old_one(world, org_a, api_client):
    staff = invite(world)
    old = token_of(staff["invite_link"])
    world.client(world.admin).post(f"{STAFF_URL}{staff['id']}/invite/")

    assert accept(api_client, org_a, old).status_code == 404


def test_an_expired_link_is_refused(world, org_a, api_client):
    token = token_of(invite(world)["invite_link"])
    with organization_context(org_a.id):
        StaffInvitation.objects.update(
            expires_at=StaffInvitation.objects.get().created_at - timedelta(days=1)
        )

    assert (
        api_client.get(PUBLIC_URL, {"organization": org_a.slug, "token": token}).status_code == 404
    )


def test_a_link_is_bound_to_its_organization(world, org_a, org_b, api_client):
    token = token_of(invite(world)["invite_link"])

    assert accept(api_client, org_b, token).status_code == 404


def test_a_weak_password_is_refused(world, org_a, api_client):
    token = token_of(invite(world)["invite_link"])

    assert accept(api_client, org_a, token, password="12345").status_code == 400


def test_someone_already_set_up_cannot_be_invited_again(world):
    with organization_context(world.org.id):
        membership = Membership.objects.get(user=world.manager)

    response = world.client(world.admin).post(f"{STAFF_URL}{membership.id}/invite/")

    assert response.status_code == 400


def test_a_password_can_still_be_given_directly(world):
    with organization_context(world.org.id):
        role_id = str(Role.objects.get(code="pib").id)
    response = world.client(world.admin).post(
        STAFF_URL,
        {
            "email": "direct@a.test",
            "full_name": "Direct",
            "password": PASSWORD,
            "role_ids": [role_id],
        },
    )

    assert response.data["status"] == "active"
    assert "invite_link" not in response.data


def test_staff_show_whose_signature_is_needed(world):
    team = make_member(world.org, "cs2@a.test", "cs_legal")
    rows = {row["email"]: row for row in world.client(world.admin).get(STAFF_URL).data["results"]}

    assert rows["am@a.test"]["needs_signature"] is True
    assert rows["field@a.test"]["needs_signature"] is True
    assert rows["cs@a.test"]["needs_signature"] is True  # the head
    assert rows[team.email]["needs_signature"] is False
    assert rows["am@a.test"]["has_signature"] is True


def signature_photo(paper=(236, 232, 224)):
    image = Image.new("RGB", (900, 500), paper)
    ImageDraw.Draw(image).line([(150, 350), (400, 150), (700, 330)], fill=(20, 30, 120), width=14)
    buffer = BytesIO()
    image.save(buffer, "JPEG")
    return SimpleUploadedFile("sign.jpg", buffer.getvalue())


def test_staff_upload_their_own_signature_from_a_photo(world, org_a):
    client = world.client(world.manager)
    with organization_context(org_a.id):
        membership = Membership.objects.get(user=world.manager)
    url = f"{STAFF_URL}{membership.id}/signature/"

    assert client.post(url, {"file": signature_photo()}, format="multipart").status_code == 200

    stored = Image.open(BytesIO(client.get(f"{url}file/").content))
    assert stored.mode == "RGBA"
    assert stored.getpixel((0, 0))[3] == 0  # the paper is gone
    assert stored.width < 900  # cut down to the ink


def test_a_blank_page_is_refused(world, org_a):
    client = world.client(world.manager)
    with organization_context(org_a.id):
        membership = Membership.objects.get(user=world.manager)
    blank = BytesIO()
    Image.new("RGB", (400, 200), "white").save(blank, "JPEG")

    response = client.post(
        f"{STAFF_URL}{membership.id}/signature/",
        {"file": SimpleUploadedFile("blank.jpg", blank.getvalue())},
        format="multipart",
    )

    assert response.status_code == 400


def test_nobody_sets_anyone_elses_signature(world, org_a):
    with organization_context(org_a.id):
        other = Membership.objects.get(user=world.legal)

    response = world.client(world.manager).post(
        f"{STAFF_URL}{other.id}/signature/", {"file": signature_photo()}, format="multipart"
    )

    assert response.status_code == 403


def test_me_says_whether_a_signature_is_needed(world, org_a):
    team = make_member(org_a, "cs2@a.test", "cs_legal")

    assert (
        authenticated_client(org_a, team).get("/api/v1/auth/me/").data["needs_signature"] is False
    )
    me = world.client(world.manager).get("/api/v1/auth/me/").data
    assert (me["needs_signature"], me["has_signature"]) == (True, True)
