from django.conf import settings as django_settings
from django.db import IntegrityError, transaction
from django.db.models import Count, F, OuterRef, Subquery
from django.db.models.fields.json import KT
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import exceptions

from apps.audit.services import record_event
from apps.core import crypto
from apps.core.exceptions import Conflict, DuplicateRecord, StaleVersion
from apps.documents import storage
from apps.documents.models import Document, DocumentType
from apps.documents.services import current_signature, missing_documents
from apps.hierarchy.services import accessible_mpps
from apps.notifications import services as notifications
from apps.rbac.catalog import APPROVE_ALL

from . import form, form_lists, legacy, place, review_checks, review_steps
from .models import (
    Application,
    ApplicationDecision,
    ApplicationRevision,
    ApplicationStepApproval,
    Decision,
    GeneratedPdf,
    LegacyMember,
    Member,
    MemberCodeSettings,
    OrganizationProfile,
    ReviewStepAccess,
    Sequence,
    Signatory,
    Status,
)
from .pdf.render import render_pdf

# The workflow, in order. No stage can be skipped.
STAGES = {
    Status.PENDING_AM: ("applications.approve_am", Status.PENDING_CS),
    Status.PENDING_CS: ("applications.approve_cs", Status.PENDING_FINANCE),
    Status.PENDING_FINANCE: ("applications.approve_finance", Status.APPROVED),
}
FIRST_STAGE = Status.PENDING_AM
EDITABLE_STATUSES = (Status.DRAFT, Status.REJECTED)
SERIAL_DIGITS = 4


def display_name(user) -> str:
    return user.full_name or user.email


def visible_applications(membership, permissions):
    """Applications follow the MPP, so a transfer moves them with no data change."""
    return Application.objects.filter(mpp__in=accessible_mpps(membership, permissions)).exclude(
        status=Status.DISCARDED
    )


def searchable_applications(membership, permissions):
    return visible_applications(membership, permissions).annotate(
        search_name=KT("data__applicant__full_name")
    )


def with_waiting_since(queryset):
    """When each form reached its current stage: the last stage approval, or the submission."""
    moved = (
        ApplicationDecision.objects.filter(
            application=OuterRef("pk"), revision=OuterRef("revision"), decision=Decision.APPROVED
        )
        .order_by("-decided_at")
        .values("decided_at")[:1]
    )
    return queryset.annotate(waiting_since=Coalesce(Subquery(moved), F("submitted_at")))


def status_counts(membership, permissions) -> dict[str, int]:
    counts = (
        visible_applications(membership, permissions)
        .order_by()
        .values("status")
        .annotate(total=Count("id"))
    )
    return {row["status"]: row["total"] for row in counts}


def next_value(key: str) -> int:
    sequence, _ = Sequence.objects.select_for_update().get_or_create(key=key)
    sequence.value = F("value") + 1
    sequence.save(update_fields=["value", "updated_at"])
    sequence.refresh_from_db(fields=["value"])
    return sequence.value


def code_settings() -> MemberCodeSettings:
    settings, _ = MemberCodeSettings.objects.get_or_create()
    return settings


def organization_profile() -> OrganizationProfile:
    profile, _ = OrganizationProfile.objects.get_or_create()
    return profile


def printed_form(application, variant: str) -> bytes:
    """Rendered once, then always served from the stored copy."""
    if application.status != Status.APPROVED:
        raise Conflict("The form can be printed after final approval.")

    stored = GeneratedPdf.objects.filter(application=application, variant=variant).first()
    if stored:
        return storage.read(stored.relative_path)

    content = render_pdf(application, organization_profile(), code_settings(), variant)
    path = storage.application_file_path(application, f"form-{variant}")
    storage.write(path, content)
    try:
        with transaction.atomic():
            GeneratedPdf.objects.create(
                application=application, variant=variant, relative_path=path
            )
    except IntegrityError:
        # The approval's background copy and a download raced: the first one stays.
        storage.delete_quietly(path)
        stored = GeneratedPdf.objects.get(application=application, variant=variant)
        return storage.read(stored.relative_path)
    return content


