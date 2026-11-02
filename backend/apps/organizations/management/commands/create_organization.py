import getpass
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.audit.services import record_event
from apps.core.tenancy import organization_context
from apps.organizations.models import Membership, Organization
from apps.rbac.services import grant_role, sync_system_roles


class Command(BaseCommand):
    help = "Create an organization and its first admin. Reads ONBOARDING_ADMIN_PASSWORD if set."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--slug", required=True)
        parser.add_argument("--admin-email", required=True)

    def handle(self, *args, name, slug, admin_email, **options):
        password = os.environ.get("ONBOARDING_ADMIN_PASSWORD") or getpass.getpass(
            "Admin password: "
        )
        validate_password(password)

        with transaction.atomic():
            organization = Organization.objects.create(name=name, slug=slug)
            user = get_user_model().objects.create_user(admin_email, password)
            with organization_context(organization.id):
                sync_system_roles()
                membership = Membership.objects.create(organization=organization, user=user)
                grant_role(membership, "org_admin")
                record_event("organization.created", actor=user, target=organization)

        self.stdout.write(self.style.SUCCESS(f"Created {slug} with admin {user.email}"))
