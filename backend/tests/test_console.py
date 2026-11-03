from datetime import timedelta

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.mfa import issue_tokens
from apps.applications.models import Application, Status
from apps.applications.services import printed_form
from apps.console import quotas
from apps.console.throttling import OrganizationRateThrottle
from apps.core.tenancy import organization_context
from apps.notifications.failures import record_failure
from apps.notifications.models import DeliveryFailure
from apps.organizations.models import Membership, Organization
from apps.rbac.models import MembershipRole
from apps.rbac.navigation import locked_paths, navigation_for

from .conftest import make_member
from .test_applications import OTHER_AADHAAR, URL, World, jpeg_bytes

pytestmark = pytest.mark.django_db(transaction=True)

ORGANIZATIONS = "/api/v1/console/organizations/"
ME = "/api/v1/auth/me/"


def operator_client(organization, user, *, mfa=True):
    user.is_superuser = True
    user.save()
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {issue_tokens(user, organization, mfa=mfa)['access']}"
    )
    return client


@pytest.fixture
def world(org_a):
    return World(org_a)


def new_org(client, **overrides):
    body = {
        "name": "Paayas Milk",
        "slug": "paayas",
        "admin_name": "Paayas Admin",
        "admin_email": "admin@paayasmilk.com",
        "email_domain": "paayasmilk.com",
    } | overrides
    return client.post(ORGANIZATIONS, body, format="json")


def test_an_operator_creates_an_organization_with_its_first_admin(world):
    response = new_org(operator_client(world.org, world.admin))

    assert response.status_code == 201, response.content
    assert "accept-invite?organization=paayas" in response.data["invitation_link"]
    organization = Organization.objects.get(slug="paayas")
    with organization_context(organization.id):
        admin = Membership.objects.get(user__email="admin@paayasmilk.com")
        assert list(
            MembershipRole.objects.filter(membership=admin).values_list("role__code", flat=True)
        ) == ["org_admin"]
    setup = response.data["organization"]["health"]["setup"]
    assert setup["email_domain"] is True
    assert setup["mpps"] == 0


def test_a_new_organization_admin_must_use_its_domain(world):
    response = new_org(operator_client(world.org, world.admin), admin_email="admin@gmail.com")

    assert response.status_code == 400
    assert not Organization.objects.filter(slug="paayas").exists()


def test_a_taken_short_name_is_refused(world):
    assert new_org(operator_client(world.org, world.admin), slug="org-a").status_code == 400


def test_someone_already_working_elsewhere_needs_no_invitation(world):
    response = new_org(
        operator_client(world.org, world.admin), admin_email="admin@a.test", email_domain=""
    )

    assert response.status_code == 201
    assert response.data["invitation_link"] is None


def test_health_counts_each_organizations_own_work(world, org_b):
    world.fully_approved()
    world.submitted(OTHER_AADHAAR)
    make_member(org_b, "someone@b.test", "org_admin")
    with organization_context(org_b.id):
        record_failure("sms", "The SMS gateway could not be reached.")

    rows = {
        row["slug"]: row for row in operator_client(world.org, world.admin).get(ORGANIZATIONS).data
    }

    assert rows["org-a"]["health"]["forms_total"] == 2
    assert rows["org-a"]["health"]["members"] == 1
    assert rows["org-a"]["health"]["pending"] == 1
    assert rows["org-b"]["health"]["forms_total"] == 0
    assert rows["org-b"]["health"]["failures_this_week"] == {"mail": 0, "sms": 1, "push": 0}
    assert rows["org-a"]["health"]["failures_this_week"]["sms"] == 0


def test_an_operator_switches_an_organization_off_but_not_their_own(world, org_b):
    client = operator_client(world.org, world.admin)

    assert (
        client.patch(f"{ORGANIZATIONS}{org_b.id}/", {"is_active": False}, format="json").status_code
        == 200
    )
    assert Organization.objects.get(pk=org_b.id).is_active is False
    own = client.patch(f"{ORGANIZATIONS}{world.org.id}/", {"is_active": False}, format="json")
    assert own.status_code == 400


