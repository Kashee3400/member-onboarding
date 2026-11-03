import pytest

from apps.branding.models import Branding
from apps.core.tenancy import organization_context
from apps.organizations.models import Membership
from apps.rbac.models import Role

from .conftest import authenticated_client

pytestmark = pytest.mark.django_db(transaction=True)

STAFF = "/api/v1/staff/"
BRANDING = "/api/v1/organization/branding/"


@pytest.fixture
def official(org_a):
    with organization_context(org_a.id):
        Branding.objects.update_or_create(
            organization=org_a, defaults={"email_domain": "kasheemilk.com"}
        )


def roles(org):
    with organization_context(org.id):
        return [str(Role.objects.get(code="area_manager").id)]


def test_new_staff_need_the_official_domain(org_a, admin_a, official):
    client = authenticated_client(org_a, admin_a)
    body = {"full_name": "Sita", "role_ids": roles(org_a)}

    refused = client.post(STAFF, {**body, "email": "sita@gmail.com"}, format="json")
    accepted = client.post(STAFF, {**body, "email": "Sita.Devi@KasheeMilk.com"}, format="json")

    assert refused.status_code == 400
    assert "@kasheemilk.com" in str(refused.data)
    assert accepted.status_code == 201, accepted.content


def test_an_email_change_keeps_to_the_domain(org_a, admin_a, staff_a, official):
    with organization_context(org_a.id):
        member = Membership.objects.get(user=staff_a)
    client = authenticated_client(org_a, admin_a)

    response = client.patch(f"{STAFF}{member.id}/", {"email": "sita@gmail.com"}, format="json")

    assert response.status_code == 400


def test_without_a_domain_any_address_will_do(org_a, admin_a):
    client = authenticated_client(org_a, admin_a)

    response = client.post(
        STAFF,
        {"full_name": "Sita", "email": "sita@gmail.com", "role_ids": roles(org_a)},
        format="json",
    )

    assert response.status_code == 201, response.content


def test_the_login_page_knows_the_domain(org_a, official, api_client):
    data = api_client.get("/api/v1/public/branding/", {"organization": org_a.slug}).data

    assert data["email_domain"] == "kasheemilk.com"


def test_the_domain_is_set_from_branding(org_a, admin_a):
    client = authenticated_client(org_a, admin_a)
    current = client.get(BRANDING).data

    response = client.patch(BRANDING, {"email_domain": " @KasheeMilk.com "}, format="json")
    wrong = client.patch(BRANDING, {"email_domain": "not a domain"}, format="json")

    assert response.status_code == 200, response.content
    assert response.data["email_domain"] == "kasheemilk.com"
    assert wrong.status_code == 400
    assert current
