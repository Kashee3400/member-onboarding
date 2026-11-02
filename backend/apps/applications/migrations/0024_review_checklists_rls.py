from django.db import migrations

from apps.core.rls import enable_rls


class Migration(migrations.Migration):
    dependencies = [("applications", "0023_review_checklists")]

    operations = [
        enable_rls("application_review_check"),
        enable_rls("application_step_check_tick"),
    ]
