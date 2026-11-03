import zipfile
from datetime import timedelta
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from pypdf import PdfReader

from apps.applications.form import is_valid_aadhaar
from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context
from apps.hierarchy.imports import COLUMNS
from apps.hierarchy.models import Mcc, Mpp, Route
from apps.organizations.models import Membership
from apps.rbac.models import Role
from apps.reports.models import BatchStatus, PdfBatch
from apps.reports.services import _safe_cell

from .test_applications import AADHAAR, OTHER_AADHAAR, URL, World

pytestmark = pytest.mark.django_db(transaction=True)

SUMMARY = "/api/v1/reports/summary/"
EXPORT = "/api/v1/reports/export/"
BATCHES = "/api/v1/reports/pdf-batches/"
IMPORT = "/api/v1/hierarchy/mpps/import/"


@pytest.fixture
def world(org_a):
    return World(org_a)


def sheet_rows(content):
    return list(load_workbook(BytesIO(content)).active.iter_rows(values_only=True))


def workbook_file(rows, columns=COLUMNS):
    book = Workbook()
    book.active.append(list(columns))
    for row in rows:
        book.active.append(list(row))
    buffer = BytesIO()
    book.save(buffer)
    return SimpleUploadedFile("masters.xlsx", buffer.getvalue())


def row(mpp="2001", village="00300001", internal="902001", mcc="7"):
    return ("P9", "Plant Nine", mcc, "MCC Seven", mpp, internal, "New MPP", village)


def test_the_summary_counts_by_status(world):
    world.fully_approved(AADHAAR)
    world.submitted(OTHER_AADHAAR)

    data = world.client(world.finance).get(SUMMARY).data

    assert data["total"] == 2
    assert data["by_status"] == {"approved": 1, "pending_am": 1}


def test_reports_can_be_filtered(world):
    world.fully_approved(AADHAAR)
    world.submitted(OTHER_AADHAAR)

    data = world.client(world.finance).get(SUMMARY, {"status": "approved"}).data

    assert data["total"] == 1


def test_bad_filters_are_rejected(world):
    client = world.client(world.finance)
    assert client.get(SUMMARY, {"status": "nope"}).status_code == 400
    assert client.get(SUMMARY, {"submitted_from": "yesterday"}).status_code == 400


def test_a_report_never_exceeds_mpp_access(world):
    world.fully_approved()
    outsider = world.member("am2@a.test", "area_manager")
    with organization_context(world.org.id):
        Role.objects.filter(code="area_manager").update(
            permissions=["reports.view", "applications.approve_am"]
        )

    assert world.client(outsider).get(SUMMARY).data["total"] == 0


def test_the_excel_export_has_the_member_and_no_aadhaar(world):
    final = world.fully_approved()

    response = world.client(world.finance).get(EXPORT)

    assert response.status_code == 200
    rows = sheet_rows(response.content)
    assert rows[0][0] == "Form number"
    assert rows[1][1] == final["tr_code"]
    assert AADHAAR not in str(rows)


def test_exports_need_their_own_permission(world):
    legal = world.client(world.legal)
    assert legal.get(SUMMARY).status_code == 200
    assert legal.get(EXPORT).status_code == 403


def test_exports_are_audited(world, org_a):
    world.client(world.finance).get(EXPORT, {"status": "approved"})
    with organization_context(org_a.id):
        event = AuditEvent.objects.get(action="report.exported")
    assert event.metadata == {"status": "approved"}


@pytest.mark.parametrize("value", ["=1+1", "+91", "-5", "@cmd"])
def test_text_cannot_run_as_a_formula_in_excel(value):
    assert _safe_cell(value) == f"'{value}"


# Bulk PDF ----------------------------------------------------------------------------


def job(client, **body):
    return client.post(BATCHES, {"variant": "full", **body}, format="json")


