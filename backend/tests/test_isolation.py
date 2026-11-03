"""
Organizations must never see each other's data, through any table or any endpoint.

These checks are generic on purpose: a model or an endpoint added later is covered
without anyone remembering to write a test for it.
"""

import json
import re

import pytest
from django.apps import apps
from django.db import connection
from drf_spectacular.generators import EndpointEnumerator

from apps.applications.models import Bank, BankBranch
from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context
from apps.federation.models import TrustedIssuer
from apps.organizations.models import Membership, OrganizationOwnedModel
from apps.rbac.catalog import PERMISSIONS
from apps.rbac.models import MembershipRole, Role
from apps.reports.models import BatchStatus, PdfBatch

from .conftest import authenticated_client, make_member
from .test_applications import OTHER_AADHAAR, World

pytestmark = pytest.mark.django_db(transaction=True)

PARAMETER = re.compile(r"\{(\w+)\}")

# Tables that hold organization_id without row-level security, each for a reason.
UNSCOPED = {
    # A host app's sign-in names its issuer before any organization is known; the
    # admin API filters by organization itself (federation/views.py).
    "federation_trusted_issuer",
}


def test_every_table_with_an_organization_column_is_isolated():
    """Catches tables that hold organization_id without the base model, too."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.table_name, k.relrowsecurity, k.relforcerowsecurity,
                   EXISTS (SELECT 1 FROM pg_policies p WHERE p.tablename = c.table_name)
            FROM information_schema.columns c
            JOIN pg_class k ON k.relname = c.table_name
            WHERE c.table_schema = 'public' AND c.column_name = 'organization_id'
              AND k.relkind = 'r'
            """
        )
        rows = cursor.fetchall()

    assert rows
    unprotected = [
        table
        for table, enabled, forced, policy in rows
        if not (enabled and forced and policy) and table not in UNSCOPED
    ]
    assert unprotected == [], f"organization_id without row-level security: {unprotected}"


def _everything_role(organization):
    with organization_context(organization.id):
        return Role.objects.create(
            code="everything", name="Everything", permissions=sorted(PERMISSIONS)
        )


def _ids_of(organization) -> set[str]:
    """Every row id one organization owns, and the people who work in it."""
    models = [AuditEvent] + [
        model for model in apps.get_models() if issubclass(model, OrganizationOwnedModel)
    ]
    found = set()
    with organization_context(organization.id):
        for model in models:
            found.update(str(pk) for pk in model.objects.values_list("pk", flat=True))
        found.update(str(pk) for pk in Membership.objects.values_list("user_id", flat=True))
    # Not row-level isolated, so not found above: see UNSCOPED.
    found.update(
        str(pk)
        for pk in TrustedIssuer.objects.filter(organization=organization).values_list(
            "pk", flat=True
        )
    )
    return found


@pytest.fixture
def two_organizations(org_a, org_b):
    """Org A with forms at every stage; org B's user holds every permission there is."""
    world = World(org_a)
    done = world.fully_approved()
    world.submitted(OTHER_AADHAAR)
    with organization_context(org_a.id):
        # The one table without row-level security: its API must filter by itself.
        TrustedIssuer.objects.create(
            organization=org_a,
            name="Org A ERP",
            issuer="https://erp.a.test",
            audience="onboarding",
            public_key="-",
        )
        bank = Bank.objects.create(name="Org A Bank")
        BankBranch.objects.create(bank=bank, name="Main", ifsc="ORGA0000001")
        PdfBatch.objects.create(
            organization=org_a,
            status=BatchStatus.DONE,
            filters={"application_ids": [done["id"]]},
            requested_by=world.admin,
            requested_by_name="A",
        )
    outsider = make_member(org_b, "outsider@b.test", "org_admin")
    role = _everything_role(org_b)
    with organization_context(org_b.id):
        MembershipRole.objects.create(membership=Membership.objects.get(user=outsider), role=role)
    return org_a, _ids_of(org_a), authenticated_client(org_b, outsider)


def _leaks(response, secrets: set[str]) -> set[str]:
    if "json" not in response.get("Content-Type", ""):
        return set()
    text = json.dumps(response.json())
    return {secret for secret in secrets if secret in text}


def test_no_endpoint_shows_another_organizations_rows(two_organizations):
    owner, secrets, outsider = two_organizations
    with organization_context(owner.id):
        branch_codes = list(BankBranch.objects.values_list("ifsc", flat=True))
    assert len(secrets) > 50, "the world should own plenty of rows"

    leaks, broken, asked = {}, [], set()
    for path, _, method, _ in EndpointEnumerator().get_api_endpoints():
        if method != "GET":
            continue
        names = PARAMETER.findall(path)
        if not names:
            attempts = [path]
        elif names == ["pk"]:
            # Every row the other organization owns, whatever kind the page expects.
            attempts = [path.replace("{pk}", pk) for pk in secrets]
        elif names == ["ifsc"]:
            attempts = [path.replace("{ifsc}", code) for code in branch_codes]
        else:
            # Integrations by kind and public branding by slug are covered in test_tenancy.
            continue

        for url in attempts:
            response = outsider.get(url)
            asked.add(path)
            if response.status_code >= 500:
                broken.append(url)
            elif response.status_code < 300 and names:
                leaks.setdefault(path, set()).add("served another organization's row")
            elif found := _leaks(response, secrets):
                leaks.setdefault(path, set()).update(found)

    # The sweep is only worth something while it reaches most of the API.
    assert len(asked) > 60, sorted(asked)
    assert leaks == {}, leaks
    assert broken == [], broken
