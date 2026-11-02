from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context
from apps.hierarchy.models import Mcc, MccCover
from apps.notifications.models import Notification

from .test_applications import URL, World
from .test_teams import allot, membership

pytestmark = pytest.mark.django_db(transaction=True)

COVERS = "/api/v1/hierarchy/mcc-covers/"


@pytest.fixture
def world(org_a):
    return World(org_a)


@pytest.fixture
def team(world):
    """Sita holds the form's MCC; Ravi, in the same team, holds another."""
    with organization_context(world.org.id):
        far = Mcc.objects.create(plant=world.mpp.mcc.plant, code="99", name="Other")
    sita = world.member("sita@a.test", "cs_legal")
    ravi = world.member("ravi@a.test", "cs_legal")
    allot(world, sita, world.mpp.mcc)
    allot(world, ravi, far)
    return sita, ravi


def give(world, absent, colleague, start=0, end=2, reason="Leave", by=None):
    today = timezone.localdate()
    return world.client(by or world.admin).post(
        COVERS,
        {
            "absent": str(membership(world, absent).id),
            "colleague": str(membership(world, colleague).id),
            "starts_on": (today + timedelta(days=start)).isoformat(),
            "ends_on": (today + timedelta(days=end)).isoformat(),
            "reason": reason,
        },
    )


@pytest.fixture
def at_cs(world):
    application = world.submitted()
    world.approve(application, world.manager)
    return application


def sees(world, user, application) -> bool:
    return world.client(user).get(f"{URL}{application['id']}/").status_code == 200


def test_a_colleague_works_the_mccs_during_the_cover(world, team, at_cs):
    sita, ravi = team
    assert not sees(world, ravi, at_cs)

    response = give(world, sita, ravi, reason="Wedding leave")

    assert response.status_code == 201, response.content
    assert response.data["state"] == "active"
    assert response.data["mccs"] == ["6"]
    assert sees(world, ravi, at_cs)
    assert sees(world, sita, at_cs)
    assert world.approve(at_cs, ravi).status_code == 200
    with organization_context(world.org.id):
        told = Notification.objects.get(recipient__user=ravi, title__startswith="You cover")
        assert "Wedding leave" in told.body
        event = AuditEvent.objects.get(action="mcc.cover_given")
        assert event.metadata["reason"] == "Wedding leave"
        assert event.actor_id == world.admin.id


def test_the_cover_stops_by_itself_after_the_last_day(world, team, at_cs):
    sita, ravi = team
    give(world, sita, ravi)
    with organization_context(world.org.id):
        MccCover.objects.update(
            starts_on=timezone.localdate() - timedelta(days=5),
            ends_on=timezone.localdate() - timedelta(days=1),
        )

    assert not sees(world, ravi, at_cs)
    past = world.client(world.admin).get(COVERS, {"state": "past"}).data["results"]
    assert [row["state"] for row in past] == ["over"]


def test_an_upcoming_cover_gives_nothing_yet(world, team, at_cs):
    sita, ravi = team

    response = give(world, sita, ravi, start=1, end=3)

    assert response.data["state"] == "upcoming"
    assert not sees(world, ravi, at_cs)
    current = world.client(world.admin).get(COVERS, {"state": "current"}).data["results"]
    assert len(current) == 1


def test_end_now_stops_it_and_keeps_the_history(world, team, at_cs):
    sita, ravi = team
    cover = give(world, sita, ravi).data

    response = world.client(world.admin).post(f"{COVERS}{cover['id']}/end/")

    assert response.status_code == 204
    assert not sees(world, ravi, at_cs)
    assert world.client(world.admin).post(f"{COVERS}{cover['id']}/end/").status_code == 404
    past = world.client(world.admin).get(COVERS, {"state": "past"}).data["results"]
    assert past[0]["state"] == "ended"
    assert past[0]["ended_by_name"] == world.admin.email
    with organization_context(world.org.id):
        assert AuditEvent.objects.filter(action="mcc.cover_ended").count() == 1


def test_a_covering_area_manager_is_told_about_new_forms(world, team):
    away = world.member("am2@a.test", "area_manager")
    cover_am = world.member("am3@a.test", "area_manager")
    allot(world, away, world.mpp.mcc)
    assert give(world, away, cover_am).status_code == 201

    world.submitted()

    with organization_context(world.org.id):
        told = set(
            Notification.objects.filter(title__startswith="Application waiting").values_list(
                "recipient__user__email", flat=True
            )
        )
    assert {"am2@a.test", "am3@a.test"} <= told


@pytest.mark.parametrize(
    ("case", "problem"),
    [
        ("self", "someone other"),
        ("no_mccs", "holds no MCCs"),
        ("wrong_role", "cannot approve"),
        ("past", "already over"),
        ("backwards", "on or after"),
    ],
)
def test_a_cover_that_cannot_work_is_refused(world, team, case, problem):
    sita, ravi = team
    response = {
        "self": lambda: give(world, sita, sita),
        "no_mccs": lambda: give(world, world.legal, ravi),
        "wrong_role": lambda: give(world, sita, world.finance),
        "past": lambda: give(world, sita, ravi, start=-3, end=-1),
        "backwards": lambda: give(world, sita, ravi, start=2, end=1),
    }[case]()

    assert response.status_code == 400
    assert problem in str(response.data)


def test_the_same_pair_cannot_overlap(world, team):
    sita, ravi = team
    give(world, sita, ravi, end=3)

    assert give(world, sita, ravi, start=2, end=5).status_code == 400
    assert give(world, sita, ravi, start=4, end=5).status_code == 201


def test_giving_cover_needs_the_permission(world, team):
    sita, ravi = team

    assert give(world, sita, ravi, by=world.manager).status_code == 403
