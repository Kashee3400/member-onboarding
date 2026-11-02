from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context
from apps.organizations.models import Membership

from .conftest import authenticated_client, make_member

pytestmark = pytest.mark.django_db(transaction=True)


def picture(size=(900, 600)):
    buffer = BytesIO()
    Image.new("RGB", size, "teal").save(buffer, "JPEG")
    return SimpleUploadedFile("me.jpg", buffer.getvalue())


def url_of(org, user):
    with organization_context(org.id):
        return f"/api/v1/staff/{Membership.objects.get(user=user).id}/photo/"


def upload(client, url, file=None):
    return client.post(url, {"file": file or picture()}, format="multipart")


def test_staff_set_their_own_photo(org_a, staff_a):
    client = authenticated_client(org_a, staff_a)

    response = upload(client, url_of(org_a, staff_a))

    assert response.status_code == 200
    assert client.get("/api/v1/auth/me/").data["photo_url"] == response.data["photo_url"]


def test_it_is_stored_as_a_square(org_a, staff_a):
    client = authenticated_client(org_a, staff_a)
    url = url_of(org_a, staff_a)
    upload(client, url)

    response = client.get(url)

    assert response["Content-Type"] == "image/webp"
    image = Image.open(BytesIO(response.content))
    assert image.size == (512, 512)


def test_an_admin_can_set_anyones_and_it_is_logged(org_a, admin_a, staff_a):
    response = upload(authenticated_client(org_a, admin_a), url_of(org_a, staff_a))

    assert response.status_code == 200
    with organization_context(org_a.id):
        assert AuditEvent.objects.get(action="staff.photo_updated").actor_id == admin_a.pk


def test_others_cannot_change_someones_photo(org_a, staff_a):
    other = make_member(org_a, "other@a.test", "facilitator")

    response = upload(authenticated_client(org_a, other), url_of(org_a, staff_a))

    assert response.status_code == 403


def test_colleagues_can_see_it(org_a, staff_a):
    url = url_of(org_a, staff_a)
    upload(authenticated_client(org_a, staff_a), url)
    other = make_member(org_a, "other@a.test", "facilitator")

    assert authenticated_client(org_a, other).get(url).status_code == 200


def test_another_organization_cannot(org_a, org_b, staff_a, admin_b):
    url = url_of(org_a, staff_a)
    upload(authenticated_client(org_a, staff_a), url)

    assert authenticated_client(org_b, admin_b).get(url).status_code == 404


def test_removing_it(org_a, staff_a):
    client = authenticated_client(org_a, staff_a)
    url = url_of(org_a, staff_a)
    upload(client, url)

    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    assert client.get("/api/v1/auth/me/").data["photo_url"] is None


def test_a_file_that_is_not_a_picture_is_refused(org_a, staff_a):
    client = authenticated_client(org_a, staff_a)

    response = upload(client, url_of(org_a, staff_a), SimpleUploadedFile("x.jpg", b"not an image"))

    assert response.status_code == 400


def test_a_huge_file_is_refused(org_a, staff_a):
    client = authenticated_client(org_a, staff_a)
    file = SimpleUploadedFile("x.jpg", b"0" * (2 * 1024 * 1024 + 1))

    assert upload(client, url_of(org_a, staff_a), file).status_code == 400


def test_the_staff_list_carries_the_photo(org_a, admin_a, staff_a):
    client = authenticated_client(org_a, admin_a)
    photo = upload(client, url_of(org_a, staff_a)).data["photo_url"]

    rows = client.get("/api/v1/staff/").data["results"]

    assert photo in [row["photo_url"] for row in rows]