def draft_form(application, variant: str) -> bytes:
    """
    The printed form as it would look if approved now, for checking before the final
    approval. Rendered on each request and never kept, so it cannot pass for the real one.
    """
    if application.status not in STAGES:
        raise Conflict("A preview is for forms waiting for approval.")
    return render_pdf(application, organization_profile(), code_settings(), variant, draft=True)


def _print_when_committed(application) -> None:
    """Approval must not wait for, or fail because of, the PDFs."""
    if not django_settings.PRINT_FORMS_ON_APPROVAL:
        return
    from .tasks import make_printed_forms

    application_id, organization_id = str(application.id), str(application.organization_id)
    transaction.on_commit(
        lambda: make_printed_forms.delay(application_id, organization_id), robust=True
    )


def _context(application, name: str) -> str:
    return f"application:{application.id}:{name}"


def _organization_scope(application) -> str:
    return str(application.organization_id)


def contact_index(kind: str, value: str, organization_id) -> str:
    return crypto.blind_index(value, f"{kind}:{organization_id}")


def _active_member_with(**index) -> str | None:
    """
    The code of a current member holding this Aadhaar or mobile number. A member who
    has left does not count, so they can join again.
    """
    legacy = LegacyMember.objects.filter(is_active=True, **index).values_list("tr_code", flat=True)
    return legacy.first()


def already_used(application) -> dict[str, str]:
    """Aadhaar, mobile and email must be new to everything that is still current."""
    errors = {}
    others = Application.objects.exclude(pk=application.pk).exclude(status=Status.DISCARDED)
    organization = _organization_scope(application)

    if application.aadhaar_index:
        existing = _active_member_with(aadhaar_index=application.aadhaar_index)
        if existing:
            errors["applicant.aadhaar_number"] = (
                f"This Aadhaar number already belongs to member {existing}."
            )

    address = application.data.get("address", {})
    mobile = str(address.get("mobile") or "").strip()
    if mobile:
        member = Member.objects.filter(mobile=mobile).values_list("tr_code", flat=True).first()
        legacy = _active_member_with(mobile_index=contact_index("mobile", mobile, organization))
        if member or legacy:
            errors["address.mobile"] = (
                f"This mobile number already belongs to member {member or legacy}."
            )
        elif others.filter(data__address__mobile=mobile).exists():
            errors["address.mobile"] = "Another form already uses this mobile number."

    email = str(address.get("email") or "").strip().lower()
    if email and others.filter(data__address__email__iexact=email).exists():
        errors["address.email"] = "Another form already uses this email."
    return errors


def set_aadhaar(application, number: str) -> None:
    if not form.is_valid_aadhaar(number):
        raise exceptions.ValidationError({"aadhaar_number": ["Enter a valid Aadhaar number."]})

    index = crypto.blind_index(number, f"aadhaar:{_organization_scope(application)}")
    duplicate = (
        Application.objects.filter(aadhaar_index=index)
        .exclude(pk=application.pk)
        .exclude(status=Status.DISCARDED)
        .exists()
    )
    if duplicate:
        # Told at once, so nobody fills a long form for someone already enrolled.
        raise DuplicateRecord("An application already exists for this Aadhaar number.")
    existing = _active_member_with(aadhaar_index=index)
    if existing:
        raise DuplicateRecord(f"This Aadhaar number already belongs to member {existing}.")

    application.aadhaar_encrypted = crypto.encrypt(
        number.encode(), _context(application, "aadhaar")
    )
    application.aadhaar_index = index
    application.aadhaar_last4 = number[-4:]


def set_account(application, number: str) -> None:
    if not form.is_valid_account(number):
        raise exceptions.ValidationError({"account_number": ["Enter a valid account number."]})

    application.account_encrypted = crypto.encrypt(
        number.encode(), _context(application, "account")
    )
    application.account_index = crypto.blind_index(
        number, f"account:{_organization_scope(application)}"
    )
    application.account_last4 = number[-4:]


