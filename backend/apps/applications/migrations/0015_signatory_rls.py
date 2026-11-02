from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("applications", "0014_applicationdecision_signed_by_name_signatory")]

    operations = [
        enable_rls("application_signatory"),
        migrations.RunSQL(
            "UPDATE application_decision SET signed_by_name = decided_by_name WHERE signed_by_name = ''",
            migrations.RunSQL.noop,
        ),
    ]