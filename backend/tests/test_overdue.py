from datetime import timedelta

import pytest
from django.utils import timezone

from apps.applications.models import Application
from apps.core.tenancy import organization_context

from .test_applications import URL, World

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def world(org_a):
    return World(org_a)


def submitted_days_ago(world, days):
    application = world.submitted()
    with organization_context(world.org.id):
        Application.objects.filter(pk=application["id"]).update(
            submitted_at=timezone.now() - timedelta(days=days)
        )
    return application


def row_of(world, user, application):
    rows = world.client(user).get(URL).data["results"]
    return next(row for row in rows if row["id"] == application["id"])


def test_a_form_waiting_too_long_is_late(world):
    application = submitted_days_ago(world, 3)

    row = row_of(world, world.manager, application)
    queue = world.client(world.manager).get("/api/v1/home/").data["my_queue"]

    assert row["is_overdue"] is True
    assert queue["overdue"] == 1
    assert queue["oldest_days"] == 3


def test_a_recent_form_is_not_late(world):
    application = submitted_days_ago(world, 1)

    assert row_of(world, world.manager, application)["is_overdue"] is False


def test_the_wait_restarts_at_each_stage(world):
    application = submitted_days_ago(world, 5)
    world.approve(application, world.manager)

    row = row_of(world, world.legal, application)

    assert row["status"] == "pending_cs"
    assert row["is_overdue"] is False
    assert row["waiting_since"] > row["submitted_at"]


def test_late_forms_are_counted_by_mcc(world):
    submitted_days_ago(world, 4)

    rows = (
        world.client(world.admin).get("/api/v1/home/").data.get("by_mcc")
        or world.client(world.manager).get("/api/v1/home/").data["by_mcc"]
    )

    assert rows[0]["overdue"] == 1