def sensitive_numbers(application, *, user) -> dict:
    """The full numbers, for checking against the card and passbook photos."""
    record_event("application.numbers_viewed", actor=user, target=application)
    return {
        name: (crypto.decrypt(sealed, _context(application, label)).decode() if sealed else "")
        for name, label, sealed in (
            ("aadhaar_number", "aadhaar", application.aadhaar_encrypted),
            ("account_number", "account", application.account_encrypted),
        )
    }


# A team works these stages, and the printed form carries its head's signature.
HEAD_SIGNED = {Status.PENDING_CS: "CS & Legal", Status.PENDING_FINANCE: "Finance"}


def _signer(application, user):
    """The signature this stage prints, and whose it is."""
    label = HEAD_SIGNED.get(application.status)
    if label is None:
        return _signature_of(user), display_name(user)

    head = (
        Signatory.objects.filter(stage=application.status)
        .select_related("membership__user")
        .first()
    )
    if head is None:
        raise Conflict(f"Choose who signs for {label} under Review Steps first.")
    signature = current_signature(head.membership)
    if signature is None:
        raise Conflict(f"The {label} signatory has no signature on file.")
    return signature, display_name(head.membership.user)


def _signature_of(user):
    """Checked before acting, so the printed form can never have an empty signature box."""
    signature = current_signature(user.active_membership)
    if signature is None:
        raise exceptions.ValidationError(
            {"signature": ["Your signature is not on file. Ask an administrator to add it."]}
        )
    return signature


def _ensure_editable(application) -> None:
    if application.status not in EDITABLE_STATUSES:
        raise Conflict("This application can no longer be edited.")


def _ensure_current(application, version: int | None) -> None:
    if version is not None and version != application.version:
        raise StaleVersion()


def save_draft(application, *, user, data=None, aadhaar=None, account=None, version=None):
    """Autosave. Accepts partial answers: completeness is only checked on submit."""
    _ensure_editable(application)
    _ensure_current(application, version)

    if data is not None:
        before = application.data.get("address", {})
        cleaned = form.clean_draft(data, saved=application.data, choices=form_lists.choices())
        merged = {**application.data, **cleaned}
        after = merged.get("address", {})
        # A proof of the old number or address says nothing about a new one.
        if after.get("mobile") != before.get("mobile"):
            application.mobile_verified_at = None
        if after.get("email") != before.get("email"):
            application.email_verified_at = None
        application.data = merged
    place.apply(application)
    if aadhaar:
        set_aadhaar(application, aadhaar)
    if account:
        set_account(application, account)

    application.version += 1
    application.last_edited_by = user
    application.last_edited_by_name = display_name(user)
    application.save()
    return application


@transaction.atomic
def submit(application, *, user, version=None):
    _ensure_editable(application)
    _ensure_current(application, version)

    now = timezone.now()
    # Again here, so a draft saved before the MPP's place changed goes in with the new one.
    place.apply(application)
    last = application.revisions.order_by("-number").first()
    errors = form.validate_for_submit(
        application.data,
        has_aadhaar=bool(application.aadhaar_index),
        has_account=bool(application.account_index),
        today=timezone.localdate(now),
        choices=form_lists.choices(),
        previous=last.data if last else None,
    )
    errors |= missing_documents(application)
    errors |= already_used(application)
    applicant_gender = application.data.get("applicant", {}).get("gender")
    if organization_profile().members_female_only and applicant_gender != "female":
        errors["applicant.gender"] = "Membership is open to women only."
    signature = _signature_of(user)
    if errors:
        raise exceptions.ValidationError(errors)

    if not application.form_number:
        prefix = code_settings().form_prefix
        application.form_number = f"{prefix}{next_value('form_number'):05d}"

    application.revision += 1
    application.version += 1
    application.status = FIRST_STAGE
    application.submitted_at = now
    application.rejection_reason = ""
    application.rejected_fields = []
    application.last_edited_by = user
    application.last_edited_by_name = display_name(user)
    application.save()

    ApplicationRevision.objects.create(
        application=application,
        number=application.revision,
        data=application.data,
        aadhaar_last4=application.aadhaar_last4,
        account_last4=application.account_last4,
        submitted_by=user,
        submitted_by_name=display_name(user),
        signature=signature,
        submitted_at=now,
    )
    notifications.application_awaits_area_manager(application)
    record_event(
        "application.submitted",
        actor=user,
        target=application,
        metadata={"revision": application.revision},
    )
    return application


