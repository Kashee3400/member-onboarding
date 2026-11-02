import csv

import pytest
from django.core.management import call_command
from django.db import connection

from apps.applications.legacy import import_legacy_members
from apps.applications.models import LegacyMember, Sequence
from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context
from apps.hierarchy.models import Mpp
from apps.rbac.models import Role

from .test_applications import AADHAAR, OTHER_AADHAAR, URL, World

pytestmark = pytest.mark.django_db(transaction=True)

COLUMNS = [
    "member_tr_code",
    "member_code",
    "member_name",
    "mpp_code",
    "is_active",
    "is_default",
    "application_no",
    "aadhar_no",
]
VILLAGE = "00209982"


def row(serial=25, state_code="09", aadhaar="", active="True", default="True", application=""):
    code = f"{state_code}{VILLAGE}01{serial:04d}"
    return [code, f"M{code}", "Old Member", "9013", active, default, application, aadhaar]


def csv_file(tmp_path, rows):
    path = tmp_path / "members.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    return path


def load(org, tmp_path, rows):
    path = csv_file(tmp_path, rows)
    with organization_context(org.id):
        return import_legacy_members(path, organization_id=org.id, form_prefix="A")


@pytest.fixture
def world(org_a):
    return World(org_a)


def test_new_codes_continue_after_the_last_real_one(world, org_a, tmp_path):
    load(org_a, tmp_path, [row(state_code="10", serial=40), row(state_code="10", serial=7)])

    assert world.fully_approved()["tr_code"] == f"10{VILLAGE}010041"


def test_inactive_members_keep_their_numbers_taken(world, org_a, tmp_path):
    load(org_a, tmp_path, [row(state_code="10", serial=90, active="False", default="False")])

    assert world.fully_approved()["tr_code"].endswith("0091")


def test_each_series_counts_separately(world, org_a, tmp_path):
    load(org_a, tmp_path, [row(state_code="09", serial=500)])

    assert world.fully_approved()["tr_code"] == f"10{VILLAGE}010001"


def test_a_repeated_import_never_lowers_a_counter(world, org_a, tmp_path):
    load(org_a, tmp_path, [row(state_code="10", serial=40)])
    world.fully_approved()

    load(org_a, tmp_path, [row(state_code="10", serial=40)])

    assert world.fully_approved(OTHER_AADHAAR)["tr_code"].endswith("0042")


def test_form_numbers_continue_from_the_old_system(world, org_a, tmp_path):
    load(org_a, tmp_path, [row(application="A56073"), row(serial=26, application="A00012")])

    assert world.submitted()["form_number"] == "A56074"


def test_someone_already_a_member_cannot_apply_again(world, org_a, tmp_path):
    load(org_a, tmp_path, [row(aadhaar=AADHAAR)])
    client = world.client(world.facilitator)
    application = world.draft(client)

    response = client.patch(f"{URL}{application['id']}/", {"aadhaar_number": AADHAAR})

    assert response.status_code == 409
    assert response.data["error"]["code"] == "duplicate_record"


def test_a_former_member_can_join_again(world, org_a, tmp_path):
    load(org_a, tmp_path, [row(aadhaar=AADHAAR, active="False", default="False")])
    client = world.client(world.facilitator)
    application = world.draft(client)

    assert (
        client.patch(f"{URL}{application['id']}/", {"aadhaar_number": AADHAAR}).status_code == 200
    )


def test_aadhaar_is_never_stored(org_a, tmp_path):
    load(org_a, tmp_path, [row(aadhaar=AADHAAR)])

    with organization_context(org_a.id), connection.cursor() as cursor:
        cursor.execute("SELECT row_to_json(member_legacy)::text FROM member_legacy")
        stored = cursor.fetchone()[0]
    assert AADHAAR not in stored


def test_the_same_code_on_two_rows_is_one_member(org_a, tmp_path):
    report = load(
        org_a,
        tmp_path,
        [row(active="False", default="False"), row(aadhaar=AADHAAR)],
    )

    assert report["rows"] == 2
    assert report["members"] == 1
    with organization_context(org_a.id):
        member = LegacyMember.objects.get()
    assert member.is_active
    assert member.aadhaar_index


