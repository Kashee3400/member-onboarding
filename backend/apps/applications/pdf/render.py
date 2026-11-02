"""
The printed membership form, in two variants: "full" (five pages) and "single"
(page one only, which carries no Aadhaar data).

Everything comes from what was saved at approval, including the exact signatures
used. The result is stored the first time, so reprints stay byte-identical even if
the template or anyone's name later changes.

A draft is the same layout before final approval: marked on every page, with no
member code and only the signatures already given.
"""

import base64
from datetime import date
from itertools import zip_longest
from pathlib import Path

from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from apps.documents import storage
from apps.documents.models import Document, DocumentType, StaffSignature

from .. import form
from ..models import Status

FONTS = Path(__file__).parent / "fonts"
VARIANTS = ("full", "single")
FAMILY_LABELS = {"male": "Male", "female": "Female", "other": "Other"}
DRAFT_MARK = "DRAFT – NOT APPROVED"
DRAFT_CODE = "Assigned at approval"


def _label(options, value) -> str:
    return next((o["label"] for o in options if o["value"] == value), value or "")


def _indian_date(value) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return value.strftime("%d-%m-%Y")


def _data_uri(content: bytes, content_type: str) -> str:
    return f"data:{content_type};base64,{base64.b64encode(content).decode()}"


def _document_image(documents, kind):
    document = documents.get(kind)
    return (
        _data_uri(storage.read(document.relative_path), document.content_type) if document else ""
    )


def _signature_image(signature):
    return _data_uri(storage.read(signature.relative_path), "image/png") if signature else ""


def _count(animals, animal, kind) -> int:
    try:
        return int(animals.get(f"{animal}_{kind}") or 0)
    except TypeError, ValueError:
        return 0


def _animal_table(values) -> dict:
    table = {
        animal: {kind: _count(values, animal, kind) for kind in form.ANIMAL_COUNTS}
        for animal in form.ANIMAL_TYPES
    }
    table["total"] = {
        kind: sum(table[animal][kind] for animal in form.ANIMAL_TYPES)
        for kind in form.ANIMAL_COUNTS
    }
    return table


def _family_rows(family) -> list:
    """Rows numbered 1 to 3 on the left and 4 to 6 on the right, as printed."""
    people = []
    for number in range(1, form.MAX_FAMILY_MEMBERS + 1):
        person = family[number - 1] if number <= len(family) else {}
        people.append(
            {
                "number": number,
                "name": person.get("name", ""),
                "gender": FAMILY_LABELS.get(person.get("gender"), ""),
                "age": person.get("age", ""),
                "relation": _label(form.FAMILY_RELATIONS, person.get("relation")),
            }
        )
    half = form.MAX_FAMILY_MEMBERS // 2
    return list(zip_longest(people[:half], people[half:]))


def _facilitator(application, revision):
    """The form says the member signed before the facilitator, so that person is named."""
    mark = (
        Document.objects.filter(
            application=application,
            document_type__in=(DocumentType.MEMBER_SIGNATURE, DocumentType.MEMBER_THUMBPRINT),
            is_current=True,
        )
        .select_related("uploaded_by")
        .first()
    )
    took_signature = application.revisions.filter(submitted_by=mark.uploaded_by).order_by("number")
    if earliest := took_signature.first():
        return earliest.submitted_by_name, earliest.signature

    signature = (
        StaffSignature.objects.filter(membership__user=mark.uploaded_by)
        .order_by("-created_at")
        .first()
    )
    return mark.uploaded_by_name, signature or revision.signature


