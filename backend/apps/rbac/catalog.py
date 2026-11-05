"""
The permission catalog and standard roles.

Permissions live in code because code enforces them. Organizations compose them
into roles from the admin. Every sidebar page has a permission of its own, so any
page can be handed to a role, or to one person through a small extra role.

The stage approval permissions are left out of org_admin, so administering the
system does not make someone an Area Manager or a head. Instead org_admin holds
APPROVE_ALL: it may act on any review step a form has reached, as the user asked
for on 2026-11-02.
"""

PERMISSIONS = {
    "dashboard.view": "View the dashboard",
    "applications.view": "View applications in assigned MPPs",
    "applications.create": "Create applications",
    "applications.edit": "Edit draft and rejected applications",
    "applications.submit": "Submit applications",
    "applications.download_full_pdf": "Download the full form, with Aadhaar and bank images",
    "applications.list_pending": "Open the Pending Members page",
    "applications.list_approved": "Open the Approved Members page",
    "applications.list_rejected": "Open the Rejected Members page",
    "applications.pdf_center": "Bulk-print approved forms in the PDF Center",
    "applications.approve_am": "Approve or reject as Area Manager",
    "applications.approve_cs": "Approve or reject as CS & Legal",
    "applications.approve_finance": "Approve or reject as Finance",
    "members.view": "View members",
    "members.export_data": "Export everything held about one member, decrypted, for a data request",
    "reports.view": "View reports",
    "reports.export": "Export reports",
    "hierarchy.view": "Read plants, MCCs and MPPs, as filters and pickers on other pages",
    "masters.hierarchy": "Open the Hierarchy page: plants, MCCs, BMCs, routes and MPPs",
    "hierarchy.manage": "Manage plants, MCCs and MPPs",
    "locations.view": "View the Locations page: states to hamlets",
    "mpp.view_all": "Access every MPP, not only assigned ones",
    "mpp.assign": "Assign and transfer MPPs",
    "staff.view": "View staff",
    "staff.manage": "Manage staff and their roles",
    "roles.view": "View roles",
    "roles.manage": "Manage roles",
    "settings.branding": "Manage branding: logo, colours and login image",
    "settings.review_steps": "Manage review steps, signatories and reject reasons",
    "settings.integrations": "Manage mail, SMS, WhatsApp and push",
    "settings.connected_apps": "Manage apps that sign people in here",
    "settings.member_code": "Manage the member code series, form prefix, fees and profile",
    "settings.form_lists": "Manage the choices offered in the membership form",
    "settings.banks": "Manage banks and branches",
    "audit.view": "View the audit log",
    "applications.approve_all": "Act on every review step, at whichever stage a form is",
}

# Acts on every open step, whatever Review Steps says. Not a stage permission.
APPROVE_ALL = "applications.approve_all"

# One per settings page.
SETTINGS_PERMISSIONS = frozenset(code for code in PERMISSIONS if code.startswith("settings."))

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
                "applications.list_pending",
                "applications.list_approved",
                "applications.list_rejected",
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
                "applications.list_pending",
                "applications.list_approved",
                "applications.list_rejected",
                "applications.approve_cs",
                "applications.download_full_pdf",
                "applications.pdf_center",
                "members.view",
                "members.export_data",
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
                "applications.list_pending",
                "applications.list_approved",
                "applications.list_rejected",
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