def _ensure_payment_recorded(application) -> None:
    errors = {}
    if not application.payment:
        errors["payment"] = ["Record the payment before final approval."]
    has_proof = Document.objects.filter(
        application=application, document_type=DocumentType.PAYMENT_PROOF, is_current=True
    ).exists()
    if not has_proof:
        errors["payment_proof"] = ["Upload the payment proof before final approval."]
    if errors:
        raise exceptions.ValidationError(errors)


def _steps_to_approve(application, user, steps) -> set[str]:
    if not ReviewStepAccess.objects.exists():
        raise Conflict("Choose who acts on each step under Review Steps first.")

    open_steps = review_steps.actionable(application, user.active_membership)
    stage_steps = review_steps.stage_steps(application.status)
    if stage_steps and not open_steps:
        raise exceptions.PermissionDenied("None of this form's open steps are yours.")
    if steps is None:
        return open_steps

    chosen = set(steps)
    if not chosen and stage_steps:
        raise exceptions.ValidationError({"steps": ["Choose at least one step."]})
    if not chosen <= open_steps:
        raise exceptions.ValidationError({"steps": ["You can approve only your own open steps."]})
    return chosen


def record_payment(application, *, user, permissions, payment: dict):
    membership = user.active_membership
    if review_steps.FEE_STEP not in review_steps.my_steps(membership):
        raise exceptions.PermissionDenied("Only the Member Fee step's role can record a payment.")
    if review_steps.FEE_STEP not in review_steps.actionable(application, membership):
        raise Conflict("Payment is recorded while the Member Fee step is open.")

    application.payment = {
        **payment,
        "deposited_on": payment["deposited_on"].isoformat(),
        "recorded_by_name": display_name(user),
    }
    application.version += 1
    application.save()
    record_event("application.payment_recorded", actor=user, target=application)
    return application


def code_parts(mpp, settings: MemberCodeSettings) -> tuple[str, str]:
    """A member code is state + village + hamlet + serial, and the first and third are the MPP's."""
    return mpp.state_code or settings.state_code, mpp.hamlet_code or settings.hamlet_code


def build_tr_code(application, serial: int, settings: MemberCodeSettings) -> str:
    mpp = application.mpp
    state_code, hamlet_code = code_parts(mpp, settings)
    return f"{state_code}{mpp.village_code}{hamlet_code}{serial:0{SERIAL_DIGITS}d}"


def _next_free_code(application, settings: MemberCodeSettings) -> str:
    """The counter normally suffices. The check catches codes it never heard about."""
    state_code, hamlet_code = code_parts(application.mpp, settings)
    key = legacy.serial_key(state_code, application.mpp.village_code, hamlet_code)
    while True:
        serial = next_value(key)
        if serial >= 10**SERIAL_DIGITS:
            raise Conflict("This MPP has run out of member numbers.")
        code = build_tr_code(application, serial, settings)
        if not legacy.existing_code_taken(code):
            return code


def _create_member(application, now):
    return Member.objects.create(
        application=application,
        mpp=application.mpp,
        tr_code=_next_free_code(application, code_settings()),
        full_name=application.data["applicant"]["full_name"],
        mobile=application.data["address"]["mobile"],
        aadhaar_index=application.aadhaar_index,
        aadhaar_last4=application.aadhaar_last4,
        joined_at=now,
    )


def _record_decision(application, user, decision, now, *, reason="", rejected_fields=None):
    """One stage's decision, signed as that stage prints: by its head, or by whoever decided."""
    signature, signed_by = _signer(application, user)
    ApplicationDecision.objects.create(
        application=application,
        revision=application.revision,
        stage=application.status,
        decision=decision,
        reason=reason.strip(),
        rejected_fields=(rejected_fields or []) if decision == Decision.REJECTED else [],
        decided_by=user,
        decided_by_name=display_name(user),
        signature=signature,
        signed_by_name=signed_by,
        decided_at=now,
    )


