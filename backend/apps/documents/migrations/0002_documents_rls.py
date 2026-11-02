from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("documents", "0001_initial")]

    operations = [enable_rls("application_document"), enable_rls("staff_signature")]
