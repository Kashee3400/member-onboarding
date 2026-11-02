from django.core.management.base import BaseCommand

from apps.core.tenancy import organization_context
from apps.organizations.models import Organization
from apps.rbac.services import sync_system_roles


class Command(BaseCommand):
    help = "Update every organization's system roles from the catalog. Run after deployments."

    def handle(self, *args, **options):
        for organization in Organization.objects.all():
            with organization_context(organization.id):
                sync_system_roles()
            self.stdout.write(f"Synced {organization.slug}")