@transaction.atomic
def decide(
    application, *, user, permissions, decision, reason="", rejected_fields=None, steps=None
):
    """Runs one workflow stage. The row is locked, so a double click cannot act twice."""
    application = (
        Application.objects.select_for_update(of=("self",))
        .select_related("mpp")
        .get(pk=application.pk)
    )

    stage = STAGES.get(application.status)
    if stage is None:
        raise Conflict("This application is not waiting for a decision.")
    permission, next_status = stage
    if permission not in permissions and APPROVE_ALL not in permissions:
        raise exceptions.PermissionDenied("This stage needs a different role.")

    worked_on_it = ApplicationRevision.objects.filter(
        application=application, submitted_by=user
    ).exists()
    if worked_on_it or application.created_by_id == user.pk:
        raise exceptions.PermissionDenied("You cannot decide on an application you prepared.")

    if decision == Decision.REJECTED and not reason.strip():
        raise exceptions.ValidationError({"reason": ["Give a reason for rejecting."]})
    if decision == Decision.REJECTED and rejected_fields:
        allowed = review_steps.my_sections(user.active_membership)
        if any(field.split(".")[0] not in allowed for field in rejected_fields):
            raise exceptions.ValidationError(
                {"rejected_fields": ["You can mark fields only on your own steps."]}
            )

    # A missing signature stops even one step being approved, before anything is saved.
    _signer(application, user)
    now = timezone.now()
    if decision == Decision.APPROVED:
        chosen = _steps_to_approve(application, user, steps)
        if review_steps.FEE_STEP in chosen:
            _ensure_payment_recorded(application)
        checked = review_checks.proof(application, user, chosen)
        ApplicationStepApproval.objects.bulk_create(
            ApplicationStepApproval(
                organization_id=application.organization_id,
                application=application,
                revision=application.revision,
                step=step,
                decided_by=user,
                decided_by_name=display_name(user),
                decided_at=now,
                checks=checked[step],
            )
            for step in sorted(chosen)
        )
        approved = set(review_steps.approvals_of(application))
        if review_steps.stage_steps(application.status) - approved:
            # Others on this stage still have steps to check, so the form stays here.
            application.version += 1
            application.save()
            record_event(
                "application.steps_approved",
                actor=user,
                target=application,
                metadata={"revision": application.revision, "steps": sorted(chosen)},
            )
            return application

        # This stage is done. A later stage whose steps were all checked ahead (the
        # admin may do that) is done too, so the form never waits on a stage with
        # nothing left to check. Each stage still records its own signed decision.
        while True:
            _permission, next_status = STAGES[application.status]
            missing = set(review_steps.STEP_KEYS) - approved
            if next_status == Status.APPROVED and missing:
                titles = ", ".join(review_steps.TITLES[key] for key in sorted(missing))
                raise Conflict(f"These steps have not been approved: {titles}.")
            _record_decision(application, user, Decision.APPROVED, now)
            application.status = next_status
            if next_status not in STAGES or review_steps.stage_steps(next_status) - approved:
                break
    else:
        _record_decision(
            application, user, decision, now, reason=reason, rejected_fields=rejected_fields
        )
        # Back to the MPP's current facilitator, and later from the first stage again.
        application.status = Status.REJECTED
        application.rejection_reason = reason.strip()
        application.rejected_fields = rejected_fields or []
        notifications.application_rejected(application, reason.strip())

    application.version += 1
    application.save()

    metadata = {"revision": application.revision, "decision": decision}
    if application.status == Status.APPROVED:
        member = _create_member(application, now)
        metadata["tr_code"] = member.tr_code
        notifications.application_approved(application, member.tr_code)
        _print_when_committed(application)
    elif application.status in STAGES:
        notifications.application_awaits(application, STAGES[application.status][0])

    record_event("application.decided", actor=user, target=application, metadata=metadata)
    return application
