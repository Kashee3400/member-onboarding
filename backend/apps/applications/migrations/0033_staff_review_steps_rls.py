from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("applications", "0032_staff_review_steps")]

    operations = [enable_rls("application_staff_review_steps")]
