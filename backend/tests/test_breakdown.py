from datetime import timedelta

import pytest
from django.utils import timezone

from apps.applications.models import Application
from apps.core.tenancy import organization_context

from .test_applications import AADHAAR, OTHER_AADHAAR, World

pytestmark = pytest.mark.django_db(transaction=True)

URL = "/api/v1/home/breakdown/"


@pytest.fixture
def world(org_a):
    return World(org_a)


def rows(world, user, **query):
    response = world.client(user).get(URL, query)
    assert response.status_code == 200, response.content
    return response.data


def test_counts_each_facilitator_for_today(world):
    world.submitted(AADHAAR)
    world.draft()

    [row] = rows(world, world.manager)

    assert row["started"] == 2
    assert row["submitted"] == 1
    assert row["pending"] == 1
    assert row["approved"] == 0


def test_counts_by_place(world):
    world.fully_approved(AADHAAR)

    [mcc] = rows(world, world.legal, by="mcc")
    [mpp] = rows(world, world.legal, by="mpp")

    assert (mcc["code"], mcc["approved"], mcc["pending"]) == ("6", 1, 0)
    assert (mpp["code"], mpp["name"]) == ("1305", "Dudwa")


def test_rejections_are_counted(world):
    application = world.submitted(AADHAAR)
    world.client(world.manager).post(
        f"/api/v1/applications/{application['id']}/decide/", {"decision": "rejected", "reason": "x"}
    )

    [row] = rows(world, world.manager)

    assert row["rejected"] == 1


def test_other_days_are_left_out(world, org_a):
    world.submitted(AADHAAR)
    world.submitted(OTHER_AADHAAR)
    week_ago = timezone.now() - timedelta(days=7)
    with organization_context(org_a.id):
        first = Application.objects.order_by("created_at").first()
        Application.objects.filter(pk=first.pk).update(created_at=week_ago, submitted_at=week_ago)

    [today] = rows(world, world.manager)
    [past] = rows(
        world, world.manager, **{"from": (timezone.localdate() - timedelta(days=7)).isoformat()}
    )

    assert today["started"] == 1
    assert past["started"] == 2


def test_facilitators_cannot_see_it(world):
    assert world.client(world.facilitator).get(URL).status_code == 403


def test_a_wrong_group_or_range_is_refused(world):
    client = world.client(world.manager)

    assert client.get(URL, {"by": "village"}).status_code == 400
    assert client.get(URL, {"from": "2026-11-02", "to": "2026-11-01"}).status_code == 400


def test_others_mpps_stay_out(world):
    world.submitted(AADHAAR)
    outsider = world.member("outsider@a.test", "area_manager")

    assert rows(world, outsider) == []


def test_each_mcc_lists_its_facilitators(world, org_a):
    world.submitted(AADHAAR)
    second = world.member("field2@a.test", "facilitator")
    second.full_name = "Second Field"
    second.save()
    from apps.hierarchy.services import assign_mpp
    from apps.organizations.models import Membership

    with organization_context(org_a.id):
        assign_mpp(
            mpp=world.other_mpp,
            membership=Membership.objects.get(user=second),
            responsibility="facilitator",
            actor=world.admin,
        )
    client = world.client(second)
    client.post("/api/v1/applications/", {"client_id": "c2", "mpp": str(world.other_mpp.id)})

    result = rows(world, world.legal, by="mcc_facilitator")

    assert sorted((row["group_code"], row["name"], row["started"]) for row in result) == sorted(
        [("6", world.facilitator.full_name or world.facilitator.email, 1), ("6", "Second Field", 1)]
    )


def test_a_facilitator_sees_their_own_totals(world):
    world.submitted(AADHAAR)
    world.draft()
    client = world.client(world.facilitator)

    summary = client.get("/api/v1/applications/summary/", {"mine": "1"}).data
    listed = client.get(
        "/api/v1/applications/", {"mine": "1", "created_from": timezone.localdate()}
    ).data

    assert (summary["started"], summary["submitted"], summary["pending"]) == (2, 1, 1)
    assert listed["count"] == 2
    assert "created_at" in listed["results"][0]


def test_a_past_range_lists_nothing_from_today(world):
    world.submitted(AADHAAR)
    yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
    client = world.client(world.facilitator)

    assert client.get("/api/v1/applications/", {"created_to": yesterday}).data["count"] == 0
    assert (
        client.get("/api/v1/applications/summary/", {"from": yesterday, "to": yesterday}).data[
            "started"
        ]
        == 0
    )
