import pytest
from django.db import IntegrityError, transaction

from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context
from apps.hierarchy.models import Mcc, Mpp, MppAssignment, Plant
from apps.organizations.models import Membership

from .conftest import authenticated_client, make_member

pytestmark = pytest.mark.django_db(transaction=True)

MPPS_URL = "/api/v1/hierarchy/mpps/"
STAFF_URL = "/api/v1/staff/"


@pytest.fixture
def mpps(org_a):
    with organization_context(org_a.id):
        plant = Plant.objects.create(code="P1", name="Plant")
        mcc = Mcc.objects.create(plant=plant, code="6", name="Bhadohi")
        return [
            Mpp.objects.create(mcc=mcc, code="1305", name="One", village_code="00209982"),
            Mpp.objects.create(mcc=mcc, code="1152", name="Two", village_code="00211673"),
        ]


@pytest.fixture
def admin(org_a, admin_a):
    return authenticated_client(org_a, admin_a)


def membership_of(org, user):
    with organization_context(org.id):
        return str(Membership.objects.get(user=user).id)


def assign(admin, mpp, org, user, responsibility="facilitator"):
    return admin.post(
        f"{MPPS_URL}{mpp.id}/assignments/",
        {"membership": membership_of(org, user), "responsibility": responsibility},
    )


def visible_codes(client):
    return sorted(item["code"] for item in client.get(MPPS_URL).data["results"])


def test_a_facilitator_sees_only_assigned_mpps(org_a, admin, staff_a, mpps):
    assert assign(admin, mpps[0], org_a, staff_a).status_code == 201

    client = authenticated_client(org_a, staff_a)

    assert visible_codes(client) == ["1305"]
    assert client.get(f"{MPPS_URL}{mpps[1].id}/").status_code == 404


def test_one_facilitator_can_hold_many_mpps(org_a, admin, staff_a, mpps):
    assign(admin, mpps[0], org_a, staff_a)
    assign(admin, mpps[1], org_a, staff_a)

    assert visible_codes(authenticated_client(org_a, staff_a)) == ["1152", "1305"]


def test_roles_with_org_wide_access_see_every_mpp(org_a, mpps):
    finance = make_member(org_a, "finance@a.test", "finance")
    assert visible_codes(authenticated_client(org_a, finance)) == ["1152", "1305"]


def test_transfer_moves_access_at_once_and_keeps_history(org_a, admin, staff_a, mpps):
    replacement = make_member(org_a, "next@a.test", "facilitator")
    leaver_client = authenticated_client(org_a, staff_a)
    replacement_client = authenticated_client(org_a, replacement)

    assign(admin, mpps[0], org_a, staff_a)
    assert visible_codes(leaver_client) == ["1305"]

    assert assign(admin, mpps[0], org_a, replacement).status_code == 201

    assert visible_codes(leaver_client) == []
    assert visible_codes(replacement_client) == ["1305"]

    history = admin.get(f"{MPPS_URL}{mpps[0].id}/assignments/").data
    assert [item["person"] for item in history] == [replacement.email, staff_a.email]
    assert history[0]["ended_at"] is None
    assert history[1]["ended_at"] is not None


def test_transfers_are_audited_with_both_people(org_a, admin, staff_a, mpps):
    replacement = make_member(org_a, "next@a.test", "facilitator")
    assign(admin, mpps[0], org_a, staff_a)
    assign(admin, mpps[0], org_a, replacement)

    with organization_context(org_a.id):
        event = AuditEvent.objects.filter(action="mpp.assigned").order_by("-occurred_at").first()
    assert event.metadata["from_membership"] == membership_of(org_a, staff_a)
    assert event.metadata["to_membership"] == membership_of(org_a, replacement)


def test_assigning_the_same_person_again_changes_nothing(org_a, admin, staff_a, mpps):
    first = assign(admin, mpps[0], org_a, staff_a)
    second = assign(admin, mpps[0], org_a, staff_a)

    assert first.data["id"] == second.data["id"]


