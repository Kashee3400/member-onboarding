"""
The Aadhaar QR check. Only UIDAI can sign with UIDAI's key, so these codes are
signed with a test certificate pinned in its place; the real certificates are
checked separately for being UIDAI's and loadable.
"""

import datetime
import gzip
import io

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.applications import aadhaar_qr
from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context

from .test_applications import AADHAAR, URL, World

pytestmark = pytest.mark.django_db(transaction=True)


def _key_and_certificate():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test signer")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return key, certificate.public_bytes(serialization.Encoding.PEM)


SIGNER, SIGNER_PEM = _key_and_certificate()
STRANGER, _ = _key_and_certificate()


@pytest.fixture(autouse=True)
def pinned(tmp_path, monkeypatch):
    """The test signer stands in for UIDAI."""
    (tmp_path / "test_signer.cer").write_bytes(SIGNER_PEM)
    monkeypatch.setattr(aadhaar_qr, "CERTIFICATES", tmp_path)
    aadhaar_qr._uidai_keys.cache_clear()
    yield
    aadhaar_qr._uidai_keys.cache_clear()


def jp2_photo() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (60, 80), (180, 120, 90)).save(buffer, "JPEG2000")
    return buffer.getvalue()


def secure_qr(key=SIGNER, tamper=False, **overrides) -> str:
    """A V2 Secure QR as the scanner reads it: one big decimal number."""
    values = {
        "email_mobile_status": "3",
        "reference_id": f"{AADHAAR[-4:]}20190101120000000",
        "name": "Poonam Kushwaha",
        "date_of_birth": "15-01-1984",
        "gender": "F",
        "care_of": "W/O: Shyam Kushwaha",
        "district": "Mirzapur",
        "landmark": "",
        "house": "12",
        "location": "",
        "pincode": "231304",
        "post_office": "Chunar",
        "state": "Uttar Pradesh",
        "street": "",
        "subdistrict": "Chunar",
        "village": "Dudwa",
    } | overrides
    fields = ["V2", *(values[name] for name in aadhaar_qr.FIELDS), "3210"]
    signed = b"".join(value.encode("iso-8859-1") + b"\xff" for value in fields) + jp2_photo()
    signature = key.sign(signed, padding.PKCS1v15(), hashes.SHA256())
    if tamper:
        signed = signed.replace(b"Poonam", b"Poonan")
    return str(int.from_bytes(gzip.compress(signed + signature), "big"))


# Reading -------------------------------------------------------------------------------


def test_a_signed_secure_qr_is_verified_and_read():
    reading = aadhaar_qr.read(secure_qr())

    assert reading.status == aadhaar_qr.Status.VERIFIED
    assert reading.certificate == "test_signer"
    assert reading.details["name"] == "Poonam Kushwaha"
    assert reading.details["date_of_birth"] == "1984-01-15"
    assert reading.details["gender"] == "female"
    assert (reading.details["relation_type"], reading.details["relation_name"]) == (
        "husband",
        "Shyam Kushwaha",
    )
    assert reading.aadhaar_last4 == AADHAAR[-4:]
    assert Image.open(io.BytesIO(reading.photo)).size == (60, 80)


def test_an_altered_qr_is_caught():
    assert aadhaar_qr.read(secure_qr(tamper=True)).status == aadhaar_qr.Status.INVALID


def test_a_qr_signed_by_anyone_else_is_caught():
    reading = aadhaar_qr.read(secure_qr(key=STRANGER))

    assert reading.status == aadhaar_qr.Status.INVALID
    assert reading.certificate == ""


def test_an_old_xml_qr_is_read_but_not_verified():
    xml = (
        '<?xml version="1.0"?><PrintLetterBarcodeData uid="'
        + AADHAAR
        + '" name="Poonam Kushwaha" gender="F" yob="1984" co="W/O Shyam Kushwaha"'
        ' dist="Mirzapur" state="Uttar Pradesh" pc="231304"/>'
    )

    reading = aadhaar_qr.read(xml)

    assert reading.status == aadhaar_qr.Status.UNSIGNED
    assert reading.details["date_of_birth"] == "1984"
    assert reading.aadhaar_last4 == AADHAAR[-4:]


@pytest.mark.parametrize("raw", ["", "hello", "12345", "<not aadhaar/>"])
def test_anything_else_is_not_an_aadhaar_qr(raw):
    assert aadhaar_qr.read(raw) is None