def test_an_aadhaar_on_an_older_row_is_not_lost(world, org_a, tmp_path):
    load(
        org_a,
        tmp_path,
        [row(), row(aadhaar=AADHAAR, active="True", default="False")],
    )
    client = world.client(world.facilitator)
    application = world.draft(client)

    assert (
        client.patch(f"{URL}{application['id']}/", {"aadhaar_number": AADHAAR}).status_code == 409
    )


def test_the_report_counts_problems(org_a, tmp_path):
    report = load(
        org_a,
        tmp_path,
        [
            row(),
            row(serial=26, aadhaar="123456789012"),
            ["SHORT1", "M2", "", "", "True", "True", "", ""],
            ["", "M3", "", "", "True", "True", "", ""],
        ],
    )

    assert report["without_code"] == 1
    assert report["unusual_code"] == 1
    assert report["invalid_aadhaar"] == 1
    assert report["without_aadhaar"] == 2


def test_a_code_taken_outside_the_counter_is_skipped(world, org_a):
    with organization_context(org_a.id):
        LegacyMember.objects.create(tr_code=f"10{VILLAGE}010001", erp_member_code="X")

    assert world.fully_approved()["tr_code"].endswith("0002")


def test_legacy_members_stay_within_their_organization(org_a, org_b, tmp_path):
    load(org_a, tmp_path, [row()])

    with organization_context(org_b.id):
        assert LegacyMember.objects.count() == 0


def test_the_command_logs_counts_only(org_a, tmp_path, capsys):
    path = csv_file(tmp_path, [row(aadhaar=AADHAAR)])

    call_command("import_legacy_members", str(path), organization=org_a.slug)

    output = capsys.readouterr().out
    assert "members: 1" in output
    assert AADHAAR not in output
    with organization_context(org_a.id):
        assert AADHAAR not in str(AuditEvent.objects.get().metadata)
        assert Sequence.objects.filter(key=f"member_serial:09:{VILLAGE}:01").exists()


def test_an_mpp_keeps_its_own_series_and_village_number(world, org_a, tmp_path):
    load(org_a, tmp_path, [[f"09{VILLAGE}020040", "M1", "", "1305", "True", "True", "", ""]])
    with organization_context(org_a.id):
        Mpp.objects.filter(pk=world.mpp.pk).update(state_code="09", hamlet_code="02")

    assert world.fully_approved()["tr_code"] == f"09{VILLAGE}020041"


def test_two_mpps_in_a_village_count_separately(world, org_a, tmp_path):
    load(org_a, tmp_path, [row(state_code="10", serial=40)])
    with organization_context(org_a.id):
        Mpp.objects.filter(pk=world.mpp.pk).update(hamlet_code="02")

    assert world.fully_approved()["tr_code"] == f"10{VILLAGE}020001"


def test_existing_members_can_be_listed(world, org_a, tmp_path):
    with organization_context(org_a.id):
        Mpp.objects.filter(pk=world.mpp.pk).update(source_code="9013")
    load(org_a, tmp_path, [row()])

    rows = world.client(world.finance).get("/api/v1/legacy-members/").data["results"]

    assert rows[0]["full_name"] == "Old Member"
    assert rows[0]["mpp_code"] == "1305"
    assert "aadhaar" not in str(rows[0])


def test_other_mpps_members_stay_out_of_reach(world, org_a, tmp_path):
    outsider = world.member("outsider@a.test", "area_manager")
    with organization_context(org_a.id):
        Mpp.objects.filter(pk=world.mpp.pk).update(source_code="9013")
        role = Role.objects.get(code="area_manager")
        role.permissions = [*role.permissions, "members.view"]
        role.save()
    load(org_a, tmp_path, [row()])

    assert world.client(outsider).get("/api/v1/legacy-members/").data["count"] == 0


def test_a_mistyped_form_number_is_ignored(world, org_a, tmp_path):
    history = [row(serial=n, application=f"A{56000 + n:05d}") for n in range(1, 201)]
    report = load(org_a, tmp_path, [*history, row(serial=999, application="A263645")])

    assert report["form_number_typos"] == 1
    assert world.submitted()["form_number"] == "A56201"
