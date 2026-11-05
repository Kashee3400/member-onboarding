import pytest

from apps.core.tenancy import organization_context
from apps.rbac.catalog import SYSTEM_ROLES
from apps.rbac.models import Role
from apps.rbac.navigation import navigation_for
from apps.rbac.services import permissions_for, sync_system_roles

from .test_applications import World

pytestmark = pytest.mark.django_db(transaction=True)

ROLES = "/api/v1/roles/"


@pytest.fixture
def world(org_a):
    return World(org_a)


def role(world, code) -> Role:
    with organization_context(world.org.id):
        return Role.objects.get(code=code)


def without(permissions, *codes):
    return sorted(set(permissions) - set(codes))


def keys(permissions):
    return {
        child["key"]
        for node in navigation_for(set(permissions))
        for child in node["children"] or [node]
    }


def test_an_admin_takes_a_permission_off_a_standard_role(world):
    legal = role(world, "cs_legal")

    response = world.client(world.admin).patch(
        f"{ROLES}{legal.id}/",
        {"permissions": without(legal.permissions, "reports.view")},
        format="json",
    )

    # Org admins hold no approval rights, yet may still trim a role that has them.
    assert response.status_code == 200, response.content
    assert response.data["customized"] is True
    assert "reports.view" not in role(world, "cs_legal").permissions


def test_a_changed_standard_role_survives_a_deployment(world):
    legal = role(world, "cs_legal")
    world.client(world.admin).patch(
        f"{ROLES}{legal.id}/",
        {"permissions": without(legal.permissions, "reports.view")},
        format="json",
    )

    with organization_context(world.org.id):
        sync_system_roles()

    assert "reports.view" not in role(world, "cs_legal").permissions
    # An unchanged one still follows the catalog.
    assert set(role(world, "finance").permissions) == SYSTEM_ROLES["finance"]["permissions"]


def test_a_standard_role_goes_back_to_standard(world):
    legal = role(world, "cs_legal")
    client = world.client(world.admin)
    client.patch(
        f"{ROLES}{legal.id}/",
        {"permissions": without(legal.permissions, "reports.view")},
        format="json",
    )

    response = client.post(f"{ROLES}{legal.id}/reset/")

    assert response.status_code == 200
    assert response.data["customized"] is False
    assert set(response.data["permissions"]) == SYSTEM_ROLES["cs_legal"]["permissions"]


def test_nobody_adds_what_they_do_not_hold(world):
    manager = role(world, "area_manager")

    response = world.client(world.admin).patch(
        f"{ROLES}{manager.id}/",
        {"permissions": [*manager.permissions, "applications.approve_cs"]},
        format="json",
    )

    assert response.status_code == 403


def test_the_platform_operator_may_add_anything(world):
    from rest_framework.test import APIClient

    from apps.accounts.mfa import issue_tokens

    world.admin.is_superuser = True
    world.admin.save()
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {issue_tokens(world.admin, world.org, mfa=True)['access']}"
    )
    manager = role(world, "area_manager")

    response = client.patch(
        f"{ROLES}{manager.id}/",
        {"permissions": [*manager.permissions, "applications.approve_cs"]},
        format="json",
    )

    assert response.status_code == 200, response.content


def test_a_standard_role_keeps_its_code_and_cannot_be_deleted(world):
    legal = role(world, "cs_legal")
    client = world.client(world.admin)

    assert (
        client.patch(f"{ROLES}{legal.id}/", {"code": "lawyers"}, format="json").status_code == 409
    )
    assert client.delete(f"{ROLES}{legal.id}/").status_code == 409


def test_masters_pages_are_the_administrators(world):
    for code in ("area_manager", "cs_legal", "finance", "pib"):
        pages = keys(SYSTEM_ROLES[code]["permissions"])
        assert not pages & {"masters.hierarchy", "masters.locations", "masters.assignments"}, code
    with organization_context(world.org.id):
        admin = permissions_for(world.admin.memberships.get())
    assert {"masters.hierarchy", "masters.locations", "masters.assignments"} <= keys(admin)


def test_working_roles_still_read_masters_for_their_filters(world):
    response = world.client(world.manager).get("/api/v1/hierarchy/plants/")

    assert response.status_code == 200
