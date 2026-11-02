import pytest

from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context
from apps.organizations.models import Membership
from apps.rbac.catalog import APPROVAL_PERMISSIONS, PERMISSIONS, SYSTEM_ROLES
from apps.rbac.models import Role
from apps.rbac.navigation import all_navigation_permissions

from .conftest import PASSWORD, authenticated_client, login, make_member

pytestmark = pytest.mark.django_db(transaction=True)

NAVIGATION_URL = "/api/v1/auth/me/navigation/"
ROLES_URL = "/api/v1/roles/"
STAFF_URL = "/api/v1/staff/"


def keys(items):
    found = []
    for item in items:
        found.append(item["key"])
        found.extend(keys(item["children"]))
    return found


def role_id(organization, code):
    with organization_context(organization.id):
        return str(Role.objects.get(code=code).id)


def staff_id(client, email):
    return next(
        item["id"] for item in client.get(STAFF_URL).data["results"] if item["email"] == email
    )


# Catalog -----------------------------------------------------------------------------


def test_roles_and_navigation_only_use_known_permissions():
    for role in SYSTEM_ROLES.values():
        assert role["permissions"] <= set(PERMISSIONS)
    assert all_navigation_permissions() <= set(PERMISSIONS)


def test_each_approval_belongs_to_exactly_one_system_role():
    for permission in APPROVAL_PERMISSIONS:
        holders = [c for c, role in SYSTEM_ROLES.items() if permission in role["permissions"]]
        assert len(holders) == 1, permission


def test_org_admin_cannot_approve_applications():
    assert not SYSTEM_ROLES["org_admin"]["permissions"] & APPROVAL_PERMISSIONS


def test_pib_can_read_reports_but_never_approve():
    permissions = SYSTEM_ROLES["pib"]["permissions"]
    assert {"reports.view", "reports.export"} <= permissions
    assert not permissions & APPROVAL_PERMISSIONS


# Sidebar -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "visible", "hidden"),
    [
        (
            "org_admin",
            {"administration.roles", "administration.audit", "masters.assignments"},
            {"applications.am", "applications.cs", "applications.finance"},
        ),
        (
            "area_manager",
            {"dashboard", "applications.am"},
            {"applications.cs", "applications.finance", "administration", "reports"},
        ),
        (
            "cs_legal",
            {"applications.cs", "members", "reports"},
            {"applications.am", "applications.finance", "administration"},
        ),
        (
            "finance",
            {"applications.finance", "members", "reports"},
            {"applications.am", "applications.cs", "administration"},
        ),
        ("pib", {"members", "reports"}, {"applications", "administration"}),
    ],
)
def test_the_sidebar_follows_the_role(org_a, role, visible, hidden):
    user = make_member(org_a, f"{role}@a.test", role)

    shown = set(keys(authenticated_client(org_a, user).get(NAVIGATION_URL).data))

    assert visible <= shown
    assert not hidden & shown


def test_a_group_with_nothing_visible_is_dropped(org_a):
    user = make_member(org_a, "none@a.test")
    assert authenticated_client(org_a, user).get(NAVIGATION_URL).data == []


def test_the_sidebar_changes_as_soon_as_a_role_changes(org_a, admin_a):
    user = make_member(org_a, "pib@a.test", "pib")
    client = authenticated_client(org_a, user)
    assert "applications" not in keys(client.get(NAVIGATION_URL).data)

    admin = authenticated_client(org_a, admin_a)
    response = admin.patch(
        f"{STAFF_URL}{staff_id(admin, user.email)}/",
        {"role_ids": [role_id(org_a, "finance")]},
    )
    assert response.status_code == 200

    assert "applications.finance" in keys(client.get(NAVIGATION_URL).data)


def test_hidden_menus_are_also_blocked_at_the_api(org_a):
    user = make_member(org_a, "pib@a.test", "pib")
    client = authenticated_client(org_a, user)

    for url in (ROLES_URL, STAFF_URL, "/api/v1/settings/integrations/", "/api/v1/audit/events/"):
        assert client.get(url).status_code == 403, url


# Roles -------------------------------------------------------------------------------


def test_a_custom_role_can_be_created_and_used(org_a, admin_a):
    admin = authenticated_client(org_a, admin_a)
    created = admin.post(
        ROLES_URL,
        {"code": "report-viewer", "name": "Report Viewer", "permissions": ["reports.view"]},
    )
    assert created.status_code == 201

    user = make_member(org_a, "viewer@a.test")
    admin.patch(f"{STAFF_URL}{staff_id(admin, user.email)}/", {"role_ids": [created.data["id"]]})

    assert keys(authenticated_client(org_a, user).get(NAVIGATION_URL).data) == ["reports"]


def test_unknown_permissions_are_rejected(org_a, admin_a):
    response = authenticated_client(org_a, admin_a).post(
        ROLES_URL, {"code": "x", "name": "X", "permissions": ["made.up"]}
    )
    assert response.status_code == 400


def test_nobody_can_create_a_role_stronger_than_themselves(org_a, admin_a):
    response = authenticated_client(org_a, admin_a).post(
        ROLES_URL,
        {"code": "approver", "name": "Approver", "permissions": ["applications.approve_finance"]},
    )
    assert response.status_code == 403