def test_only_operators_with_mfa_reach_the_console(world):
    org_admin = APIClient()
    org_admin.credentials(
        HTTP_AUTHORIZATION=f"Bearer {issue_tokens(world.admin, world.org, mfa=True)['access']}"
    )
    assert org_admin.get(ORGANIZATIONS).status_code == 403
    # An Area Manager may sign in without MFA, so only the console's own check stops them.
    assert (
        operator_client(world.org, world.manager, mfa=False).get(ORGANIZATIONS).status_code == 403
    )


def test_no_role_permission_opens_the_console():
    from apps.rbac.catalog import PERMISSIONS

    keys = [node["key"] for node in navigation_for(set(PERMISSIONS))]
    assert "console" not in keys
    assert "/console" in locked_paths(set(PERMISSIONS))
    assert "console" in [node["key"] for node in navigation_for(set(), operator=True)]
    assert "/console" not in locked_paths(set(), operator=True)


def test_the_command_makes_and_removes_an_operator(world):
    call_command("make_platform_operator", "admin@a.test")
    world.admin.refresh_from_db()
    assert world.admin.is_superuser

    call_command("make_platform_operator", "admin@a.test", "--remove")
    world.admin.refresh_from_db()
    assert not world.admin.is_superuser


def test_a_failure_outside_an_organization_is_not_recorded(db):
    record_failure("mail", "x")

    assert DeliveryFailure.objects.count() == 0


def test_a_pending_form_waiting_too_long_is_late(world):
    world.submitted()
    with organization_context(world.org.id):
        Application.objects.filter(status=Status.PENDING_AM).update(
            updated_at=timezone.now() - timedelta(days=30)
        )

    rows = operator_client(world.org, world.admin).get(ORGANIZATIONS).data

    assert rows[0]["health"]["late"] == 1


# Fair shares ---------------------------------------------------------------------------


def over_the_limit(organization, limit_mb=1):
    """However much the test photos weighed, the organization is now past its limit."""
    Organization.objects.filter(pk=organization.id).update(storage_limit_mb=limit_mb)
    cache.set(f"console:storage:{organization.id}", (limit_mb + 1) * quotas.MB, 600)


def test_uploads_stop_at_the_storage_limit_but_printed_forms_do_not(world):
    done = world.fully_approved()
    over_the_limit(world.org)
    draft = world.draft()

    refused = world.client(world.facilitator).post(
        f"{URL}{draft['id']}/documents/",
        {"document_type": "photo", "file": SimpleUploadedFile("x.jpg", jpeg_bytes())},
        format="multipart",
    )

    assert refused.status_code == 409
    assert refused.data["error"]["code"] == "storage_full"
    with organization_context(world.org.id):
        assert printed_form(Application.objects.get(pk=done["id"]), "single")


def test_an_operator_sets_and_lifts_the_storage_limit(world):
    operator = operator_client(world.org, world.admin)
    url = f"{ORGANIZATIONS}{world.org.id}/"

    assert (
        operator.patch(url, {"storage_limit_mb": 5}, format="json").data["health"][
            "storage_limit_mb"
        ]
        == 5
    )
    lifted = operator.patch(url, {"storage_limit_mb": None}, format="json")
    assert lifted.data["health"]["storage_limit_mb"] is None


@pytest.fixture
def ceiling_of_three():
    rates = {**SimpleRateThrottle.THROTTLE_RATES, "organization": "3/min"}
    OrganizationRateThrottle.THROTTLE_RATES = rates
    yield
    OrganizationRateThrottle.THROTTLE_RATES = SimpleRateThrottle.THROTTLE_RATES


def test_one_organization_has_a_ceiling_on_its_requests(world, ceiling_of_three):
    manager, legal = world.client(world.manager), world.client(world.legal)

    codes = [client.get(ME).status_code for client in (manager, legal, manager, legal)]

    # Two people, one organization: the fourth request is over their shared ceiling.
    assert codes == [200, 200, 200, 429]
