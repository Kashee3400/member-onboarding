import pytest

from apps.applications.models import ApplicationDecision, Signatory, Status
from apps.core.tenancy import organization_context
from apps.hierarchy.models import Mcc, Mpp
from apps.notifications.models import Notification
from apps.organizations.models import Membership

from .test_applications import URL, World

pytestmark = pytest.mark.django_db(transaction=True)

MCC_URL = "/api/v1/hierarchy/mccs/"


@pytest.fixture
def world(org_a):
    return World(org_a)


def membership(world, user):
    with organization_context(world.org.id):
        return Membership.objects.get(user=user)


def allot(world, user, mcc):
    response = world.client(world.admin).post(
        f"{MCC_URL}{mcc.id}/area-manager/", {"membership": str(membership(world, user).id)}
    )
    assert response.status_code == 201, response.content


@pytest.fixture
def other_mcc(world):
    with organization_context(world.org.id):
        plant = world.mpp.mcc.plant
        mcc = Mcc.objects.create(plant=plant, code="99", name="Other")
        Mpp.objects.create(mcc=mcc, code="9999", name="Far", village_code="00999999")
    return mcc


def test_a_cs_team_member_sees_only_their_mcc(world, other_mcc):
    junior = world.member("cs2@a.test", "cs_legal")
    allot(world, junior, other_mcc)
    application = world.submitted()
    world.approve(application, world.manager)

    assert world.client(junior).get(f"{URL}{application['id']}/").status_code == 404
    assert world.client(world.legal).get(f"{URL}{application['id']}/").status_code == 200


def test_a_team_member_approves_their_mcc_and_the_head_signs(world):
    junior = world.member("cs2@a.test", "cs_legal")
    junior.full_name = "Junior Clerk"
    junior.save()
    world.legal.full_name = "Head Of Legal"
    world.legal.save()
    with organization_context(world.org.id):
        mcc = world.mpp.mcc
    allot(world, junior, mcc)
    application = world.submitted()
    world.approve(application, world.manager)

    response = world.approve(application, junior)

    assert response.status_code == 200
    with organization_context(world.org.id):
        decision = ApplicationDecision.objects.get(stage=Status.PENDING_CS)
        head = Membership.objects.get(user=world.legal)
        assert decision.decided_by == junior
        assert decision.signed_by_name == "Head Of Legal"
        assert decision.signature.membership == head


def test_a_stage_needs_its_signatory(world):
    with organization_context(world.org.id):
        Signatory.objects.filter(stage=Status.PENDING_CS).delete()
    application = world.submitted()
    world.approve(application, world.manager)

    response = world.approve(application, world.legal)

    assert response.status_code == 409


def test_only_the_teams_people_for_that_mcc_are_told(world, other_mcc):
    junior = world.member("cs2@a.test", "cs_legal")
    allot(world, junior, other_mcc)
    application = world.submitted()
    world.approve(application, world.manager)

    with organization_context(world.org.id):
        told = set(
            Notification.objects.filter(title__startswith="Application waiting").values_list(
                "recipient__user__email", flat=True
            )
        )
    assert "cs@a.test" in told
    assert "cs2@a.test" not in told


def test_signatories_are_chosen_among_signers(world):
    client = world.client(world.admin)
    state = client.get("/api/v1/settings/signatories/").data
    cs = next(item for item in state["stages"] if item["stage"] == "pending_cs")

    assert cs["membership"] == membership(world, world.legal).id
    bad = client.put(
        "/api/v1/settings/signatories/",
        {"pending_cs": str(membership(world, world.finance).id)},
        format="json",
    )
    assert bad.status_code == 400


def test_home_shows_each_role_its_own_blocks(world):
    application = world.submitted()

    manager = world.client(world.manager).get("/api/v1/home/").data
    facilitator = world.client(world.facilitator).get("/api/v1/home/").data
    admin = world.client(world.admin).get("/api/v1/home/").data
    finance = world.client(world.finance).get("/api/v1/home/").data

    assert manager["my_queue"]["waiting"] == 1
    assert "setup" not in manager
    assert "my_queue" not in facilitator and "mine" in facilitator
    assert admin["setup"]["signatories_missing"] == 0
    assert "fee" in finance and finance["my_queue"]["waiting"] == 0
    assert len(manager["trend"]) == 14
    world.approve(application, world.manager)
    assert world.client(world.legal).get("/api/v1/home/").data["my_queue"]["waiting"] == 1