def test_every_uidai_certificate_is_pinned_and_loads(monkeypatch):
    monkeypatch.undo()
    aadhaar_qr._uidai_keys.cache_clear()

    keys = aadhaar_qr._uidai_keys()

    names = {name for name, _ in keys}
    assert "uidai_offline_publickey_2026" in names
    # Old cards were signed with the certificates of their day.
    assert {"uidai_12_06_18_cer", "uidai_prod_cdup", "uidai_offline_publickey_29032019"} <= names
    assert all(key.key_size == 2048 for _, key in keys)


# Through the form ----------------------------------------------------------------------


@pytest.fixture
def world(org_a):
    return World(org_a)


def scanned(world, draft, raw, consent=True):
    client = world.client(world.facilitator)
    version = client.get(f"{URL}{draft['id']}/").data["version"]
    return client.patch(
        f"{URL}{draft['id']}/",
        {"version": version, "aadhaar_qr": raw, "aadhaar_qr_consent": consent},
        format="json",
    )


def matching_form(world):
    draft = world.draft()
    response = world.client(world.facilitator).patch(
        f"{URL}{draft['id']}/",
        {
            "data": {
                "applicant": {
                    "full_name": "POONAM  KUSHWAHA.",
                    "date_of_birth": "1984-01-15",
                    "gender": "female",
                    "relation_type": "husband",
                    "relation_name": "Shyam Kushwaha",
                }
            },
            "aadhaar_number": AADHAAR,
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    return draft


def test_a_scan_that_agrees_with_the_form_is_a_full_match(world):
    draft = matching_form(world)

    response = scanned(world, draft, secure_qr())

    assert response.status_code == 200, response.content
    check = response.data["aadhaar_check"]
    assert check["status"] == "verified"
    assert check["consent"] is True
    assert all(item["match"] for item in check["fields"])
    assert check["full_match"] is True


def test_a_field_that_disagrees_shows_and_spoils_the_match(world):
    draft = matching_form(world)

    check = scanned(world, draft, secure_qr(gender="M")).data["aadhaar_check"]

    gender = next(item for item in check["fields"] if item["field"] == "gender")
    assert (gender["form"], gender["aadhaar"], gender["match"]) == ("female", "male", False)
    assert check["full_match"] is False


def test_an_unsigned_qr_is_never_a_full_match(world):
    draft = matching_form(world)
    xml = (
        '<PrintLetterBarcodeData name="Poonam Kushwaha" gender="F" dob="15/01/1984"'
        ' co="W/O Shyam Kushwaha"/>'
    )

    check = scanned(world, draft, xml).data["aadhaar_check"]

    assert check["status"] == "unsigned"
    assert check["full_match"] is False


def test_the_member_must_agree_first(world):
    draft = matching_form(world)

    assert scanned(world, draft, secure_qr(), consent=False).status_code == 400


def test_a_form_with_no_scan_says_so(world):
    draft = world.draft()

    assert world.client(world.facilitator).get(f"{URL}{draft['id']}/").data["aadhaar_check"] is None


def test_the_qr_photo_is_shown_to_reviewers_and_audited(world):
    draft = matching_form(world)
    scanned(world, draft, secure_qr())

    response = world.client(world.legal).get(f"{URL}{draft['id']}/aadhaar-photo/")

    assert response.status_code == 200
    assert Image.open(io.BytesIO(response.content)).format == "JPEG"
    with organization_context(world.org.id):
        assert AuditEvent.objects.filter(action="application.aadhaar_photo_viewed").exists()


def test_a_new_scan_replaces_the_old_one(world):
    draft = matching_form(world)
    scanned(world, draft, secure_qr(gender="M"))

    check = scanned(world, draft, secure_qr()).data["aadhaar_check"]

    assert check["full_match"] is True


def test_the_qr_is_read_from_an_uploaded_aadhaar_photo(world):
    zxingcpp = pytest.importorskip("zxingcpp")
    draft = matching_form(world)
    code = zxingcpp.create_barcode(secure_qr(), zxingcpp.BarcodeFormat.QRCode)
    picture = Image.fromarray(code.to_image(scale=4)).convert("RGB")
    buffer = io.BytesIO()
    picture.save(buffer, "JPEG", quality=95)

    upload = world.client(world.facilitator).post(
        f"{URL}{draft['id']}/documents/",
        {
            "document_type": "aadhaar_back",
            "file": SimpleUploadedFile("back.jpg", buffer.getvalue()),
        },
        format="multipart",
    )

    assert upload.status_code == 201, upload.content
    check = world.client(world.legal).get(f"{URL}{draft['id']}/").data["aadhaar_check"]
    assert check["source"] == "photo"
    assert check["full_match"] is True