def test_nobody_can_assign_a_role_stronger_than_themselves(org_a, admin_a):
    admin = authenticated_client(org_a, admin_a)

    response = admin.patch(
        f"{STAFF_URL}{staff_id(admin, admin_a.email)}/",
        {"role_ids": [role_id(org_a, "org_admin"), role_id(org_a, "finance")]},
    )

    assert response.status_code == 403
    assert "applications.finance" not in keys(admin.get(NAVIGATION_URL).data)


def test_system_roles_cannot_be_edited_or_deleted(org_a, admin_a):
    admin = authenticated_client(org_a, admin_a)
    url = f"{ROLES_URL}{role_id(org_a, 'facilitator')}/"

    assert admin.patch(url, {"name": "Renamed"}).status_code == 409
    assert admin.delete(url).status_code == 409


def test_a_role_in_use_cannot_be_deleted(org_a, admin_a):
    admin = authenticated_client(org_a, admin_a)
    role = admin.post(ROLES_URL, {"code": "temp", "name": "Temp", "permissions": []}).data
    user = make_member(org_a, "temp@a.test")
    admin.patch(f"{STAFF_URL}{staff_id(admin, user.email)}/", {"role_ids": [role["id"]]})

    assert admin.delete(f"{ROLES_URL}{role['id']}/").status_code == 409


def test_roles_of_another_organization_cannot_be_assigned(org_a, org_b, admin_a):
    admin = authenticated_client(org_a, admin_a)

    response = admin.patch(
        f"{STAFF_URL}{staff_id(admin, admin_a.email)}/",
        {"role_ids": [role_id(org_b, "pib")]},
    )

    assert response.status_code == 400


def test_the_last_role_manager_cannot_be_removed(org_a, admin_a):
    admin = authenticated_client(org_a, admin_a)
    membership = staff_id(admin, admin_a.email)

    assert admin.patch(f"{STAFF_URL}{membership}/", {"role_ids": []}).status_code == 400
    assert admin.patch(f"{STAFF_URL}{membership}/", {"is_active": False}).status_code == 400

    assert admin.get("/api/v1/auth/me/").data["roles"] == ["org_admin"]


# Staff -------------------------------------------------------------------------------


def staff_payload(org, **overrides):
    return {
        "email": "new@a.test",
        "full_name": "New Person",
        "password": PASSWORD,
        "role_ids": [role_id(org, "pib")],
    } | overrides


def test_staff_can_be_created_and_can_log_in(org_a, admin_a, api_client):
    admin = authenticated_client(org_a, admin_a)

    response = admin.post(STAFF_URL, staff_payload(org_a))

    assert response.status_code == 201
    assert response.data["roles"][0]["code"] == "pib"
    assert PASSWORD not in response.content.decode()
    login = api_client.post(
        "/api/v1/auth/login/",
        {"email": "new@a.test", "password": PASSWORD, "organization": org_a.slug},
    )
    assert login.status_code == 200


def test_weak_passwords_are_rejected(org_a, admin_a):
    admin = authenticated_client(org_a, admin_a)
    assert admin.post(STAFF_URL, staff_payload(org_a, password="12345")).status_code == 400


def test_an_admin_can_appoint_approvers_without_being_one(org_a, admin_a):
    admin = authenticated_client(org_a, admin_a)
    payload = staff_payload(org_a, role_ids=[role_id(org_a, "finance")])

    assert admin.post(STAFF_URL, payload).status_code == 201
    assert "applications.finance" not in keys(admin.get(NAVIGATION_URL).data)


def test_a_role_manager_without_a_permission_cannot_pass_it_on_through_a_custom_role(org_a):
    with organization_context(org_a.id):
        strong = Role.objects.create(
            code="strong", name="Strong", permissions=["applications.approve_finance"]
        )
        Role.objects.create(code="manager", name="Manager", permissions=["staff.manage"])
    manager = make_member(org_a, "manager@a.test", "manager")
    target = make_member(org_a, "target@a.test")
    with organization_context(org_a.id):
        membership = Membership.objects.get(user=target)

    response = authenticated_client(org_a, manager).patch(
        f"{STAFF_URL}{membership.id}/", {"role_ids": [str(strong.id)]}
    )

    assert response.status_code == 403


def test_the_same_person_cannot_be_added_twice(org_a, admin_a):
    admin = authenticated_client(org_a, admin_a)
    assert admin.post(STAFF_URL, staff_payload(org_a)).status_code == 201
    assert admin.post(STAFF_URL, staff_payload(org_a)).status_code == 409


def test_someone_from_another_organization_keeps_their_password(org_a, org_b, admin_a, admin_b):
    admin = authenticated_client(org_a, admin_a)

    response = admin.post(
        STAFF_URL,
        staff_payload(org_a, email=admin_b.email, password="An0ther-long-password!"),
    )

    assert response.status_code == 201
    admin_b.refresh_from_db()
    assert admin_b.check_password(PASSWORD)


def test_role_and_staff_changes_are_audited(org_a, admin_a):
    admin = authenticated_client(org_a, admin_a)
    admin.post(ROLES_URL, {"code": "x", "name": "X", "permissions": ["reports.view"]})
    admin.post(STAFF_URL, staff_payload(org_a))

    with organization_context(org_a.id):
        actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {"role.created", "staff.created"} <= actions


def test_the_audit_log_is_readable_with_permission(org_a, admin_a, staff_a, api_client):
    login(api_client, org_a, staff_a)
    response = authenticated_client(org_a, admin_a).get("/api/v1/audit/events/")
    assert response.status_code == 200
    assert response.data["results"][0]["action"] == "auth.login.succeeded"
