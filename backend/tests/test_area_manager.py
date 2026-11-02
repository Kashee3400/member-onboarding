import pytest

from apps.applications.models import Application
from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context
from apps.hierarchy.models import Bmc, Mcc, Mpp, Route
from apps.hierarchy.services import end_assignments_for
from apps.notifications.models import Notification
from apps.organizations.models import Membership

from .test_applications import AADHAAR, ACCOUNT, URL, World

pytestmark = pytest.mark.django_db(transaction=True)

MCC_URL = "/api/v1/hierarchy/mccs/"


@pytest.fixture
def world(org_a):
    return World(org_a)


@pytest.fixture
def regional(world):
    """An Area Manager with no MPP of their own."""
    return world.member("regional@a.test", "area_manager")


def membership(world, user):
    with organization_context(world.org.id):
        return Membership.objects.get(user=user)


def assign(world, user):
    with organization_context(world.org.id):
        mcc = world.mpp.mcc
    response = world.client(world.admin).post(
        f"{MCC_URL}{mcc.id}/area-manager/", {"membership": str(membership(world, user).id)}
    )
    assert response.status_code == 201, response.content
    return mcc


def test_the_area_manager_of_an_mcc_reaches_all_its_mpps(world, regional):
    before = world.client(regional).get("/api/v1/hierarchy/mpps/").data["count"]
    assign(world, regional)

    assert before == 0
    assert world.client(regional).get("/api/v1/hierarchy/mpps/").data["count"] == 2


def test_they_can_decide_forms_from_any_mpp_under_it(world, regional):
    assign(world, regional)
    application = world.submitted()

    response = world.client(regional).post(
        f"{URL}{application['id']}/decide/", {"decision": "approved"}
    )

    assert response.status_code == 200


def test_they_are_told_about_new_forms(world, regional):
    assign(world, regional)
    world.submitted()

    with organization_context(world.org.id):
        assert Notification.objects.filter(recipient__user=regional).count() == 1


def test_an_mpp_moved_to_another_mcc_moves_out_of_reach(world, regional):
    mcc = assign(world, regional)
    with organization_context(world.org.id):
        other = Mcc.objects.create(plant=mcc.plant, code="99", name="Other")
        Mpp.objects.filter(pk=world.mpp.pk).update(mcc=other)

    assert world.client(regional).get("/api/v1/hierarchy/mpps/").data["count"] == 1


def test_an_mcc_can_have_several_area_managers(world, regional):
    assign(world, regional)
    second = world.member("second@a.test", "area_manager")
    assign(world, second)

    assert world.client(regional).get("/api/v1/hierarchy/mpps/").data["count"] == 2
    assert world.client(second).get("/api/v1/hierarchy/mpps/").data["count"] == 2


def test_each_of_them_is_told_about_new_forms(world, regional):
    assign(world, regional)
    second = world.member("second@a.test", "area_manager")
    assign(world, second)
    world.submitted()

    with organization_context(world.org.id):
        assert Notification.objects.filter(recipient__user__in=[regional, second]).count() == 2


def test_one_person_can_hold_several_mccs(world, regional):
    mcc = assign(world, regional)
    with organization_context(world.org.id):
        other = Mcc.objects.create(plant=mcc.plant, code="99", name="Other")
        Mpp.objects.create(mcc=other, code="9999", name="Far", village_code="00999999")
    response = world.client(world.admin).post(
        f"{MCC_URL}{other.id}/area-manager/", {"membership": str(membership(world, regional).id)}
    )

    assert response.status_code == 201
    assert world.client(regional).get("/api/v1/hierarchy/mpps/").data["count"] == 3


def test_assigning_twice_changes_nothing(world, regional):
    mcc = assign(world, regional)
    assign(world, regional)

    assert len(world.client(world.admin).get(f"{MCC_URL}{mcc.id}/area-manager/").data) == 1


def test_only_someone_who_approves_can_hold_an_mcc(world):
    with organization_context(world.org.id):
        mcc = world.mpp.mcc
    response = world.client(world.admin).post(
        f"{MCC_URL}{mcc.id}/area-manager/",
        {"membership": str(membership(world, world.facilitator).id)},
    )

    assert response.status_code == 400


