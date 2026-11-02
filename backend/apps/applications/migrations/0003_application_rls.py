from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("applications", "0002_initial")]

    operations = [
        enable_rls("application"),
        enable_rls("application_revision"),
        enable_rls("application_decision"),
        enable_rls("member"),
        enable_rls("member_code_settings"),
        enable_rls("application_sequence"),
    ]
