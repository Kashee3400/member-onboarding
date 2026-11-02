import os
import stat
from io import BytesIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from PIL import Image

from apps.applications.models import ApplicationDecision
from apps.audit.models import AuditEvent
from apps.core import crypto
from apps.core.tenancy import organization_context
from apps.documents import images, storage
from apps.documents.models import Document, StaffSignature
from apps.organizations.models import Membership

from .conftest import authenticated_client
from .test_applications import URL, World, jpeg_bytes, png_bytes

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def world(org_a):
    return World(org_a)


def upload(client, application_id, document_type, content, name="x.jpg", kind="image/jpeg"):
    return client.post(
        f"{URL}{application_id}/documents/",
        {"document_type": document_type, "file": SimpleUploadedFile(name, content, kind)},
        format="multipart",
    )


def stored_file(org, document_id):
    with organization_context(org.id):
        return Document.objects.get(pk=document_id)


def test_files_go_under_media_root_in_the_defined_layout(world, org_a):
    application = world.draft()
    client = world.client(world.facilitator)

    response = upload(client, application["id"], "photo", jpeg_bytes())

    assert response.status_code == 201
    document = stored_file(org_a, response.data["id"])
    parts = document.relative_path.split("/")
    assert parts[0] == str(org_a.id)
    assert parts[1] == "applications"
    assert len(parts[2]) == 4 and len(parts[3]) == 2
    assert parts[4] == application["id"]
    assert parts[5].startswith("photo-") and parts[5].endswith(".enc")
    assert (Path(settings.MEDIA_ROOT) / document.relative_path).is_file()


def test_the_client_file_name_is_never_used(world, org_a):
    application = world.draft()
    response = upload(
        world.client(world.facilitator),
        application["id"],
        "photo",
        jpeg_bytes(),
        name="../../../etc/evil.php",
    )

    assert "evil" not in stored_file(org_a, response.data["id"]).relative_path


def test_files_are_encrypted_on_disk(world, org_a):
    application = world.draft()
    response = upload(
        world.client(world.facilitator), application["id"], "aadhaar_front", jpeg_bytes()
    )

    document = stored_file(org_a, response.data["id"])
    on_disk = (Path(settings.MEDIA_ROOT) / document.relative_path).read_bytes()
    assert not on_disk.startswith(b"\xff\xd8")
    assert b"JFIF" not in on_disk


def test_a_moved_file_will_not_open(world, org_a):
    application = world.draft()
    response = upload(world.client(world.facilitator), application["id"], "photo", jpeg_bytes())
    document = stored_file(org_a, response.data["id"])
    sealed = (Path(settings.MEDIA_ROOT) / document.relative_path).read_bytes()

    with pytest.raises(crypto.DecryptionError):
        crypto.open_file(sealed, "other/path.enc")


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_files_are_not_world_readable(world, org_a):
    application = world.draft()
    response = upload(world.client(world.facilitator), application["id"], "photo", jpeg_bytes())
    path = Path(settings.MEDIA_ROOT) / stored_file(org_a, response.data["id"]).relative_path

    assert not stat.S_IMODE(path.stat().st_mode) & stat.S_IROTH


def test_paths_cannot_escape_media_root():
    with pytest.raises(storage.UnsafePath):
        storage.read("../outside.enc")


def test_a_failed_save_leaves_no_temporary_files(world):
    application = world.draft()
    client = world.client(world.facilitator)
    upload(client, application["id"], "photo", jpeg_bytes())

    assert not list(Path(settings.MEDIA_ROOT).rglob("*.tmp"))


def test_location_metadata_is_stripped(world, org_a):
    exif = Image.Exif()
    exif[0x010F] = "SecretCamera"
    buffer = BytesIO()
    Image.new("RGB", (40, 40)).save(buffer, "JPEG", exif=exif)
    assert b"SecretCamera" in buffer.getvalue()

    content, _ = images.normalize_document(buffer.getvalue())

    assert b"SecretCamera" not in content


@pytest.mark.parametrize(
    "content",
    [b"<?php system($_GET['c']); ?>", b"%PDF-1.7 not an image", b"GIF89a" + b"0" * 50, b""],
)
def test_only_real_images_are_accepted(world, content):
    application = world.draft()
    response = upload(world.client(world.facilitator), application["id"], "photo", content)
    assert response.status_code == 400


def test_oversized_images_are_rejected(world):
    application = world.draft()
    too_big = jpeg_bytes() + b"0" * images.MAX_UPLOAD_BYTES
    response = upload(world.client(world.facilitator), application["id"], "photo", too_big)
    assert response.status_code == 400


def test_replacing_a_document_keeps_the_old_file(world, org_a):
    application = world.draft()
    client = world.client(world.facilitator)
    first = upload(client, application["id"], "passbook", jpeg_bytes()).data
    second = upload(client, application["id"], "passbook", jpeg_bytes()).data

    listed = client.get(f"{URL}{application['id']}/documents/").data
    assert [item["id"] for item in listed] == [second["id"]]
    assert (Path(settings.MEDIA_ROOT) / stored_file(org_a, first["id"]).relative_path).is_file()


def test_documents_cannot_change_after_submission(world):
    application = world.submitted()
    response = upload(world.client(world.facilitator), application["id"], "photo", jpeg_bytes())
    assert response.status_code == 409