def test_an_mpp_has_one_facilitator_and_one_am_at_a_time(org_a, admin, staff_a, mpps):
    manager = make_member(org_a, "am@a.test", "area_manager")

    assert assign(admin, mpps[0], org_a, staff_a).status_code == 201
    assert assign(admin, mpps[0], org_a, manager, "area_manager").status_code == 201

    assert len(admin.get(f"{MPPS_URL}{mpps[0].id}/assignments/").data) == 2


def test_the_database_refuses_two_active_facilitators(org_a, admin, admin_a, staff_a, mpps):
    assign(admin, mpps[0], org_a, staff_a)

    with organization_context(org_a.id):
        membership = Membership.objects.get(user=admin_a)
        with pytest.raises(IntegrityError), transaction.atomic():
            MppAssignment.objects.create(
                mpp=mpps[0],
                membership=membership,
                responsibility="facilitator",
                assigned_by=admin_a,
            )


def test_the_role_must_allow_the_responsibility(org_a, admin, mpps):
    pib = make_member(org_a, "pib@a.test", "pib")
    assert assign(admin, mpps[0], org_a, pib).status_code == 400


def test_only_mpp_assigners_can_assign(org_a, staff_a, mpps):
    client = authenticated_client(org_a, staff_a)
    assert assign(client, mpps[0], org_a, staff_a).status_code == 403


def test_ending_an_assignment_removes_access(org_a, admin, staff_a, mpps):
    assign(admin, mpps[0], org_a, staff_a)

    url = f"{MPPS_URL}{mpps[0].id}/assignments/facilitator/"
    assert admin.delete(url).status_code == 204
    assert admin.delete(url).status_code == 404

    assert visible_codes(authenticated_client(org_a, staff_a)) == []


def test_deactivating_staff_frees_their_mpps(org_a, admin, staff_a, mpps):
    assign(admin, mpps[0], org_a, staff_a)

    response = admin.patch(f"{STAFF_URL}{membership_of(org_a, staff_a)}/", {"is_active": False})

    assert response.status_code == 200
    history = admin.get(f"{MPPS_URL}{mpps[0].id}/assignments/").data
    assert history[0]["ended_at"] is not None


def test_mpps_of_another_organization_are_not_reachable(org_a, org_b, admin, admin_b, mpps):
    other = authenticated_client(org_b, admin_b)

    assert visible_codes(other) == []
    assert other.get(f"{MPPS_URL}{mpps[0].id}/").status_code == 404
    assert other.get(f"{MPPS_URL}{mpps[0].id}/assignments/").status_code == 404


def test_masters_reject_duplicates(org_a, admin, mpps):
    payload = {"mcc": str(mpps[0].mcc_id), "code": "1305", "name": "X", "village_code": "00000001"}
    assert admin.post(MPPS_URL, payload).status_code == 400

    payload |= {"code": "9999", "village_code": "00209982"}
    assert admin.post(MPPS_URL, payload).status_code == 400


def test_village_codes_must_be_eight_digits(org_a, admin, mpps):
    payload = {"mcc": str(mpps[0].mcc_id), "code": "9999", "name": "X", "village_code": "123"}
    assert admin.post(MPPS_URL, payload).status_code == 400


def test_masters_can_be_created_and_listed(admin):
    plant = admin.post("/api/v1/hierarchy/plants/", {"code": "P2", "name": "Plant 2"})
    assert plant.status_code == 201

    mcc = admin.post(
        "/api/v1/hierarchy/mccs/", {"plant": plant.data["id"], "code": "7", "name": "MCC 7"}
    )
    assert mcc.status_code == 201

    listed = admin.get("/api/v1/hierarchy/mccs/", {"plant": plant.data["id"]})
    assert [item["code"] for item in listed.data["results"]] == ["7"]
