from datetime import timedelta

import pytest
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from apps.applications.models import Application
from apps.core.tenancy import organization_context
from apps.notifications.models import MorningSummary, Notification
from apps.notifications.summary import send_morning_summaries

from .test_applications import OTHER_AADHAAR, World

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def world(org_a):
    return World(org_a)


def summaries(world):
    with organization_context(world.org.id):
        return dict(
            Notification.objects.filter(title__contains=" for you").values_list(
                "recipient__user__email", "title"
            )
        )


def test_each_approver_hears_about_their_own_queue(world):
    world.submitted()

    assert send_morning_summaries() == 1

    # Only the Area Manager has a form waiting; CS and Finance hear nothing.
    assert summaries(world) == {"am@a.test": "1 form waits for you"}


def test_late_forms_are_called_out(world):
    late = world.submitted()
    world.submitted(OTHER_AADHAAR)
    with organization_context(world.org.id):
        Application.objects.filter(pk=late["id"]).update(
            submitted_at=timezone.now() - timedelta(days=3)
        )

    send_morning_summaries()

    assert summaries(world)["am@a.test"] == "2 forms wait for you, 1 of them over 2 days"


def test_a_second_run_the_same_day_sends_nothing(world, capsys):
    world.submitted()
    send_morning_summaries()

    call_command("send_morning_summary")

    assert "Sent 0" in capsys.readouterr().out
    with organization_context(world.org.id):
        assert Notification.objects.filter(title__contains=" for you").count() == 1
        assert MorningSummary.objects.get().waiting == 1


def test_the_next_day_sends_again(world):
    world.submitted()
    send_morning_summaries()

    assert send_morning_summaries(timezone.localdate() + timedelta(days=1)) == 1


def test_someone_can_turn_it_off(world):
    world.submitted()
    client = world.client(world.manager)
    assert client.get("/api/v1/notifications/preferences/").data == {"morning_summary": True}

    response = client.patch("/api/v1/notifications/preferences/", {"morning_summary": False})

    assert response.status_code == 200
    assert send_morning_summaries() == 0
    assert client.get("/api/v1/notifications/preferences/").data == {"morning_summary": False}


def test_beat_runs_it_every_morning():
    schedule = settings.CELERY_BEAT_SCHEDULE["morning-summary"]

    assert schedule["task"] == "apps.notifications.tasks.send_morning_summary"
    assert schedule["schedule"].hour == {9} and schedule["schedule"].minute == {0}
