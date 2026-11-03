import pytest

from apps.applications.models import ApplicationStepApproval
from apps.applications.review_checks import DEFAULT_CHECKS
from apps.applications.review_steps import STEP_KEYS
from apps.core.tenancy import organization_context
from apps.documents.services import set_staff_signature
from apps.organizations.models import Membership

from .conftest import authenticated_client
from .test_applications import URL, World, png_bytes

pytestmark = pytest.mark.django_db(transaction=True)

SETTINGS_URL = "/api/v1/settings/review/"
MILK = ["Cows counted", "Milk figure is realistic"]


@pytest.fixture
def world(org_a, settings):
    settings.SEED_REVIEW_CHECKS = True
    return World(org_a)


@pytest.fixture
def application(world):
    return world.submitted()


def save_checks(world, checks):
    return world.client(world.admin).put(
        SETTINGS_URL,
        {"overdue_days": 2, "reject_reasons": [], "checks": checks},
        format="json",
    )


def steps(world, user, application):
    data = world.client(user).get(f"{URL}{application['id']}/").data
    return {step["key"]: step for step in data["review_steps"]}


def tick(world, user, application, step, text, ticked=True):
    return world.client(user).post(
        f"{URL}{application['id']}/checks/",
        {"step": step, "text": text, "ticked": ticked},
        format="json",
    )


def approve(world, user, application, step):
    return world.client(user).post(
        f"{URL}{application['id']}/decide/",
        {"decision": "approved", "steps": [step]},
        format="json",
    )


def test_every_step_starts_with_a_few_checks(world):
    checks = world.client(world.admin).get(SETTINGS_URL).data["checks"]

    assert checks == {key: list(texts) for key, texts in DEFAULT_CHECKS.items()}
    assert set(checks) == set(STEP_KEYS)
    assert all(2 <= len(texts) <= 4 for texts in checks.values())


def test_saved_checklists_replace_the_old_ones(world):
    response = save_checks(world, {"milk": MILK, "bank": []})

    assert response.status_code == 200, response.content
    assert response.data["checks"]["milk"] == MILK
    # Emptied or left out: no checklist, and the defaults never come back.
    assert all(not texts for key, texts in response.data["checks"].items() if key != "milk")
    assert world.client(world.admin).get(SETTINGS_URL).data["checks"]["bank"] == []


def test_saving_without_checks_keeps_them(world):
    save_checks(world, {"milk": MILK})

    response = world.client(world.admin).put(
        SETTINGS_URL, {"overdue_days": 3, "reject_reasons": []}, format="json"
    )

    assert response.status_code == 200
    assert response.data["checks"]["milk"] == MILK


@pytest.mark.parametrize(
    "checks",
    [
        {"kitchen": ["Clean"]},
        {"milk": ["Same", "same"]},
        {"milk": [""]},
        {"milk": ["x" * 201]},
        {"milk": [f"Check {n}" for n in range(11)]},
    ],
)
def test_checklists_must_make_sense(world, checks):
    assert save_checks(world, checks).status_code == 400


def test_a_step_waits_for_every_check(world, application):
    save_checks(world, {"milk": MILK})

    refused = approve(world, world.manager, application, "milk")
    assert refused.status_code == 400
    assert "Milk Production" in str(refused.data)

    assert tick(world, world.manager, application, "milk", MILK[0]).data["ticked"] == [MILK[0]]
    assert approve(world, world.manager, application, "milk").status_code == 400

    assert tick(world, world.manager, application, "milk", MILK[1]).data["ticked"] == MILK
    assert approve(world, world.manager, application, "milk").status_code == 200


def test_the_approval_keeps_what_was_checked(world, application, org_a):
    save_checks(world, {"milk": MILK})
    for text in MILK:
        tick(world, world.manager, application, "milk", text)
    approve(world, world.manager, application, "milk")

    # Rewording the checklist later does not change what was checked.
    save_checks(world, {"milk": ["Something new"]})

    step = steps(world, world.legal, application)["milk"]
    assert step["approved_checks"] == MILK
    with organization_context(org_a.id):
        assert ApplicationStepApproval.objects.get(step="milk").checks == MILK


