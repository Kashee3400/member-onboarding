import uuid
from pathlib import PurePosixPath

from django.db import transaction

from apps.audit.services import record_event
from apps.core.tenancy import organization_context
from apps.documents import storage
from apps.organizations.models import Organization

from .images import normalize_login_image, normalize_logo
from .models import DEFAULT_ACCENT, DEFAULT_PRIMARY, Branding

DEFAULT_NAME = "Member Onboarding"
FIELDS = {"logo": "logo_path", "login_image": "login_image_path"}
NORMALIZERS = {"logo": normalize_logo, "login_image": normalize_login_image}
CONTENT_TYPES = {".png": "image/png", ".webp": "image/webp"}
EXTENSIONS = {"image/png": "png", "image/webp": "webp"}


def _image_url(organization, kind: str, path: str) -> str | None:
    if not path:
        return None
    # The name changes with each upload, so browsers can cache an image for a long time.
    version = PurePosixPath(path).stem.rsplit("-", 1)[-1]
    return f"/api/v1/public/branding/{organization.slug}/{kind}/?v={version}"


def describe(organization, branding, *, name: str = "") -> dict:
    if branding is None:
        return {
            "display_name": name or DEFAULT_NAME,
            "tagline": "",
            "primary_color": DEFAULT_PRIMARY,
            "accent_color": DEFAULT_ACCENT,
            "logo_url": None,
            "login_image_url": None,
            "email_domain": "",
        }
    return {
        "display_name": branding.display_name or name or DEFAULT_NAME,
        "tagline": branding.tagline,
        "primary_color": branding.primary_color,
        "accent_color": branding.accent_color,
        "logo_url": _image_url(organization, "logo", branding.logo_path),
        "login_image_url": _image_url(organization, "login_image", branding.login_image_path),
        "email_domain": branding.email_domain,
    }


def _public_row(slug: str):
    organization = Organization.objects.filter(slug=slug, is_active=True).first()
    if organization is None:
        return None, None
    with organization_context(organization.id):
        return organization, Branding.objects.first()


def public_branding(slug: str) -> dict:
    """An organization that set nothing looks exactly like one that does not exist."""
    organization, branding = _public_row(slug)
    return describe(organization, branding)


def public_image(slug: str, kind: str) -> tuple[bytes, str] | None:
    _, branding = _public_row(slug)
    path = getattr(branding, FIELDS[kind], "") if branding else ""
    if not path:
        return None
    return storage.read_public(path), CONTENT_TYPES[PurePosixPath(path).suffix]


def staff_email_problem(email: str) -> str | None:
    """Why this address cannot be a staff login here, or None when it can."""
    branding = Branding.objects.first()
    domain = branding.email_domain if branding else ""
    if domain and not email.strip().lower().endswith(f"@{domain}"):
        return f"Use an official @{domain} address."
    return None


def branding_for(membership) -> Branding:
    branding, _ = Branding.objects.get_or_create(organization_id=membership.organization_id)
    return branding


def _forget(path: str) -> None:
    if path:
        transaction.on_commit(lambda: storage.delete_quietly(path))


def set_image(branding: Branding, kind: str, *, raw: bytes, actor) -> Branding:
    content, content_type = NORMALIZERS[kind](raw)
    path = storage.branding_file_path(
        branding.organization_id, kind, uuid.uuid4().hex, EXTENSIONS[content_type]
    )
    storage.write_public(path, content)

    field = FIELDS[kind]
    previous = getattr(branding, field)
    setattr(branding, field, path)
    try:
        branding.save(update_fields=[field, "updated_at"])
    except BaseException:
        storage.delete_quietly(path)
        raise
    _forget(previous)
    record_event("branding.image_updated", actor=actor, target=branding, metadata={"kind": kind})
    return branding


def remove_image(branding: Branding, kind: str, *, actor) -> Branding:
    field = FIELDS[kind]
    previous = getattr(branding, field)
    setattr(branding, field, "")
    branding.save(update_fields=[field, "updated_at"])
    _forget(previous)
    record_event("branding.image_removed", actor=actor, target=branding, metadata={"kind": kind})
    return branding