def test_assigning_needs_the_permission(world, regional):
    with organization_context(world.org.id):
        mcc = world.mpp.mcc
    response = world.client(regional).post(
        f"{MCC_URL}{mcc.id}/area-manager/", {"membership": str(membership(world, regional).id)}
    )

    assert response.status_code == 403


def test_ending_removes_access_and_keeps_history(world, regional):
    mcc = assign(world, regional)
    client = world.client(world.admin)
    url = f"{MCC_URL}{mcc.id}/area-manager/{membership(world, regional).id}/end/"

    assert client.post(url).status_code == 204
    assert client.post(url).status_code == 404
    assert world.client(regional).get("/api/v1/hierarchy/mpps/").data["count"] == 0
    history = client.get(f"{MCC_URL}{mcc.id}/area-manager/").data
    assert history[0]["ended_at"] is not None


def test_a_person_leaving_frees_their_mcc(world, regional):
    mcc = assign(world, regional)
    with organization_context(world.org.id):
        end_assignments_for(membership(world, regional), actor=world.admin)

    row = world.client(world.admin).get(f"{MCC_URL}{mcc.id}/").data
    assert row["allotted"] == []


def test_the_list_shows_counts_and_holder(world, regional):
    regional.full_name = "Regional Person"
    regional.save()
    mcc = assign(world, regional)

    row = world.client(world.admin).get(f"{MCC_URL}{mcc.id}/").data

    assert row["mpp_count"] == 2
    assert row["allotted"] == [{"name": "Regional Person", "roles": ["Area Manager"]}]


def test_the_area_manager_sees_the_full_numbers(world):
    application = world.submitted()

    response = world.client(world.manager).post(f"{URL}{application['id']}/numbers/")

    assert response.status_code == 200
    assert response.data == {"aadhaar_number": AADHAAR, "account_number": ACCOUNT}
    assert response.headers["Cache-Control"] == "no-store"


def test_others_do_not(world):
    application = world.submitted()

    assert (
        world.client(world.facilitator).post(f"{URL}{application['id']}/numbers/").status_code
        == 403
    )
    # The organization admin acts on every step, so checks numbers like an approver.
    assert world.client(world.admin).post(f"{URL}{application['id']}/numbers/").status_code == 200


def test_an_area_manager_of_another_mcc_does_not(world):
    application = world.submitted()
    outsider = world.member("outsider@a.test", "area_manager")

    assert world.client(outsider).post(f"{URL}{application['id']}/numbers/").status_code == 404


def test_every_look_is_logged_without_the_numbers(world):
    application = world.submitted()
    world.client(world.manager).post(f"{URL}{application['id']}/numbers/")

    with organization_context(world.org.id):
        event = AuditEvent.objects.get(action="application.numbers_viewed")
        assert Application.objects.filter(pk=event.target_id).exists()
    assert event.actor_id == world.manager.pk
    assert AADHAAR not in str(event.metadata)


def test_the_form_itself_still_carries_only_the_last_digits(world):
    application = world.submitted()

    detail = world.client(world.manager).get(f"{URL}{application['id']}/")

    assert AADHAAR not in str(detail.data)
    assert detail.data["aadhaar_last4"] == AADHAAR[-4:]


def test_an_mpp_cannot_take_a_route_of_another_mcc(world):
    with organization_context(world.org.id):
        plant = world.mpp.mcc.plant
        other = Mcc.objects.create(plant=plant, code="99", name="Other")
        bmc = Bmc.objects.create(mcc=other, code="B", name="Cooler")
        route = Route.objects.create(bmc=bmc, code="R", name="Route")

    response = world.client(world.admin).patch(
        f"/api/v1/hierarchy/mpps/{world.mpp.id}/", {"route": str(route.id)}
    )

    assert response.status_code == 400
    assert "route" in response.data["error"]["details"]


def test_routes_can_be_listed_by_mcc(world):
    with organization_context(world.org.id):
        mcc = world.mpp.mcc
        bmc = Bmc.objects.create(mcc=mcc, code="B", name="Cooler")
        Route.objects.create(bmc=bmc, code="R", name="Route")

    rows = world.client(world.admin).get(f"/api/v1/hierarchy/routes/?bmc__mcc={mcc.id}").data

    assert rows["count"] == 1
    assert str(rows["results"][0]["mcc"]) == str(mcc.id)
