from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("applications", "0021_form_lists_and_banks")]

    operations = [
        enable_rls("application_form_option"),
        enable_rls("bank"),
        enable_rls("bank_branch"),
    ]