def build_context(application, profile, settings, variant, *, draft=False) -> dict:
    data = application.data
    applicant = data.get("applicant", {})
    address = data.get("address", {})
    animals = data.get("animals", {})
    nominee = data.get("nominee", {})
    payment = application.payment

    revision = application.revisions.order_by("-number").first()
    decisions = {
        decision.stage: decision
        for decision in application.decisions.filter(
            revision=application.revision, decision="approved"
        ).select_related("signature")
    }
    area_manager = decisions.get(Status.PENDING_AM)
    secretary = decisions.get(Status.PENDING_CS)
    finance = decisions.get(Status.PENDING_FINANCE)
    facilitator_name, facilitator_signature = _facilitator(application, revision)

    documents = {
        document.document_type: document
        for document in Document.objects.filter(application=application, is_current=True)
    }
    submitted_on = timezone.localdate(revision.submitted_at)
    born = date.fromisoformat(applicant["date_of_birth"])
    nominee_born = date.fromisoformat(nominee["date_of_birth"])
    totals = form.computed_totals(data)
    share_count = application.payment.get("share_quantity", settings.share_count)
    share_total = settings.share_price * share_count

    images = {
        "photo": _document_image(documents, DocumentType.PHOTO),
        "member_mark": _document_image(documents, DocumentType.MEMBER_SIGNATURE)
        or _document_image(documents, DocumentType.MEMBER_THUMBPRINT),
    }
    if variant == "full":
        images |= {
            "aadhaar_front": _document_image(documents, DocumentType.AADHAAR_FRONT),
            "aadhaar_back": _document_image(documents, DocumentType.AADHAAR_BACK),
            "passbook": _document_image(documents, DocumentType.PASSBOOK),
            "facilitator": _signature_image(facilitator_signature),
            "area_manager": _signature_image(area_manager and area_manager.signature),
            "finance": _signature_image(finance and finance.signature),
            "company_secretary": _signature_image(secretary and secretary.signature),
        }

    member = None if draft else application.member
    return {
        "variant": variant,
        "draft_mark": DRAFT_MARK if draft else "",
        "fonts": FONTS.as_uri(),
        "company": profile,
        "application": application,
        "member": member,
        "member_code": member.tr_code if member else DRAFT_CODE,
        "applicant": applicant,
        "address": address,
        "bank": data.get("bank", {}),
        "nominee": nominee,
        "location": data.get("location", {}),
        "images": images,
        "form_date": _indian_date(submitted_on),
        "age": form.age_on(born, submitted_on),
        "nominee_age": form.age_on(nominee_born, submitted_on),
        "nominee_relation": str(nominee.get("relation", "")).title(),
        "relation_label": str(applicant.get("relation_type", "")).upper(),
        "gender_label": _label(form.GENDERS, applicant.get("gender")),
        "education_label": _label(form.EDUCATION, applicant.get("education")),
        "category_label": _label(form.CATEGORIES, applicant.get("category")),
        "family_status_label": _label(form.FAMILY_STATUS, applicant.get("family_status")),
        "shg_label": "Yes" if applicant.get("is_shg_member") else "No",
        "account_number": _account_number(application),
        "animals": _animal_table(animals),
        "production": animals.get("production_lpd", ""),
        "consumption": animals.get("consumption_lpd", ""),
        "surplus": f"{totals['surplus_lpd']:g}",
        "family_rows": _family_rows(data.get("family", [])),
        "masked_aadhaar": f"XXXX XXXX {application.aadhaar_last4}",
        "facilitator_name": facilitator_name,
        "area_manager": area_manager,
        "area_manager_date": _indian_date(
            area_manager and timezone.localdate(area_manager.decided_at)
        ),
        "finance": finance,
        "company_secretary": secretary,
        "payment": payment,
        "payment_reference": payment.get("reference") or "NA",
        "payment_date": _indian_date(payment.get("deposited_on")),
        "board_date": (
            profile.board_resolution_date.strftime("%d/%m/%Y")
            if profile.board_resolution_date
            else ""
        ),
        "fees": {
            "entry_fee": settings.entry_fee,
            "share_price": settings.share_price,
            "share_count": share_count,
            "share_total": share_total,
            "total": settings.entry_fee + share_total,
        },
    }


def _account_number(application) -> str:
    from apps.core import crypto

    return crypto.decrypt(
        application.account_encrypted, f"application:{application.id}:account"
    ).decode()


def render_pdf(application, profile, settings, variant, *, draft=False) -> bytes:
    html = render_to_string(
        "applications/pdf/form.html",
        build_context(application, profile, settings, variant, draft=draft),
    )
    return HTML(string=html, base_url=str(FONTS)).write_pdf()
