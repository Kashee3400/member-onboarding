from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from apps.applications.models import Bank, BankBranch
from apps.core.tenancy import organization_context

from .conftest import authenticated_client
from .test_applications import World

pytestmark = pytest.mark.django_db(transaction=True)

URL = "/api/v1/banks/branches/"
CSV = (
    "ifsc,bank_name,branch_name,bank_code,branch_code,is_active\n"
    "UBIN0572161,Union Bank of India,Siyarha,12,901,1\n"
    "SBIN0001234,State Bank of India,Bhadohi,3,902,1\n"
    "sbin0009999,STATE BANK OF INDIA,Gopiganj,3,903,0\n"
    "BAD,Some Bank,Nowhere,4,904,1\n"
)


@pytest.fixture
def world(org_a):
    return World(org_a)


def upload(client, content: bytes, name="banks.csv"):
    return client.post(
        f"{URL}import/", {"file": SimpleUploadedFile(name, content)}, format="multipart"
    )


def test_an_admin_imports_the_erp_file(world, org_a):
    response = upload(world.client(world.admin), CSV.encode())

    assert response.status_code == 200, response.content
    assert response.data["created"] == 3
    assert response.data["skipped"] == 1
    assert response.data["problems"] == [{"row": 5, "problem": "ifsc is not valid"}]
    with organization_context(org_a.id):
        # Matched without regard to case, so State Bank is there once.
        assert Bank.objects.count() == 2
        assert BankBranch.objects.get(ifsc="SBIN0009999").is_active is False


def test_importing_again_updates_by_ifsc(world, org_a):
    client = world.client(world.admin)
    upload(client, CSV.encode())

    again = "ifsc,bank_name,branch_name\nUBIN0572161,Union Bank of India,Siyarha Bazar\n"
    response = upload(client, again.encode())

    assert response.data["created"] == 0
    assert response.data["updated"] == 1
    with organization_context(org_a.id):
        assert BankBranch.objects.get(ifsc="UBIN0572161").name == "Siyarha Bazar"


def test_an_excel_file_works_too(world):
    workbook = Workbook()
    workbook.active.append(("IFSC", "Bank_Name", "Branch_Name", "District"))
    workbook.active.append(("UBIN0572161", "Union Bank of India", "Siyarha", "Bhadohi"))
    buffer = BytesIO()
    workbook.save(buffer)

    response = upload(world.client(world.admin), buffer.getvalue(), "banks.xlsx")

    assert response.status_code == 200, response.content
    found = world.client(world.facilitator).get(f"{URL}by-ifsc/UBIN0572161/").data
    assert found["district"] == "Bhadohi"


def test_a_file_without_the_columns_is_refused(world):
    response = upload(world.client(world.admin), b"code,name\n1,x\n")

    assert response.status_code == 400
    assert "Missing columns" in str(response.data)


def test_a_facilitator_finds_a_branch_by_ifsc(world):
    upload(world.client(world.admin), CSV.encode())
    client = world.client(world.facilitator)

    response = client.get(f"{URL}by-ifsc/ubin0572161/")

    assert response.status_code == 200
    assert response.data == {
        "ifsc": "UBIN0572161",
        "bank_name": "Union Bank of India",
        "branch_name": "Siyarha",
        "address": "",
        "district": "",
    }
    # A branch out of use, or one never heard of, is left to the online lookup.
    assert client.get(f"{URL}by-ifsc/SBIN0009999/").status_code == 404
    assert client.get(f"{URL}by-ifsc/HDFC0000001/").status_code == 404


def test_branches_are_searched(world):
    upload(world.client(world.admin), CSV.encode())
    client = world.client(world.facilitator)

    by_bank = client.get(URL, {"q": "state bank"}).data
    by_branch = client.get(URL, {"q": "siyarha"}).data
    active = client.get(URL, {"is_active": "true", "q": "SBIN"}).data

    assert by_bank["count"] == 2
    assert [row["ifsc"] for row in by_branch["results"]] == ["UBIN0572161"]
    assert [row["ifsc"] for row in active["results"]] == ["SBIN0001234"]


def test_an_admin_adds_and_edits_a_branch(world, org_a):
    client = world.client(world.admin)
    body = {"ifsc": "punb0123400", "bank_name": "Punjab National Bank", "branch_name": "Aurai"}

    created = client.post(URL, body, format="json")

    assert created.status_code == 201, created.content
    assert created.data["ifsc"] == "PUNB0123400"
    assert client.post(URL, body, format="json").status_code == 400
    edited = client.patch(
        f"{URL}{created.data['id']}/",
        {"is_active": False, "bank_name": "punjab national bank"},
        format="json",
    )
    assert edited.status_code == 200, edited.content
    assert edited.data["is_active"] is False
    with organization_context(org_a.id):
        assert Bank.objects.count() == 1


def test_only_admins_change_the_master(world):
    client = world.client(world.facilitator)

    assert upload(client, CSV.encode()).status_code == 403
    body = {"ifsc": "PUNB0123400", "bank_name": "PNB", "branch_name": "Aurai"}
    assert client.post(URL, body, format="json").status_code == 403


def test_each_organization_has_its_own_master(world, org_b, admin_b):
    upload(world.client(world.admin), CSV.encode())

    other = authenticated_client(org_b, admin_b)

    assert other.get(f"{URL}by-ifsc/UBIN0572161/").status_code == 404
    assert other.get(URL).data["count"] == 0
