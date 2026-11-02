"""
The eight steps of a form, as staff review it. Everyone who can open a form can read
all of it. An organization chooses, role by role, who acts on each step, and each
step is approved on its own: nothing here assumes which role does what.
"""

from dataclasses import dataclass

from apps.rbac.catalog import APPROVE_ALL
from apps.rbac.models import Role
from apps.rbac.services import permissions_for, role_codes_for

from .models import ApplicationStepApproval, ReviewStepAccess


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    sections: tuple[str, ...]
    documents: tuple[str, ...] = ()


FEE_STEP = "fee"
STEPS = (
    Step(
        "member",
        "Member Detail",
        ("applicant",),
        ("photo", "member_signature", "member_thumbprint", "aadhaar_front", "aadhaar_back"),
    ),
    Step("address", "Address and Contact", ("address",)),
    Step("milk", "Milk Production", ("animals",)),
    Step("bank", "Saving Bank Account", ("bank",), ("passbook",)),
    Step("household", "Household Members", ("family",)),
    Step("nominee", "Nominee Declaration", ("nominee", "declaration")),
    Step("village", "Village Details", ("place", "location")),
    Step(FEE_STEP, "Member Fee", ("payment",), ("payment_proof",)),
)
STEP_KEYS = tuple(step.key for step in STEPS)
TITLES = {step.key: step.title for step in STEPS}

STAGE_PERMISSIONS = {
    "pending_am": "applications.approve_am",
    "pending_cs": "applications.approve_cs",
    "pending_finance": "applications.approve_finance",
}


def roles_by_step() -> dict[str, set[str]]:
    saved = {key: set() for key in STEP_KEYS}
    for step, role in ReviewStepAccess.objects.values_list("step", "role__code"):
        saved[step].add(role)
    return saved


def approver_roles():
    permissions = set(STAGE_PERMISSIONS.values())
    return [role for role in Role.objects.order_by("name") if permissions & set(role.permissions)]


def _stage_roles(status: str) -> set[str]:
    permission = STAGE_PERMISSIONS.get(status)
    if permission is None:
        return set()
    return set(
        Role.objects.filter(permissions__contains=[permission]).values_list("code", flat=True)
    )


def stage_steps(status: str) -> set[str]:
    """The steps a form's current stage has to get through."""
    roles = _stage_roles(status)
    return {key for key, chosen in roles_by_step().items() if chosen & roles}


def acts_on_all(membership) -> bool:
    """The organization admin, and anyone else given APPROVE_ALL."""
    return APPROVE_ALL in permissions_for(membership)


def my_steps(membership) -> set[str]:
    if acts_on_all(membership):
        return set(STEP_KEYS)
    held = role_codes_for(membership)
    return {key for key, chosen in roles_by_step().items() if chosen & held}


def my_sections(membership) -> set[str]:
    mine = my_steps(membership)
    return {section for step in STEPS if step.key in mine for section in step.sections}


def approvals_of(application) -> dict:
    """Only this submission counts: a form sent back is checked from the start."""
    rows = ApplicationStepApproval.objects.filter(
        application=application, revision=application.revision
    )
    return {row.step: row for row in rows}


def actionable(application, membership) -> set[str]:
    """What this person can approve on this form right now."""
    if acts_on_all(membership):
        # Any step, at any review stage: the admin may check ahead of the stage.
        if application.status not in STAGE_PERMISSIONS:
            return set()
        return set(STEP_KEYS) - set(approvals_of(application))
    held = role_codes_for(membership) & _stage_roles(application.status)
    open_steps = {key for key, chosen in roles_by_step().items() if chosen & held}
    return open_steps - set(approvals_of(application))


def steps_for(membership=None, application=None) -> list[dict]:
    mine = my_steps(membership) if membership else set()
    approved = approvals_of(application) if application else {}
    open_steps = actionable(application, membership) if membership and application else set()
    return [
        {
            "key": step.key,
            "number": number,
            "title": step.title,
            "sections": list(step.sections),
            "documents": list(step.documents),
            "mine": step.key in mine,
            "can_approve": step.key in open_steps,
            "approved_by_name": approved[step.key].decided_by_name if step.key in approved else "",
            "approved_at": approved[step.key].decided_at if step.key in approved else None,
        }
        for number, step in enumerate(STEPS, start=1)
    ]