def test_a_job_gives_one_pdf_per_form_named_by_form_number(world):
    first = world.fully_approved(AADHAAR)
    second = world.fully_approved(OTHER_AADHAAR)
    world.submitted(_third_aadhaar())
    client = world.client(world.legal)

    started = job(client, want_zip=True, want_merged=True)

    assert started.status_code == 202, started.content
    done = client.get(f"{BATCHES}{started.data['id']}/").data
    assert (done["status"], done["processed"], done["form_count"]) == ("done", 2, 2)
    archive = zipfile.ZipFile(
        BytesIO(b"".join(client.get(f"{BATCHES}{done['id']}/zip/").streaming_content))
    )
    assert sorted(archive.namelist()) == sorted(
        [f"{first['form_number']}.pdf", f"{second['form_number']}.pdf"]
    )
    merged = client.get(f"{BATCHES}{done['id']}/file/", {"part": 0})
    assert len(PdfReader(BytesIO(merged.content)).pages) == 10


def _third_aadhaar():
    return next(n for n in (f"56781234567{d}" for d in range(10)) if is_valid_aadhaar(n))


def test_the_preview_counts_by_approval_day_and_search(world):
    final = world.fully_approved(AADHAAR)
    world.fully_approved(OTHER_AADHAAR)
    client = world.client(world.legal)
    today = timezone.localdate()

    def count(**filters):
        return client.post(f"{BATCHES}preview/", filters, format="json").data["count"]

    assert count() == 2
    assert count(approved_from=str(today), approved_to=str(today)) == 2
    assert count(approved_from=str(today + timedelta(days=1))) == 0
    assert count(search=final["form_number"]) == 1
    assert count(search=final["tr_code"]) == 1


def test_a_job_with_nothing_to_print_is_refused(world):
    assert job(world.client(world.legal), want_zip=True).status_code == 400


def test_the_pdf_center_needs_its_permission(world):
    world.fully_approved()

    # Finance sees every form but was not given the PDF Center.
    assert job(world.client(world.finance), want_zip=True).status_code == 403
    assert world.client(world.manager).get(BATCHES).status_code == 403


def test_the_full_form_needs_its_permission(world):
    world.fully_approved()
    with organization_context(world.org.id):
        role = Role.objects.get(code="area_manager")
        role.permissions = [*role.permissions, "applications.pdf_center"]
        role.save()
    manager = world.client(world.manager)

    assert job(manager, want_zip=True).status_code == 403
    assert job(manager, variant="single", want_zip=True).status_code == 202


def test_a_zip_or_a_print_file_must_be_chosen(world):
    world.fully_approved()
    response = job(world.client(world.legal), want_zip=False, want_merged=False)
    assert response.status_code == 400


def test_forms_that_fail_are_listed_and_can_be_retried(world, monkeypatch):
    final = world.fully_approved()
    monkeypatch.setattr("apps.reports.tasks.printed_form", _explode)
    client = world.client(world.legal)

    failed = client.get(f"{BATCHES}{job(client, want_zip=True).data['id']}/").data

    assert failed["status"] == "failed"
    assert failed["failed_forms"] == [final["form_number"]]
    monkeypatch.undo()
    retried = client.post(f"{BATCHES}{failed['id']}/retry/")
    assert retried.status_code == 202
    assert client.get(f"{BATCHES}{retried.data['id']}/").data["status"] == "done"


def _explode(*args):
    raise RuntimeError("no")


def running_job(world, user):
    with organization_context(world.org.id):
        return PdfBatch.objects.create(
            organization=world.org,
            status=BatchStatus.RUNNING,
            filters={"application_ids": []},
            requested_by=user,
            requested_by_name="x",
        )


def test_one_job_at_a_time_per_person(world):
    world.fully_approved()
    running_job(world, world.legal)

    assert job(world.client(world.legal), want_zip=True).status_code == 409


def test_jobs_wait_their_turn_and_can_be_cancelled(world):
    world.fully_approved()
    running_job(world, world.admin)
    client = world.client(world.legal)

    queued = job(client, want_zip=True).data

    assert (queued["status"], queued["queue_position"]) == ("queued", 2)
    cancelled = client.post(f"{BATCHES}{queued['id']}/cancel/")
    assert cancelled.data["status"] == "cancelled"
    assert client.post(f"{BATCHES}{queued['id']}/cancel/").status_code == 409


def test_a_job_is_seen_only_by_whoever_asked(world):
    world.fully_approved()
    started = job(world.client(world.legal), want_zip=True).data

    other = world.client(world.admin)
    assert other.get(f"{BATCHES}{started['id']}/").status_code == 404
    assert other.get(f"{BATCHES}{started['id']}/zip/").status_code == 404


