"""
Organization isolation.

PostgreSQL row level security enforces isolation, so a forgotten filter cannot
leak another organization's rows. The policy reads `app.organization_id`, which
is only ever set for the current transaction. With no organization active, the
policy matches nothing.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

from django.db import connection, transaction

SETTING_NAME = "app.organization_id"

_current_organization_id: ContextVar[UUID | None] = ContextVar(
    "current_organization_id", default=None
)


def get_current_organization_id() -> UUID | None:
    return _current_organization_id.get()


def _apply_to_transaction(organization_id: UUID | None) -> None:
    value = str(organization_id) if organization_id else ""
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, true)", [SETTING_NAME, value])


def activate_organization(organization_id: UUID | str) -> None:
    """Scope the current request's transaction to one organization."""
    organization_id = UUID(str(organization_id))
    _current_organization_id.set(organization_id)
    _apply_to_transaction(organization_id)


def clear_organization() -> None:
    _current_organization_id.set(None)


@contextmanager
def organization_context(organization_id: UUID | str):
    """Run a block for one organization, for code outside a request such as Celery tasks."""
    organization_id = UUID(str(organization_id))
    previous = _current_organization_id.get()
    with transaction.atomic():
        token = _current_organization_id.set(organization_id)
        _apply_to_transaction(organization_id)
        try:
            yield
            # On an exception the atomic rollback restores the previous value.
            _apply_to_transaction(previous)
        finally:
            _current_organization_id.reset(token)
