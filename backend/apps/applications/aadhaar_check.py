"""
Proving a member's details with her Aadhaar QR, so the office need not compare them
by eye. The facilitator scans the QR in the village (or the server reads it from the
uploaded Aadhaar photo); here it is checked against UIDAI's signature and kept.
The comparison with the form is made on every read, so a later correction shows.
"""

import io
import re

from django.utils import timezone

from apps.audit.services import record_event
from apps.documents import storage

from . import aadhaar_qr
from .models import AadhaarCheck

# The form fields a reviewer would otherwise check against the card, with how to read them.
COMPARED = (
    ("full_name", "Name"),
    ("date_of_birth", "Date of birth"),
    ("gender", "Gender"),
    ("relation_type", "Relation"),
    ("relation_name", "Father / husband name"),
)


def _photo_jpeg(jp2: bytes | None) -> bytes | None:
    """Browsers cannot show JPEG 2000, so the QR photo is kept as JPEG."""
    if not jp2:
        return None
    from PIL import Image

    try:
        image = Image.open(io.BytesIO(jp2)).convert("RGB")
    except OSError:
        return None
    output = io.BytesIO()
    image.save(output, "JPEG", quality=90)
    return output.getvalue()


def record(application, raw: str, *, source: str, user=None, consent: bool = False):
    """Keeps what the QR says. Returns the check, or None when it is no Aadhaar QR."""
    reading = aadhaar_qr.read(raw)
    if reading is None:
        return None
    old = AadhaarCheck.objects.filter(application=application).first()
    photo_path = ""
    if photo := _photo_jpeg(reading.photo):
        photo_path = storage.application_file_path(application, "aadhaar_qr_photo")
        storage.write(photo_path, photo, upload=False)
    if old:
        if old.photo_path:
            storage.delete_quietly(old.photo_path)
        old.delete()
    check = AadhaarCheck.objects.create(
        application=application,
        status=reading.status,
        source=source,
        certificate=reading.certificate,
        details=reading.details,
        aadhaar_last4=reading.aadhaar_last4,
        photo_path=photo_path,
        consent_at=timezone.now() if consent else None,
        checked_by=user,
        checked_by_name=(user.full_name or user.email) if user else "",
    )
    record_event(
        "application.aadhaar_qr_checked",
        actor=user,
        target=application,
        metadata={"status": check.status, "source": source, "certificate": check.certificate},
    )
    return check


def read_from_photo(application, content: bytes, *, user=None) -> None:
    """After an Aadhaar photo is uploaded: read its QR, unless one was scanned already."""
    if AadhaarCheck.objects.filter(
        application=application, source=AadhaarCheck.Source.SCAN
    ).exists():
        return
    raw = aadhaar_qr.scan_image(content)
    if raw:
        record(application, raw, source=AadhaarCheck.Source.PHOTO, user=user)


def _plain(value) -> str:
    """Names compare by their letters: case, dots and spacing do not matter."""
    return re.sub(r"[^A-Z]+", " ", str(value or "").upper()).strip()


def _same(name: str, form_value, qr_value) -> bool | None:
    if not qr_value:
        return None  # the QR says nothing about it
    if name in ("full_name", "relation_name"):
        return _plain(form_value) == _plain(qr_value)
    if name == "date_of_birth" and len(str(qr_value)) == 4:
        # Some cards hold only the year of birth.
        return str(form_value or "")[:4] == qr_value
    return str(form_value or "") == str(qr_value)


def comparison(application) -> dict | None:
    """The check as the reviewer sees it: each field from the form beside the QR's."""
    check = getattr(application, "aadhaar_check", None)
    if check is None:
        return None
    applicant = application.data.get("applicant", {})
    fields = []
    for name, label in COMPARED:
        qr_name = "name" if name == "full_name" else name
        qr_value = check.details.get(qr_name, "")
        fields.append(
            {
                "field": name,
                "label": label,
                "form": applicant.get(name, ""),
                "aadhaar": qr_value,
                "match": _same(name, applicant.get(name), qr_value),
            }
        )
    if check.aadhaar_last4:
        fields.append(
            {
                "field": "aadhaar_number",
                "label": "Aadhaar number (last 4)",
                "form": application.aadhaar_last4,
                "aadhaar": check.aadhaar_last4,
                "match": application.aadhaar_last4 == check.aadhaar_last4,
            }
        )
    compared = [item["match"] for item in fields if item["match"] is not None]
    return {
        "status": check.status,
        "source": check.source,
        "certificate": check.certificate,
        "checked_at": check.created_at,
        "checked_by_name": check.checked_by_name,
        "consent": check.consent_at is not None,
        "has_photo": bool(check.photo_path),
        "fields": fields,
        # Only a UIDAI-signed QR that agrees with every field it holds is a full match.
        "full_match": check.status == aadhaar_qr.Status.VERIFIED
        and bool(compared)
        and all(compared),
    }
