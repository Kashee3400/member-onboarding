"""
The permission catalog and standard roles.

Permissions live in code because code enforces them. Organizations compose them
into roles from the admin. The stage approval permissions are left out of
org_admin, so administering the system does not make someone an Area Manager or a
head. Instead org_admin holds APPROVE_ALL: it may act on any review step a form
has reached, as the user asked for on 2026-11-02.
"""

PERMISSIONS = {
    "dashboard.view": "View the dashboard",
    "applications.view": "View applications in assigned MPPs",
    "applications.create": "Create applications",
    "applications.edit": "Edit draft and rejected applications",
    "applications.submit": "Submit applications",
    "applications.download_full_pdf": "Download the full form, with Aadhaar and bank images",
    "applications.approve_am": "Approve or reject as Area Manager",
    "applications.approve_cs": "Approve or reject as CS & Legal",
    "applications.approve_finance": "Approve or reject as Finance",
    "members.view": "View members",
    "reports.view": "View reports",
    "reports.export": "Export reports",
    "hierarchy.view": "View plants, MCCs and MPPs",
    "hierarchy.manage": "Manage plants, MCCs and MPPs",
    "mpp.view_all": "Access every MPP, not only assigned ones",
    "mpp.assign": "Assign and transfer MPPs",
    "staff.view": "View staff",
    "staff.manage": "Manage staff and their roles",
    "roles.view": "View roles",
    "roles.manage": "Manage roles",
    "settings.manage": "Manage integrations",
    "audit.view": "View the audit log",
    "applications.approve_all": "Act on every review step, at whichever stage a form is",
}

# Acts on every open step, whatever Review Steps says. Not a stage permission.
APPROVE_ALL = "applications.approve_all"

APPROVAL_PERMISSIONS = frozenset(
    {
        "applications.approve_am",
        "applications.approve_cs",
        "applications.approve_finance",
    }
)

SYSTEM_ROLES = {
    "org_admin": {
        "name": "Organization Admin",
        "requires_mfa": True,
        "permissions": frozenset(PERMISSIONS) - APPROVAL_PERMISSIONS,
    },
    "facilitator": {
        "name": "Facilitator",
        "permissions": frozenset(
            {
                "applications.view",
                "applications.create",
                "applications.edit",
                "applications.submit",
            }
        ),
    },
    "area_manager": {
        "name": "Area Manager",
        "permissions": frozenset(
            {
                "dashboard.view",
                "applications.view",
                "applications.approve_am",
                "hierarchy.view",
            }
        ),
    },
    "cs_legal": {
        "name": "CS & Legal",
        "requires_mfa": True,
        "permissions": frozenset(
            {
                "dashboard.view",
                "applications.view",
                "applications.approve_cs",
                "applications.download_full_pdf",
                "members.view",
                "hierarchy.view",
                "mpp.view_all",
                "reports.view",
            }
        ),
    },
    "finance": {
        "name": "Finance",
        "requires_mfa": True,
        "permissions": frozenset(
            {
                "dashboard.view",
                "applications.view",
                "applications.approve_finance",
                "applications.download_full_pdf",
                "members.view",
                "hierarchy.view",
                "mpp.view_all",
                "reports.view",
                "reports.export",
            }
        ),
    },
    "pib": {
        "name": "PIB",
        "permissions": frozenset(
            {
                "dashboard.view",
                "members.view",
                "hierarchy.view",
                "mpp.view_all",
                "reports.view",
                "reports.export",
            }
        ),
    },
}