def test_files_go_after_seven_days(world):
    world.fully_approved()
    client = world.client(world.legal)
    started = job(client, want_zip=True).data
    with organization_context(world.org.id):
        PdfBatch.objects.filter(pk=started["id"]).update(
            finished_at=timezone.now() - timedelta(days=8)
        )

    assert client.get(f"{BATCHES}{started['id']}/zip/").status_code == 410


# MPP import --------------------------------------------------------------------------


def upload(client, file):
    return client.post(IMPORT, {"file": file}, format="multipart")


def preview(client, file):
    return client.post(IMPORT, {"file": file, "preview": "true"}, format="multipart")


def test_a_preview_shows_new_changed_and_missing_mpps_and_saves_nothing(world, org_a):
    renamed = ("P1", "Plant", "6", "Bhadohi", "1305", "", "Dudwa Khurd", "00209982")

    response = preview(world.client(world.admin), workbook_file([row(), renamed]))

    assert response.status_code == 200, response.content
    found = response.data["preview"]
    assert (response.data["created"], response.data["updated"]) == (1, 1)
    assert [entry["code"] for entry in found["new"]] == ["2001"]
    assert found["changed"] == [
        {"code": "1305", "name": "Dudwa Khurd", "changes": {"name": ["Dudwa", "Dudwa Khurd"]}}
    ]
    # In the masters but not in the file: listed, never switched off.
    assert [entry["code"] for entry in found["missing"]] == ["1152"]
    assert (found["new_plants"], found["new_mccs"]) == (1, 1)
    with organization_context(org_a.id):
        assert not Mpp.objects.filter(code="2001").exists()
        assert Mpp.objects.get(code="1305").name == "Dudwa"


def test_a_preview_reports_the_same_problems_as_the_import(world):
    bad = row(village="123")

    previewed = preview(world.client(world.admin), workbook_file([bad])).data
    imported = upload(world.client(world.admin), workbook_file([bad])).data

    assert previewed["problems"] == imported["problems"] != []


def test_a_preview_leaves_no_audit_trail(world, org_a):
    preview(world.client(world.admin), workbook_file([row()]))

    with organization_context(org_a.id):
        assert not AuditEvent.objects.filter(action="hierarchy.imported").exists()


def test_a_file_creates_the_whole_hierarchy(world, org_a):
    response = upload(world.client(world.admin), workbook_file([row()]))

    assert response.status_code == 200
    assert response.data == {"created": 1, "updated": 0, "problems": []}
    with organization_context(org_a.id):
        mpp = Mpp.objects.get(code="2001")
        assert mpp.source_code == "902001"
        assert mpp.mcc.plant.code == "P9"


def test_importing_again_updates_instead_of_duplicating(world, org_a):
    client = world.client(world.admin)
    upload(client, workbook_file([row()]))

    response = upload(client, workbook_file([row(mcc="8")]))

    assert response.data == {"created": 0, "updated": 1, "problems": []}
    with organization_context(org_a.id):
        assert Mcc.objects.filter(code="7").exists()


def test_one_bad_row_stops_the_whole_file(world, org_a):
    response = upload(
        world.client(world.admin),
        workbook_file([row(), row(mpp="2002", village="123", internal="902002")]),
    )

    assert response.data["created"] == 0
    assert response.data["problems"][0]["row"] == 3
    with organization_context(org_a.id):
        assert not Mpp.objects.filter(code="2001").exists()


def test_repeats_inside_a_file_are_reported(world):
    response = upload(
        world.client(world.admin), workbook_file([row(), row(village="00300002", internal="9")])
    )
    assert "repeated" in response.data["problems"][0]["problem"]


def test_a_village_cannot_be_taken_from_another_mpp(world):
    response = upload(world.client(world.admin), workbook_file([row(village="00209982")]))
    assert "another MPP" in response.data["problems"][0]["problem"]


def test_missing_columns_are_named(world):
    response = upload(world.client(world.admin), workbook_file([], columns=("plant_code",)))
    assert response.status_code == 400
    assert "mpp_code" in str(response.data["error"]["details"])


