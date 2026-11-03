from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("applications", "0025_field_marks")]

    operations = [enable_rls("application_field_mark")]
