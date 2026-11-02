from django.core.management.base import BaseCommand, CommandError

from apps.applications.legacy import import_legacy_members
from apps.applications.services import code_settings
from apps.audit.services import record_event
from apps.core.tenancy import organization_context
from apps.organizations.models import Organization


class Command(BaseCommand):
    help = "Load existing members, so that their codes and Aadhaar numbers are respected."

    def add_arguments(self, parser):
        parser.add_argument("path", help="CSV from erp_master's export_members_for_onboarding")
        parser.add_argument("--organization", required=True, help="Organization slug")

    def handle(self, *args, path, organization, **options):
        found = Organization.objects.filter(slug=organization).first()
        if found is None:
            raise CommandError(f"No organization called {organization}.")

        with organization_context(found.id):
            report = import_legacy_members(
                path, organization_id=found.id, form_prefix=code_settings().form_prefix
            )
            # Counts only: this file is full of Aadhaar numbers, and none may reach a log.
            record_event("legacy_members.imported", metadata=report)

        for name, value in sorted(report.items()):
            self.stdout.write(f"{name}: {value}")
        self.stdout.write(self.style.WARNING(f"Delete {path} now. It holds Aadhaar numbers."))
