"""
Private file storage on the local file system.

Layout under MEDIA_ROOT:
    <organization>/applications/<year>/<month>/<application>/<type>-<uuid>.enc
    <organization>/signatures/<membership>/<uuid>.enc
    <organization>/branding/<kind>-<uuid>.<extension>

Paths are built here from IDs, never from anything a client sent. Files are sealed
with the path as context, so a copied or renamed file will not open, and nothing
under MEDIA_ROOT is ever served directly. Access always goes through the API.
Branding images are public, so they are the one thing stored unsealed.
"""

import os
import tempfile
import uuid
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.core import crypto

FILE_MODE = 0o640
DIRECTORY_MODE = 0o750


class UnsafePath(Exception):
    pass


def application_file_path(application, document_type: str) -> str:
    created = timezone.localtime(application.created_at)
    return "/".join(
        [
            str(application.organization_id),
            "applications",
            f"{created.year:04d}",
            f"{created.month:02d}",
            str(application.id),
            f"{document_type}-{uuid.uuid4().hex}.enc",
        ]
    )


def signature_file_path(membership) -> str:
    return "/".join(
        [
            str(membership.organization_id),
            "signatures",
            str(membership.id),
            f"{uuid.uuid4().hex}.enc",
        ]
    )


def branding_file_path(organization_id, kind: str, name: str, extension: str) -> str:
    return "/".join([str(organization_id), "branding", f"{kind}-{name}.{extension}"])


def photo_file_path(membership) -> str:
    return "/".join(
        [str(membership.organization_id), "photos", str(membership.id), f"{uuid.uuid4().hex}.webp"]
    )


def _absolute(relative_path: str) -> Path:
    root = Path(settings.MEDIA_ROOT).resolve()
    path = (root / relative_path).resolve()
    if root not in path.parents:
        raise UnsafePath(relative_path)
    return path


def write(relative_path: str, content: bytes) -> None:
    _write_bytes(relative_path, crypto.seal_file(content, relative_path))


def write_public(relative_path: str, content: bytes) -> None:
    _write_bytes(relative_path, content)


def _write_bytes(relative_path: str, content: bytes) -> None:
    path = _absolute(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=DIRECTORY_MODE)

    # Written beside the target and renamed, so a crash never leaves half a file.
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, FILE_MODE)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def read(relative_path: str) -> bytes:
    return crypto.open_file(_absolute(relative_path).read_bytes(), relative_path)


def read_public(relative_path: str) -> bytes:
    return _absolute(relative_path).read_bytes()


def delete_quietly(relative_path: str) -> None:
    """Cleans up after a failed database write. Saved records keep their files."""
    _absolute(relative_path).unlink(missing_ok=True)
