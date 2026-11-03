"""
How much an organization stores, and its limit. Only uploads count against the
limit: a form's generated PDF is never refused, or an approved member would be
left without their paperwork.
"""

from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from rest_framework import exceptions

USAGE_CACHE_SECONDS = 600
MB = 1024 * 1024


class StorageFull(exceptions.APIException):
    status_code = 409
    default_code = "storage_full"
    default_detail = (
        "This organization has used all its file storage. Ask the platform operator to raise it."
    )


def _key(organization_id) -> str:
    return f"console:storage:{organization_id}"


def storage_bytes(organization_id) -> int:
    """Walking the files is slow, so the total is kept for a few minutes."""
    found = cache.get(_key(organization_id))
    if found is None:
        root = Path(settings.MEDIA_ROOT) / str(organization_id)
        found = (
            sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) if root.is_dir() else 0
        )
        cache.set(_key(organization_id), found, USAGE_CACHE_SECONDS)
    return found


def ensure_room(organization_id, incoming: int) -> None:
    from apps.organizations.models import Organization

    limit = (
        Organization.objects.filter(pk=organization_id)
        .values_list("storage_limit_mb", flat=True)
        .first()
    )
    if limit is not None and storage_bytes(organization_id) + incoming > limit * MB:
        raise StorageFull()


def stored(organization_id, written: int) -> None:
    """Keeps the cached total close between walks."""
    key = _key(organization_id)
    if cache.get(key) is not None:
        try:
            cache.incr(key, written)
        except ValueError:
            pass