def test_ticks_are_kept_per_person(world, application):
    save_checks(world, {"milk": MILK})
    tick(world, world.manager, application, "milk", MILK[0])

    assert steps(world, world.manager, application)["milk"]["ticked"] == [MILK[0]]
    assert steps(world, world.admin, application)["milk"]["ticked"] == []
    assert steps(world, world.admin, application)["milk"]["checks"] == MILK


def test_a_tick_can_be_taken_back(world, application):
    save_checks(world, {"milk": MILK})
    for text in MILK:
        tick(world, world.manager, application, "milk", text)

    assert tick(world, world.manager, application, "milk", MILK[0], False).data["ticked"] == [
        MILK[1]
    ]
    assert approve(world, world.manager, application, "milk").status_code == 400


def test_a_reworded_check_is_ticked_again(world, application):
    save_checks(world, {"milk": MILK})
    for text in MILK:
        tick(world, world.manager, application, "milk", text)

    save_checks(world, {"milk": [MILK[0], "Milk figure looks right"]})

    assert steps(world, world.manager, application)["milk"]["ticked"] == [MILK[0]]
    assert approve(world, world.manager, application, "milk").status_code == 400


def test_only_open_steps_of_ones_own_can_be_ticked(world, application):
    save_checks(world, {"milk": MILK, "bank": ["Passbook matches"]})

    assert tick(world, world.legal, application, "milk", MILK[0]).status_code == 409
    # Finance acts later, at its own stage.
    assert tick(world, world.finance, application, "bank", "Passbook matches").status_code == 409
    assert tick(world, world.manager, application, "milk", "Not on the list").status_code == 400


def test_a_step_without_a_checklist_approves_as_before(world, application):
    save_checks(world, {})

    assert approve(world, world.manager, application, "milk").status_code == 200
    assert steps(world, world.legal, application)["milk"]["approved_checks"] == []


def test_the_admin_ticks_too(world, application, org_a):
    with organization_context(org_a.id):
        set_staff_signature(
            Membership.objects.get(user=world.admin), raw=png_bytes(), actor=world.admin
        )
    save_checks(world, {"member": ["Aadhaar matches"]})

    assert approve(world, world.admin, application, "member").status_code == 400
    tick(world, world.admin, application, "member", "Aadhaar matches")
    assert approve(world, world.admin, application, "member").status_code == 200


def test_a_resubmitted_form_is_checked_from_the_start(world, application):
    save_checks(world, {"milk": MILK})
    tick(world, world.manager, application, "milk", MILK[0])
    world.client(world.manager).post(
        f"{URL}{application['id']}/decide/", {"decision": "rejected", "reason": "Fix it"}
    )
    world.client(world.facilitator).post(f"{URL}{application['id']}/submit/")

    assert steps(world, world.manager, application)["milk"]["ticked"] == []


def test_each_organization_has_its_own_checklists(world, org_b, admin_b):
    save_checks(world, {"milk": MILK})

    data = authenticated_client(org_b, admin_b).get(SETTINGS_URL).data

    assert data["checks"]["milk"] == list(DEFAULT_CHECKS["milk"])


def test_a_withdrawn_step_must_be_checked_again(world, application):
    for text in DEFAULT_CHECKS["milk"]:
        tick(world, world.manager, application, "milk", text)
    assert approve(world, world.manager, application, "milk").status_code == 200

    withdrawn = world.client(world.manager).post(
        f"{URL}{application['id']}/steps/milk/withdraw/", format="json"
    )

    assert withdrawn.status_code == 200, withdrawn.content
    assert steps(world, world.manager, application)["milk"]["ticked"] == []
    assert approve(world, world.manager, application, "milk").status_code == 400
