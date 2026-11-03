"""
One organization's data and files, as a single archive.

For handing an organization its records, answering a legal request, or restoring one
organization: restore the nightly dump into a scratch database, export the
organization from there, and load it where it is needed.

The archive holds:
    manifest.json   counts per table, so a copy can be checked against the source
    data.json       every row the organization owns, in Django's fixture format
    media/...       its uploaded files, still sealed

Encrypted columns and files stay encrypted, so the archive is exactly as safe as the
database, and as useless without FIELD_ENCRYPTION_KEYS. Password hashes are left out.
"""

import io
import json
import tarfile
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.core.tenancy import organization_context
from apps.federation.models import TrustedIssuer
from apps.organizations.models import Membership, Organization, OrganizationOwnedModel

USER_FIELDS = (
    "email",
    "full_name",
    "is_active",
    "must_change_password",
    "created_at",
    "updated_at",
)


def owned_models():
    # Parents before children, so the fixture loads in order.
    found = [m for m in apps.get_models() if issubclass(m, OrganizationOwnedModel)]
    ordered, seen = [], set()

    def visit(model):
        if model in seen:
            return
        seen.add(model)
        for field in model._meta.concrete_fields:
            target = field.related_model
            if field.is_relation and target in found and target is not model:
                visit(target)
        ordered.append(model)

    for model in sorted(found, key=lambda m: m._meta.label):
        visit(model)
    return ordered


def collect(organization) -> tuple[list, dict]:
    """The organization's rows as fixture records, and how many of each."""
    records, counts = [], {}

    def add(label, queryset, fields=None):
        rows = json.loads(serializers.serialize("json", queryset, fields=fields))
        records.extend(rows)
        counts[label] = len(rows)

    add("organizations.organization", Organization.objects.filter(pk=organization.pk))
    with organization_context(organization.id):
        people = Membership.objects.values_list("user_id", flat=True)
        add("accounts.user", User.objects.filter(pk__in=list(people)), USER_FIELDS)
        add("federation.trustedissuer", TrustedIssuer.objects.filter(organization=organization))
        for model in owned_models():
            add(model._meta.label_lower, model.objects.order_by("pk"))
        add("audit.auditevent", AuditEvent.objects.order_by("occurred_at"))
    return records, counts


def _add_bytes(archive, name, content: bytes):
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mtime = int(timezone.now().timestamp())
    archive.addfile(info, io.BytesIO(content))


class Command(BaseCommand):
    help = "Write one organization's data and uploaded files to a .tar.gz archive."

    def add_arguments(self, parser):
        parser.add_argument("slug")
        parser.add_argument("--out", default=".", help="Folder for the archive.")

    def handle(self, *args, slug, out, **options):
        try:
            organization = Organization.objects.get(slug=slug)
        except Organization.DoesNotExist as exc:
            raise CommandError(f"No organization {slug!r}.") from exc

        records, counts = collect(organization)
        media = Path(settings.MEDIA_ROOT) / str(organization.id)
        files = sorted(p for p in media.rglob("*") if p.is_file()) if media.is_dir() else []
        manifest = {
            "organization": {
                "id": str(organization.id),
                "slug": organization.slug,
                "name": organization.name,
            },
            "exported_at": timezone.now().isoformat(),
            "rows": counts,
            "files": len(files),
        }

        stamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
        target = Path(out) / f"{organization.slug}_{stamp}.tar.gz"
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        with tarfile.open(partial, "w:gz") as archive:
            _add_bytes(archive, "manifest.json", json.dumps(manifest, indent=2).encode())
            _add_bytes(archive, "data.json", json.dumps(records, ensure_ascii=False).encode())
            for path in files:
                archive.add(path, arcname=f"media/{path.relative_to(media).as_posix()}")

        # Read it back before calling it done: a broken archive must fail now.
        with tarfile.open(partial, "r:gz") as archive:
            data = json.load(archive.extractfile("data.json"))
            stored = sum(1 for member in archive.getmembers() if member.name.startswith("media/"))
        if len(data) != sum(counts.values()) or stored != len(files):
            raise CommandError("The archive does not match what was exported.")
        partial.replace(target)

        self.stdout.write(f"{target}: {len(data)} rows, {len(files)} files")
        for label, count in counts.items():
            if count:
                self.stdout.write(f"  {label}: {count}")
