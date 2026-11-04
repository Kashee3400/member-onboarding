from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("applications", "0028_aadhaar_check")]

    operations = [enable_rls("application_aadhaar_check")]
