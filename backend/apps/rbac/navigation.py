"""
The staff portal sidebar.

The backend decides what each person sees, so a role change needs no frontend
release. This only shapes the menu: every API still checks its own permission.
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
                "applications.view",
                description="Forms somewhere in approval",
            ),
            NavItem(
                "applications.approved",
                "Approved Members",
                "badge-check",
                "/applications/approved",
                "applications.view",
                description="Members made through this portal",
            ),
            NavItem(
                "applications.rejected",
                "Rejected Members",
                "circle-x",
                "/applications/rejected",
                "applications.view",
                description="Forms sent back to the facilitator",
            ),
            NavItem(
                "applications.pdf",
                "PDF Center",
                "file-down",
                "/applications/pdf",
                "applications.view",
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
                "hierarchy.view",
                description="The collection network",
            ),
            NavItem(
                "masters.locations",
                "Locations",
                "map-pin",
                "/masters/locations",
                "hierarchy.view",
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
                "settings.manage",
                description="Logo, colours and login image",
            ),
            NavItem(
                "administration.review_steps",
                "Review Steps",
                "list-checks",
                "/admin/review-steps",
                "settings.manage",
                description="Which role acts on which step of a form",
            ),
            NavItem(
                "administration.integrations",
                "Integrations",
                "plug",
                "/admin/integrations",
                "settings.manage",
                description="Mail, SMS and WhatsApp",
            ),
            NavItem(
                "administration.host_apps",
                "Connected Apps",
                "plug",
                "/admin/connected-apps",
                "settings.manage",
                description="Apps that sign people in here",
            ),
            NavItem(
                "administration.member_code",
                "Member Code",
                "hash",
                "/admin/member-code",
                "settings.manage",
                description="Series, form prefix and fees",
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


def _visible(item: NavItem, permissions) -> dict | None:
    if item.permission and item.permission not in permissions:
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


def navigation_for(permissions) -> list[dict]:
    return [node for item in NAVIGATION if (node := _visible(item, permissions)) is not None]


def all_navigation_permissions() -> set[str]:
    found = set()

    def walk(items):
        for item in items:
            if item.permission:
                found.add(item.permission)
            walk(item.children)

    walk(NAVIGATION)
    return found
