from io import BytesIO

import pytest
from pypdf import PdfReader

from apps.applications import services
from apps.applications.models import GeneratedPdf, Member
from apps.applications.tasks import PRINT_RETRIES
from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context

from .test_applications import OTHER_AADHAAR, URL, World
from .test_pdf import pdf_of, text_of

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def world(org_a):
    return World(org_a)


@pytest.fixture
def at_finance(world):
    application = world.submitted()
    for user in (world.manager, world.legal):
        assert world.approve(application, user).status_code == 200
    return application


def preview_of(client, application, variant):
    return client.get(f"{URL}{application['id']}/preview-pdf/", {"variant": variant})


def stored(org):
    with organization_context(org.id):
        return set(GeneratedPdf.objects.values_list("variant", flat=True))


# Preview before final approval -------------------------------------------------------


def test_finance_can_preview_the_full_form_before_approving(world, at_finance):
    response = preview_of(world.client(world.finance), at_finance, "full")

    assert response.status_code == 200, response.content
    assert response["Content-Type"] == "application/pdf"
    assert response["Cache-Control"] == "private, no-store"
    pages = PdfReader(BytesIO(response.content)).pages
    assert len(pages) == 5
    assert all("NOT APPROVED" in page.extract_text() for page in pages)


def test_the_preview_has_no_member_code_and_no_signature_still_to_come(world, at_finance):
    text = text_of(preview_of(world.client(world.finance), at_finance, "full").content)

    assert "Assigned at approval" in text
    assert "cs@a.test" in text
    assert "finance@a.test" not in text


def test_a_preview_is_never_stored(world, at_finance, org_a):
    preview_of(world.client(world.finance), at_finance, "full")
    preview_of(world.client(world.finance), at_finance, "single")

    assert stored(org_a) == set()


def test_previews_are_audited(world, at_finance, org_a):
    preview_of(world.client(world.finance), at_finance, "single")

    with organization_context(org_a.id):
        event = AuditEvent.objects.get(action="application.pdf_previewed")
    assert event.metadata == {"variant": "single", "status": "pending_finance"}


def test_earlier_stages_can_preview_within_their_pdf_rights(world):
    application = world.submitted()
    client = world.client(world.manager)

    assert preview_of(client, application, "full").status_code == 403
    single = preview_of(client, application, "single")
    assert single.status_code == 200
    assert len(PdfReader(BytesIO(single.content)).pages) == 1


def test_the_full_preview_works_before_anyone_has_approved(world):
    application = world.submitted()
    response = preview_of(world.client(world.legal), application, "full")

    assert response.status_code == 200, response.content
    assert len(PdfReader(BytesIO(response.content)).pages) == 5


def test_only_approvers_can_preview(world, at_finance):
    assert preview_of(world.client(world.facilitator), at_finance, "single").status_code == 403
    # The organization admin acts on every step, so may check the printed form too.
    assert preview_of(world.client(world.admin), at_finance, "single").status_code == 200


def test_there_is_no_preview_outside_the_review_stages(world):
    draft = world.filled()
    approved = world.fully_approved(OTHER_AADHAAR)
    client = world.client(world.finance)

    assert preview_of(client, draft, "single").status_code == 409
    assert preview_of(client, approved, "single").status_code == 409


def test_unknown_preview_variants_are_rejected(world, at_finance):
    assert preview_of(world.client(world.finance), at_finance, "other").status_code == 400


# PDFs made at approval ---------------------------------------------------------------


@pytest.fixture
def printing(settings):
    settings.PRINT_FORMS_ON_APPROVAL = True


def test_final_approval_makes_both_pdfs(world, org_a, printing):
    world.fully_approved()

    assert stored(org_a) == {"full", "single"}


def test_approval_leaves_printing_to_the_first_download_when_switched_off(world, org_a):
    world.fully_approved()

    assert stored(org_a) == set()


def test_a_download_after_approval_serves_the_stored_copy(world, org_a, monkeypatch, printing):
    approved = world.fully_approved()
    monkeypatch.setattr(services, "render_pdf", pytest.fail)

    assert pdf_of(world.client(world.finance), approved, "full").status_code == 200


def test_approval_succeeds_when_the_pdf_cannot_be_made(
    world, at_finance, org_a, monkeypatch, printing
):
    calls = []

    def broken(*args, **kwargs):
        calls.append(args[-1])
        raise RuntimeError("renderer down")

    monkeypatch.setattr(services, "render_pdf", broken)
    response = world.approve(at_finance, world.finance)

    assert response.status_code == 200, response.content
    assert response.data["status"] == "approved"
    assert response.data["tr_code"]
    with organization_context(org_a.id):
        assert Member.objects.count() == 1
    assert stored(org_a) == set()
    # Retried a few times, then left for the first download.
    assert len(calls) == 1 + PRINT_RETRIES

    monkeypatch.undo()
    assert pdf_of(world.client(world.finance), response.data, "full").status_code == 200
