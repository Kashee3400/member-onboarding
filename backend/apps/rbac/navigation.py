"""
The staff portal sidebar.

The backend decides what each person sees, so a role change needs no frontend
release. Every page has a permission of its own; `requires` names the data a page
also reads, so nobody is shown a page that would only fail. The portal refuses a
page whose item is hidden, and every API still checks its own permission.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    icon: str
    path: str | None = None
    permission: str | None = None
    children: tuple[NavItem, ...] = ()
    requires: tuple[str, ...] = ()
    description: str = ""


NAVIGATION = (
    NavItem(
        "dashboard",
        "Dashboard",
        "layout-dashboard",
        "/",
        "dashboard.view",
        description="Today's work at a glance",
    ),
    NavItem(
        "applications",
        "Applications",
        "file-text",
        description="Member forms and their approvals",
        children=(
            NavItem(
                "applications.all",
                "All Applications",
                "files",
                "/applications",
                "applications.view",
                description="Every form in your MPPs",
            ),
            NavItem(
                "applications.pending",
                "Pending Members",
                "clock",
                "/applications/pending",
                "applications.list_pending",
                requires=("applications.view",),
                description="Forms somewhere in approval",
            ),
            NavItem(
                "applications.approved",
                "Approved Members",
                "badge-check",
                "/applications/approved",
                "applications.list_approved",
                requires=("applications.view",),
                description="Members made through this portal",
            ),
            NavItem(
                "applications.rejected",
                "Rejected Members",
                "circle-x",
                "/applications/rejected",
                "applications.list_rejected",
                requires=("applications.view",),
                description="Forms sent back to the facilitator",
            ),
            NavItem(
                "applications.pdf",
                "PDF Center",
                "file-down",
                "/applications/pdf",
                "applications.pdf_center",
                description="Print approved forms in bulk, in the background",
            ),
            NavItem(
                "applications.am",
                "AM Approvals",
                "user-check",
                "/approvals/area-manager",
                "applications.approve_am",
                description="Forms waiting for your check",
            ),
            NavItem(
                "applications.cs",
                "CS & Legal Approvals",
                "scale",
                "/approvals/cs-legal",
                "applications.approve_cs",
                description="Forms waiting for legal review",
            ),
            NavItem(
                "applications.finance",
                "Finance Approvals",
                "landmark",
                "/approvals/finance",
                "applications.approve_finance",
                description="Payment check and final approval",
            ),
        ),
    ),
    NavItem(
        "members",
        "Members",
        "users",
        "/members",
        "members.view",
        description="Approved members and their codes",
    ),
    NavItem(
        "reports",
        "Reports",
        "bar-chart",
        "/reports",
        "reports.view",
        description="Filter, export and print forms",
    ),
    NavItem(
        "masters",
        "Masters",
        "database",
        description="Plants, MPPs and who looks after them",
        children=(
            NavItem(
                "masters.hierarchy",
                "Hierarchy",
                "network",
                "/masters/hierarchy",
                "masters.hierarchy",
                requires=("hierarchy.view",),
                description="The collection network",
            ),
            NavItem(
                "masters.locations",
                "Locations",
                "map-pin",
                "/masters/locations",
                "locations.view",
                description="States to hamlets, and where each MPP is",
            ),
            NavItem(
                "masters.assignments",
                "Assignments",
                "route",
                "/masters/assignments",
                "mpp.assign",
                description="Area Managers by MCC, facilitators by MPP",
            ),
        ),
    ),
    NavItem(
        "administration",
        "Administration",
        "settings",
        description="People, access and system settings",
        children=(
            NavItem(
                "administration.staff",
                "Staff",
                "id-card",
                "/admin/staff",
                "staff.view",
                description="Accounts, roles and signatures",
            ),
            NavItem(
                "administration.roles",
                "Roles & Permissions",
                "shield",
                "/admin/roles",
                "roles.view",
                description="What each role can do",
            ),
            NavItem(
                "administration.branding",
                "Branding",
                "palette",
                "/admin/branding",
                "settings.branding",
                description="Logo, colours and login image",
            ),
            NavItem(
                "administration.review_steps",
                "Review Steps",
                "list-checks",
                "/admin/review-steps",
                "settings.review_steps",
                description="Which role acts on which step of a form",
            ),
            NavItem(
                "administration.integrations",
                "Integrations",
                "plug",
                "/admin/integrations",
                "settings.integrations",
                description="Mail, SMS and WhatsApp",
            ),
            NavItem(
                "administration.host_apps",
                "Connected Apps",
                "plug",
                "/admin/connected-apps",
                "settings.connected_apps",
                description="Apps that sign people in here",
            ),
            NavItem(
                "administration.member_code",
                "Member Code",
                "hash",
                "/admin/member-code",
                "settings.member_code",
                description="Series, form prefix and fees",
            ),
            NavItem(
                "administration.form_lists",
                "Form Lists",
                "list",
                "/admin/form-lists",
                "settings.form_lists",
                description="Choices offered in the membership form",
            ),
            NavItem(
                "administration.banks",
                "Banks",
                "landmark",
                "/admin/banks",
                "settings.banks",
                description="Banks and branches, found by IFSC",
            ),
            NavItem(
                "administration.audit",
                "Audit Log",
                "history",
                "/admin/audit",
                "audit.view",
                description="Who did what, and when",
            ),
        ),
    ),
)


def _allowed(item: NavItem, permissions) -> bool:
    needed = ((item.permission,) if item.permission else ()) + item.requires
    return all(code in permissions for code in needed)


def _visible(item: NavItem, permissions) -> dict | None:
    if not _allowed(item, permissions):
        return None

    children = [
        node for child in item.children if (node := _visible(child, permissions)) is not None
    ]
    # A group with nothing inside it would be an empty heading.
    if item.children and not children:
        return None

    return {
        "key": item.key,
        "label": item.label,
        "icon": item.icon,
        "path": item.path,
        "description": item.description,
        "children": children,
    }


# Not in NAVIGATION: no role permission opens it, so no organization admin can grant it.
CONSOLE = NavItem(
    "console",
    "Platform",
    "server",
    "/console",
    description="Every organization, its health and setup",
)


def _console_node() -> dict:
    return {
        "key": CONSOLE.key,
        "label": CONSOLE.label,
        "icon": CONSOLE.icon,
        "path": CONSOLE.path,
        "description": CONSOLE.description,
        "children": [],
    }


def navigation_for(permissions, *, operator: bool = False) -> list[dict]:
    nodes = [node for item in NAVIGATION if (node := _visible(item, permissions)) is not None]
    return [*nodes, _console_node()] if operator else nodes


def locked_paths(permissions, *, operator: bool = False) -> list[str]:
    """The pages this person may not open. The portal shows them a refusal instead."""
    found = [] if operator else [CONSOLE.path]

    def walk(items):
        for item in items:
            if item.path and not _allowed(item, permissions):
                found.append(item.path)
            walk(item.children)

    walk(NAVIGATION)
    return found


def all_navigation_permissions() -> set[str]:
    found = set()

    def walk(items):
        for item in items:
            if item.permission:
                found.add(item.permission)
            found.update(item.requires)
            walk(item.children)

    walk(NAVIGATION)
    return found