def test_a_file_is_served_to_those_who_can_see_the_application(world):
    application = world.filled()
    client = world.client(world.facilitator)
    document = client.get(f"{URL}{application['id']}/documents/").data[0]

    response = client.get(f"/api/v1/documents/{document['id']}/file/")

    assert response.status_code == 200
    assert response["Content-Type"] == "image/jpeg"
    assert response["Cache-Control"] == "private, no-store"
    assert response.content.startswith(b"\xff\xd8")


def test_viewing_a_file_is_audited(world, org_a):
    application = world.filled()
    client = world.client(world.facilitator)
    document = client.get(f"{URL}{application['id']}/documents/").data[0]
    client.get(f"/api/v1/documents/{document['id']}/file/")

    with organization_context(org_a.id):
        assert AuditEvent.objects.filter(action="document.viewed").count() == 1


def test_anonymous_callers_get_no_file(world, api_client):
    application = world.filled()
    client = world.client(world.facilitator)
    document = client.get(f"{URL}{application['id']}/documents/").data[0]

    assert api_client.get(f"/api/v1/documents/{document['id']}/file/").status_code == 401


def test_a_transfer_takes_file_access_away(world):
    application = world.filled()
    client = world.client(world.facilitator)
    document = client.get(f"{URL}{application['id']}/documents/").data[0]
    other_am = world.member("am2@a.test", "area_manager")

    assert (
        world.client(other_am).get(f"/api/v1/documents/{document['id']}/file/").status_code == 404
    )


def test_files_stay_within_their_organization(world, org_b, admin_b):
    application = world.filled()
    client = world.client(world.facilitator)
    document = client.get(f"{URL}{application['id']}/documents/").data[0]

    other = authenticated_client(org_b, admin_b)

    assert other.get(f"/api/v1/documents/{document['id']}/file/").status_code == 404


# Required documents ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("missing", "path"),
    [
        ("photo", "documents.photo"),
        ("aadhaar_front", "documents.aadhaar_front"),
        ("aadhaar_back", "documents.aadhaar_back"),
        ("passbook", "documents.passbook"),
        ("member_signature", "documents.member_signature"),
    ],
)
def test_every_document_is_required_to_submit(world, org_a, missing, path):
    application = world.filled()
    with organization_context(org_a.id):
        Document.objects.filter(document_type=missing).update(is_current=False)

    response = world.client(world.facilitator).post(f"{URL}{application['id']}/submit/")

    assert response.status_code == 400
    assert path in response.data["error"]["details"]


def test_a_thumbprint_can_replace_a_signature(world, org_a):
    application = world.filled()
    client = world.client(world.facilitator)
    with organization_context(org_a.id):
        Document.objects.filter(document_type="member_signature").update(is_current=False)
    upload(client, application["id"], "member_thumbprint", jpeg_bytes())

    assert client.post(f"{URL}{application['id']}/submit/").status_code == 200


# Staff signatures --------------------------------------------------------------------


def membership_of(org, user):
    with organization_context(org.id):
        return Membership.objects.get(user=user)


def signature_url(org, user):
    return f"/api/v1/staff/{membership_of(org, user).id}/signature/"


def put_signature(client, url, content=None, name="sign.png"):
    return client.post(
        url,
        {"file": SimpleUploadedFile(name, content or png_bytes(), "image/png")},
        format="multipart",
    )


def test_admins_upload_a_png_signature(world, org_a):
    admin = world.client(world.admin)
    url = signature_url(org_a, world.legal)

    assert put_signature(admin, url).status_code == 200
    assert admin.get(url).data == {"has_signature": True}
    assert admin.get(f"{url}file/").content.startswith(b"\x89PNG")


def test_a_signature_must_be_a_png(world, org_a):
    url = signature_url(org_a, world.legal)
    response = put_signature(world.client(world.admin), url, jpeg_bytes())
    assert response.status_code == 400


def test_signatures_need_the_staff_permission(world, org_a):
    url = signature_url(org_a, world.legal)
    assert put_signature(world.client(world.facilitator), url).status_code == 403


def test_submitting_needs_a_signature_on_file(world, org_a):
    application = world.filled()
    with organization_context(org_a.id):
        StaffSignature.objects.filter(membership=membership_of(org_a, world.facilitator)).update(
            is_current=False
        )

    response = world.client(world.facilitator).post(f"{URL}{application['id']}/submit/")

    assert response.status_code == 400


def test_approving_needs_a_signature_on_file(world, org_a):
    application = world.submitted()
    with organization_context(org_a.id):
        StaffSignature.objects.filter(membership=membership_of(org_a, world.manager)).update(
            is_current=False
        )

    assert world.approve(application, world.manager).status_code == 400


def test_a_new_signature_does_not_change_a_past_approval(world, org_a):
    application = world.submitted()
    world.approve(application, world.manager)
    with organization_context(org_a.id):
        used = ApplicationDecision.objects.get(stage="pending_am").signature_id

    put_signature(world.client(world.admin), signature_url(org_a, world.manager))

    with organization_context(org_a.id):
        decision = ApplicationDecision.objects.get(stage="pending_am")
        assert decision.signature_id == used
        assert not decision.signature.is_current


def test_media_root_inside_the_code_stops_the_app(settings):
    settings.MEDIA_ROOT = Path(settings.BASE_DIR) / "media"
    with pytest.raises(SystemCheckError):
        call_command("check")
