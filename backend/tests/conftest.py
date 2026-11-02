import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.mfa import issue_tokens
from apps.accounts.models import User
from apps.core.tenancy import organization_context
from apps.organizations.models import Membership, Organization
from apps.rbac.services import grant_role, sync_system_roles

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


def make_organization(name, slug):
    organization = Organization.objects.create(name=name, slug=slug)
    with organization_context(organization.id):
        sync_system_roles()
    return organization


def make_member(organization, email, role=None):
    user = User.objects.create_user(email, PASSWORD)
    with organization_context(organization.id):
        membership = Membership.objects.create(organization=organization, user=user)
        if role:
            grant_role(membership, role)
    return user


def login(client, organization, user):
    response = client.post(
        "/api/v1/auth/login/",
        {"email": user.email, "password": PASSWORD, "organization": organization.slug},
    )
    assert response.status_code == 200, response.content
    return response.data


def authenticated_client(organization, user):
    client = APIClient()
    tokens = issue_tokens(user, organization, mfa=True)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client


@pytest.fixture
def org_a(db):
    return make_organization("Org A", "org-a")


@pytest.fixture
def org_b(db):
    return make_organization("Org B", "org-b")


@pytest.fixture
def admin_a(org_a):
    return make_member(org_a, "admin@a.test", "org_admin")


@pytest.fixture
def staff_a(org_a):
    return make_member(org_a, "staff@a.test", "facilitator")


@pytest.fixture
def admin_b(org_b):
    return make_member(org_b, "admin@b.test", "org_admin")