def test_a_non_excel_file_is_refused(world):
    response = upload(world.client(world.admin), SimpleUploadedFile("x.xlsx", b"not excel"))
    assert response.status_code == 400


def test_importing_needs_the_masters_permission(world):
    response = upload(world.client(world.facilitator), workbook_file([row()]))
    assert response.status_code == 403


# Hindi -------------------------------------------------------------------------------


def test_every_part_of_the_form_has_hindi(world):
    schema = world.client(world.facilitator).get(f"{URL}form/").data

    for section in schema["sections"]:
        assert section["title_hi"], section["key"]
        for field in section["fields"]:
            assert field["label_hi"], field["key"]
            for option in field.get("options", []):
                assert option["label_hi"], option["value"]
    assert schema["family"]["relations"][0]["label_hi"]


def test_membership_import_keeps_existing_assignments(world, org_a):
    upload(world.client(world.admin), workbook_file([row(mpp="1305", village="00209982")]))

    with organization_context(org_a.id):
        membership = Membership.objects.get(user=world.facilitator)
        assert Mpp.objects.get(code="1305").assignments.filter(membership=membership).exists()


def numbered_file(rows):
    workbook = Workbook()
    workbook.active.append((*COLUMNS, "state_code", "hamlet_code"))
    for values in rows:
        workbook.active.append(values)
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    buffer.name = "masters.xlsx"
    return buffer


def test_a_village_can_have_several_mpps_with_their_own_numbers(world):
    rows = [
        (*row(mpp="2001", internal="1"), "09", "01"),
        (*row(mpp="2002", internal="2"), "09", "02"),
    ]

    response = upload(world.client(world.admin), numbered_file(rows))

    assert response.data["created"] == 2
    assert response.data["problems"] == []
    with organization_context(world.org.id):
        assert Mpp.objects.get(code="2002").hamlet_code == "02"


def test_the_same_village_number_twice_is_refused(world):
    rows = [
        (*row(mpp="2001", internal="1"), "09", "01"),
        (*row(mpp="2002", internal="2"), "09", "01"),
    ]

    response = upload(world.client(world.admin), numbered_file(rows))

    assert response.data["created"] == 0
    assert "repeated" in response.data["problems"][0]["problem"]


def test_a_bad_series_is_refused(world):
    response = upload(world.client(world.admin), numbered_file([(*row(), "9", "01")]))

    assert response.data["problems"][0]["problem"] == "state_code must be 2 digits"


def test_an_mcc_with_no_mpps_is_kept(world):
    rows = [("P9", "Plant Nine", "77", "Empty MCC", "", "", "", "", "", "")]

    response = upload(world.client(world.admin), numbered_file(rows))

    assert response.data["created"] == 0
    assert response.data["problems"] == []
    with organization_context(world.org.id):
        assert Mcc.objects.get(code="77").name == "Empty MCC"


def full_file(rows):
    workbook = Workbook()
    workbook.active.append(
        (*COLUMNS, "state_code", "hamlet_code", "bmc_code", "bmc_name", "route_code", "route_name")
    )
    for values in rows:
        workbook.active.append(values)
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    buffer.name = "masters.xlsx"
    return buffer


def test_a_file_builds_bmcs_and_routes_too(world):
    rows = [
        (*row(), "09", "01", "B7", "Cooler", "R7", "Route Seven"),
        (
            "P9",
            "Plant Nine",
            "7",
            "MCC Seven",
            "",
            "",
            "",
            "",
            "",
            "",
            "B7",
            "Cooler",
            "R8",
            "Empty Route",
        ),
    ]

    response = upload(world.client(world.admin), full_file(rows))

    assert response.data["problems"] == []
    with organization_context(world.org.id):
        mpp = Mpp.objects.select_related("route__bmc__mcc").get(code="2001")
        assert mpp.route.code == "R7"
        assert mpp.route.bmc.mcc.code == "7"
        assert Route.objects.get(code="R8").bmc.code == "B7"


def test_a_route_needs_its_bmc(world):
    rows = [(*row(), "09", "01", "", "", "R7", "Route Seven")]

    response = upload(world.client(world.admin), full_file(rows))

    assert "a route needs a bmc_code" in response.data["problems"][0]["problem"]
