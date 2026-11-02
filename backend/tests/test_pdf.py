from io import BytesIO

import pytest
from pypdf import PdfReader

from apps.applications.models import GeneratedPdf
from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context

from .test_applications import AADHAAR, ACCOUNT, URL, World

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def world(org_a):
    return World(org_a)


@pytest.fixture
def approved(world):
    application = world.fully_approved()
    response = world.client(world.admin).put(
        "/api/v1/settings/organization-profile/",
        {
            "company_name_hi": "परीक्षण कंपनी",
            "company_name_hi_short": "परीक्षण कंपनी",
            "cin": "U01409UP2021PTC000000",
            "board_resolution_no": "138/19/6",
            "board_resolution_date": "2024-01-08",
            "members_female_only": True,
        },
    )
    assert response.status_code == 200, response.content
    return application


def pdf_of(client, application, variant):
    return client.get(f"{URL}{application['id']}/pdf/", {"variant": variant})


def text_of(content):
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(content)).pages)


def test_the_full_form_has_five_pages(world, approved):
    response = pdf_of(world.client(world.finance), approved, "full")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert len(PdfReader(BytesIO(response.content)).pages) == 5


def test_the_single_form_has_one_page(world, approved):
    response = pdf_of(world.client(world.finance), approved, "single")
    assert len(PdfReader(BytesIO(response.content)).pages) == 1


def test_the_form_carries_the_member_code_and_a_masked_aadhaar(world, approved):
    text = text_of(pdf_of(world.client(world.finance), approved, "full").content)

    assert approved["tr_code"] in text
    assert f"XXXX XXXX {AADHAAR[-4:]}" in text
    assert AADHAAR not in text


def test_the_bank_account_is_printed_as_on_the_paper_form(world, approved):
    text = text_of(pdf_of(world.client(world.finance), approved, "full").content)
    assert ACCOUNT in text


def test_the_approvers_are_named(world, approved):
    text = text_of(pdf_of(world.client(world.finance), approved, "full").content)

    assert "am@a.test" in text
    assert "cs@a.test" in text
    assert "finance@a.test" in text
    assert "field@a.test" in text


def test_signatures_and_documents_are_embedded(world, approved):
    reader = PdfReader(BytesIO(pdf_of(world.client(world.finance), approved, "full").content))
    images = sum(len(page.images) for page in reader.pages)
    # Photo and member mark on page 1, member mark on 3, four staff on 4, three scans on 5.
    assert images >= 10


def test_the_single_page_leaves_out_aadhaar_images(world, approved):
    reader = PdfReader(BytesIO(pdf_of(world.client(world.finance), approved, "single").content))
    # The photo and the member's mark: identical test images may be stored as one.
    assert 1 <= len(reader.pages[0].images) <= 2


def test_reprints_are_identical(world, approved, org_a):
    client = world.client(world.finance)
    first = pdf_of(client, approved, "full").content
    second = pdf_of(client, approved, "full").content

    assert first == second
    with organization_context(org_a.id):
        assert GeneratedPdf.objects.count() == 1


def test_a_stored_pdf_is_encrypted_on_disk(world, approved, org_a, settings):
    pdf_of(world.client(world.finance), approved, "full")
    with organization_context(org_a.id):
        path = GeneratedPdf.objects.get().relative_path

    assert not (settings.MEDIA_ROOT / path).read_bytes().startswith(b"%PDF")


def test_there_is_no_form_before_final_approval(world):
    application = world.submitted()
    assert pdf_of(world.client(world.manager), application, "single").status_code == 409


def test_the_full_form_needs_its_own_permission(world, approved):
    client = world.client(world.manager)

    assert pdf_of(client, approved, "full").status_code == 403
    assert pdf_of(client, approved, "single").status_code == 200


def test_unknown_variants_are_rejected(world, approved):
    assert pdf_of(world.client(world.finance), approved, "other").status_code == 400


def test_downloads_are_audited(world, approved, org_a):
    pdf_of(world.client(world.finance), approved, "full")

    with organization_context(org_a.id):
        event = AuditEvent.objects.get(action="application.pdf_downloaded")
    assert event.metadata == {"variant": "full"}
