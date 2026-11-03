from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Make an existing staff account a platform operator, who sees every organization "
        "in the console. They must sign in with MFA. --remove takes it away."
    )

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--remove", action="store_true")

    def handle(self, *args, email, remove, **options):
        user = get_user_model().objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f"No account {email!r}. Create it in an organization first.")
        user.is_superuser = user.is_staff = not remove
        user.save(update_fields=["is_superuser", "is_staff", "updated_at"])
        self.stdout.write(f"{user.email} is {'no longer ' if remove else ''}a platform operator.")
